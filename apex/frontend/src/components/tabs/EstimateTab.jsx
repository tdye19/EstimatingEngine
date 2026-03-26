import { useEffect, useState, lazy, Suspense } from 'react';
import { getEstimate, getEstimateVersions, getEstimateByVersion, exportEstimatePdf, exportEstimateXlsx, exportEstimateCsv, exportEstimateQb, updateEstimateMarkups } from '../../api';
import { Calculator, DollarSign, FileDown, FileSpreadsheet, Pencil, Check, X, ChevronDown } from 'lucide-react';

const EstimateCharts = lazy(() => import('../charts/EstimateCharts'));

function fmt$(val) {
  return '$' + Number(val || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function EstimateTab({ projectId, project }) {
  const [est, setEst] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');
  const [editingMarkups, setEditingMarkups] = useState(false);
  const [markupForm, setMarkupForm] = useState({ overhead_pct: 0, profit_pct: 0, contingency_pct: 0, gc_markup_pct: 0 });
  const [savingMarkups, setSavingMarkups] = useState(false);
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);

  const load = () => {
    setLoading(true);
    setError('');
    Promise.all([
      getEstimate(projectId),
      getEstimateVersions(projectId),
    ])
      .then(([estData, versionsData]) => {
        setEst(estData);
        setVersions(versionsData || []);
        if (estData && estData.version != null) {
          setSelectedVersion(estData.version);
        } else if (versionsData && versionsData.length > 0) {
          setSelectedVersion(versionsData[0].version);
        }
      })
      .catch((err) => setError(err.message || 'Failed to load estimate'))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId]);

  const handleVersionChange = (version) => {
    setSelectedVersion(version);
    setLoading(true);
    setError('');
    getEstimateByVersion(projectId, version)
      .then(setEst)
      .catch((err) => setError(err.message || 'Failed to load estimate version'))
      .finally(() => setLoading(false));
  };

  const handleExport = async (type) => {
    setExporting(type);
    try {
      const num = project?.project_number || `PRJ-${projectId}`;
      if (type === 'pdf') await exportEstimatePdf(projectId, num);
      else if (type === 'xlsx') await exportEstimateXlsx(projectId, num);
      else if (type === 'csv') await exportEstimateCsv(projectId, num);
      else if (type === 'qb') await exportEstimateQb(projectId, num);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExporting('');
    }
  };

  const startEditMarkups = () => {
    setMarkupForm({
      overhead_pct: est.overhead_pct || 0,
      profit_pct: est.profit_pct || 0,
      contingency_pct: est.contingency_pct || 0,
      gc_markup_pct: est.gc_markup_pct || 0,
    });
    setEditingMarkups(true);
  };

  const cancelEditMarkups = () => {
    setEditingMarkups(false);
  };

  const saveMarkups = async () => {
    setSavingMarkups(true);
    try {
      const updated = await updateEstimateMarkups(projectId, est.id, markupForm);
      setEst((prev) => ({ ...prev, ...updated }));
      setEditingMarkups(false);
    } catch (err) {
      console.error('Failed to save markups:', err);
    } finally {
      setSavingMarkups(false);
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading estimate...</div>;
  if (error) return <div className="text-red-500 py-8 text-center">{error}<button onClick={load} className="ml-3 text-sm underline">Retry</button></div>;
  if (!est) return <div className="text-gray-400 py-8 text-center">No estimate available.</div>;

  // Group line items by division
  const divTotals = {};
  (est.line_items || []).forEach((li) => {
    const div = li.division_number || '??';
    if (!divTotals[div]) divTotals[div] = { div, labor: 0, material: 0, equipment: 0, total: 0 };
    divTotals[div].labor += li.labor_cost || 0;
    divTotals[div].material += li.material_cost || 0;
    divTotals[div].equipment += li.equipment_cost || 0;
    divTotals[div].total += li.total_cost || 0;
  });
  const divData = Object.values(divTotals).sort((a, b) => a.div.localeCompare(b.div));

  const pieData = divData.map((d) => ({ name: `Div ${d.div}`, value: Math.round(d.total) }));

  const markups = [
    { label: 'Direct Cost', amount: est.total_direct_cost },
    { label: `Overhead (${est.overhead_pct}%)`, amount: est.overhead_amount },
    { label: `Profit (${est.profit_pct}%)`, amount: est.profit_amount },
    { label: `Contingency (${est.contingency_pct}%)`, amount: est.contingency_amount },
  ];

  return (
    <div className="space-y-6">
      {/* Version selector */}
      {versions.length > 1 && (
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-gray-600">Version:</label>
          <select
            value={selectedVersion ?? ''}
            onChange={(e) => handleVersionChange(Number(e.target.value))}
            className="input text-sm"
          >
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version} — {v.status} — {fmt$(v.total_bid_amount)} — {v.created_at ? new Date(v.created_at).toLocaleDateString() : 'N/A'}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Export buttons */}
      <div className="flex justify-end gap-2">
        <button
          onClick={() => handleExport('pdf')}
          disabled={!!exporting}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <FileDown className="h-4 w-4" />
          {exporting === 'pdf' ? 'Generating…' : 'Export PDF'}
        </button>
        <button
          onClick={() => handleExport('xlsx')}
          disabled={!!exporting}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <FileSpreadsheet className="h-4 w-4" />
          {exporting === 'xlsx' ? 'Generating…' : 'Export Excel'}
        </button>
        <button
          onClick={() => handleExport('csv')}
          disabled={!!exporting}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <FileDown className="h-4 w-4" />
          {exporting === 'csv' ? 'Generating…' : 'Export CSV'}
        </button>
        <button
          onClick={() => handleExport('qb')}
          disabled={!!exporting}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <FileDown className="h-4 w-4" />
          {exporting === 'qb' ? 'Generating…' : 'Export QB'}
        </button>
      </div>

      {/* Big number */}
      <div className="card bg-gradient-to-r from-apex-600 to-apex-800 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-apex-200 text-sm">Total Bid Amount</p>
            <p className="text-4xl font-bold mt-1">{fmt$(est.total_bid_amount)}</p>
          </div>
          <DollarSign className="h-12 w-12 text-apex-300 opacity-50" />
        </div>
        <div className="grid grid-cols-3 gap-4 mt-6 pt-4 border-t border-apex-500">
          <div>
            <p className="text-apex-200 text-xs">Labor</p>
            <p className="font-semibold">{fmt$(est.total_labor_cost)}</p>
          </div>
          <div>
            <p className="text-apex-200 text-xs">Material</p>
            <p className="font-semibold">{fmt$(est.total_material_cost)}</p>
          </div>
          <div>
            <p className="text-apex-200 text-xs">Direct Cost</p>
            <p className="font-semibold">{fmt$(est.total_direct_cost)}</p>
          </div>
        </div>
      </div>

      {/* Charts row */}
      <Suspense fallback={<div className="text-gray-400 text-center py-8">Loading chart...</div>}>
        <EstimateCharts divData={divData} pieData={pieData} />
      </Suspense>

      {/* Markup breakdown */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold">Estimate Build-Up</h3>
          {!editingMarkups && (
            <button
              onClick={startEditMarkups}
              className="text-gray-400 hover:text-apex-600 transition-colors"
              title="Edit Markups"
            >
              <Pencil className="h-4 w-4" />
            </button>
          )}
        </div>
        {editingMarkups ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Direct Cost</span>
              <span className="font-semibold">{fmt$(est.total_direct_cost)}</span>
            </div>
            {[
              { key: 'overhead_pct', label: 'Overhead' },
              { key: 'profit_pct', label: 'Profit' },
              { key: 'contingency_pct', label: 'Contingency' },
              { key: 'gc_markup_pct', label: 'GC Markup' },
            ].map(({ key, label }) => (
              <div key={key} className="flex items-center justify-between">
                <label className="text-sm text-gray-600">{label} (%)</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={markupForm[key]}
                  onChange={(e) => setMarkupForm((prev) => ({ ...prev, [key]: parseFloat(e.target.value) || 0 }))}
                  className="input w-24 text-right text-sm"
                />
              </div>
            ))}
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={cancelEditMarkups}
                disabled={savingMarkups}
                className="btn-secondary flex items-center gap-1 text-sm"
              >
                <X className="h-3.5 w-3.5" /> Cancel
              </button>
              <button
                onClick={saveMarkups}
                disabled={savingMarkups}
                className="btn-primary flex items-center gap-1 text-sm"
              >
                <Check className="h-3.5 w-3.5" /> {savingMarkups ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {markups.map((m) => (
              <div key={m.label} className="flex items-center justify-between">
                <span className="text-sm text-gray-600">{m.label}</span>
                <span className="font-semibold">{fmt$(m.amount)}</span>
              </div>
            ))}
            <div className="border-t border-gray-200 pt-3 flex items-center justify-between">
              <span className="font-bold">Total Bid</span>
              <span className="text-lg font-bold text-apex-600">{fmt$(est.total_bid_amount)}</span>
            </div>
          </div>
        )}
      </div>

      {/* Exclusions and Assumptions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold mb-3">Exclusions</h3>
          <ul className="space-y-1.5">
            {(est.exclusions || []).map((e, i) => (
              <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                <span className="text-red-400 mt-0.5">&#x2717;</span> {e}
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold mb-3">Assumptions</h3>
          <ul className="space-y-1.5">
            {(est.assumptions || []).map((a, i) => (
              <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                <span className="text-green-500 mt-0.5">&#x2713;</span> {a}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Line items table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <h3 className="text-sm font-semibold">Estimate Line Items ({(est.line_items || []).length})</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-2">Div</th>
                <th className="px-4 py-2">CSI</th>
                <th className="px-4 py-2">Description</th>
                <th className="px-4 py-2 text-right">Qty</th>
                <th className="px-4 py-2">Unit</th>
                <th className="px-4 py-2 text-right">Labor</th>
                <th className="px-4 py-2 text-right">Material</th>
                <th className="px-4 py-2 text-right">Equip</th>
                <th className="px-4 py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(est.line_items || []).map((li) => (
                <tr key={li.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-400">{li.division_number}</td>
                  <td className="px-4 py-2 font-mono text-xs">{li.csi_code}</td>
                  <td className="px-4 py-2">{li.description}</td>
                  <td className="px-4 py-2 text-right">{Number(li.quantity).toLocaleString()}</td>
                  <td className="px-4 py-2 text-gray-500">{li.unit_of_measure}</td>
                  <td className="px-4 py-2 text-right">{fmt$(li.labor_cost)}</td>
                  <td className="px-4 py-2 text-right">{fmt$(li.material_cost)}</td>
                  <td className="px-4 py-2 text-right">{fmt$(li.equipment_cost)}</td>
                  <td className="px-4 py-2 text-right font-semibold">{fmt$(li.total_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
