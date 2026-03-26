import { useEffect, useState, useMemo } from 'react';
import { getTakeoff, updateTakeoffItem, bulkUpdateTakeoff } from '../../api';
import { Ruler, Pencil, Check, X, ChevronUp, ChevronDown, Search, StickyNote } from 'lucide-react';

export default function TakeoffTab({ projectId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editId, setEditId] = useState(null);
  const [editQty, setEditQty] = useState('');
  const [saving, setSaving] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [confidenceFilter, setConfidenceFilter] = useState('all');
  const [sortField, setSortField] = useState('csi_code');
  const [sortDir, setSortDir] = useState('asc');

  // Bulk selection state
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkUpdating, setBulkUpdating] = useState(false);
  const [showBulkNotes, setShowBulkNotes] = useState(false);
  const [bulkNotesValue, setBulkNotesValue] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    getTakeoff(projectId)
      .then((data) => {
        setItems(data || []);
        setSelectedIds(new Set());
      })
      .catch((err) => setError(err.message || 'Failed to load takeoff'))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId]);

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

  const toggleSelect = (itemId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    // Select/deselect all currently filtered items
    if (selectedIds.size === sorted.length && sorted.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(sorted.map((i) => i.id)));
    }
  };

  const handleBulkSetNotes = async () => {
    if (selectedIds.size === 0 || !bulkNotesValue.trim()) return;
    setBulkUpdating(true);
    try {
      await bulkUpdateTakeoff(projectId, [...selectedIds], { notes: bulkNotesValue.trim() });
      setSelectedIds(new Set());
      setShowBulkNotes(false);
      setBulkNotesValue('');
      load();
    } catch (err) {
      setError(`Bulk update failed: ${err.message}`);
    } finally {
      setBulkUpdating(false);
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading takeoff...</div>;
  if (error) return <div className="text-red-500 py-8 text-center">{error}<button onClick={load} className="ml-3 text-sm underline">Retry</button></div>;
  if (!items.length) return <div className="text-gray-400 py-8 text-center">No takeoff items.</div>;

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return null;
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 inline ml-0.5" />
      : <ChevronDown className="h-3 w-3 inline ml-0.5" />;
  };

  // Apply search filter
  const searchLower = searchText.toLowerCase();
  const afterSearch = items.filter((item) => {
    if (!searchText) return true;
    return (
      (item.csi_code || '').toLowerCase().includes(searchLower) ||
      (item.description || '').toLowerCase().includes(searchLower)
    );
  });

  // Apply confidence filter
  const confThresholds = { 'all': 0, '> 90%': 0.9, '> 70%': 0.7, '> 50%': 0.5 };
  const confMin = confThresholds[confidenceFilter] || 0;
  const filtered = afterSearch.filter((item) => (item.confidence || 0) >= confMin);

  // Apply sort
  const sorted = [...filtered].sort((a, b) => {
    let va = a[sortField], vb = b[sortField];
    if (typeof va === 'number') return sortDir === 'asc' ? va - vb : vb - va;
    return sortDir === 'asc' ? String(va || '').localeCompare(String(vb || '')) : String(vb || '').localeCompare(String(va || ''));
  });

  // Group by CSI division
  const byDiv = {};
  sorted.forEach((item) => {
    const div = item.csi_code?.substring(0, 2) || '??';
    if (!byDiv[div]) byDiv[div] = [];
    byDiv[div].push(item);
  });

  const allFilteredSelected = sorted.length > 0 && selectedIds.size === sorted.length;

  return (
    <div className="space-y-6">
      {/* Toolbar with search, confidence filter, and item count */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Ruler className="h-4 w-4" />
          {filtered.length} of {items.length} items
          {Object.keys(byDiv).length > 0 && ` across ${Object.keys(byDiv).length} divisions`}
        </div>
        <div className="flex items-center gap-3 ml-auto">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search CSI or description..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="input text-sm py-1.5 pl-8 pr-3 w-56"
            />
          </div>
          <select
            value={confidenceFilter}
            onChange={(e) => setConfidenceFilter(e.target.value)}
            className="input text-sm py-1.5"
          >
            <option value="all">All Confidence</option>
            <option value="> 90%">&gt; 90%</option>
            <option value="> 70%">&gt; 70%</option>
            <option value="> 50%">&gt; 50%</option>
          </select>
        </div>
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-4 bg-apex-50 border border-apex-200 rounded-lg px-4 py-2 text-sm">
          <span className="font-medium text-apex-700">{selectedIds.size} selected</span>
          <button
            onClick={() => { setShowBulkNotes(true); setBulkNotesValue(''); }}
            className="flex items-center gap-1 text-apex-600 hover:text-apex-800 font-medium"
          >
            <StickyNote className="h-4 w-4" />
            Set Notes
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-gray-500 hover:text-gray-700 font-medium"
          >
            Clear Selection
          </button>
        </div>
      )}

      {/* Bulk notes modal */}
      {showBulkNotes && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-lg font-semibold">Set Notes for {selectedIds.size} Item(s)</h3>
            <textarea
              value={bulkNotesValue}
              onChange={(e) => setBulkNotesValue(e.target.value)}
              placeholder="Enter notes to apply to all selected items..."
              className="input w-full h-28 resize-none"
              autoFocus
            />
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => { setShowBulkNotes(false); setBulkNotesValue(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkSetNotes}
                disabled={bulkUpdating || !bulkNotesValue.trim()}
                className="btn-primary text-sm disabled:opacity-50"
              >
                {bulkUpdating ? 'Updating…' : 'Apply Notes'}
              </button>
            </div>
          </div>
        </div>
      )}

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
                  <th className="px-4 py-2 w-10">
                    <input
                      type="checkbox"
                      checked={allFilteredSelected}
                      onChange={toggleSelectAll}
                      className="rounded border-gray-300"
                    />
                  </th>
                  <th className="px-4 py-2 cursor-pointer select-none" onClick={() => handleSort('csi_code')}>
                    CSI <SortIcon field="csi_code" />
                  </th>
                  <th className="px-4 py-2 cursor-pointer select-none" onClick={() => handleSort('description')}>
                    Description <SortIcon field="description" />
                  </th>
                  <th className="px-4 py-2 text-right cursor-pointer select-none" onClick={() => handleSort('quantity')}>
                    Quantity <SortIcon field="quantity" />
                  </th>
                  <th className="px-4 py-2 cursor-pointer select-none" onClick={() => handleSort('unit_of_measure')}>
                    Unit <SortIcon field="unit_of_measure" />
                  </th>
                  <th className="px-4 py-2">Dwg Ref</th>
                  <th className="px-4 py-2 text-right cursor-pointer select-none" onClick={() => handleSort('confidence')}>
                    Confidence <SortIcon field="confidence" />
                  </th>
                  <th className="px-4 py-2 w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {divItems.map((item) => {
                  const isEditing = editId === item.id;
                  return (
                    <tr key={item.id} className={`hover:bg-gray-50 ${selectedIds.has(item.id) ? 'bg-apex-50' : ''}`}>
                      <td className="px-4 py-2">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(item.id)}
                          onChange={() => toggleSelect(item.id)}
                          className="rounded border-gray-300"
                        />
                      </td>
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
      {filtered.length === 0 && (
        <div className="text-gray-400 py-8 text-center">No items match the current filters.</div>
      )}
    </div>
  );
}

function ConfBadge({ value }) {
  const pct = Math.round((value || 0) * 100);
  const cls = pct >= 85 ? 'badge-success' : pct >= 70 ? 'badge-moderate' : 'badge-critical';
  return <span className={cls}>{pct}%</span>;
}
