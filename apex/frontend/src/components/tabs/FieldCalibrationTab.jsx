import { useEffect, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  Search,
  Upload,
  FileSpreadsheet,
  Database,
  Loader2,
} from 'lucide-react';
import { getFieldCalibration, uploadFieldActuals, getFieldActualsStats } from '../../api';

// ── Direction / calibration color config ────────────────────────────

const DIR_CONFIG = {
  optimistic:   { label: 'OPTIMISTIC',   bg: 'bg-red-100',   text: 'text-red-800',   bar: 'bg-red-500'   },
  aligned:      { label: 'ALIGNED',      bg: 'bg-green-100', text: 'text-green-800', bar: 'bg-green-500' },
  conservative: { label: 'CONSERVATIVE', bg: 'bg-blue-100',  text: 'text-blue-800',  bar: 'bg-blue-500'  },
  no_data:      { label: 'NO DATA',      bg: 'bg-gray-100',  text: 'text-gray-600',  bar: 'bg-gray-400'  },
};

const DIR_SORT_ORDER = { optimistic: 0, conservative: 1, aligned: 2, no_data: 3 };

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

function calFactorColor(v) {
  if (v == null) return 'text-gray-400';
  if (v >= 0.90 && v <= 1.10) return 'text-green-600';
  if ((v >= 0.80 && v < 0.90) || (v > 1.10 && v <= 1.20)) return 'text-yellow-600';
  return 'text-red-600';
}

function deltaColor(v) {
  if (v == null) return 'text-gray-400';
  const abs = Math.abs(v);
  if (abs < 5) return 'text-green-600';
  if (abs < 20) return 'text-yellow-600';
  return 'text-red-600';
}

// ── Component ───────────────────────────────────────────────────────

export default function FieldCalibrationTab({ projectId, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState('direction');
  const [sortAsc, setSortAsc] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);

  // Upload section
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [faStats, setFaStats] = useState(null);
  const [projectName, setProjectName] = useState('');
  const [region, setRegion] = useState('');
  const fileRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    setError('');
    Promise.all([
      getFieldCalibration(projectId),
      getFieldActualsStats().catch(() => null),
    ])
      .then(([calData, stats]) => {
        setData(calData);
        setFaStats(stats);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [projectId, refreshKey]);

  // ── Upload handler ──────────────────────────────────────────────
  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg('');
    try {
      const result = await uploadFieldActuals(file, projectName || null, region || null);
      setUploadMsg(`Ingested: ${result.line_items_count || 0} line items from ${result.name || file.name}`);
      // Refresh data
      const [fresh, stats] = await Promise.all([
        getFieldCalibration(projectId),
        getFieldActualsStats().catch(() => null),
      ]);
      setData(fresh);
      setFaStats(stats);
      setProjectName('');
      setRegion('');
    } catch (err) {
      setUploadMsg(`Error: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  // ── Loading / error states ──────────────────────────────────────
  if (loading) return <div className="text-gray-400 py-8 text-center">Loading field calibration...</div>;
  if (error) return <div className="text-red-500 py-8 text-center">{error}</div>;
  if (!data) return null;

  const comps = data.comparisons || [];
  const summary = data.calibration_summary || {};
  const itemsCompared = data.items_compared || 0;
  const withField = data.items_with_field_data || 0;
  const withoutField = data.items_without_field_data || 0;
  const avgCal = data.avg_calibration_factor;

  // Overall direction
  const overallDir = avgCal == null ? 'no_data'
    : avgCal < 0.90 ? 'optimistic'
    : avgCal > 1.10 ? 'conservative'
    : 'aligned';

  const hasNoData = itemsCompared === 0 && (!faStats || faStats.total_projects === 0);

  // ── Empty state ─────────────────────────────────────────────────
  if (hasNoData) {
    return (
      <div className="space-y-6">
        <div className="card flex flex-col items-center justify-center py-16 text-center">
          <Database className="h-16 w-16 text-gray-300 mb-4" />
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No Field Actuals Data Yet</h3>
          <p className="text-gray-500 max-w-lg mb-6">
            Upload WinEst close-out exports from completed projects to enable field calibration.
            The more projects you load, the more accurate calibration becomes.
          </p>
          <input ref={fileRef} type="file" accept=".xlsx,.csv,.xls" className="hidden" onChange={handleUpload} />
          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="btn-primary flex items-center gap-2">
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Close-Out File'}
          </button>
          <p className="text-xs text-gray-400 mt-3">
            Supported: WinEst 26-col/21-col close-out exports, or simple CSV with Activity + Rate columns
          </p>
        </div>
      </div>
    );
  }

  // ── Sorting ────────────────────────────────────────────────────
  const handleSort = (col) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(col === 'direction'); }
  };

  const filtered = comps.filter((c) =>
    c.activity?.toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    switch (sortCol) {
      case 'direction':
        cmp = (DIR_SORT_ORDER[a.calibration_direction] ?? 9) - (DIR_SORT_ORDER[b.calibration_direction] ?? 9);
        break;
      case 'activity':
        cmp = (a.activity || '').localeCompare(b.activity || '');
        break;
      case 'calibration_factor':
        cmp = (a.calibration_factor ?? 0) - (b.calibration_factor ?? 0);
        break;
      case 'est_to_field':
        cmp = Math.abs(b.estimating_to_field_delta_pct ?? 0) - Math.abs(a.estimating_to_field_delta_pct ?? 0);
        break;
      default:
        cmp = 0;
    }
    return sortAsc ? cmp : -cmp;
  });

  const totalDirs = (summary.optimistic || 0) + (summary.aligned || 0) + (summary.conservative || 0) + (summary.no_data || 0);
  const pct = (v) => totalDirs > 0 ? ((v || 0) / totalDirs) * 100 : 0;

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
          <p className="text-sm text-gray-500">Items Compared</p>
          <p className="text-2xl font-bold">{itemsCompared}</p>
          <p className="text-xs text-gray-400 mt-1">{withField} with field data</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">With Field Data</p>
          <p className="text-2xl font-bold text-green-600">{withField}</p>
          <p className="text-xs text-gray-400 mt-1">
            {itemsCompared > 0 ? ((withField / itemsCompared) * 100).toFixed(0) : 0}% coverage
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Avg Calibration Factor</p>
          <p className={`text-2xl font-bold font-mono ${calFactorColor(avgCal)}`}>
            {avgCal != null ? avgCal.toFixed(3) : '—'}
          </p>
          <p className="text-xs text-gray-400 mt-1">1.000 = perfectly aligned</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Overall Calibration</p>
          <div className="mt-1">
            {overallDir !== 'no_data' ? (
              <span className={`inline-flex px-3 py-1 rounded-full text-sm font-medium ${DIR_CONFIG[overallDir].bg} ${DIR_CONFIG[overallDir].text}`}>
                {DIR_CONFIG[overallDir].label}
              </span>
            ) : (
              <span className="text-2xl font-bold text-gray-400">—</span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {overallDir === 'optimistic' ? 'Field is slower than estimates predict'
              : overallDir === 'conservative' ? 'Field is faster — margin opportunity'
              : overallDir === 'aligned' ? 'Estimates match field reality'
              : 'No field data to compare'}
          </p>
        </div>
      </div>

      {/* ── Calibration Distribution Bar ──────────────────────────── */}
      {totalDirs > 0 && (
        <div className="card">
          <p className="text-sm font-medium text-gray-700 mb-3">Calibration Distribution</p>
          <div className="flex h-6 rounded-full overflow-hidden">
            {['optimistic', 'aligned', 'conservative', 'no_data'].map((key) => {
              const p = pct(summary[key]);
              if (p === 0) return null;
              return (
                <div
                  key={key}
                  className={`${DIR_CONFIG[key].bar} transition-all`}
                  style={{ width: `${p}%` }}
                  title={`${DIR_CONFIG[key].label}: ${summary[key]} (${p.toFixed(0)}%)`}
                />
              );
            })}
          </div>
          <div className="flex gap-4 mt-2">
            {['optimistic', 'aligned', 'conservative', 'no_data'].map((key) => (
              <span key={key} className="flex items-center gap-1 text-xs text-gray-500">
                <span className={`inline-block w-2.5 h-2.5 rounded-full ${DIR_CONFIG[key].bar}`} />
                {DIR_CONFIG[key].label}: {summary[key] || 0}
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
            placeholder="Search by activity..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span className="text-sm text-gray-400">{filtered.length} of {comps.length} items</span>
      </div>

      {/* ── Three-Way Comparison Table ────────────────────────────── */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-10">#</th>
                <SortHeader col="activity">Activity</SortHeader>
                <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Unit</th>
                <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Your Rate</th>
                <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Est. Avg</th>
                <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Field Avg</th>
                <SortHeader col="est_to_field" className="text-right">Est&rarr;Field &Delta;%</SortHeader>
                <SortHeader col="calibration_factor" className="text-right">Cal Factor</SortHeader>
                <SortHeader col="direction">Direction</SortHeader>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Projects</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {sorted.map((c) => {
                const dirCfg = DIR_CONFIG[c.calibration_direction] || DIR_CONFIG.no_data;
                const isExpanded = expandedRow === c.line_item_row;
                const projects = c.field_projects || [];
                const projectsStr = projects.length > 0 ? projects.join(', ') : '—';
                const projectsTrunc = projectsStr.length > 25 ? projectsStr.slice(0, 22) + '...' : projectsStr;

                return (
                  <tr key={c.line_item_row} className="group">
                    <td colSpan="11" className="p-0">
                      <div
                        className="flex items-center cursor-pointer hover:bg-gray-50 transition-colors"
                        onClick={() => setExpandedRow(isExpanded ? null : c.line_item_row)}
                      >
                        <div className="px-3 py-2.5 w-10 text-gray-400 text-xs">{c.line_item_row}</div>
                        <div className="px-3 py-2.5 flex-1 font-medium text-gray-800 truncate">{c.activity}</div>
                        <div className="px-3 py-2.5 w-14 text-right text-gray-500">{c.unit || '—'}</div>
                        <div className="px-3 py-2.5 w-20 text-right font-mono">{fmtNum(c.estimator_rate)}</div>
                        <div className="px-3 py-2.5 w-20 text-right font-mono text-gray-500">{fmtNum(c.estimating_avg_rate)}</div>
                        <div className="px-3 py-2.5 w-20 text-right font-mono font-medium">
                          {c.field_avg_rate != null ? fmtNum(c.field_avg_rate) : <span className="text-gray-300">—</span>}
                        </div>
                        <div className={`px-3 py-2.5 w-20 text-right font-mono font-medium ${deltaColor(c.estimating_to_field_delta_pct)}`}>
                          {fmtPct(c.estimating_to_field_delta_pct)}
                        </div>
                        <div className={`px-3 py-2.5 w-20 text-right font-mono font-medium ${calFactorColor(c.calibration_factor)}`}>
                          {c.calibration_factor != null ? c.calibration_factor.toFixed(3) : '—'}
                        </div>
                        <div className="px-3 py-2.5 w-28">
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${dirCfg.bg} ${dirCfg.text}`}>
                            {dirCfg.label}
                          </span>
                        </div>
                        <div className="px-3 py-2.5 w-28 text-xs text-gray-500 truncate" title={projectsStr}>
                          {projectsTrunc}
                        </div>
                        <div className="px-2 py-2.5 w-8">
                          {isExpanded
                            ? <ChevronUp className="h-4 w-4 text-gray-400" />
                            : <ChevronDown className="h-4 w-4 text-gray-300 group-hover:text-gray-400" />
                          }
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="bg-gray-50 border-t border-gray-100 px-6 py-3">
                          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                            <div>
                              <span className="text-gray-400 text-xs">Field Sample Count</span>
                              <p className="font-mono">{c.field_sample_count || 0}</p>
                            </div>
                            <div>
                              <span className="text-gray-400 text-xs">Entered vs Field &Delta;%</span>
                              <p className={`font-mono ${deltaColor(c.entered_to_field_delta_pct)}`}>
                                {fmtPct(c.entered_to_field_delta_pct)}
                              </p>
                            </div>
                            {projects.length > 0 && (
                              <div>
                                <span className="text-gray-400 text-xs">Field Projects</span>
                                <p className="text-gray-700">{projects.join(', ')}</p>
                              </div>
                            )}
                            {c.recommendation && (
                              <div className="md:col-span-3">
                                <span className="text-gray-400 text-xs">Recommendation</span>
                                <p className="text-gray-700">{c.recommendation}</p>
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
                  <td colSpan="11" className="px-4 py-8 text-center text-gray-400">
                    {search ? 'No items match your search.' : 'No comparisons available.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Field Actuals Upload Section (collapsible) ────────────── */}
      <div className="card">
        <button
          className="flex items-center justify-between w-full text-left"
          onClick={() => setShowUpload(!showUpload)}
        >
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Field Actuals Data</span>
            {faStats && (
              <span className="text-xs text-gray-400">
                {faStats.total_projects || 0} projects, {faStats.total_line_items || 0} line items
              </span>
            )}
          </div>
          {showUpload
            ? <ChevronUp className="h-4 w-4 text-gray-400" />
            : <ChevronDown className="h-4 w-4 text-gray-400" />
          }
        </button>

        {showUpload && (
          <div className="mt-4 pt-4 border-t border-gray-100 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                className="input"
                placeholder="Project name (e.g. Riverside Phase 1)"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
              />
              <input
                className="input"
                placeholder="Region (e.g. CCI Southeast Michigan)"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
              />
            </div>
            <input ref={fileRef} type="file" accept=".xlsx,.csv,.xls" className="hidden" onChange={handleUpload} />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="btn-secondary flex items-center gap-2"
            >
              <Upload className="h-4 w-4" />
              {uploading ? 'Uploading...' : 'Upload Close-Out File'}
            </button>
            {uploadMsg && (
              <p className={`text-sm ${uploadMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600'}`}>
                {uploadMsg}
              </p>
            )}
            <p className="text-xs text-gray-400">
              Upload WinEst close-out exports (.xlsx) from completed projects. Same format as estimating exports.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
