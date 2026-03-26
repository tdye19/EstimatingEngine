import { useEffect, useState } from 'react';
import {
  getMaterialPrices,
  createMaterialPrice,
  updateMaterialPrice,
  deleteMaterialPrice,
} from '../api';
import { DollarSign, Search, Pencil, Check, X, Trash2, Plus } from 'lucide-react';

const EMPTY_ROW = {
  csi_code: '',
  description: '',
  unit_cost: '',
  unit_of_measure: '',
  supplier: '',
  region: '',
  source: '',
  effective_date: '',
};

export default function MaterialsPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editId, setEditId] = useState(null);
  const [editData, setEditData] = useState({});
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newRow, setNewRow] = useState({ ...EMPTY_ROW });
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  useEffect(() => {
    getMaterialPrices()
      .then((d) => setData(d || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = data.filter(
    (r) =>
      r.csi_code?.toLowerCase().includes(search.toLowerCase()) ||
      r.description?.toLowerCase().includes(search.toLowerCase()) ||
      r.supplier?.toLowerCase().includes(search.toLowerCase())
  );

  const startEdit = (r) => {
    setEditId(r.id);
    setEditData({
      csi_code: r.csi_code || '',
      description: r.description || '',
      unit_cost: String(r.unit_cost ?? ''),
      unit_of_measure: r.unit_of_measure || '',
      supplier: r.supplier || '',
      region: r.region || '',
      source: r.source || '',
      effective_date: r.effective_date || '',
    });
  };

  const cancelEdit = () => {
    setEditId(null);
    setEditData({});
  };

  const saveEdit = async (r) => {
    const cost = parseFloat(editData.unit_cost);
    if (isNaN(cost)) return;
    setSaving(true);
    try {
      const payload = { ...editData, unit_cost: cost };
      const updated = await updateMaterialPrice(r.id, payload);
      setData((prev) =>
        prev.map((item) => (item.id === r.id ? { ...item, ...updated } : item))
      );
      cancelEdit();
    } catch {
      // leave edit open
    } finally {
      setSaving(false);
    }
  };

  const handleAdd = async () => {
    const cost = parseFloat(newRow.unit_cost);
    if (!newRow.csi_code.trim() || isNaN(cost)) return;
    setSaving(true);
    try {
      const payload = { ...newRow, unit_cost: cost };
      const created = await createMaterialPrice(payload);
      setData((prev) => [created, ...prev]);
      setAdding(false);
      setNewRow({ ...EMPTY_ROW });
    } catch {
      // leave form open
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteMaterialPrice(id);
      setData((prev) => prev.filter((r) => r.id !== id));
      setDeleteConfirm(null);
    } catch {
      // ignore
    }
  };

  const fmtCurrency = (v) => {
    const n = Number(v);
    if (isNaN(n)) return '—';
    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <DollarSign className="h-6 w-6 text-apex-600" />
          <div>
            <h1 className="text-2xl font-bold">Material Prices</h1>
            <p className="text-gray-500 text-sm">Material cost library by CSI division</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search CSI, description, supplier..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm w-72 focus:ring-2 focus:ring-apex-500 focus:border-apex-500 outline-none"
            />
          </div>
          <button
            onClick={() => setAdding(true)}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            <Plus className="h-4 w-4" />
            Add Material Price
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400">Loading...</div>
      ) : (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">CSI Code</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3 text-right">Unit Cost</th>
                <th className="px-4 py-3">UOM</th>
                <th className="px-4 py-3">Supplier</th>
                <th className="px-4 py-3">Region</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Effective Date</th>
                <th className="px-4 py-3 w-20"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {adding && (
                <tr className="bg-apex-50">
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      placeholder="CSI Code"
                      value={newRow.csi_code}
                      onChange={(e) => setNewRow((d) => ({ ...d, csi_code: e.target.value }))}
                      className="input w-full"
                      autoFocus
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      placeholder="Description"
                      value={newRow.description}
                      onChange={(e) => setNewRow((d) => ({ ...d, description: e.target.value }))}
                      className="input w-full"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                      value={newRow.unit_cost}
                      onChange={(e) => setNewRow((d) => ({ ...d, unit_cost: e.target.value }))}
                      className="input w-24 text-right"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      placeholder="UOM"
                      value={newRow.unit_of_measure}
                      onChange={(e) =>
                        setNewRow((d) => ({ ...d, unit_of_measure: e.target.value }))
                      }
                      className="input w-full"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      placeholder="Supplier"
                      value={newRow.supplier}
                      onChange={(e) => setNewRow((d) => ({ ...d, supplier: e.target.value }))}
                      className="input w-full"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      placeholder="Region"
                      value={newRow.region}
                      onChange={(e) => setNewRow((d) => ({ ...d, region: e.target.value }))}
                      className="input w-full"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      placeholder="Source"
                      value={newRow.source}
                      onChange={(e) => setNewRow((d) => ({ ...d, source: e.target.value }))}
                      className="input w-full"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="date"
                      value={newRow.effective_date}
                      onChange={(e) =>
                        setNewRow((d) => ({ ...d, effective_date: e.target.value }))
                      }
                      className="input w-full"
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={handleAdd}
                        disabled={saving}
                        className="text-green-600 hover:text-green-800"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => {
                          setAdding(false);
                          setNewRow({ ...EMPTY_ROW });
                        }}
                        className="text-gray-400 hover:text-gray-600"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              )}
              {filtered.map((r) => {
                const isEditing = editId === r.id;
                const isDeleting = deleteConfirm === r.id;
                return (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editData.csi_code}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, csi_code: e.target.value }))
                          }
                          className="input w-full"
                          autoFocus
                        />
                      ) : (
                        r.csi_code
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editData.description}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, description: e.target.value }))
                          }
                          className="input w-full"
                        />
                      ) : (
                        r.description
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-medium">
                      {isEditing ? (
                        <input
                          type="number"
                          step="0.01"
                          value={editData.unit_cost}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, unit_cost: e.target.value }))
                          }
                          className="input w-24 text-right"
                        />
                      ) : (
                        fmtCurrency(r.unit_cost)
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editData.unit_of_measure}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, unit_of_measure: e.target.value }))
                          }
                          className="input w-full"
                        />
                      ) : (
                        r.unit_of_measure
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editData.supplier}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, supplier: e.target.value }))
                          }
                          className="input w-full"
                        />
                      ) : (
                        r.supplier || '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editData.region}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, region: e.target.value }))
                          }
                          className="input w-full"
                        />
                      ) : (
                        r.region || '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editData.source}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, source: e.target.value }))
                          }
                          className="input w-full"
                        />
                      ) : (
                        r.source || '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {isEditing ? (
                        <input
                          type="date"
                          value={editData.effective_date}
                          onChange={(e) =>
                            setEditData((d) => ({ ...d, effective_date: e.target.value }))
                          }
                          className="input w-full"
                        />
                      ) : (
                        r.effective_date || '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {isEditing ? (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => saveEdit(r)}
                            disabled={saving}
                            className="text-green-600 hover:text-green-800"
                          >
                            <Check className="h-4 w-4" />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="text-gray-400 hover:text-gray-600"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : isDeleting ? (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleDelete(r.id)}
                            className="text-xs text-red-600 hover:text-red-800 font-medium"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            className="text-gray-400 hover:text-gray-600"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => startEdit(r)}
                            className="text-gray-300 hover:text-apex-600 transition-colors"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(r.id)}
                            className="text-gray-300 hover:text-red-600 transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && !adding && (
            <div className="text-center py-8 text-gray-400">No matching records</div>
          )}
        </div>
      )}
    </div>
  );
}
