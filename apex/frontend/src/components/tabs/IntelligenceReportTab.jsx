import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Shield,
  AlertTriangle,
  RefreshCw,
  ChevronRight,
  ArrowDown,
  ArrowUp,
  Minus,
  FileText,
  Database,
  Loader2,
} from 'lucide-react';
import { getIntelligenceReport, runAgent } from '../../api';

// ── Risk level colors ──────────────────────────────────────────────
const RISK_CONFIG = {
  low:      { bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-300',  dot: 'bg-green-500'  },
  moderate: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300', dot: 'bg-yellow-500' },
  high:     { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300', dot: 'bg-orange-500' },
  critical: { bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-300',    dot: 'bg-red-500'    },
  unknown:  { bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-300',   dot: 'bg-gray-400'   },
};

const FLAG_COLORS = {
  OK:         'bg-green-500',
  REVIEW:     'bg-yellow-500',
  UPDATE:     'bg-red-500',
  NEEDS_RATE: 'bg-purple-500',
  NO_DATA:    'bg-gray-300',
};

// ── Helpers ────────────────────────────────────────────────────────
function fmtCurrency(v) {
  if (v == null) return '--';
  return '$' + Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtPct(v) {
  if (v == null) return '--';
  const n = Number(v);
  const prefix = n > 0 ? '+' : '';
  return `${prefix}${n.toFixed(1)}%`;
}

// ── Confidence ring (pure CSS) ─────────────────────────────────────
function ConfidenceRing({ value }) {
  const pct = Math.round(value || 0);
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct >= 70 ? '#22c55e' : pct >= 40 ? '#eab308' : '#ef4444';

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="96" height="96" className="-rotate-90">
        <circle cx="48" cy="48" r="40" stroke="#e5e7eb" strokeWidth="6" fill="none" />
        <circle
          cx="48" cy="48" r="40"
          stroke={color}
          strokeWidth="6"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold">{pct}%</span>
        <span className="text-[10px] text-gray-500 uppercase tracking-wide">Confidence</span>
      </div>
    </div>
  );
}

// ── Distribution bar (pure CSS) ────────────────────────────────────
function DistributionBar({ segments }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0);
  if (total === 0) return <div className="h-3 w-full rounded-full bg-gray-200" />;

  return (
    <div className="h-3 w-full flex rounded-full overflow-hidden">
      {segments.map((seg, i) =>
        seg.value > 0 ? (
          <div
            key={i}
            className={`${seg.color} transition-all duration-500`}
            style={{ width: `${(seg.value / total) * 100}%` }}
            title={`${seg.label}: ${seg.value}`}
          />
        ) : null,
      )}
    </div>
  );
}

// ── Section card wrapper ───────────────────────────────────────────
function SectionCard({ title, icon: Icon, onNavigate, children }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        </div>
        {onNavigate && (
          <button
            onClick={onNavigate}
            className="text-xs text-apex-600 hover:text-apex-800 flex items-center gap-0.5"
          >
            View Details <ChevronRight className="h-3 w-3" />
          </button>
        )}
      </div>
      <div className="px-5 py-4 flex-1">{children}</div>
    </div>
  );
}

// ── Severity badge ─────────────────────────────────────────────────
function SeverityBadge({ severity, count }) {
  const colors = {
    critical: 'bg-red-100 text-red-700',
    watch: 'bg-yellow-100 text-yellow-700',
    spec_vs_takeoff: 'bg-orange-100 text-orange-700',
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colors[severity] || 'bg-gray-100 text-gray-600'}`}>
      {count} {severity.replace(/_/g, ' ')}
    </span>
  );
}

// ── Main component ─────────────────────────────────────────────────
export default function IntelligenceReportTab({ projectId, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [regenerating, setRegenerating] = useState(false);
  const navigate = useNavigate();
  const { id } = useParams();

  const load = () => {
    setLoading(true);
    setError('');
    getIntelligenceReport(projectId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId, refreshKey]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await runAgent(projectId, 6);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setRegenerating(false);
    }
  };

  const navTo = (tab) => navigate(`/projects/${id}/${tab}`);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-400">
        <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading intelligence report...
      </div>
    );
  }

  if (error) {
    return <div className="p-6 text-red-600 bg-red-50 rounded-lg">{error}</div>;
  }

  // Empty state
  if (!data || data.status === 'no_report') {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Shield className="h-16 w-16 text-gray-300 mb-4" />
        <h2 className="text-lg font-semibold text-gray-700 mb-2">No Intelligence Report Yet</h2>
        <p className="text-sm text-gray-500 max-w-md">
          Upload a spec and takeoff, then run the pipeline to generate your bid intelligence briefing.
        </p>
      </div>
    );
  }

  const risk = RISK_CONFIG[data.overall_risk_level] || RISK_CONFIG.unknown;
  const ri = data.rate_intelligence || {};
  const fc = data.field_calibration || {};
  const sr = data.scope_risk || {};
  const cp = data.comparable_projects || {};

  const rateAttention = (ri.items_review || 0) + (ri.items_update || 0);

  return (
    <div className="space-y-6">
      {/* ── Header row ─────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-6 bg-white rounded-xl border border-gray-200 shadow-sm px-6 py-4">
        {/* Risk badge */}
        <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${risk.bg} ${risk.border}`}>
          <div className={`h-4 w-4 rounded-full ${risk.dot}`} />
          <div>
            <div className={`text-lg font-bold uppercase ${risk.text}`}>
              {data.overall_risk_level || 'Unknown'}
            </div>
            <div className="text-xs text-gray-500">Risk Level</div>
          </div>
        </div>

        {/* Confidence ring */}
        <ConfidenceRing value={data.confidence_score} />

        {/* Meta */}
        <div className="flex-1 min-w-0">
          <div className="text-sm text-gray-500">
            Version {data.version}
            {data.generated_at && (
              <span className="ml-2 text-gray-400">
                {new Date(data.generated_at).toLocaleString()}
              </span>
            )}
          </div>
          <div className="text-sm text-gray-500 mt-1">
            {data.takeoff_item_count || 0} takeoff items analyzed
          </div>
        </div>

        {/* Regenerate */}
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <RefreshCw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
          {regenerating ? 'Regenerating...' : 'Regenerate Report'}
        </button>
      </div>

      {/* ── Executive narrative ─────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-800">Executive Briefing</h3>
          </div>
          <span className="text-xs text-gray-400">
            {data.narrative_method === 'llm' ? 'AI-Generated Briefing' : 'Template Summary'}
          </span>
        </div>
        <div className="px-6 py-5 bg-gray-50/50">
          <div className="text-[15px] leading-relaxed text-gray-700 whitespace-pre-line">
            {data.executive_narrative || 'No narrative available.'}
          </div>
        </div>
      </div>

      {/* ── 4 Intelligence cards (2x2 grid) ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Card 1: Rate Intelligence */}
        <SectionCard title="Rate Intelligence" icon={AlertTriangle} onNavigate={() => navTo('rate-intelligence')}>
          <DistributionBar
            segments={[
              { value: ri.items_ok || 0, color: FLAG_COLORS.OK, label: 'OK' },
              { value: ri.items_review || 0, color: FLAG_COLORS.REVIEW, label: 'Review' },
              { value: ri.items_update || 0, color: FLAG_COLORS.UPDATE, label: 'Update' },
              { value: ri.items_needs_rate || 0, color: FLAG_COLORS.NEEDS_RATE, label: 'Needs Rate' },
              { value: ri.items_no_match || 0, color: FLAG_COLORS.NO_DATA, label: 'No Data' },
            ]}
          />
          <div className="flex items-center gap-3 mt-3 text-xs text-gray-500 flex-wrap">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-500" /> OK: {ri.items_ok || 0}</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-yellow-500" /> Review: {ri.items_review || 0}</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> Update: {ri.items_update || 0}</span>
            {(ri.items_needs_rate || 0) > 0 && (
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-purple-500" /> Needs Rate: {ri.items_needs_rate}</span>
            )}
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-gray-300" /> No Data: {ri.items_no_match || 0}</span>
          </div>

          {rateAttention > 0 && (
            <p className="mt-3 text-sm font-medium text-amber-700">
              {rateAttention} item{rateAttention !== 1 ? 's' : ''} need attention
            </p>
          )}

          {(ri.items_needs_rate || 0) > 0 && (
            <p className="mt-1 text-sm font-medium text-purple-700">
              {ri.items_needs_rate} item{ri.items_needs_rate !== 1 ? 's' : ''} need rates entered
            </p>
          )}

          {/* Optimism indicator */}
          {ri.optimism_score != null && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <span className="text-gray-500">Optimism:</span>
              {ri.optimism_score > 2 ? (
                <span className="flex items-center gap-1 text-red-600"><ArrowUp className="h-3 w-3" /> Optimistic ({fmtPct(ri.optimism_score)})</span>
              ) : ri.optimism_score < -2 ? (
                <span className="flex items-center gap-1 text-blue-600"><ArrowDown className="h-3 w-3" /> Conservative ({fmtPct(ri.optimism_score)})</span>
              ) : (
                <span className="flex items-center gap-1 text-green-600"><Minus className="h-3 w-3" /> Aligned ({fmtPct(ri.optimism_score)})</span>
              )}
            </div>
          )}

          {/* Top deviations */}
          {(ri.top_deviations || []).length > 0 && (
            <div className="mt-3">
              <p className="text-xs text-gray-500 mb-1">Top Deviations</p>
              <div className="space-y-1">
                {ri.top_deviations.slice(0, 3).map((d, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 truncate mr-2">{d.activity}</span>
                    <span className={`font-mono text-xs font-medium ${
                      d.flag === 'UPDATE' ? 'text-red-600' : d.flag === 'REVIEW' ? 'text-yellow-600' : 'text-green-600'
                    }`}>
                      {fmtPct(d.delta_pct)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </SectionCard>

        {/* Card 2: Field Calibration */}
        <SectionCard title="Field Calibration" icon={Database} onNavigate={() => navTo('field-calibration')}>
          {fc.items_with_field_data > 0 || fc.items_without_field_data > 0 ? (
            <>
              <DistributionBar
                segments={[
                  { value: fc.optimistic_count || 0, color: 'bg-red-500', label: 'Optimistic' },
                  { value: fc.aligned_count || 0, color: 'bg-green-500', label: 'Aligned' },
                  { value: fc.conservative_count || 0, color: 'bg-blue-500', label: 'Conservative' },
                  { value: (fc.items_without_field_data || 0), color: 'bg-gray-300', label: 'No Data' },
                ]}
              />
              <div className="flex items-center gap-3 mt-3 text-xs text-gray-500">
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> Optimistic: {fc.optimistic_count || 0}</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-500" /> Aligned: {fc.aligned_count || 0}</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-blue-500" /> Conservative: {fc.conservative_count || 0}</span>
              </div>

              <p className="mt-3 text-sm text-gray-600">
                <span className="font-medium">{fc.items_with_field_data}</span> activities with field data
                {fc.optimistic_count > 0 && (
                  <span className="text-red-600 ml-1">
                    ({fc.optimistic_count} optimistic alert{fc.optimistic_count !== 1 ? 's' : ''})
                  </span>
                )}
              </p>

              {(fc.critical_alerts || []).length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-500 mb-1">Critical Alerts</p>
                  <div className="space-y-1">
                    {fc.critical_alerts.slice(0, 3).map((a, i) => (
                      <div key={i} className="flex items-center justify-between text-sm">
                        <span className="text-gray-700 truncate mr-2">{a.activity}</span>
                        <span className="font-mono text-xs text-red-600 font-medium">
                          {Number(a.calibration_factor).toFixed(2)}x
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-gray-500 py-4 text-center">
              <Database className="h-8 w-8 text-gray-300 mx-auto mb-2" />
              No field actuals loaded — upload close-out data to enable calibration.
            </div>
          )}
        </SectionCard>

        {/* Card 3: Scope Risk */}
        <SectionCard title="Scope Risk" icon={AlertTriangle} onNavigate={() => navTo('gap-report')}>
          {sr.total_gaps > 0 ? (
            <>
              <div className="flex flex-wrap gap-2">
                {sr.critical_gaps > 0 && <SeverityBadge severity="critical" count={sr.critical_gaps} />}
                {sr.watch_gaps > 0 && <SeverityBadge severity="watch" count={sr.watch_gaps} />}
                {sr.spec_vs_takeoff_gaps > 0 && <SeverityBadge severity="spec_vs_takeoff" count={sr.spec_vs_takeoff_gaps} />}
              </div>

              {(sr.missing_divisions || []).length > 0 && (
                <p className="mt-3 text-sm text-gray-600">
                  <span className="font-medium text-red-600">Missing divisions:</span>{' '}
                  {sr.missing_divisions.join(', ')}
                </p>
              )}

              {(sr.top_risks || []).length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-500 mb-1">Top Risks</p>
                  <div className="space-y-1.5">
                    {sr.top_risks.slice(0, 3).map((r, i) => (
                      <div key={i} className="text-sm">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium mr-1.5 ${
                          r.severity === 'critical' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
                        }`}>
                          {r.severity}
                        </span>
                        <span className="text-gray-700">{r.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-gray-500 py-4 text-center">
              <Shield className="h-8 w-8 text-green-300 mx-auto mb-2" />
              No scope gaps identified. Looking good!
            </div>
          )}
        </SectionCard>

        {/* Card 4: Comparable Projects */}
        <SectionCard title="Comparable Projects" icon={Database} onNavigate={() => navTo('bid-intelligence')}>
          {cp.comparable_count > 0 ? (
            <>
              <div className="flex items-baseline gap-4 mb-3">
                <p className="text-sm text-gray-600">
                  <span className="font-medium">{cp.comparable_count}</span> similar bids
                </p>
                {cp.company_hit_rate != null && (
                  <p className="text-sm text-gray-600">
                    Hit rate: <span className="font-medium">{cp.company_hit_rate}%</span>
                  </p>
                )}
                {cp.avg_bid_amount != null && (
                  <p className="text-sm text-gray-600">
                    Avg bid: <span className="font-medium">{fmtCurrency(cp.avg_bid_amount)}</span>
                  </p>
                )}
              </div>

              {(cp.comparables || []).length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-gray-500 border-b border-gray-100">
                        <th className="text-left py-1 pr-3 font-medium">Project</th>
                        <th className="text-right py-1 px-2 font-medium">Bid Amount</th>
                        <th className="text-right py-1 px-2 font-medium">$/CY</th>
                        <th className="text-right py-1 pl-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cp.comparables.slice(0, 5).map((c, i) => (
                        <tr key={i} className="border-b border-gray-50">
                          <td className="py-1.5 pr-3 text-gray-700 truncate max-w-[180px]">{c.name}</td>
                          <td className="py-1.5 px-2 text-right font-mono">{fmtCurrency(c.bid_amount)}</td>
                          <td className="py-1.5 px-2 text-right font-mono">{c.cost_per_cy != null ? `$${Number(c.cost_per_cy).toFixed(0)}` : '--'}</td>
                          <td className="py-1.5 pl-2 text-right">
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              c.status === 'Awarded' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                            }`}>
                              {c.status || '--'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-gray-500 py-4 text-center">
              <Database className="h-8 w-8 text-gray-300 mx-auto mb-2" />
              Load estimation history to enable comparable project lookup.
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Data coverage footer ───────────────────────────── */}
      <div className="flex flex-wrap gap-3 text-xs">
        <span className="px-3 py-1.5 rounded-full bg-gray-100 text-gray-600">
          PB: {data.pb_projects_loaded || 0} projects, {data.pb_activities_available || 0} activities
        </span>
        <span className="px-3 py-1.5 rounded-full bg-gray-100 text-gray-600">
          Spec: {data.spec_sections_parsed || 0} sections ({data.material_specs_extracted || 0} with materials)
        </span>
        <span className="px-3 py-1.5 rounded-full bg-gray-100 text-gray-600">
          Takeoff: {data.takeoff_item_count || 0} items
        </span>
        <span className="px-3 py-1.5 rounded-full bg-gray-100 text-gray-600">
          Field Calibration: {fc.items_with_field_data || 0} with data
        </span>
        <span className="px-3 py-1.5 rounded-full bg-gray-100 text-gray-600">
          Comparable Bids: {cp.comparable_count || 0}
        </span>
      </div>
    </div>
  );
}
