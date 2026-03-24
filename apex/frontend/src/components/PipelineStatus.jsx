import { useEffect, useRef, useState } from 'react';
import { getPipelineStatus } from '../api';
import { CheckCircle2, XCircle, Clock, Loader2, SkipForward } from 'lucide-react';

const AGENT_LABELS = [
  'Ingestion',
  'Spec Parser',
  'Gap Analysis',
  'Takeoff',
  'Labor',
  'Estimate',
];

function StepIcon({ status }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case 'failed':
      return <XCircle className="h-5 w-5 text-red-500" />;
    case 'running':
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
    case 'skipped':
      return <SkipForward className="h-5 w-5 text-gray-300" />;
    default:
      return <Clock className="h-5 w-5 text-gray-300" />;
  }
}

function stepBg(status) {
  switch (status) {
    case 'completed': return 'bg-green-50 border-green-200';
    case 'failed':    return 'bg-red-50 border-red-200';
    case 'running':   return 'bg-blue-50 border-blue-200';
    case 'skipped':   return 'bg-gray-50 border-gray-200';
    default:          return 'bg-white border-gray-200';
  }
}

function fmtDuration(seconds) {
  if (seconds == null) return null;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
}

export default function PipelineStatus({ projectId, onComplete }) {
  const [agents, setAgents] = useState([]);
  const [overall, setOverall] = useState('pending');
  const [active, setActive] = useState(false);
  const pollRef = useRef(null);

  const fetchStatus = async () => {
    try {
      const data = await getPipelineStatus(projectId);
      if (!data) return;
      setAgents(data.agents || []);
      setOverall(data.overall || 'pending');

      const isDone = data.overall === 'completed' || data.overall === 'failed';
      if (isDone) {
        stopPolling();
        if (data.overall === 'completed') onComplete?.();
      }
    } catch {
      // ignore transient errors
    }
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setActive(false);
  };

  // Start polling when component mounts or projectId changes
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 3000);
    setActive(true);
    return () => stopPolling();
  }, [projectId]);

  // Don't render when all agents are still pending (no pipeline has run yet)
  const hasActivity = agents.some((a) => a.status !== 'pending');
  if (!hasActivity) return null;

  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Pipeline Status</h3>
        {overall === 'running' && (
          <span className="flex items-center gap-1.5 text-xs text-blue-600">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Running…
          </span>
        )}
        {overall === 'completed' && (
          <span className="text-xs font-medium text-green-600">All agents complete</span>
        )}
        {overall === 'failed' && (
          <span className="text-xs font-medium text-red-600">Pipeline stopped</span>
        )}
      </div>

      {/* Horizontal step bar */}
      <div className="flex items-start gap-2 overflow-x-auto pb-1">
        {agents.map((agent, idx) => (
          <div key={agent.agent_number} className="flex flex-1 flex-col items-center min-w-[80px]">
            {/* Connector line (left side) */}
            <div className="flex w-full items-center">
              <div className={`h-0.5 flex-1 ${idx === 0 ? 'invisible' : agent.status === 'completed' ? 'bg-green-300' : 'bg-gray-200'}`} />
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 ${stepBg(agent.status)}`}
                   title={agent.error_message || ''}>
                <StepIcon status={agent.status} />
              </div>
              <div className={`h-0.5 flex-1 ${idx === agents.length - 1 ? 'invisible' : agent.status === 'completed' ? 'bg-green-300' : 'bg-gray-200'}`} />
            </div>

            {/* Label */}
            <p className={`mt-1 text-center text-xs leading-tight ${
              agent.status === 'completed' ? 'text-green-700 font-medium'
              : agent.status === 'failed' ? 'text-red-600 font-medium'
              : agent.status === 'running' ? 'text-blue-600 font-medium'
              : agent.status === 'skipped' ? 'text-gray-400 italic'
              : 'text-gray-400'
            }`}>
              {AGENT_LABELS[idx] || agent.agent_name}
            </p>

            {/* Duration */}
            {agent.duration_seconds != null && (
              <p className="text-center text-[10px] text-gray-400">
                {fmtDuration(agent.duration_seconds)}
              </p>
            )}

            {/* Error tooltip (visible on hover via title attr above; also show truncated below) */}
            {agent.status === 'failed' && agent.error_message && (
              <p className="mt-0.5 max-w-[80px] truncate text-center text-[10px] text-red-400"
                 title={agent.error_message}>
                {agent.error_message}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
