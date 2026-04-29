import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Upload, Target, DollarSign, TrendingUp, ArrowUpDown, Search,
} from 'lucide-react';
import {
  biUploadFile, biGetStats, biGetBenchmarks, biGetHitRate,
  biGetEstimatorPerformance, biGetEstimates,
} from '../../api';

const fmt$ = (v) => (v != null ? `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` : '—');
const fmtPct = (v) => (v != null ? `${v}%` : '—');

const STATUS_COLORS = {
  Awarded: 'text-green-700 bg-green-50',
  Closed: 'text-red-700 bg-red-50',
  Open: 'text-blue-700 bg-blue-50',
};

function HitRateChart({ data, title }) {
  const [rc, setRc] = useState(null);
  useEffect(() => { import('recharts').then(setRc); }, []);
  if (!rc || !data?.length) return null;

  const { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } = rc;
  const chartData = data.map((d) => ({ name: d.group, hitRate: d.hit_rate ?? 0, total: d.total_bids }));

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 36)}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(v) => `${v}%`} />
          <Bar dataKey="hitRate" radius={[0, 4, 4, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={chartData[i].hitRate >= 40 ? '#16a34a' : chartData[i].hitRate >= 20 ? '#ca8a04' : '#dc2626'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function BidIntelligenceTab() {
  const [stats, setStats] = useState(null);
  const [benchmarks, setBenchmarks] = useState(null);
  const [hitBySector, setHitBySector] = useState([]);
  const [hitByEstimator, setHitByEstimator] = useState([]);
  const [estimates, setEstimates] = useState({ estimates: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [sortField, setSortField] = useState('bid_date');
  const [sortDir, setSortDir] = useState('desc');
  const [sectorFilter, setSectorFilter] = useState('');
  const [regionFilter, setRegionFilter] = useState('');

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      biGetStats(),
      biGetBenchmarks(),
      biGetHitRate('market_sector'),
      biGetHitRate('estimator'),
      biGetEstimates({ per_page: 100 }),
    ])
      .then(([s, b, hs, he, est]) => {
        setStats(s);
        setBenchmarks(b);
        setHitBySector(hs || []);
        setHitByEstimator(he || []);
        setEstimates(est || { estimates: [], total: 0 });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Reload benchmarks when filters change
  useEffect(() => {
    const params = {};
    if (sectorFilter) params.market_sector = sectorFilter;
    if (regionFilter) params.region = regionFilter;
    biGetBenchmarks(params).then(setBenchmarks).catch(() => {});
  }, [sectorFilter, regionFilter]);

  const handleFile = async (file) => {
    if (!file || !file.name.endsWith('.xlsx')) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const token = localStorage.getItem('apex_token');
      const form = new FormData();
      form.append('file', file);
      let response;
      try {
        response = await fetch('/api/library/bid-intelligence/upload', {
          method: 'POST',
          body: form,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
      } catch {
        setUploadResult({
          ok: false,
          networkError: true,
          error: `Upload failed to reach the server (network error). The file may be too large for the server to process. Try with a smaller file or contact support.`,
        });
        return;
      }

      let data;
      try {
        data = await response.json();
      } catch {
        data = { ok: false, error: `Server returned status ${response.status} with no JSON body.` };
      }

      if (!response.ok) {
        // 422 with missing_required_columns gets special rendering
        setUploadResult({ ok: false, httpStatus: response.status, ...data });
        return;
      }

      // 200 or 207 — at least some rows loaded
      setUploadResult({ ok: true, httpStatus: response.status, ...data });
      loadData();
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    handleFile(file);
  };

  // Sorted estimates
  const sortedEstimates = useMemo(() => {
    if (!estimates.estimates) return [];
    return [...estimates.estimates].sort((a, b) => {
      const av = a[sortField] ?? '';
      const bv = b[sortField] ?? '';
      if (typeof av === 'number' && typeof bv === 'number')
        return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }, [estimates.estimates, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortField(field); setSortDir('desc'); }
  };

  // Unique sectors/regions for filter dropdowns
  const sectors = useMemo(
    () => [...new Set((estimates.estimates || []).map((e) => e.market_sector).filter(Boolean))].sort(),
    [estimates.estimates],
  );
  const regions = useMemo(
    () => [...new Set((estimates.estimates || []).map((e) => e.region).filter(Boolean))].sort(),
    [estimates.estimates],
  );

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading Bid Intelligence...</div>;

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
          { label: 'Total Bids', value: stats?.total_estimates ?? 0, icon: Target },
          { label: 'Hit Rate', value: fmtPct(stats?.hit_rate), icon: TrendingUp },
          { label: 'Avg Bid Amount', value: fmt$(stats?.avg_bid_amount), icon: DollarSign },
          { label: 'Avg Contract (Awarded)', value: fmt$(stats?.avg_contract_amount), icon: DollarSign },
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
        <div className="flex flex-col items-center py-4 text-center">
          <Upload className="h-8 w-8 text-gray-400 mb-2" />
          <p className="text-gray-600 font-medium">
            {uploading ? 'Uploading...' : 'Drop EstimationHistory .xlsx here'}
          </p>
          <p className="text-sm text-gray-400 mt-1">Reads the Estimating sheet, upserts by Estimate #</p>
          <label className="mt-3 btn-primary cursor-pointer text-sm px-4 py-2">
            Browse Files
            <input
              type="file"
              accept=".xlsx"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
          </label>
        </div>
        {uploadResult && (
          <div className="mt-3 border-t pt-3 text-sm">
            {uploadResult.networkError ? (
              /* 502 / network failure */
              <p className="text-red-600">{uploadResult.error}</p>
            ) : !uploadResult.ok ? (
              /* 422 schema error or 500 */
              <div className="text-red-600">
                {uploadResult.error === 'missing_required_columns' ? (
                  <>
                    <p className="font-medium">Your file is missing these required columns:</p>
                    <ul className="list-disc ml-4 mt-1">
                      {(uploadResult.missing || []).map((c) => <li key={c}>{c}</li>)}
                    </ul>
                    {uploadResult.found_columns?.length > 0 && (
                      <p className="mt-1 text-gray-500 text-xs">
                        Found: {uploadResult.found_columns.join(', ')}
                      </p>
                    )}
                  </>
                ) : (
                  <p>{uploadResult.error || `Upload failed (HTTP ${uploadResult.httpStatus})`}</p>
                )}
              </div>
            ) : uploadResult.skipped > 0 ? (
              /* 207 partial success */
              <div>
                <p className="text-yellow-700 font-medium">
                  Loaded {uploadResult.loaded} of {uploadResult.loaded + uploadResult.skipped} rows.{' '}
                  {uploadResult.skipped} row{uploadResult.skipped !== 1 ? 's' : ''} skipped — see details below.
                </p>
                <ul className="mt-2 space-y-1 max-h-40 overflow-y-auto text-xs text-red-600">
                  {(uploadResult.errors || []).slice(0, 10).map((e, i) => (
                    <li key={i}>Row {e.row ?? '?'}: {e.error}</li>
                  ))}
                </ul>
              </div>
            ) : (
              /* 200 full success */
              <p className="text-green-700">
                Loaded {uploadResult.loaded} rows successfully.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <HitRateChart data={hitBySector} title="Hit Rate by Market Sector" />
        <HitRateChart data={hitByEstimator} title="Hit Rate by Estimator" />
      </div>

      {/* Benchmarks */}
      {benchmarks && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Cost Benchmarks</h3>
            <div className="flex items-center gap-3">
              <select
                className="input text-sm py-1"
                value={sectorFilter}
                onChange={(e) => setSectorFilter(e.target.value)}
              >
                <option value="">All Sectors</option>
                {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <select
                className="input text-sm py-1"
                value={regionFilter}
                onChange={(e) => setRegionFilter(e.target.value)}
              >
                <option value="">All Regions</option>
                {regions.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-gray-500">Avg $/CY</p>
              <p className="text-2xl font-bold text-gray-900">{fmt$(benchmarks.avg_cost_per_cy)}</p>
            </div>
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-gray-500">Avg $/SF</p>
              <p className="text-2xl font-bold text-gray-900">{fmt$(benchmarks.avg_cost_per_sf)}</p>
            </div>
            <div className="p-4 rounded-lg bg-gray-50">
              <p className="text-sm text-gray-500">Hit Rate</p>
              <p className="text-2xl font-bold text-gray-900">{fmtPct(benchmarks.hit_rate)}</p>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-2 text-right">{benchmarks.count} estimates in selection</p>
        </div>
      )}

      {/* Estimates table */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Recent Bids ({estimates.total})</h3>
        {sortedEstimates.length === 0 ? (
          <p className="text-gray-400 text-center py-6">No estimates loaded. Upload a file above.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <SortHeader field="name">Name</SortHeader>
                  <SortHeader field="status">Status</SortHeader>
                  <SortHeader field="bid_amount" className="text-right">Bid Amount</SortHeader>
                  <SortHeader field="contract_amount" className="text-right">Contract</SortHeader>
                  <SortHeader field="estimator">Estimator</SortHeader>
                  <SortHeader field="region">Region</SortHeader>
                  <SortHeader field="market_sector">Sector</SortHeader>
                  <SortHeader field="cost_per_cy" className="text-right">$/CY</SortHeader>
                  <SortHeader field="cost_per_sf" className="text-right">$/SF</SortHeader>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sortedEstimates.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium max-w-[220px] truncate">{r.name}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[r.status] || 'text-gray-500 bg-gray-50'}`}>
                        {r.status || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{fmt$(r.bid_amount)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt$(r.contract_amount)}</td>
                    <td className="px-3 py-2">{r.estimator || '—'}</td>
                    <td className="px-3 py-2">{r.region || '—'}</td>
                    <td className="px-3 py-2">{r.market_sector || '—'}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt$(r.cost_per_cy)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt$(r.cost_per_sf)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
