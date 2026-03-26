import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ScatterChart, Scatter, ResponsiveContainer,
} from 'recharts';
import { TrendingUp, Building2, DollarSign, Filter } from 'lucide-react';
import { getBenchmarkProjects, getDivisionTrends } from '../api';

const FMT = (v) => (v === null || v === undefined ? '—' : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
const FMT_PSF = (v) => (v === null || v === undefined ? '—' : `$${Number(v).toFixed(2)}/SF`);

export default function BenchmarkingPage() {
  const [projects, setProjects] = useState([]);
  const [stats, setStats] = useState({});
  const [trends, setTrends] = useState({});
  const [loading, setLoading] = useState(true);
  const [projectType, setProjectType] = useState('');

  const load = (type) => {
    setLoading(true);
    Promise.all([
      getBenchmarkProjects(type ? { project_type: type } : {}),
      getDivisionTrends(type ? { project_type: type } : {}),
    ])
      .then(([bm, tr]) => {
        setProjects(bm?.projects || []);
        setStats(bm?.stats || {});
        setTrends(tr?.division_trends || {});
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(projectType); }, [projectType]);

  // Chart data: cost per SF per project
  const scatterData = projects
    .filter((p) => p.square_footage && p.cost_per_sf)
    .map((p) => ({ name: p.project_number, sf: p.square_footage, cost_per_sf: p.cost_per_sf }));

  // Division trend chart
  const divChartData = Object.entries(trends).map(([div, t]) => ({
    division: div,
    avg_pct: t.avg_pct,
    min_pct: t.min_pct,
    max_pct: t.max_pct,
  }));

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-apex-600" />
            Multi-Project Benchmarking
          </h1>
          <p className="text-gray-500 mt-1">
            Compare cost patterns across projects to build institutional pricing knowledge.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-400" />
          <select
            className="input"
            value={projectType}
            onChange={(e) => setProjectType(e.target.value)}
          >
            <option value="">All Types</option>
            <option value="commercial">Commercial</option>
            <option value="healthcare">Healthcare</option>
            <option value="industrial">Industrial</option>
            <option value="residential">Residential</option>
            <option value="education">Education</option>
          </select>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading benchmarks...</p>
      ) : (
        <>
          {/* Stats row */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Projects Analyzed" value={stats.project_count ?? '—'} icon={Building2} />
            <StatCard label="Avg Cost / SF" value={FMT_PSF(stats.avg_cost_per_sf)} icon={DollarSign} />
            <StatCard label="Min Cost / SF" value={FMT_PSF(stats.min_cost_per_sf)} icon={DollarSign} color="text-green-600" />
            <StatCard label="Max Cost / SF" value={FMT_PSF(stats.max_cost_per_sf)} icon={DollarSign} color="text-red-600" />
          </div>

          {/* Project table */}
          {projects.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-100">
                <h2 className="font-semibold">Project Cost Comparison</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                    <tr>
                      <th className="px-4 py-3 text-left">Project</th>
                      <th className="px-4 py-3 text-left">Type</th>
                      <th className="px-4 py-3 text-right">Sq Ft</th>
                      <th className="px-4 py-3 text-right">Total Bid</th>
                      <th className="px-4 py-3 text-right">$/SF</th>
                      <th className="px-4 py-3 text-right">Labor</th>
                      <th className="px-4 py-3 text-right">Materials</th>
                      <th className="px-4 py-3 text-left">Bid Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {projects.map((p) => (
                      <tr key={p.project_id} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="font-medium">{p.project_name}</div>
                          <div className="text-xs text-gray-400 font-mono">{p.project_number}</div>
                        </td>
                        <td className="px-4 py-3 capitalize text-gray-600">{p.project_type}</td>
                        <td className="px-4 py-3 text-right font-mono">{(p.square_footage || 0).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right font-mono font-semibold">{FMT(p.total_bid_amount)}</td>
                        <td className="px-4 py-3 text-right font-mono">{FMT_PSF(p.cost_per_sf)}</td>
                        <td className="px-4 py-3 text-right text-gray-600">{FMT(p.total_labor_cost)}</td>
                        <td className="px-4 py-3 text-right text-gray-600">{FMT(p.total_material_cost)}</td>
                        <td className="px-4 py-3 text-gray-500">{p.bid_date || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Division trend chart */}
          {divChartData.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h2 className="font-semibold mb-4">Average Cost Distribution by CSI Division</h2>
              <p className="text-sm text-gray-500 mb-4">
                Each bar shows the average % of total bid cost allocated to that division across all projects.
              </p>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={divChartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="division" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => `${v.toFixed(0)}%`} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
                  <Legend />
                  <Bar dataKey="avg_pct" name="Avg %" fill="#1e40af" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="min_pct" name="Min %" fill="#93c5fd" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="max_pct" name="Max %" fill="#60a5fa" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {projects.length === 0 && (
            <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
              <TrendingUp className="h-12 w-12 mx-auto mb-4 text-gray-300" />
              <p className="font-medium text-lg">No projects to benchmark yet</p>
              <p className="text-sm mt-2">
                Once you have multiple projects with completed estimates, comparison data will appear here.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color = 'text-gray-900' }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-4 w-4 text-gray-400" />
        <p className="text-xs text-gray-500 font-medium">{label}</p>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
