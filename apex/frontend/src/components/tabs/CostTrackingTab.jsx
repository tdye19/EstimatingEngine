import { useEffect, useState, lazy, Suspense, memo } from 'react';
import { getProjectTokenUsage, getTokenUsageSummary } from '../../api';
import { DollarSign, Zap, RefreshCw, Database } from 'lucide-react';

const CostBarChart = lazy(() => import('../charts/CostBarChart'));

const AGENT_COLORS = {
  2: '#3b82f6',   // blue  — Spec Parser
  3: '#f59e0b',   // amber — Gap Analysis
  4: '#10b981',   // green — Quantity Takeoff
  5: '#8b5cf6',   // purple — Labor Productivity
  6: '#ef4444',   // red   — Estimate Assembly
  7: '#ec4899',   // pink  — IMPROVE Feedback
};

function fmtCost(val) {
  if (!val) return '$0.000000';
  return '$' + Number(val).toFixed(6);
}

function fmtTokens(n) {
  return Number(n || 0).toLocaleString();
}

const CostTrackingTab = memo(function CostTrackingTab({ projectId, refreshKey }) {
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    Promise.all([
      getProjectTokenUsage(projectId),
      getTokenUsageSummary(projectId),
    ])
      .then(([recs, sum]) => {
        setRecords(recs || []);
        setSummary(sum || null);
      })
      .catch((err) => setError(err.message || 'Failed to load cost data'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [projectId, refreshKey]);

  if (loading) {
    return <div className="text-gray-400 py-8 text-center">Loading cost data...</div>;
  }

  if (error) {
    return (
      <div className="text-red-500 py-8 text-center">
        {error}
        <button onClick={load} className="ml-3 btn-secondary text-sm">
          Retry
        </button>
      </div>
    );
  }

  const totalCost = summary?.total_cost ?? 0;
  const byAgent = summary?.by_agent ?? [];
  const byProvider = summary?.by_provider ?? [];
  const chartData = byAgent.map((a) => ({
    name: a.agent_name,
    cost: a.total_cost,
    agent_number: a.agent_number,
  }));

  return (
    <div className="space-y-6">
      {/* ── Total cost hero ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-apex-200 bg-apex-50 p-5 sm:col-span-1">
          <div className="flex items-center gap-3">
            <DollarSign className="h-8 w-8 text-apex-600" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-apex-500">
                Total Pipeline Cost
              </p>
              <p className="text-3xl font-bold text-apex-700">{fmtCost(totalCost)}</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-center gap-3">
            <Zap className="h-6 w-6 text-blue-500" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                Total Tokens
              </p>
              <p className="text-2xl font-bold text-gray-800">
                {fmtTokens((summary?.total_input_tokens ?? 0) + (summary?.total_output_tokens ?? 0))}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {fmtTokens(summary?.total_input_tokens ?? 0)} in &nbsp;/&nbsp;
                {fmtTokens(summary?.total_output_tokens ?? 0)} out
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-center gap-3">
            <RefreshCw className="h-6 w-6 text-purple-500" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                LLM Calls
              </p>
              <p className="text-2xl font-bold text-gray-800">
                {summary?.total_calls ?? 0}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {byProvider.map((p) => p.provider).join(', ') || '—'}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-green-200 bg-green-50 p-5">
          <div className="flex items-center gap-3">
            <Database className="h-6 w-6 text-green-600" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-green-600">
                Cache Savings
              </p>
              <p className="text-2xl font-bold text-green-700">
                {fmtCost(summary?.cache_savings ?? 0)}
              </p>
              <p className="text-xs text-green-500 mt-0.5">
                {fmtTokens(summary?.total_cache_read_tokens ?? 0)} tokens from cache
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Cost by agent bar chart ──────────────────────────────────────── */}
      {chartData.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Cost by Agent</h3>
          <Suspense fallback={<div className="text-gray-400 text-center py-8">Loading chart...</div>}>
            <CostBarChart chartData={chartData} />
          </Suspense>
        </div>
      )}

      {/* ── Provider summary ────────────────────────────────────────────── */}
      {byProvider.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Cost by Provider</h3>
          <div className="divide-y divide-gray-100">
            {byProvider.map((p) => (
              <div key={p.provider} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <span className="font-medium capitalize text-gray-800">{p.provider}</span>
                  <span className="ml-2 text-gray-400 text-xs">{p.call_count} calls</span>
                </div>
                <div className="text-right">
                  <span className="font-mono text-gray-700">{fmtCost(p.total_cost)}</span>
                  <span className="ml-3 text-gray-400 text-xs">
                    {fmtTokens(p.input_tokens + p.output_tokens)} tok
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Detailed call log table ──────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">LLM Call Log</h3>
          <span className="text-xs text-gray-400">{records.length} records</span>
        </div>

        {records.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">
            No LLM calls recorded yet. Run the agent pipeline to see cost data.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left">
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Agent
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Provider
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">
                    Input
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">
                    Output
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">
                    Cost
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Cache
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Time
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {records.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-800">
                      <span
                        className="inline-block w-2 h-2 rounded-full mr-2"
                        style={{ backgroundColor: AGENT_COLORS[r.agent_number] || '#9ca3af' }}
                      />
                      {r.agent_name}
                    </td>
                    <td className="px-4 py-3 capitalize text-gray-600">{r.provider}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500 max-w-[180px] truncate">
                      {r.model}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 tabular-nums">
                      {fmtTokens(r.input_tokens)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 tabular-nums">
                      {fmtTokens(r.output_tokens)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700 tabular-nums">
                      {fmtCost(r.estimated_cost)}
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap">
                      {r.cache_read_tokens > 0 ? (
                        <span className="text-green-600 font-medium">
                          HIT ({fmtTokens(r.cache_read_tokens)})
                        </span>
                      ) : (
                        <span className="text-gray-400">MISS</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                      {r.created_at
                        ? new Date(r.created_at).toLocaleString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
});

export default CostTrackingTab;
