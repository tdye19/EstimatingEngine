import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Upload, Database, Activity, ChevronDown, ChevronRight,
  Search, ArrowUpDown, FileSpreadsheet,
} from 'lucide-react';
import { pbUploadFiles, pbGetStats, pbGetRates, pbGetProjects, pbCompareEstimate } from '../../api';

const fmt$ = (v) => (v != null ? `$${v.toFixed(2)}` : '—');
const fmtN = (v) => (v != null ? v.toFixed(2) : '—');

function confidenceColor(count) {
  if (count >= 10) return 'bg-green-50 text-green-800';
  if (count >= 5) return 'bg-yellow-50 text-yellow-800';
  return 'bg-gray-50 text-gray-600';
}

function flagColor(flag) {
  if (flag === 'OK') return 'text-green-700 bg-green-50';
  if (flag === 'REVIEW') return 'text-yellow-700 bg-yellow-50';
  if (flag === 'UPDATE') return 'text-red-700 bg-red-50';
  return 'text-gray-500 bg-gray-50';
}

export default function ProductivityBrainTab({ projectId, estimate }) {
  const [stats, setStats] = useState(null);
  const [rates, setRates] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState('activity');
  const [sortDir, setSortDir] = useState('asc');
  const [showProjects, setShowProjects] = useState(false);
  const [uploadResults, setUploadResults] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [comparison, setComparison] = useState(null);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([pbGetStats(), pbGetRates(), pbGetProjects()])
      .then(([s, r, p]) => {
        setStats(s);
        setRates(r || []);
        setProjects(p || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Compare estimate if available
  useEffect(() => {
    if (!estimate?.line_items?.length) return;
    const items = estimate.line_items
      .filter((li) => li.production_rate || li.productivity_rate)
      .map((li) => ({
        activity: li.description || li.activity,
        rate: li.production_rate || li.productivity_rate,
        unit: li.unit || li.unit_of_measure,
        csi_code: li.csi_code,
      }));
    if (items.length === 0) return;
    pbCompareEstimate(items).then(setComparison).catch(() => {});
  }, [estimate]);

  // Upload handler
  const handleFiles = async (fileList) => {
    const files = Array.from(fileList).filter((f) => f.name.endsWith('.xlsx'));
    if (files.length === 0) return;
    setUploading(true);
    setUploadResults(null);
    try {
      const results = await pbUploadFiles(files);
      setUploadResults(results);
      loadData();
    } catch (err) {
      setUploadResults([{ filename: 'upload', status: 'error', error: err.message }]);
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  // Filtered + sorted rates
  const filteredRates = useMemo(() => {
    let data = rates;
    if (search) {
      const q = search.toLowerCase();
      data = data.filter(
        (r) =>
          (r.activity || '').toLowerCase().includes(q) ||
          (r.unit || '').toLowerCase().includes(q) ||
          (r.crew_trade || '').toLowerCase().includes(q)
      );
    }
    data = [...data].sort((a, b) => {
      const av = a[sortField] ?? '';
      const bv = b[sortField] ?? '';
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return data;
  }, [rates, search, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortField(field); setSortDir('asc'); }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading Productivity Brain...</div>;

  const SortHeader = ({ field, children, className = '' }) => (
    <th
      className={`px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none ${className}`}
      onClick={() => toggleSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {sortField === field && <ArrowUpDown className="h-3 w-3" />}
      </span>
    </th>
  );

  return (
    <div className="space-y-6">
      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Projects', value: stats?.total_projects ?? 0, icon: Database },
          { label: 'Line Items', value: (stats?.total_line_items ?? 0).toLocaleString(), icon: FileSpreadsheet },
          { label: 'Activities', value: stats?.total_activities ?? 0, icon: Activity },
          { label: 'Last Updated', value: stats?.last_ingested ? new Date(stats.last_ingested).toLocaleDateString() : 'Never', icon: Upload },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="card flex items-center gap-4">
            <div className="p-2 rounded-lg bg-apex-50">
              <Icon className="h-5 w-5 text-apex-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">{label}</p>
              <p className="text-xl font-semibold">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Upload zone */}
      <div
        className={`card border-2 border-dashed transition-colors ${
          dragOver ? 'border-apex-400 bg-apex-50' : 'border-gray-300'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <div className="flex flex-col items-center py-6 text-center">
          <Upload className="h-8 w-8 text-gray-400 mb-2" />
          <p className="text-gray-600 font-medium">
            {uploading ? 'Uploading...' : 'Drop WinEst .xlsx files here'}
          </p>
          <p className="text-sm text-gray-400 mt-1">
            Supports CCI Civil Est Report, CCI Estimate Report, and averaged-rates formats (up to 50 files)
          </p>
          <label className="mt-3 btn-primary cursor-pointer text-sm px-4 py-2">
            Browse Files
            <input
              type="file"
              accept=".xlsx"
              multiple
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </label>
        </div>

        {uploadResults && (
          <div className="mt-4 border-t pt-4 space-y-1">
            {uploadResults.map((r, i) => (
              <div
                key={i}
                className={`text-sm flex items-center gap-2 px-3 py-1.5 rounded ${
                  r.status === 'ingested'
                    ? 'bg-green-50 text-green-700'
                    : r.status === 'skipped'
                    ? 'bg-yellow-50 text-yellow-700'
                    : 'bg-red-50 text-red-700'
                }`}
              >
                <span className="font-medium">{r.filename}</span>
                <span>
                  {r.status === 'ingested'
                    ? `${r.line_items} line items ingested`
                    : r.status === 'skipped'
                    ? `Skipped (${r.reason})`
                    : r.error || 'Error'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Rates table */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Production Rates</h3>
          <div className="relative">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="input pl-9 w-64"
              placeholder="Search activities..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {filteredRates.length === 0 ? (
          <p className="text-gray-400 text-center py-6">
            {rates.length === 0 ? 'No rates loaded yet. Upload WinEst files above.' : 'No matching activities.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <SortHeader field="activity">Activity</SortHeader>
                  <SortHeader field="unit">Unit</SortHeader>
                  <SortHeader field="crew_trade">Crew</SortHeader>
                  <SortHeader field="avg_rate" className="text-right">Avg Rate</SortHeader>
                  <SortHeader field="min_rate" className="text-right">Min</SortHeader>
                  <SortHeader field="max_rate" className="text-right">Max</SortHeader>
                  <SortHeader field="spread" className="text-right">Spread</SortHeader>
                  <SortHeader field="project_count" className="text-right">Projects</SortHeader>
                  <SortHeader field="avg_labor_cost_per_unit" className="text-right">Labor $/Unit</SortHeader>
                  <SortHeader field="avg_material_cost_per_unit" className="text-right">Material $/Unit</SortHeader>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredRates.map((r, i) => (
                  <tr key={i} className={`hover:bg-gray-50 ${confidenceColor(r.project_count)}`}>
                    <td className="px-3 py-2 font-medium">{r.activity}</td>
                    <td className="px-3 py-2">{r.unit || '—'}</td>
                    <td className="px-3 py-2">{r.crew_trade || '—'}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtN(r.avg_rate)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtN(r.min_rate)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtN(r.max_rate)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtN(r.spread)}</td>
                    <td className="px-3 py-2 text-right">{r.project_count}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt$(r.avg_labor_cost_per_unit)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt$(r.avg_material_cost_per_unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Estimate comparison */}
      {comparison && comparison.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Estimate vs Historical Rates</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Activity</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Estimate Rate</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Historical Avg</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Delta %</th>
                  <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">Flag</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Samples</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {comparison.map((r, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium">{r.activity}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtN(r.estimate_rate)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtN(r.historical_avg)}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {r.delta_pct != null ? `${r.delta_pct > 0 ? '+' : ''}${r.delta_pct}%` : '—'}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${flagColor(r.flag)}`}>
                        {r.flag}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">{r.sample_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Projects list */}
      {projects.length > 0 && (
        <div className="card">
          <button
            className="flex items-center gap-2 w-full text-left"
            onClick={() => setShowProjects(!showProjects)}
          >
            {showProjects ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <h3 className="text-lg font-semibold">Ingested Projects ({projects.length})</h3>
          </button>

          {showProjects && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">File</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Format</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Line Items</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Projects</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Ingested</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {projects.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-medium">{p.name}</td>
                      <td className="px-3 py-2">
                        <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-600 text-xs">
                          {p.format_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">{p.total_line_items}</td>
                      <td className="px-3 py-2 text-right">{p.project_count}</td>
                      <td className="px-3 py-2">{p.ingested_at ? new Date(p.ingested_at).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
