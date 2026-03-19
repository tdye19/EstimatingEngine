import { useEffect, useState } from 'react';
import { getTakeoff, updateTakeoffItem } from '../../api';
import { Ruler, Pencil, Check, X } from 'lucide-react';

export default function TakeoffTab({ projectId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState(null);
  const [editQty, setEditQty] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getTakeoff(projectId)
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  const startEdit = (item) => {
    setEditId(item.id);
    setEditQty(String(item.quantity));
  };

  const cancelEdit = () => {
    setEditId(null);
    setEditQty('');
  };

  const saveEdit = async (item) => {
    const qty = parseFloat(editQty);
    if (isNaN(qty)) return;
    setSaving(true);
    try {
      const updated = await updateTakeoffItem(projectId, item.id, {
        quantity: qty,
        manual_override: true,
      });
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, ...updated } : i)));
      cancelEdit();
    } catch {
      // leave edit open on error
    } finally {
      setSaving(false);
    }
  };

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
                  <th className="px-4 py-2 w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {divItems.map((item) => {
                  const isEditing = editId === item.id;
                  return (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono text-xs">{item.csi_code}</td>
                      <td className="px-4 py-2">{item.description}</td>
                      <td className="px-4 py-2 text-right font-medium">
                        {isEditing ? (
                          <input
                            type="number"
                            value={editQty}
                            onChange={(e) => setEditQty(e.target.value)}
                            className="input w-24 text-right"
                            autoFocus
                          />
                        ) : (
                          Number(item.quantity).toLocaleString()
                        )}
                      </td>
                      <td className="px-4 py-2 text-gray-500">{item.unit_of_measure}</td>
                      <td className="px-4 py-2 text-gray-400 text-xs">{item.drawing_reference}</td>
                      <td className="px-4 py-2 text-right">
                        <ConfBadge value={item.confidence} />
                      </td>
                      <td className="px-4 py-2 text-right">
                        {isEditing ? (
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => saveEdit(item)}
                              disabled={saving}
                              className="text-green-600 hover:text-green-800"
                            >
                              <Check className="h-4 w-4" />
                            </button>
                            <button onClick={cancelEdit} className="text-gray-400 hover:text-gray-600">
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => startEdit(item)}
                            className="text-gray-300 hover:text-apex-600 transition-colors"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
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
