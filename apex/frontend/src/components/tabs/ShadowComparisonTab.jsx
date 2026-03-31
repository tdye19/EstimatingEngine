import { useEffect, useState } from 'react';
import { getComparison, updateProject } from '../../api';

function fmt$(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function ShadowComparisonTab({ projectId, project, refreshKey, onProjectUpdated }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [manualTotal, setManualTotal] = useState('');
  const [manualNotes, setManualNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    getComparison(projectId)
      .then((d) => {
        setData(d);
        setManualTotal(d?.manual_estimate_total ?? '');
        setManualNotes(d?.manual_estimate_notes ?? '');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId, refreshKey]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateProject(projectId, {
        manual_estimate_total: manualTotal === '' ? null : Number(manualTotal),
        manual_estimate_notes: manualNotes || null,
      });
      onProjectUpdated?.(updated);
      setEditing(false);
      // Refresh comparison data
      const fresh = await getComparison(projectId);
      setData(fresh);
      setManualTotal(fresh?.manual_estimate_total ?? '');
      setManualNotes(fresh?.manual_estimate_notes ?? '');
    } catch (err) {
      alert(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="p-8 text-gray-400">Loading comparison...</div>;
  if (!data) return <div className="p-8 text-gray-400">No comparison data available.</div>;

  const hasComparison = data.apex_estimate_total != null && data.manual_estimate_total != null;
  const varianceColor =
    data.variance_pct == null ? 'text-gray-500' :
    Math.abs(data.variance_pct) <= 5 ? 'text-green-600' :
    Math.abs(data.variance_pct) <= 15 ? 'text-yellow-600' : 'text-red-600';

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card text-center">
          <p className="text-sm text-gray-500 mb-1">APEX Estimate</p>
          <p className="text-2xl font-bold text-apex-600">{fmt$(data.apex_estimate_total)}</p>
        </div>

        <div className="card text-center">
          <p className="text-sm text-gray-500 mb-1">Manual Estimate</p>
          {editing ? (
            <div className="space-y-2">
              <input
                type="number"
                className="input w-full text-center text-lg font-bold"
                placeholder="Enter manual estimate total"
                value={manualTotal}
                onChange={(e) => setManualTotal(e.target.value)}
                autoFocus
              />
              <textarea
                className="input w-full text-sm"
                rows={2}
                placeholder="Notes (optional)"
                value={manualNotes}
                onChange={(e) => setManualNotes(e.target.value)}
              />
              <div className="flex justify-center gap-2">
                <button
                  onClick={() => {
                    setEditing(false);
                    setManualTotal(data.manual_estimate_total ?? '');
                    setManualNotes(data.manual_estimate_notes ?? '');
                  }}
                  className="btn-secondary text-sm"
                >
                  Cancel
                </button>
                <button onClick={handleSave} disabled={saving} className="btn-primary text-sm">
                  {saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold text-gray-800">{fmt$(data.manual_estimate_total)}</p>
              {data.manual_estimate_notes && (
                <p className="text-xs text-gray-400 mt-1">{data.manual_estimate_notes}</p>
              )}
              <button
                onClick={() => setEditing(true)}
                className="mt-2 text-xs text-apex-600 hover:text-apex-700 underline"
              >
                {data.manual_estimate_total != null ? 'Edit' : 'Enter manual estimate'}
              </button>
            </>
          )}
        </div>

        <div className="card text-center">
          <p className="text-sm text-gray-500 mb-1">Variance</p>
          {hasComparison ? (
            <>
              <p className={`text-2xl font-bold ${varianceColor}`}>
                {data.variance_pct > 0 ? '+' : ''}{data.variance_pct}%
              </p>
              <p className={`text-sm ${varianceColor}`}>
                {data.variance_absolute > 0 ? '+' : ''}{fmt$(data.variance_absolute)}
              </p>
            </>
          ) : (
            <p className="text-2xl font-bold text-gray-300">—</p>
          )}
        </div>
      </div>

      {/* Interpretation guide */}
      {hasComparison && (
        <div className={`p-4 rounded-lg border ${
          Math.abs(data.variance_pct) <= 5 ? 'bg-green-50 border-green-200' :
          Math.abs(data.variance_pct) <= 15 ? 'bg-yellow-50 border-yellow-200' :
          'bg-red-50 border-red-200'
        }`}>
          <p className="text-sm font-medium">
            {Math.abs(data.variance_pct) <= 5
              ? 'Excellent agreement between APEX and manual estimates.'
              : Math.abs(data.variance_pct) <= 15
              ? 'Moderate variance — review division-level differences below.'
              : 'Significant variance — detailed review recommended.'}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            APEX is {data.variance_absolute > 0 ? 'higher' : 'lower'} than the manual estimate
            by {fmt$(Math.abs(data.variance_absolute))}.
          </p>
        </div>
      )}

      {/* Division breakdown */}
      {data.by_division && data.by_division.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3">APEX Estimate by Division</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="py-2 pr-4 font-medium text-gray-500">Division</th>
                  <th className="py-2 pr-4 font-medium text-gray-500 text-right">APEX Total</th>
                </tr>
              </thead>
              <tbody>
                {data.by_division.map((div) => (
                  <tr key={div.division} className="border-b border-gray-100">
                    <td className="py-2 pr-4 font-mono">{div.division}</td>
                    <td className="py-2 pr-4 text-right">{fmt$(div.apex_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!hasComparison && (
        <div className="text-center py-8 text-gray-400">
          <p>Enter both an APEX estimate (run the pipeline) and a manual estimate to see the comparison.</p>
        </div>
      )}
    </div>
  );
}
