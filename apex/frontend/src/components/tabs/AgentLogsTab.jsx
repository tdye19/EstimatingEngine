import { useEffect, useState, memo } from 'react';
import { getAgentLogs, runAgent } from '../../api';
import { Activity, CheckCircle2, XCircle, Clock, Loader2, RotateCcw } from 'lucide-react';

const STATUS_ICON = {
  completed: { icon: CheckCircle2, color: 'text-green-500' },
  running:   { icon: Loader2,      color: 'text-blue-500 animate-spin' },
  failed:    { icon: XCircle,      color: 'text-red-500' },
  pending:   { icon: Clock,        color: 'text-gray-400' },
};

/** Returns "llm" | "regex" | null from a log's output_data */
function getParseMethod(log) {
  return log?.output_data?.parse_method ?? null;
}

function ParseMethodBadge({ method }) {
  if (!method) return null;
  if (method === 'llm') {
    return (
      <span className="ml-2 bg-blue-100 text-blue-700 text-xs font-medium px-2 py-0.5 rounded-full">
        LLM
      </span>
    );
  }
  return (
    <span className="ml-2 bg-gray-100 text-gray-600 text-xs font-medium px-2 py-0.5 rounded-full">
      Regex
    </span>
  );
}

const AgentLogsTab = memo(function AgentLogsTab({ projectId, onAgentComplete }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rerunning, setRerunning] = useState({}); // { [agentNumber]: true }
  const [rerunMsg, setRerunMsg] = useState({});   // { [agentNumber]: 'message' }

  const fetchLogs = () =>
    getAgentLogs(projectId)
      .then((data) => setLogs(data || []))
      .catch(() => {});

  useEffect(() => {
    fetchLogs().finally(() => setLoading(false));
  }, [projectId]);

  const handleRerun = async (agentNumber) => {
    setRerunning((prev) => ({ ...prev, [agentNumber]: true }));
    setRerunMsg((prev) => ({ ...prev, [agentNumber]: '' }));
    try {
      const result = await runAgent(projectId, agentNumber);
      setRerunMsg((prev) => ({ ...prev, [agentNumber]: `Completed in ${result?.duration_seconds?.toFixed(1) ?? '?'}s` }));
      await fetchLogs();
      onAgentComplete?.(agentNumber);
    } catch (err) {
      setRerunMsg((prev) => ({ ...prev, [agentNumber]: `Error: ${err.message}` }));
    } finally {
      setRerunning((prev) => ({ ...prev, [agentNumber]: false }));
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading agent logs...</div>;
  if (!logs.length) return <div className="text-gray-400 py-8 text-center">No agent runs recorded.</div>;

  const sorted = [...logs].sort((a, b) => a.agent_number - b.agent_number);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Activity className="h-4 w-4" />
        {logs.length} agent runs
      </div>

      {/* Pipeline timeline */}
      <div className="card">
        <h3 className="text-sm font-semibold mb-4">Agent Pipeline</h3>
        <div className="space-y-4">
          {sorted.map((log, i) => {
            const st = STATUS_ICON[log.status] || STATUS_ICON.pending;
            const Icon = st.icon;
            const isRunning = rerunning[log.agent_number];
            const msg = rerunMsg[log.agent_number];
            const parseMethod = getParseMethod(log);
            return (
              <div key={log.id} className="flex items-start gap-4">
                {/* Timeline connector */}
                <div className="flex flex-col items-center">
                  <div className={`p-1 rounded-full ${isRunning ? 'text-blue-500' : st.color}`}>
                    {isRunning ? <Loader2 className="h-5 w-5 animate-spin" /> : <Icon className="h-5 w-5" />}
                  </div>
                  {i < sorted.length - 1 && (
                    <div className="w-0.5 h-8 bg-gray-200 mt-1" />
                  )}
                </div>

                <div className="flex-1 pb-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center flex-wrap">
                      <span className="text-xs text-gray-400 font-mono mr-2">#{log.agent_number}</span>
                      <span className="font-medium">{log.agent_name}</span>
                      <ParseMethodBadge method={parseMethod} />
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-400">
                      {log.duration_seconds && (
                        <span>{log.duration_seconds.toFixed(1)}s</span>
                      )}
                      {log.tokens_used && (
                        <span>{log.tokens_used.toLocaleString()} tokens</span>
                      )}
                      <button
                        onClick={() => handleRerun(log.agent_number)}
                        disabled={isRunning}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-500 hover:text-apex-600 hover:bg-apex-50 border border-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        title={`Re-run Agent ${log.agent_number}`}
                      >
                        {isRunning
                          ? <Loader2 className="h-3 w-3 animate-spin" />
                          : <RotateCcw className="h-3 w-3" />
                        }
                        {isRunning ? 'Running...' : 'Re-run'}
                      </button>
                    </div>
                  </div>
                  {msg && (
                    <p className={`text-xs mt-1 ${msg.startsWith('Error') ? 'text-red-600' : 'text-green-600'}`}>{msg}</p>
                  )}
                  {log.output_summary && (
                    <p className="text-sm text-gray-500 mt-1">{log.output_summary}</p>
                  )}
                  {log.error_message && (
                    <p className="text-sm text-red-600 mt-1">{log.error_message}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Table view */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Started</th>
              <th className="px-4 py-3 text-right">Duration</th>
              <th className="px-4 py-3 text-right">Tokens</th>
              <th className="px-4 py-3">Output</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((log) => {
              const isRunning = rerunning[log.agent_number];
              const parseMethod = getParseMethod(log);
              return (
                <tr key={log.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 font-mono text-xs">{log.agent_number}</td>
                  <td className="px-4 py-2 font-medium">
                    {log.agent_name}
                    <ParseMethodBadge method={parseMethod} />
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={isRunning ? 'running' : log.status} />
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-400">
                    {log.started_at ? new Date(log.started_at).toLocaleTimeString() : '-'}
                  </td>
                  <td className="px-4 py-2 text-right">{log.duration_seconds?.toFixed(1)}s</td>
                  <td className="px-4 py-2 text-right">{(log.tokens_used || 0).toLocaleString()}</td>
                  <td className="px-4 py-2 text-gray-500 max-w-xs truncate">{log.output_summary}</td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => handleRerun(log.agent_number)}
                      disabled={isRunning}
                      className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-500 hover:text-apex-600 hover:bg-apex-50 border border-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {isRunning
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <RotateCcw className="h-3 w-3" />
                      }
                      {isRunning ? 'Running...' : 'Re-run'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
});

export default AgentLogsTab;

function StatusBadge({ status }) {
  const cfg = {
    completed: 'badge-success',
    running: 'bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded-full',
    failed: 'badge-critical',
    pending: 'bg-gray-100 text-gray-800 text-xs font-medium px-2.5 py-0.5 rounded-full',
  };
  return <span className={cfg[status] || cfg.pending}>{status}</span>;
}
