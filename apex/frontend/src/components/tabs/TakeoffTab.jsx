import { useEffect, useState } from 'react';
import { getTakeoff } from '../../api';
import { Ruler } from 'lucide-react';

export default function TakeoffTab({ projectId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTakeoff(projectId)
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading takeoff...</div>;
  if (!items.length) return <div className="text-gray-400 py-8 text-center">No takeoff items.</div>;

  // Group by CSI division
  const byDiv = {};
  items.forEach((item) => {
    const div = item.csi_code?.substring(0, 2) || '??';
    if (!byDiv[div]) byDiv[div] = [];
    byDiv[div].push(item);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Ruler className="h-4 w-4" />
        {items.length} takeoff items across {Object.keys(byDiv).length} divisions
      </div>

      {Object.entries(byDiv)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([div, divItems]) => (
          <div key={div} className="card p-0 overflow-hidden">
            <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700">Division {div}</h3>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-2">CSI</th>
                  <th className="px-4 py-2">Description</th>
                  <th className="px-4 py-2 text-right">Quantity</th>
                  <th className="px-4 py-2">Unit</th>
                  <th className="px-4 py-2">Dwg Ref</th>
                  <th className="px-4 py-2 text-right">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {divItems.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono text-xs">{item.csi_code}</td>
                    <td className="px-4 py-2">{item.description}</td>
                    <td className="px-4 py-2 text-right font-medium">
                      {Number(item.quantity).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-gray-500">{item.unit_of_measure}</td>
                    <td className="px-4 py-2 text-gray-400 text-xs">{item.drawing_reference}</td>
                    <td className="px-4 py-2 text-right">
                      <ConfBadge value={item.confidence} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </div>
  );
}

function ConfBadge({ value }) {
  const pct = Math.round((value || 0) * 100);
  const cls = pct >= 85 ? 'badge-success' : pct >= 70 ? 'badge-moderate' : 'badge-critical';
  return <span className={cls}>{pct}%</span>;
}
