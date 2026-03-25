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

function fmtMs(ms) {
  if (ms == null) return null;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
}

function fmtDuration(seconds) {
  if (seconds == null) return null;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
}

/** Derive overall status from an agent list (mirrors backend logic). */
function deriveOverall(agentList) {
  const statuses = agentList.map((a) => a.status);
  if (statuses.some((s) => s === 'running')) return 'running';
  if (statuses.some((s) => s === 'failed'))  return 'failed';
  if (statuses.every((s) => s === 'completed' || s === 'skipped')) return 'completed';
  if (statuses.every((s) => s === 'pending')) return 'pending';
  return 'pending';
}

/**
 * Normalise a WebSocket broadcast message into the same agent shape used by
 * the polling endpoint so applyUpdate() can handle both sources uniformly.
 *
 * WS broadcasts use agent_number / agent_name (matches REST API).
 * duration_ms (ms precision) is added by the orchestrator; the REST API uses
 * duration_seconds.  We keep both so the display can use whichever is present.
 */
function normalizeWsMessage(msg) {
  const agents = (msg.agents || []).map((a) => ({
    agent_number:     a.agent_number ?? a.number,
    agent_name:       a.agent_name   ?? a.name,
    status:           a.status,
    started_at:       a.started_at ?? null,
    // REST gives duration_seconds; WS gives duration_ms — keep both
    duration_seconds: a.duration_seconds ?? (a.duration_ms != null ? a.duration_ms / 1000 : null),
    duration_ms:      a.duration_ms ?? null,
    error_message:    a.error_message ?? null,
    output_summary:   a.output_summary ?? null,
  }));
  return {
    agents,
    overall: msg.overall ?? msg.status ?? deriveOverall(agents),
  };
}

export default function PipelineStatus({ projectId, onComplete }) {
  const [agents, setAgents]         = useState([]);
  const [overall, setOverall]       = useState('pending');
  const [connMode, setConnMode]     = useState(null);   // 'ws' | 'poll' | null
  const [liveElapsedMs, setLiveMs]  = useState(0);

  // Keep a stable ref to onComplete so the effect closure never goes stale
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    // ── Mutable state local to this effect (no re-render triggers needed) ──
    let destroyed     = false;
    let ws            = null;
    let pollTimer     = null;
    let liveTimer     = null;
    let heartbeat     = null;
    let runningAgentNum  = null;   // which agent number is currently "running"
    let runningAgentStart = null;  // its start timestamp (ms)

    // ── Live timer helpers ──────────────────────────────────────────────────
    function startLiveTimer(startMs) {
      clearInterval(liveTimer);
      liveTimer = setInterval(() => {
        setLiveMs(Date.now() - startMs);
      }, 200);
    }
    function stopLiveTimer() {
      clearInterval(liveTimer);
      liveTimer = null;
      setLiveMs(0);
    }

    // ── Apply a status update from any source ───────────────────────────────
    function applyUpdate(data) {
      if (destroyed) return;

      const newAgents  = data.agents || [];
      const newOverall = data.overall || deriveOverall(newAgents);

      setAgents(newAgents);
      setOverall(newOverall);

      // Live timer — track elapsed time for the currently-running agent
      const runningAgent = newAgents.find((a) => a.status === 'running');
      if (runningAgent) {
        const agentNum = runningAgent.agent_number ?? runningAgent.number;
        if (agentNum !== runningAgentNum) {
          // A new agent has started running — reset the timer
          runningAgentNum   = agentNum;
          runningAgentStart = runningAgent.started_at
            ? new Date(runningAgent.started_at).getTime()
            : Date.now();
          startLiveTimer(runningAgentStart);
        }
      } else {
        runningAgentNum = null;
        stopLiveTimer();
      }

      // Stop polling once the pipeline is terminal
      if (newOverall === 'completed' || newOverall === 'failed') {
        clearInterval(pollTimer);
        pollTimer = null;
        if (newOverall === 'completed') onCompleteRef.current?.();
      }
    }

    // ── Polling fallback ────────────────────────────────────────────────────
    async function fetchStatus() {
      try {
        const data = await getPipelineStatus(projectId);
        if (data) applyUpdate(data);
      } catch {
        // ignore transient errors — next poll will retry
      }
    }

    function startPolling() {
      clearInterval(pollTimer);
      fetchStatus();
      pollTimer = setInterval(fetchStatus, 3000);
      if (!destroyed) setConnMode('poll');
    }

    // ── WebSocket primary connection ────────────────────────────────────────
    function connectWs() {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url   = `${proto}//${window.location.host}/ws/pipeline/${projectId}`;

      try {
        ws = new WebSocket(url);
      } catch {
        // WebSocket not supported or immediate failure — go straight to polling
        startPolling();
        return;
      }

      // Client-side heartbeat: send "ping" every 30 s to keep NAT tables alive
      heartbeat = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send('ping');
      }, 30000);

      ws.onopen = () => {
        if (!destroyed) setConnMode('ws');
      };

      ws.onmessage = (evt) => {
        if (destroyed) return;
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'ping') return;  // server keepalive — ignore

          if (msg.type === 'pipeline_update') {
            applyUpdate(normalizeWsMessage(msg));
          } else if (msg.type === 'pipeline_complete') {
            applyUpdate({ ...normalizeWsMessage(msg), overall: 'completed' });
            ws?.close(1000, 'pipeline complete');
          } else if (msg.type === 'pipeline_error') {
            applyUpdate({ ...normalizeWsMessage(msg), overall: 'failed' });
          }
        } catch {
          // non-JSON or unexpected frame — ignore
        }
      };

      ws.onerror = () => {
        if (destroyed) return;
        // Connection failed (proxy not configured, server down, etc.)
        // Fall back to the polling mechanism.
        clearInterval(heartbeat);
        heartbeat = null;
        ws = null;
        startPolling();
      };

      ws.onclose = () => {
        clearInterval(heartbeat);
        heartbeat = null;
        // If we were in WS mode and the close wasn't triggered by us, clear
        // the indicator.  If we switched to polling, leave 'poll' in place.
        if (!destroyed) {
          setConnMode((prev) => (prev === 'ws' ? null : prev));
        }
      };
    }

    // ── Boot sequence ───────────────────────────────────────────────────────
    // 1. Attempt WebSocket
    connectWs();
    // 2. Immediately fetch HTTP snapshot so there's no blank state while the
    //    WS handshake is completing.
    fetchStatus();

    // ── Cleanup ─────────────────────────────────────────────────────────────
    return () => {
      destroyed = true;
      ws?.close();
      clearInterval(pollTimer);
      clearInterval(liveTimer);
      clearInterval(heartbeat);
    };
  }, [projectId]);  // re-run only when the project changes

  // ── Don't render until the pipeline has actually started ─────────────────
  const hasActivity = agents.some((a) => a.status !== 'pending');
  if (!hasActivity) return null;

  const runningAgent = agents.find((a) => a.status === 'running');

  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Pipeline Status</h3>

        <div className="flex items-center gap-3">
          {/* Connection mode indicator */}
          <span className="flex items-center gap-1 text-[10px] text-gray-400">
            <span
              className={`h-2 w-2 rounded-full ${
                connMode === 'ws'   ? 'bg-green-400' :
                connMode === 'poll' ? 'bg-yellow-400' :
                'bg-gray-300'
              }`}
            />
            {connMode === 'ws'   && 'Live'}
            {connMode === 'poll' && 'Polling'}
          </span>

          {overall === 'running' && (
            <span className="flex items-center gap-1.5 text-xs text-blue-600">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {runningAgent
                ? `${AGENT_LABELS[(runningAgent.agent_number ?? 1) - 1]} · ${fmtMs(liveElapsedMs)}`
                : 'Running…'}
            </span>
          )}
          {overall === 'completed' && (
            <span className="text-xs font-medium text-green-600">All agents complete</span>
          )}
          {overall === 'failed' && (
            <span className="text-xs font-medium text-red-600">Pipeline stopped</span>
          )}
        </div>
      </div>

      {/* Horizontal step bar */}
      <div className="flex items-start gap-2 overflow-x-auto pb-1">
        {agents.map((agent, idx) => (
          <div key={agent.agent_number} className="flex flex-1 flex-col items-center min-w-[80px]">
            {/* Connector lines + circle */}
            <div className="flex w-full items-center">
              <div
                className={`h-0.5 flex-1 ${
                  idx === 0 ? 'invisible' : agent.status === 'completed' ? 'bg-green-300' : 'bg-gray-200'
                }`}
              />
              <div
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 ${stepBg(agent.status)}`}
                title={agent.error_message || ''}
              >
                <StepIcon status={agent.status} />
              </div>
              <div
                className={`h-0.5 flex-1 ${
                  idx === agents.length - 1 ? 'invisible' : agent.status === 'completed' ? 'bg-green-300' : 'bg-gray-200'
                }`}
              />
            </div>

            {/* Label */}
            <p className={`mt-1 text-center text-xs leading-tight ${
              agent.status === 'completed' ? 'text-green-700 font-medium'
              : agent.status === 'failed'  ? 'text-red-600 font-medium'
              : agent.status === 'running' ? 'text-blue-600 font-medium'
              : agent.status === 'skipped' ? 'text-gray-400 italic'
              : 'text-gray-400'
            }`}>
              {AGENT_LABELS[idx] || agent.agent_name}
            </p>

            {/* Duration — live timer while running, static once done */}
            {agent.status === 'running' && (
              <p className="text-center text-[10px] text-blue-400">
                {fmtMs(liveElapsedMs)}
              </p>
            )}
            {agent.status !== 'running' && (agent.duration_ms != null || agent.duration_seconds != null) && (
              <p className="text-center text-[10px] text-gray-400">
                {agent.duration_ms != null
                  ? fmtMs(agent.duration_ms)
                  : fmtDuration(agent.duration_seconds)}
              </p>
            )}

            {/* Error snippet */}
            {agent.status === 'failed' && agent.error_message && (
              <p
                className="mt-0.5 max-w-[80px] truncate text-center text-[10px] text-red-400"
                title={agent.error_message}
              >
                {agent.error_message}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
