import { useEffect, useState } from 'react';
import { getGapReport } from '../../api';
import { AlertTriangle, AlertCircle, Eye, ShieldAlert } from 'lucide-react';

const SEV_CONFIG = {
  critical: { badge: 'badge-critical', icon: ShieldAlert, label: 'Critical' },
  moderate: { badge: 'badge-moderate', icon: AlertCircle, label: 'Moderate' },
  watch:    { badge: 'badge-watch',    icon: Eye,         label: 'Watch' },
};

export default function GapReportTab({ projectId }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGapReport(projectId)
      .then(setReport)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading gap report...</div>;
  if (!report) return <div className="text-gray-400 py-8 text-center">No gap report available.</div>;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <ScoreCard label="Overall Score" value={report.overall_score?.toFixed(1)} sub="/100" color="text-apex-600" />
        <ScoreCard label="Critical Gaps" value={report.critical_count} color="text-red-600" />
        <ScoreCard label="Moderate Gaps" value={report.moderate_count} color="text-yellow-600" />
        <ScoreCard label="Watch Items" value={report.watch_count} color="text-blue-600" />
      </div>

      {report.summary && (
        <div className="card bg-amber-50 border-amber-200">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
            <p className="text-sm text-amber-800">{report.summary}</p>
          </div>
        </div>
      )}

      {/* Gap items */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">Severity</th>
              <th className="px-4 py-3">Section</th>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Recommendation</th>
              <th className="px-4 py-3 text-right">Risk</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(report.items || []).map((item) => {
              const sev = SEV_CONFIG[item.severity] || SEV_CONFIG.watch;
              return (
                <tr key={item.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className={sev.badge}>{sev.label}</span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{item.section_number}</td>
                  <td className="px-4 py-3 font-medium">{item.title}</td>
                  <td className="px-4 py-3 text-gray-600 max-w-xs">{item.description}</td>
                  <td className="px-4 py-3 text-gray-500 max-w-xs">{item.recommendation}</td>
                  <td className="px-4 py-3 text-right">
                    <RiskPill score={item.risk_score} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScoreCard({ label, value, sub, color }) {
  return (
    <div className="card text-center">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>
        {value}
        {sub && <span className="text-lg text-gray-400 font-normal">{sub}</span>}
      </p>
    </div>
  );
}

function RiskPill({ score }) {
  const color =
    score >= 8 ? 'bg-red-100 text-red-700' :
    score >= 4 ? 'bg-yellow-100 text-yellow-700' :
    'bg-green-100 text-green-700';
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>
      {score?.toFixed(1)}
    </span>
  );
}
