import { useEffect, useState, useMemo } from 'react';
import { getBenchmarks, getBenchmarkSummary, recomputeBenchmarks } from '../../api';
import { RefreshCw, ChevronUp, ChevronDown } from 'lucide-react';

const CSI_DIVISIONS = [
  '01', '02', '03', '04', '05', '06', '07', '08', '09',
  '10', '11', '12', '13', '14', '21', '22', '23', '25', '26', '27', '28',
  '31', '32', '33', '34', '35', '40', '41', '43', '44', '45', '46', '48',
];

const PROJECT_TYPES = ['all', 'healthcare', 'commercial', 'industrial'];

function SummaryCard({ label, value, sub }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value ?? '—'}</p>
      {sub && <p className="mt-1 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

function ConfidenceBadge({ score }) {
  if (score == null) return <span className="text-gray-400">—</span>;
  const pct = Math.round(score * 100);
  const cls =
    score >= 0.7
      ? 'bg-green-100 text-green-800'
      : score >= 0.5
      ? 'bg-yellow-100 text-yellow-800'
      : 'bg-red-100 text-red-800';
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {pct}%
    </span>
  );
}

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <ChevronUp className="ml-1 inline h-3 w-3 opacity-20" />;
  return sortDir === 'asc' ? (
    <ChevronUp className="ml-1 inline h-3 w-3" />
  ) : (
    <ChevronDown className="ml-1 inline h-3 w-3" />
  );
}

const fmt = (n) =>
  n != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n)
    : '—';

const COLUMNS = [
  { key: 'csi_code', label: 'CSI Code' },
  { key: 'description', label: 'Description' },
  { key: 'avg_unit_cost', label: 'Avg $/Unit' },
  { key: 'min_unit_cost', label: 'Min' },
  { key: 'max_unit_cost', label: 'Max' },
  { key: 'sample_size', label: 'Sample Size' },
  { key: 'confidence_score', label: 'Confidence' },
];

export default function BenchmarkDashboardTab() {
  const [summary, setSummary] = useState(null);
  const [benchmarks, setBenchmarks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);
  const [error, setError] = useState(null);

  const [filterDivision, setFilterDivision] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterRegion, setFilterRegion] = useState('');

  const [sortCol, setSortCol] = useState('csi_code');
  const [sortDir, setSortDir] = useState('asc');

  async function load(params = {}) {
    setLoading(true);
    setError(null);
    try {
      const [sumData, bmData] = await Promise.all([
        getBenchmarkSummary(),
        getBenchmarks(params),
      ]);
      setSummary(sumData);
      setBenchmarks(bmData?.benchmarks ?? []);
    } catch (e) {
      setError(e.message || 'Failed to load benchmarks');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function applyFilters() {
    const params = {};
    if (filterDivision) params.csi_division = filterDivision;
    if (filterType && filterType !== 'all') params.project_type = filterType;
    if (filterRegion.trim()) params.region = filterRegion.trim();
    load(params);
  }

  async function handleRecompute() {
    setRecomputing(true);
    setError(null);
    try {
      await recomputeBenchmarks();
      await load();
    } catch (e) {
      setError(e.message || 'Recompute failed');
    } finally {
      setRecomputing(false);
    }
  }

  function toggleSort(col) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }

  const sorted = useMemo(() => {
    return [...benchmarks].sort((a, b) => {
      const av = a[sortCol] ?? '';
      const bv = b[sortCol] ?? '';
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [benchmarks, sortCol, sortDir]);

  // Summary card values
  const totalBenchmarks = summary?.total_benchmarks ?? 0;
  const divisionCount = summary?.coverage_by_division
    ? Object.keys(summary.coverage_by_division).length
    : 0;
  const divisionCovPct =
    divisionCount > 0 ? Math.round((divisionCount / CSI_DIVISIONS.length) * 100) : 0;
  const avgSample = summary?.avg_sample_size ?? 0;
  const lastComputed = summary?.last_computed_at
    ? new Date(summary.last_computed_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  return (
    <div className="space-y-6 p-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label="Total Benchmarks" value={totalBenchmarks} />
        <SummaryCard
          label="Division Coverage"
          value={`${divisionCovPct}%`}
          sub={`${divisionCount} of ${CSI_DIVISIONS.length} divisions`}
        />
        <SummaryCard
          label="Avg Sample Size"
          value={avgSample.toFixed(1)}
          sub="projects per benchmark"
        />
        <SummaryCard
          label="Last Computed"
          value={lastComputed ?? 'Never'}
        />
      </div>

      {/* Filter Bar + Recompute */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">CSI Division</label>
          <select
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={filterDivision}
            onChange={(e) => setFilterDivision(e.target.value)}
          >
            <option value="">All Divisions</option>
            {CSI_DIVISIONS.map((d) => (
              <option key={d} value={d}>
                Division {d}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Project Type</label>
          <select
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            {PROJECT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Region</label>
          <input
            type="text"
            placeholder="e.g. CA, TX"
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={filterRegion}
            onChange={(e) => setFilterRegion(e.target.value)}
          />
        </div>

        <button
          className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          onClick={applyFilters}
        >
          Apply Filters
        </button>

        <div className="ml-auto">
          <button
            className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            onClick={handleRecompute}
            disabled={recomputing}
          >
            <RefreshCw className={`h-4 w-4 ${recomputing ? 'animate-spin' : ''}`} />
            {recomputing ? 'Recomputing…' : 'Recompute Benchmarks'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
        {loading ? (
          <div className="py-16 text-center text-sm text-gray-400">Loading benchmarks…</div>
        ) : sorted.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">
            No benchmarks found. Try adjusting filters or recompute.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {COLUMNS.map(({ key, label }) => (
                  <th
                    key={key}
                    className="cursor-pointer select-none whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-700"
                    onClick={() => toggleSort(key)}
                  >
                    {label}
                    <SortIcon col={key} sortCol={sortCol} sortDir={sortDir} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sorted.map((b) => (
                <tr key={b.id} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-700">
                    {b.csi_code ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-800">{b.description}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">
                    {fmt(b.avg_unit_cost)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">{fmt(b.min_unit_cost)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">{fmt(b.max_unit_cost)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-center text-gray-700">
                    {b.sample_size}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-center">
                    <ConfidenceBadge score={b.confidence_score} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!loading && sorted.length > 0 && (
        <p className="text-xs text-gray-400">{sorted.length} benchmarks shown</p>
      )}
    </div>
  );
}
