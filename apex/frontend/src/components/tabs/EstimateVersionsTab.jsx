import { useEffect, useState } from 'react';
import { GitBranch, Plus, ChevronRight, ArrowUp, ArrowDown } from 'lucide-react';
import { getEstimateVersions, snapshotEstimate, getEstimateVersion } from '../../api';

const FMT = (v) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const STATUS_COLORS = {
  draft: 'bg-gray-100 text-gray-600',
  reviewed: 'bg-blue-100 text-blue-700',
  submitted: 'bg-purple-100 text-purple-700',
  awarded: 'bg-green-100 text-green-700',
};

export default function EstimateVersionsTab({ projectId, refreshKey }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [snapshotting, setSnapshotting] = useState(false);
  const [selected, setSelected] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [msg, setMsg] = useState('');

  const load = () => {
    setLoading(true);
    getEstimateVersions(projectId)
      .then(setVersions)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId, refreshKey]);

  const handleSnapshot = async () => {
    setSnapshotting(true);
    setMsg('');
    try {
      const v = await snapshotEstimate(projectId);
      setMsg(`Version ${v.version} snapshot created.`);
      load();
    } catch (err) {
      setMsg(`Error: ${err.message}`);
    } finally {
      setSnapshotting(false);
    }
  };

  const handleSelect = async (version) => {
    setSelected(version);
    setLoadingDetail(true);
    try {
      const detail = await getEstimateVersion(projectId, version.version);
      setSelectedDetail(detail);
    } catch {
      setSelectedDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  if (loading) return <div className="text-gray-400 py-8">Loading estimate versions...</div>;

  const latestVersion = versions[0];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Estimate Versions</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Snapshot the current estimate to preserve it before re-running the pipeline.
          </p>
        </div>
        <button
          onClick={handleSnapshot}
          disabled={snapshotting || versions.length === 0}
          className="btn-secondary flex items-center gap-2"
        >
          <GitBranch className="h-4 w-4" />
          {snapshotting ? 'Creating...' : 'Snapshot Current'}
        </button>
      </div>

      {msg && <div className="text-sm bg-apex-50 text-apex-800 p-3 rounded-lg">{msg}</div>}

      {versions.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-gray-500">
          <GitBranch className="h-10 w-10 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No versions yet</p>
          <p className="text-sm mt-1">Run the pipeline to generate your first estimate, then snapshot it here.</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Version list */}
        <div className="space-y-2">
          {versions.map((v, idx) => {
            const prev = versions[idx + 1];
            const delta = prev ? v.total_bid_amount - prev.total_bid_amount : null;
            const isSelected = selected?.id === v.id;
            return (
              <button
                key={v.id}
                onClick={() => handleSelect(v)}
                className={`w-full text-left p-4 rounded-xl border transition-all ${isSelected ? 'border-apex-500 bg-apex-50' : 'border-gray-200 hover:border-gray-300 bg-white'}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[v.status] || STATUS_COLORS.draft}`}>
                      {v.status}
                    </span>
                    <span className="font-semibold">Version {v.version}</span>
                    {idx === 0 && <span className="text-xs text-apex-600 font-medium">(latest)</span>}
                  </div>
                  <ChevronRight className={`h-4 w-4 text-gray-400 transition-transform ${isSelected ? 'rotate-90' : ''}`} />
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className="font-mono text-sm font-bold">{FMT(v.total_bid_amount)}</span>
                  {delta !== null && (
                    <span className={`text-xs flex items-center gap-0.5 ${delta > 0 ? 'text-red-600' : delta < 0 ? 'text-green-600' : 'text-gray-400'}`}>
                      {delta > 0 ? <ArrowUp className="h-3 w-3" /> : delta < 0 ? <ArrowDown className="h-3 w-3" /> : null}
                      {delta !== 0 ? FMT(Math.abs(delta)) : 'no change'}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {new Date(v.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </p>
              </button>
            );
          })}
        </div>

        {/* Version detail */}
        {selected && (
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="font-bold text-sm mb-4">Version {selected.version} Detail</h3>
            {loadingDetail && <p className="text-gray-400 text-sm">Loading...</p>}
            {selectedDetail && !loadingDetail && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <DetailRow label="Direct Cost" value={FMT(selectedDetail.total_direct_cost)} />
                  <DetailRow label="Labor" value={FMT(selectedDetail.total_labor_cost)} />
                  <DetailRow label="Materials" value={FMT(selectedDetail.total_material_cost)} />
                  <DetailRow label="Subcontractors" value={FMT(selectedDetail.total_subcontractor_cost)} />
                  <DetailRow label={`Overhead (${selectedDetail.overhead_pct}%)`} value={FMT(selectedDetail.overhead_amount)} />
                  <DetailRow label={`Profit (${selectedDetail.profit_pct}%)`} value={FMT(selectedDetail.profit_amount)} />
                  <DetailRow label={`Contingency (${selectedDetail.contingency_pct}%)`} value={FMT(selectedDetail.contingency_amount)} />
                </div>
                <div className="border-t border-gray-100 pt-3">
                  <div className="flex justify-between font-bold text-base">
                    <span>Total Bid</span>
                    <span className="text-apex-700">{FMT(selectedDetail.total_bid_amount)}</span>
                  </div>
                </div>
                <div className="text-xs text-gray-400">
                  {selectedDetail.line_items?.length || 0} line items across this version
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono font-semibold">{value}</span>
    </div>
  );
}
