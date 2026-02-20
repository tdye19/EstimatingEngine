import { useEffect, useState } from 'react';
import { getAgentLogs } from '../../api';
import { Activity, CheckCircle2, XCircle, Clock, Loader2 } from 'lucide-react';

const STATUS_ICON = {
  completed: { icon: CheckCircle2, color: 'text-green-500' },
  running:   { icon: Loader2,      color: 'text-blue-500 animate-spin' },
  failed:    { icon: XCircle,      color: 'text-red-500' },
  pending:   { icon: Clock,        color: 'text-gray-400' },
};

export default function AgentLogsTab({ projectId }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAgentLogs(projectId)
      .then(setLogs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

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
            return (
              <div key={log.id} className="flex items-start gap-4">
                {/* Timeline connector */}
                <div className="flex flex-col items-center">
                  <div className={`p-1 rounded-full ${st.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  {i < sorted.length - 1 && (
                    <div className="w-0.5 h-8 bg-gray-200 mt-1" />
                  )}
                </div>

                <div className="flex-1 pb-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs text-gray-400 font-mono mr-2">#{log.agent_number}</span>
                      <span className="font-medium">{log.agent_name}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-400">
                      {log.duration_seconds && (
                        <span>{log.duration_seconds.toFixed(1)}s</span>
                      )}
                      {log.tokens_used && (
                        <span>{log.tokens_used.toLocaleString()} tokens</span>
                      )}
                    </div>
                  </div>
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
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((log) => (
              <tr key={log.id} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono text-xs">{log.agent_number}</td>
                <td className="px-4 py-2 font-medium">{log.agent_name}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={log.status} />
                </td>
                <td className="px-4 py-2 text-xs text-gray-400">
                  {log.started_at ? new Date(log.started_at).toLocaleTimeString() : '-'}
                </td>
                <td className="px-4 py-2 text-right">{log.duration_seconds?.toFixed(1)}s</td>
                <td className="px-4 py-2 text-right">{(log.tokens_used || 0).toLocaleString()}</td>
                <td className="px-4 py-2 text-gray-500 max-w-xs truncate">{log.output_summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const cfg = {
    completed: 'badge-success',
    running: 'bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded-full',
    failed: 'badge-critical',
    pending: 'bg-gray-100 text-gray-800 text-xs font-medium px-2.5 py-0.5 rounded-full',
  };
  return <span className={cfg[status] || cfg.pending}>{status}</span>;
}
