import { useEffect, useState } from 'react';
import { listProjects, getEstimate } from '../api';
import { ArrowLeftRight, BarChart3 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function fmt(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function pctDiff(a, b) {
  if (!a && !b) return '0%';
  const base = a || b;
  if (!base) return '—';
  const diff = ((b - a) / Math.abs(base)) * 100;
  const sign = diff > 0 ? '+' : '';
  return `${sign}${diff.toFixed(1)}%`;
}

export default function ComparePage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [projectA, setProjectA] = useState('');
  const [projectB, setProjectB] = useState('');
  const [estimateA, setEstimateA] = useState(null);
  const [estimateB, setEstimateB] = useState(null);
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [errorA, setErrorA] = useState('');
  const [errorB, setErrorB] = useState('');

  useEffect(() => {
    listProjects()
      .then((data) => setProjects(data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!projectA) { setEstimateA(null); return; }
    setLoadingA(true);
    setErrorA('');
    getEstimate(projectA)
      .then((data) => setEstimateA(data))
      .catch((err) => { setEstimateA(null); setErrorA(err.message); })
      .finally(() => setLoadingA(false));
  }, [projectA]);

  useEffect(() => {
    if (!projectB) { setEstimateB(null); return; }
    setLoadingB(true);
    setErrorB('');
    getEstimate(projectB)
      .then((data) => setEstimateB(data))
      .catch((err) => { setEstimateB(null); setErrorB(err.message); })
      .finally(() => setLoadingB(false));
  }, [projectB]);

  const projAData = projects.find((p) => String(p.id) === String(projectA));
  const projBData = projects.find((p) => String(p.id) === String(projectB));

  const bothLoaded = estimateA && estimateB;

  const chartData = bothLoaded ? [
    {
      name: 'Labor',
      [projAData?.name || 'Project A']: estimateA.total_labor_cost || 0,
      [projBData?.name || 'Project B']: estimateB.total_labor_cost || 0,
    },
    {
      name: 'Material',
      [projAData?.name || 'Project A']: estimateA.total_material_cost || 0,
      [projBData?.name || 'Project B']: estimateB.total_material_cost || 0,
    },
    {
      name: 'Equipment',
      [projAData?.name || 'Project A']: estimateA.total_equipment_cost || 0,
      [projBData?.name || 'Project B']: estimateB.total_equipment_cost || 0,
    },
    {
      name: 'Subcontractor',
      [projAData?.name || 'Project A']: estimateA.total_subcontractor_cost || 0,
      [projBData?.name || 'Project B']: estimateB.total_subcontractor_cost || 0,
    },
  ] : [];

  const nameA = projAData?.name || 'Project A';
  const nameB = projBData?.name || 'Project B';

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <ArrowLeftRight className="h-7 w-7 text-apex-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Compare Projects</h1>
          <p className="text-sm text-gray-500">Side-by-side estimate comparison</p>
        </div>
      </div>

      {/* Project selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Project A</label>
          <select
            value={projectA}
            onChange={(e) => setProjectA(e.target.value)}
            className="input w-full"
            disabled={loading}
          >
            <option value="">Select a project...</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id} disabled={String(p.id) === String(projectB)}>
                {p.project_number} — {p.name}
              </option>
            ))}
          </select>
          {loadingA && <p className="text-xs text-gray-400 mt-1">Loading estimate...</p>}
          {errorA && <p className="text-xs text-red-500 mt-1">{errorA}</p>}
          {projectA && !loadingA && !estimateA && !errorA && (
            <p className="text-xs text-amber-500 mt-1">No estimate available for this project.</p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Project B</label>
          <select
            value={projectB}
            onChange={(e) => setProjectB(e.target.value)}
            className="input w-full"
            disabled={loading}
          >
            <option value="">Select a project...</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id} disabled={String(p.id) === String(projectA)}>
                {p.project_number} — {p.name}
              </option>
            ))}
          </select>
          {loadingB && <p className="text-xs text-gray-400 mt-1">Loading estimate...</p>}
          {errorB && <p className="text-xs text-red-500 mt-1">{errorB}</p>}
          {projectB && !loadingB && !estimateB && !errorB && (
            <p className="text-xs text-amber-500 mt-1">No estimate available for this project.</p>
          )}
        </div>
      </div>

      {/* Comparison content */}
      {bothLoaded && (
        <div className="space-y-8">
          {/* Top summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Project A card */}
            <div className="card">
              <h3 className="text-sm font-medium text-gray-500 mb-2">Project A</h3>
              <p className="text-lg font-bold text-gray-900">{projAData?.name}</p>
              <div className="mt-3 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Bid</span>
                  <span className="font-semibold">{fmt(estimateA.total_bid_amount)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Direct Cost</span>
                  <span className="font-medium">{fmt(estimateA.total_direct_cost)}</span>
                </div>
              </div>
            </div>

            {/* Difference card */}
            <div className="card bg-gray-50 border-dashed flex flex-col items-center justify-center">
              <ArrowLeftRight className="h-6 w-6 text-gray-400 mb-2" />
              <p className="text-sm text-gray-500">Bid Difference</p>
              <p className="text-xl font-bold text-gray-900">
                {fmt(Math.abs((estimateB.total_bid_amount || 0) - (estimateA.total_bid_amount || 0)))}
              </p>
              <p className="text-sm text-gray-500">
                {pctDiff(estimateA.total_bid_amount, estimateB.total_bid_amount)}
              </p>
            </div>

            {/* Project B card */}
            <div className="card">
              <h3 className="text-sm font-medium text-gray-500 mb-2">Project B</h3>
              <p className="text-lg font-bold text-gray-900">{projBData?.name}</p>
              <div className="mt-3 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Bid</span>
                  <span className="font-semibold">{fmt(estimateB.total_bid_amount)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Direct Cost</span>
                  <span className="font-medium">{fmt(estimateB.total_direct_cost)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Cost breakdown comparison */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Cost Breakdown Comparison</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b">
                    <th className="py-2 pr-4">Category</th>
                    <th className="py-2 px-4 text-right">{nameA}</th>
                    <th className="py-2 px-4 text-right">{nameB}</th>
                    <th className="py-2 px-4 text-right">Difference</th>
                    <th className="py-2 pl-4 text-right">%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {[
                    { label: 'Labor', keyA: estimateA.total_labor_cost, keyB: estimateB.total_labor_cost },
                    { label: 'Material', keyA: estimateA.total_material_cost, keyB: estimateB.total_material_cost },
                    { label: 'Equipment', keyA: estimateA.total_equipment_cost || 0, keyB: estimateB.total_equipment_cost || 0 },
                    { label: 'Subcontractor', keyA: estimateA.total_subcontractor_cost, keyB: estimateB.total_subcontractor_cost },
                    { label: 'Direct Cost (Total)', keyA: estimateA.total_direct_cost, keyB: estimateB.total_direct_cost },
                  ].map((row) => (
                    <tr key={row.label}>
                      <td className="py-2 pr-4 font-medium text-gray-700">{row.label}</td>
                      <td className="py-2 px-4 text-right">{fmt(row.keyA)}</td>
                      <td className="py-2 px-4 text-right">{fmt(row.keyB)}</td>
                      <td className="py-2 px-4 text-right font-medium">
                        {fmt(Math.abs((row.keyB || 0) - (row.keyA || 0)))}
                      </td>
                      <td className="py-2 pl-4 text-right text-gray-500">
                        {pctDiff(row.keyA, row.keyB)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Markup comparison */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Markup Comparison</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b">
                    <th className="py-2 pr-4">Markup</th>
                    <th className="py-2 px-4 text-right">{nameA}</th>
                    <th className="py-2 px-4 text-right">{nameB}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {[
                    { label: 'Overhead', a: estimateA.overhead_pct, b: estimateB.overhead_pct },
                    { label: 'Profit', a: estimateA.profit_pct, b: estimateB.profit_pct },
                    { label: 'Contingency', a: estimateA.contingency_pct, b: estimateB.contingency_pct },
                  ].map((row) => (
                    <tr key={row.label}>
                      <td className="py-2 pr-4 font-medium text-gray-700">{row.label}</td>
                      <td className="py-2 px-4 text-right">{row.a != null ? `${row.a}%` : '—'}</td>
                      <td className="py-2 px-4 text-right">{row.b != null ? `${row.b}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Bar chart */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="h-5 w-5 text-apex-600" />
              <h3 className="text-sm font-semibold text-gray-700">Cost Comparison Chart</h3>
            </div>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barGap={8}>
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(value) => fmt(value)} />
                  <Legend />
                  <Bar dataKey={nameA} fill="#4f46e5" radius={[4, 4, 0, 0]} />
                  <Bar dataKey={nameB} fill="#06b6d4" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Empty state when no projects selected */}
      {!projectA && !projectB && !loading && (
        <div className="card text-center py-16 text-gray-400">
          <ArrowLeftRight className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p>Select two projects above to compare their estimates side by side.</p>
        </div>
      )}
    </div>
  );
}
