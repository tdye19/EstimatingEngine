import { useEffect, useState } from 'react';
import { getProductivityLibrary, updateProductivityRate } from '../api';
import { Library, Search, Pencil, Check, X } from 'lucide-react';

export default function ProductivityPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editId, setEditId] = useState(null);
  const [editRate, setEditRate] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getProductivityLibrary()
      .then((data) => setData(data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = data.filter(
    (r) =>
      r.csi_code?.toLowerCase().includes(search.toLowerCase()) ||
      r.work_type?.toLowerCase().includes(search.toLowerCase()) ||
      r.crew_type?.toLowerCase().includes(search.toLowerCase())
  );

  const startEdit = (r) => {
    setEditId(r.id);
    setEditRate(String(r.productivity_rate));
  };

  const cancelEdit = () => {
    setEditId(null);
    setEditRate('');
  };

  const saveEdit = async (r) => {
    const rate = parseFloat(editRate);
    if (isNaN(rate)) return;
    setSaving(true);
    try {
      const updated = await updateProductivityRate(r.csi_code, { productivity_rate: rate });
      setData((prev) => prev.map((item) => (item.id === r.id ? { ...item, ...updated } : item)));
      cancelEdit();
    } catch {
      // leave edit open on error
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Library className="h-6 w-6 text-apex-600" />
          <div>
            <h1 className="text-2xl font-bold">Productivity Library</h1>
            <p className="text-gray-500 text-sm">Crew productivity rates across CSI divisions</p>
          </div>
        </div>

        <div className="relative">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search CSI, work type, crew..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm w-72 focus:ring-2 focus:ring-apex-500 focus:border-apex-500 outline-none"
          />
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
                <th className="px-4 py-3">Work Type</th>
                <th className="px-4 py-3">Crew Type</th>
                <th className="px-4 py-3 text-right">Rate</th>
                <th className="px-4 py-3">Unit</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3 text-right">Confidence</th>
                <th className="px-4 py-3 w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((r) => {
                const isEditing = editId === r.id;
                return (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs">{r.csi_code}</td>
                    <td className="px-4 py-3">{r.work_type}</td>
                    <td className="px-4 py-3 text-gray-600">{r.crew_type}</td>
                    <td className="px-4 py-3 text-right font-medium">
                      {isEditing ? (
                        <input
                          type="number"
                          step="0.01"
                          value={editRate}
                          onChange={(e) => setEditRate(e.target.value)}
                          className="input w-24 text-right"
                          autoFocus
                        />
                      ) : (
                        r.productivity_rate
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{r.unit_of_measure}</td>
                    <td className="px-4 py-3">
                      {r.is_actual ? (
                        <span className="badge-success">Actual</span>
                      ) : (
                        <span className="text-gray-400 text-xs">{r.source_project || 'Baseline'}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <ConfidenceBar value={r.confidence_score} />
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
                          <button onClick={cancelEdit} className="text-gray-400 hover:text-gray-600">
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => startEdit(r)}
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
          {filtered.length === 0 && (
            <div className="text-center py-8 text-gray-400">No matching records</div>
          )}
        </div>
      )}
    </div>
  );
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 80 ? 'bg-green-500' : pct >= 60 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  );
}
