import { useEffect, useState, lazy, Suspense } from 'react';
import { getEstimate, exportEstimatePdf, exportEstimateXlsx } from '../../api';
import { Calculator, DollarSign, FileDown, FileSpreadsheet } from 'lucide-react';

const EstimateCharts = lazy(() => import('../charts/EstimateCharts'));

function fmt$(val) {
  return '$' + Number(val || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function EstimateTab({ projectId, project }) {
  const [est, setEst] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState('');

  useEffect(() => {
    getEstimate(projectId)
      .then(setEst)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  const handleExport = async (type) => {
    setExporting(type);
    try {
      const num = project?.project_number || `PRJ-${projectId}`;
      if (type === 'pdf') await exportEstimatePdf(projectId, num);
      else await exportEstimateXlsx(projectId, num);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExporting('');
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading estimate...</div>;
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
        <h3 className="text-sm font-semibold mb-4">Estimate Build-Up</h3>
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
