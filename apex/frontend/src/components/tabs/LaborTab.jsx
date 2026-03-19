import { useEffect, useState } from 'react';
import { getLaborEstimates } from '../../api';
import { HardHat } from 'lucide-react';

function fmt$(val) {
  return '$' + Number(val || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function LaborTab({ projectId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getLaborEstimates(projectId)
      .then((response) => setItems(response.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading labor estimates...</div>;
  if (!items.length) return <div className="text-gray-400 py-8 text-center">No labor estimates.</div>;

  const totalHours = items.reduce((s, i) => s + (i.labor_hours || 0), 0);
  const totalCost = items.reduce((s, i) => s + (i.total_labor_cost || 0), 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryCard label="Total Crew-Hours" value={totalHours.toLocaleString()} />
        <SummaryCard label="Total Labor Cost" value={fmt$(totalCost)} />
        <SummaryCard label="Line Items" value={items.length} />
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">CSI</th>
              <th className="px-4 py-3">Work Type</th>
              <th className="px-4 py-3">Crew</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-right">Rate</th>
              <th className="px-4 py-3 text-right">Crew-Hrs</th>
              <th className="px-4 py-3 text-center">Crew Size</th>
              <th className="px-4 py-3 text-right">Crew-Days</th>
              <th className="px-4 py-3 text-right">$/Hr</th>
              <th className="px-4 py-3 text-right">Total Cost</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((item) => (
              <tr key={item.id} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono text-xs">{item.csi_code}</td>
                <td className="px-4 py-2">{item.work_type}</td>
                <td className="px-4 py-2 text-gray-600">{item.crew_type}</td>
                <td className="px-4 py-2 text-right">{Number(item.quantity).toLocaleString()}</td>
                <td className="px-4 py-2 text-right">{item.productivity_rate}</td>
                <td className="px-4 py-2 text-right font-medium">{Number(item.labor_hours).toLocaleString()}</td>
                <td className="px-4 py-2 text-center">{item.crew_size}</td>
                <td className="px-4 py-2 text-right">{item.crew_days}</td>
                <td className="px-4 py-2 text-right">${item.hourly_rate}</td>
                <td className="px-4 py-2 text-right font-semibold">{fmt$(item.total_labor_cost)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-gray-50 font-semibold">
              <td colSpan={5} className="px-4 py-3 text-right">Totals</td>
              <td className="px-4 py-3 text-right">{totalHours.toLocaleString()}</td>
              <td colSpan={3}></td>
              <td className="px-4 py-3 text-right">{fmt$(totalCost)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function SummaryCard({ label, value }) {
  return (
    <div className="card text-center">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
