import { useEffect, useRef, useState } from 'react';
import {
  Scale,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  Search,
  Upload,
  FileSpreadsheet,
  TrendingUp,
  TrendingDown,
  Minus,
  Loader2,
} from 'lucide-react';
import { getRateIntelligence, uploadDocument } from '../../api';

// ── Flag / confidence color config ──────────────────────────────────

const FLAG_CONFIG = {
  OK:      { label: 'OK',      bg: 'bg-green-100',  text: 'text-green-800',  bar: 'bg-green-500'  },
  REVIEW:  { label: 'REVIEW',  bg: 'bg-yellow-100', text: 'text-yellow-800', bar: 'bg-yellow-500' },
  UPDATE:  { label: 'UPDATE',  bg: 'bg-red-100',    text: 'text-red-800',    bar: 'bg-red-500'    },
  NO_DATA: { label: 'NO DATA', bg: 'bg-gray-100',   text: 'text-gray-600',   bar: 'bg-gray-400'   },
};

const CONFIDENCE_DOT = {
  high:   'bg-green-500',
  medium: 'bg-yellow-500',
  low:    'bg-red-400',
  none:   'bg-gray-300',
};

const FLAG_SORT_ORDER = { UPDATE: 0, REVIEW: 1, OK: 2, NO_DATA: 3 };

// ── Helpers ─────────────────────────────────────────────────────────

function fmtNum(v, decimals = 2) {
  if (v == null) return '—';
  return Number(v).toFixed(decimals);
}

function fmtPct(v) {
  if (v == null) return '—';
  const n = Number(v);
  const prefix = n > 0 ? '+' : '';
  return `${prefix}${n.toFixed(1)}%`;
}

function deltaColor(v) {
  if (v == null) return 'text-gray-400';
  const abs = Math.abs(v);
  if (abs < 5) return 'text-green-600';
  if (abs < 20) return 'text-yellow-600';
  return 'text-red-600';
}

// ── Component ───────────────────────────────────────────────────────

export default function RateIntelligenceTab({ projectId, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState('flag');
  const [sortAsc, setSortAsc] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    setError('');
    getRateIntelligence(projectId)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [projectId, refreshKey]);

  // ── Upload handler ──────────────────────────────────────────────
  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadDocument(projectId, file);
      // Re-fetch after upload
      const fresh = await getRateIntelligence(projectId);
      setData(fresh);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  // ── Loading / error states ──────────────────────────────────────
  if (loading) return <div className="text-gray-400 py-8 text-center">Loading rate intelligence...</div>;
  if (error) return <div className="text-red-500 py-8 text-center">{error}</div>;
  if (!data) return null;

  const recs = data.recommendations || [];
  const flags = data.flags_summary || {};
  const totalParsed = data.takeoff_items_parsed || 0;
  const matched = data.items_matched || 0;
  const unmatched = data.items_unmatched || 0;
  const optimism = data.overall_optimism_score;
  const flaggedCount = (flags.REVIEW || 0) + (flags.UPDATE || 0);

  // ── Empty state — no takeoff uploaded ───────────────────────────
  if (totalParsed === 0 && recs.length === 0) {
    return (
      <div className="space-y-6">
        <div className="card flex flex-col items-center justify-center py-16 text-center">
          <FileSpreadsheet className="h-16 w-16 text-gray-300 mb-4" />
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No Takeoff Data Yet</h3>
          <p className="text-gray-500 max-w-md mb-6">
            Upload your WinEst takeoff export (.xlsx) to get rate intelligence on every line item.
            We'll match your rates against historical Productivity Brain data.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.csv,.xls"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="btn-primary flex items-center gap-2"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Takeoff File'}
          </button>
          <p className="text-xs text-gray-400 mt-3">
            Supported: WinEst 26-col, 21-col exports, or simple CSV with Activity + Qty columns
          </p>
        </div>
      </div>
    );
  }

  // ── Sorting ────────────────────────────────────────────────────
  const handleSort = (col) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(col === 'flag'); // flag defaults asc (UPDATE first)
    }
  };

  const filtered = recs.filter((r) =>
    r.activity?.toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    switch (sortCol) {
      case 'flag':
        cmp = (FLAG_SORT_ORDER[a.flag] ?? 9) - (FLAG_SORT_ORDER[b.flag] ?? 9);
        break;
      case 'activity':
        cmp = (a.activity || '').localeCompare(b.activity || '');
        break;
      case 'delta_pct':
        cmp = Math.abs(b.delta_pct ?? 0) - Math.abs(a.delta_pct ?? 0);
        break;
      case 'estimator_rate':
        cmp = (a.estimator_rate ?? 0) - (b.estimator_rate ?? 0);
        break;
      case 'historical_avg_rate':
        cmp = (a.historical_avg_rate ?? 0) - (b.historical_avg_rate ?? 0);
        break;
      case 'sample_count':
        cmp = (a.sample_count ?? 0) - (b.sample_count ?? 0);
        break;
      default:
        cmp = 0;
    }
    return sortAsc ? cmp : -cmp;
  });

  const totalFlags = (flags.OK || 0) + (flags.REVIEW || 0) + (flags.UPDATE || 0) + (flags.NO_DATA || 0);
  const pct = (v) => (totalFlags > 0 ? ((v || 0) / totalFlags) * 100 : 0);

  // ── Column header helper ────────────────────────────────────────
  const SortHeader = ({ col, children, className = '' }) => (
    <th
      className={`px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700 ${className}`}
      onClick={() => handleSort(col)}
    >
      <span className="flex items-center gap-1">
        {children}
        <ArrowUpDown className="h-3 w-3 opacity-40" />
      </span>
    </th>
  );

  return (
    <div className="space-y-6">
      {/* ── Summary Cards ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-sm text-gray-500">Total Items</p>
          <p className="text-2xl font-bold">{totalParsed}</p>
          <p className="text-xs text-gray-400 mt-1">{data.parse_format || 'auto'} format</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Matched</p>
          <p className="text-2xl font-bold text-green-600">{matched}</p>
          <p className="text-xs text-gray-400 mt-1">
            {totalParsed > 0 ? ((matched / totalParsed) * 100).toFixed(0) : 0}% of items
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Flagged for Review</p>
          <p className="text-2xl font-bold text-yellow-600">{flaggedCount}</p>
          <p className="text-xs text-gray-400 mt-1">
            {flags.REVIEW || 0} review + {flags.UPDATE || 0} update
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Optimism Score</p>
          <div className="flex items-center gap-2">
            <p className={`text-2xl font-bold ${optimism == null ? 'text-gray-400' : optimism > 0 ? 'text-red-500' : 'text-green-600'}`}>
              {optimism != null ? fmtPct(optimism) : '—'}
            </p>
            {optimism != null && (
              optimism > 0
                ? <TrendingUp className="h-5 w-5 text-red-400" />
                : optimism < 0
                  ? <TrendingDown className="h-5 w-5 text-green-500" />
                  : <Minus className="h-5 w-5 text-gray-400" />
            )}
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {optimism == null ? 'No matched data' : optimism > 0 ? 'More optimistic than history' : 'More conservative than history'}
          </p>
        </div>
      </div>

      {/* ── Flag Distribution Bar ────────────────────────────────── */}
      {totalFlags > 0 && (
        <div className="card">
          <p className="text-sm font-medium text-gray-700 mb-3">Flag Distribution</p>
          <div className="flex h-6 rounded-full overflow-hidden">
            {['OK', 'REVIEW', 'UPDATE', 'NO_DATA'].map((key) => {
              const p = pct(flags[key]);
              if (p === 0) return null;
              return (
                <div
                  key={key}
                  className={`${FLAG_CONFIG[key].bar} transition-all`}
                  style={{ width: `${p}%` }}
                  title={`${FLAG_CONFIG[key].label}: ${flags[key]} (${p.toFixed(0)}%)`}
                />
              );
            })}
          </div>
          <div className="flex gap-4 mt-2">
            {['OK', 'REVIEW', 'UPDATE', 'NO_DATA'].map((key) => (
              <span key={key} className="flex items-center gap-1 text-xs text-gray-500">
                <span className={`inline-block w-2.5 h-2.5 rounded-full ${FLAG_CONFIG[key].bar}`} />
                {FLAG_CONFIG[key].label}: {flags[key] || 0}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Search ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            className="input w-full pl-9"
            placeholder="Search by activity name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span className="text-sm text-gray-400">
          {filtered.length} of {recs.length} items
        </span>
      </div>

      {/* ── Recommendations Table ────────────────────────────────── */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-10">#</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">WBS</th>
                <SortHeader col="activity">Activity</SortHeader>
                <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Unit</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Crew</th>
                <SortHeader col="estimator_rate" className="text-right">Your Rate</SortHeader>
                <SortHeader col="historical_avg_rate" className="text-right">Hist Avg</SortHeader>
                <SortHeader col="delta_pct" className="text-right">&Delta;%</SortHeader>
                <SortHeader col="flag">Flag</SortHeader>
                <SortHeader col="sample_count">Confidence</SortHeader>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Projects</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {sorted.map((r) => {
                const flagCfg = FLAG_CONFIG[r.flag] || FLAG_CONFIG.NO_DATA;
                const confDot = CONFIDENCE_DOT[r.confidence] || CONFIDENCE_DOT.none;
                const isExpanded = expandedRow === r.line_item_row;
                const projects = r.matching_projects || [];
                const projectsStr = projects.length > 0 ? projects.join(', ') : '—';
                const projectsTrunc = projectsStr.length > 30 ? projectsStr.slice(0, 27) + '...' : projectsStr;

                return (
                  <tr key={r.line_item_row} className="group">
                    <td colSpan="12" className="p-0">
                      {/* Main row */}
                      <div
                        className="flex items-center cursor-pointer hover:bg-gray-50 transition-colors"
                        onClick={() => setExpandedRow(isExpanded ? null : r.line_item_row)}
                      >
                        <div className="px-3 py-2.5 w-10 text-gray-400 text-xs">{r.line_item_row}</div>
                        <div className="px-3 py-2.5 w-24 text-gray-500 truncate">{r.wbs_area || '—'}</div>
                        <div className="px-3 py-2.5 flex-1 font-medium text-gray-800 truncate">{r.activity}</div>
                        <div className="px-3 py-2.5 w-16 text-right text-gray-500">{r.unit || '—'}</div>
                        <div className="px-3 py-2.5 w-20 text-gray-500 truncate">{r.crew || '—'}</div>
                        <div className="px-3 py-2.5 w-20 text-right font-mono">{fmtNum(r.estimator_rate)}</div>
                        <div className="px-3 py-2.5 w-20 text-right font-mono text-gray-500">{fmtNum(r.historical_avg_rate)}</div>
                        <div className={`px-3 py-2.5 w-16 text-right font-mono font-medium ${deltaColor(r.delta_pct)}`}>
                          {fmtPct(r.delta_pct)}
                        </div>
                        <div className="px-3 py-2.5 w-20">
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${flagCfg.bg} ${flagCfg.text}`}>
                            {flagCfg.label}
                          </span>
                        </div>
                        <div className="px-3 py-2.5 w-24 flex items-center gap-1.5">
                          <span className={`inline-block w-2 h-2 rounded-full ${confDot}`} />
                          <span className="text-gray-600 text-xs capitalize">{r.confidence}</span>
                          <span className="text-gray-400 text-xs">({r.sample_count})</span>
                        </div>
                        <div className="px-3 py-2.5 w-32 text-xs text-gray-500 truncate" title={projectsStr}>
                          {projectsTrunc}
                        </div>
                        <div className="px-2 py-2.5 w-8">
                          {isExpanded
                            ? <ChevronUp className="h-4 w-4 text-gray-400" />
                            : <ChevronDown className="h-4 w-4 text-gray-300 group-hover:text-gray-400" />
                          }
                        </div>
                      </div>

                      {/* Expanded detail */}
                      {isExpanded && (
                        <div className="bg-gray-50 border-t border-gray-100 px-6 py-3">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                            <div>
                              <span className="text-gray-400 text-xs">Min Rate</span>
                              <p className="font-mono">{fmtNum(r.historical_min_rate)}</p>
                            </div>
                            <div>
                              <span className="text-gray-400 text-xs">Max Rate</span>
                              <p className="font-mono">{fmtNum(r.historical_max_rate)}</p>
                            </div>
                            <div>
                              <span className="text-gray-400 text-xs">Spread (Std Dev)</span>
                              <p className="font-mono">{fmtNum(r.historical_spread)}</p>
                            </div>
                            <div>
                              <span className="text-gray-400 text-xs">Sample Count</span>
                              <p className="font-mono">{r.sample_count}</p>
                            </div>
                            <div>
                              <span className="text-gray-400 text-xs">Labor $/Unit</span>
                              <p className="font-mono">{r.labor_cost_per_unit != null ? `$${fmtNum(r.labor_cost_per_unit)}` : '—'}</p>
                            </div>
                            <div>
                              <span className="text-gray-400 text-xs">Material $/Unit</span>
                              <p className="font-mono">{r.material_cost_per_unit != null ? `$${fmtNum(r.material_cost_per_unit)}` : '—'}</p>
                            </div>
                            {projects.length > 0 && (
                              <div className="md:col-span-2">
                                <span className="text-gray-400 text-xs">Matching Projects</span>
                                <p className="text-gray-700">{projects.join(', ')}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan="12" className="px-4 py-8 text-center text-gray-400">
                    {search ? 'No items match your search.' : 'No recommendations available.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
