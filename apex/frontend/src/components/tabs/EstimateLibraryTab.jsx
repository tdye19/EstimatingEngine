import { useEffect, useState, useCallback, Suspense, lazy } from 'react';
import {
  Search,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  BarChart2,
  Tag,
  FileText,
  Archive,
  CheckSquare,
  Edit3,
  X,
  Save,
  TrendingUp,
} from 'lucide-react';
import {
  getEstimateLibrary,
  getEstimateLibraryStats,
  updateEstimateLibraryEntry,
  deleteEstimateLibraryEntry,
  compareEstimates,
} from '../../api';

const PAGE_SIZE = 25;

const BID_RESULT_STYLES = {
  won: 'bg-green-100 text-green-800',
  lost: 'bg-red-100 text-red-800',
  pending: 'bg-gray-100 text-gray-600',
};

function fmt$(n) {
  if (n == null) return '—';
  return '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function fmtSF(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' SF';
}

function fmtDollarPerSF(cost, sqft) {
  if (!cost || !sqft) return '—';
  return '$' + (cost / sqft).toFixed(2) + '/SF';
}

// ── Stats panel ────────────────────────────────────────────────────────────

function StatsPanel({ stats }) {
  if (!stats) return null;
  const { total_estimates, win_rate, avg_cost_per_sf_by_type } = stats;
  const topTypes = avg_cost_per_sf_by_type
    ? Object.entries(avg_cost_per_sf_by_type)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
    : [];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3 mb-6">
      <div className="card p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Total Estimates</p>
        <p className="text-3xl font-bold text-gray-900">{total_estimates ?? '—'}</p>
      </div>
      <div className="card p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Win Rate</p>
        <p className="text-3xl font-bold text-green-600">
          {win_rate != null ? (win_rate * 100).toFixed(1) + '%' : '—'}
        </p>
      </div>
      <div className="card p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Avg $/SF by Type (Top 5)</p>
        {topTypes.length === 0 ? (
          <p className="text-sm text-gray-400">No data</p>
        ) : (
          <ul className="space-y-1">
            {topTypes.map(([type, val]) => (
              <li key={type} className="flex justify-between text-sm">
                <span className="capitalize text-gray-600">{type}</span>
                <span className="font-medium">${Number(val).toFixed(2)}/SF</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Expanded row detail ────────────────────────────────────────────────────

function EntryDetail({ entry, onClose, onEdit, onArchive, compareIds, onToggleCompare }) {
  const inCompare = compareIds.includes(entry.id);
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mt-1 mb-2">
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-gray-900">{entry.name}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <X className="h-4 w-4" />
        </button>
      </div>

      {entry.description && (
        <p className="text-sm text-gray-600 mb-3">{entry.description}</p>
      )}

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm mb-3">
        {entry.line_item_count != null && (
          <div><span className="text-gray-500">Line Items:</span> <span className="font-medium">{entry.line_item_count}</span></div>
        )}
        {entry.notes && (
          <div className="col-span-2"><span className="text-gray-500">Notes:</span> <span>{entry.notes}</span></div>
        )}
        {entry.tags?.length > 0 && (
          <div className="col-span-2 flex items-center gap-2 flex-wrap">
            <Tag className="h-3.5 w-3.5 text-gray-400" />
            {entry.tags.map((t) => (
              <span key={t} className="px-2 py-0.5 bg-apex-50 text-apex-700 rounded-full text-xs">{t}</span>
            ))}
          </div>
        )}
      </div>

      {entry.csi_divisions && Object.keys(entry.csi_divisions).length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">CSI Division Breakdown</p>
          <div className="space-y-1">
            {Object.entries(entry.csi_divisions).map(([div, cost]) => (
              <div key={div} className="flex justify-between text-sm">
                <span className="text-gray-600">Division {div}</span>
                <span className="font-medium">{fmt$(cost)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {entry.linked_documents?.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Linked Documents</p>
          <ul className="list-disc list-inside text-sm text-gray-600 space-y-0.5">
            {entry.linked_documents.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-2 pt-2 border-t border-gray-200">
        <button
          onClick={onEdit}
          className="btn-secondary flex items-center gap-1.5 text-xs"
        >
          <Edit3 className="h-3.5 w-3.5" /> Edit
        </button>
        <button
          onClick={onArchive}
          className="btn-secondary flex items-center gap-1.5 text-xs"
        >
          <Archive className="h-3.5 w-3.5" /> Archive
        </button>
        <button
          onClick={onToggleCompare}
          className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
            inCompare
              ? 'bg-apex-600 text-white border-apex-600'
              : 'btn-secondary'
          }`}
        >
          <CheckSquare className="h-3.5 w-3.5" />
          {inCompare ? 'Remove from Compare' : 'Add to Compare'}
        </button>
        {entry.line_item_count != null && (
          <button className="btn-secondary flex items-center gap-1.5 text-xs">
            <FileText className="h-3.5 w-3.5" /> View Line Items
          </button>
        )}
      </div>
    </div>
  );
}

// ── Edit modal ─────────────────────────────────────────────────────────────

function EditModal({ entry, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: entry.name || '',
    description: entry.description || '',
    notes: entry.notes || '',
    tags: entry.tags?.join(', ') || '',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr('');
    try {
      const updated = await updateEstimateLibraryEntry(entry.id, {
        ...form,
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
      });
      onSaved(updated);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">Edit Library Entry</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        {err && <p className="text-red-600 text-sm mb-3">{err}</p>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              className="input w-full"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              className="input w-full"
              rows={3}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
            <textarea
              className="input w-full"
              rows={2}
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tags (comma-separated)</label>
            <input
              className="input w-full"
              value={form.tags}
              onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={saving} className="btn-primary flex items-center gap-2">
              <Save className="h-4 w-4" />
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Compare panel ──────────────────────────────────────────────────────────

function ComparePanel({ ids, entries, onClear }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  const runCompare = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const data = await compareEstimates(ids);
      setResult(data);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [ids]);

  const selected = entries.filter((e) => ids.includes(e.id));

  return (
    <div className="card p-4 mb-6 border-apex-200 bg-apex-50">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-apex-600" />
          <span className="font-semibold text-sm text-apex-800">
            Compare Selected ({ids.length})
          </span>
          <div className="flex gap-1">
            {selected.map((e) => (
              <span key={e.id} className="px-2 py-0.5 bg-white text-apex-700 rounded-full text-xs border border-apex-200">
                {e.name}
              </span>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={runCompare}
            disabled={loading || ids.length < 2}
            className="btn-primary text-xs"
          >
            {loading ? 'Comparing…' : 'Run Comparison'}
          </button>
          <button onClick={onClear} className="btn-secondary text-xs">Clear</button>
        </div>
      </div>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      {result && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-200">
                <th className="pb-2 pr-4">Metric</th>
                {selected.map((e) => (
                  <th key={e.id} className="pb-2 pr-4">{e.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(result).map(([key, vals]) => (
                <tr key={key} className="border-b border-gray-100">
                  <td className="py-1 pr-4 text-gray-500 capitalize">{key.replace(/_/g, ' ')}</td>
                  {selected.map((e) => (
                    <td key={e.id} className="py-1 pr-4 font-medium">
                      {typeof vals === 'object' && vals !== null ? vals[e.id] ?? '—' : String(vals)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Sort header ────────────────────────────────────────────────────────────

function SortTh({ label, field, sortField, sortDir, onSort }) {
  const active = sortField === field;
  return (
    <th
      className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-700 select-none whitespace-nowrap"
      onClick={() => onSort(field)}
    >
      <span className="flex items-center gap-1">
        {label}
        {active ? (
          sortDir === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
        ) : (
          <span className="h-3 w-3" />
        )}
      </span>
    </th>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function EstimateLibraryTab() {
  const [entries, setEntries] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  // Filters
  const [search, setSearch] = useState('');
  const [filterProjectType, setFilterProjectType] = useState('');
  const [filterBuildingType, setFilterBuildingType] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterBidResult, setFilterBidResult] = useState('');
  const [filterState, setFilterState] = useState('');
  const [minCost, setMinCost] = useState('');
  const [maxCost, setMaxCost] = useState('');
  const [minSqft, setMinSqft] = useState('');
  const [maxSqft, setMaxSqft] = useState('');

  // Sort
  const [sortField, setSortField] = useState('');
  const [sortDir, setSortDir] = useState('asc');

  // UI state
  const [expandedId, setExpandedId] = useState(null);
  const [editEntry, setEditEntry] = useState(null);
  const [compareIds, setCompareIds] = useState([]);

  const buildParams = useCallback(() => {
    const p = { page, page_size: PAGE_SIZE };
    if (search) p.search = search;
    if (filterProjectType) p.project_type = filterProjectType;
    if (filterBuildingType) p.building_type = filterBuildingType;
    if (filterStatus) p.status = filterStatus;
    if (filterBidResult) p.bid_result = filterBidResult;
    if (filterState) p.location_state = filterState;
    if (minCost) p.min_cost = minCost;
    if (maxCost) p.max_cost = maxCost;
    if (minSqft) p.min_sqft = minSqft;
    if (maxSqft) p.max_sqft = maxSqft;
    if (sortField) { p.sort_by = sortField; p.sort_dir = sortDir; }
    return p;
  }, [page, search, filterProjectType, filterBuildingType, filterStatus, filterBidResult,
      filterState, minCost, maxCost, minSqft, maxSqft, sortField, sortDir]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getEstimateLibrary(buildParams());
      // Support both paginated { items, total } and plain array
      if (Array.isArray(data)) {
        setEntries(data);
        setTotal(data.length);
      } else {
        setEntries(data?.items ?? []);
        setTotal(data?.total ?? 0);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    getEstimateLibraryStats().then(setStats).catch(() => {});
  }, []);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
    setPage(1);
  };

  const handleSearch = (e) => {
    setSearch(e.target.value);
    setPage(1);
  };

  const handleFilterChange = (setter) => (e) => {
    setter(e.target.value);
    setPage(1);
  };

  const handleArchive = async (entry) => {
    try {
      await updateEstimateLibraryEntry(entry.id, { status: 'archived' });
      loadData();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleToggleCompare = (id) => {
    setCompareIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const sortThProps = { sortField, sortDir, onSort: handleSort };

  return (
    <div>
      <StatsPanel stats={stats} />

      {compareIds.length > 0 && (
        <ComparePanel
          ids={compareIds}
          entries={entries}
          onClear={() => setCompareIds([])}
        />
      )}

      {/* Search + filters */}
      <div className="card p-4 mb-4 space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            className="input w-full pl-9"
            placeholder="Search by name, description, tags…"
            value={search}
            onChange={handleSearch}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <select className="input text-sm" value={filterProjectType} onChange={handleFilterChange(setFilterProjectType)}>
            <option value="">All Project Types</option>
            <option value="commercial">Commercial</option>
            <option value="healthcare">Healthcare</option>
            <option value="industrial">Industrial</option>
            <option value="residential">Residential</option>
            <option value="education">Education</option>
          </select>
          <select className="input text-sm" value={filterBuildingType} onChange={handleFilterChange(setFilterBuildingType)}>
            <option value="">All Building Types</option>
            <option value="office">Office</option>
            <option value="retail">Retail</option>
            <option value="warehouse">Warehouse</option>
            <option value="hospital">Hospital</option>
            <option value="school">School</option>
            <option value="multifamily">Multifamily</option>
          </select>
          <select className="input text-sm" value={filterStatus} onChange={handleFilterChange(setFilterStatus)}>
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="estimating">Estimating</option>
            <option value="bid_submitted">Bid Submitted</option>
            <option value="completed">Completed</option>
            <option value="archived">Archived</option>
          </select>
          <select className="input text-sm" value={filterBidResult} onChange={handleFilterChange(setFilterBidResult)}>
            <option value="">All Bid Results</option>
            <option value="won">Won</option>
            <option value="lost">Lost</option>
            <option value="pending">Pending</option>
          </select>
          <input
            className="input text-sm w-28"
            placeholder="State (e.g. CA)"
            value={filterState}
            onChange={handleFilterChange(setFilterState)}
          />
          <input
            className="input text-sm w-28"
            type="number"
            placeholder="Min Cost $"
            value={minCost}
            onChange={handleFilterChange(setMinCost)}
          />
          <input
            className="input text-sm w-28"
            type="number"
            placeholder="Max Cost $"
            value={maxCost}
            onChange={handleFilterChange(setMaxCost)}
          />
          <input
            className="input text-sm w-28"
            type="number"
            placeholder="Min SF"
            value={minSqft}
            onChange={handleFilterChange(setMinSqft)}
          />
          <input
            className="input text-sm w-28"
            type="number"
            placeholder="Max SF"
            value={maxSqft}
            onChange={handleFilterChange(setMaxSqft)}
          />
        </div>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>}

      {/* Results table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <SortTh label="Name" field="name" {...sortThProps} />
                <SortTh label="Project Type" field="project_type" {...sortThProps} />
                <SortTh label="Sq Ft" field="square_footage" {...sortThProps} />
                <SortTh label="Total Cost" field="total_cost" {...sortThProps} />
                <SortTh label="$/SF" field="cost_per_sqft" {...sortThProps} />
                <SortTh label="Location" field="location_state" {...sortThProps} />
                <SortTh label="Bid Date" field="bid_date" {...sortThProps} />
                <SortTh label="Status" field="status" {...sortThProps} />
                <SortTh label="Bid Result" field="bid_result" {...sortThProps} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-400">Loading…</td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                    No entries found. Try adjusting your filters.
                  </td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <>
                    <tr
                      key={entry.id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                    >
                      <td className="px-3 py-2.5 font-medium text-gray-900 max-w-xs truncate">
                        {entry.name}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600 capitalize">
                        {entry.project_type ?? '—'}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {fmtSF(entry.square_footage)}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {fmt$(entry.total_cost)}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {fmtDollarPerSF(entry.total_cost, entry.square_footage)}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">
                        {entry.location_state ?? '—'}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600 whitespace-nowrap">
                        {entry.bid_date ? new Date(entry.bid_date).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-3 py-2.5 text-gray-600 capitalize">
                        {entry.status ?? '—'}
                      </td>
                      <td className="px-3 py-2.5">
                        {entry.bid_result ? (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${BID_RESULT_STYLES[entry.bid_result] ?? 'bg-gray-100 text-gray-600'}`}>
                            {entry.bid_result}
                          </span>
                        ) : '—'}
                      </td>
                    </tr>
                    {expandedId === entry.id && (
                      <tr key={`${entry.id}-detail`}>
                        <td colSpan={9} className="px-3 py-1">
                          <EntryDetail
                            entry={entry}
                            onClose={() => setExpandedId(null)}
                            onEdit={() => { setEditEntry(entry); setExpandedId(null); }}
                            onArchive={() => handleArchive(entry)}
                            compareIds={compareIds}
                            onToggleCompare={() => handleToggleCompare(entry.id)}
                          />
                        </td>
                      </tr>
                    )}
                  </>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="px-4 py-3 border-t border-gray-200 flex items-center justify-between">
          <span className="text-sm text-gray-500">
            {total} {total === 1 ? 'entry' : 'entries'}
            {totalPages > 1 && ` — page ${page} of ${totalPages}`}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-secondary p-1.5 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="btn-secondary p-1.5 disabled:opacity-40"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {editEntry && (
        <EditModal
          entry={editEntry}
          onClose={() => setEditEntry(null)}
          onSaved={() => { setEditEntry(null); loadData(); }}
        />
      )}
    </div>
  );
}
