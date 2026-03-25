import { useEffect, useState } from 'react';

const POLL_INTERVAL_MS = 60_000;

// Human-readable names for each agent key
const AGENT_LABELS = {
  agent_1_ingestion:        { num: 1, name: 'Document Ingestion' },
  agent_2_spec_parser:      { num: 2, name: 'Spec Parser' },
  agent_3_gap_analysis:     { num: 3, name: 'Gap Analysis' },
  agent_4_quantity_takeoff: { num: 4, name: 'Quantity Takeoff' },
  agent_5_labor_productivity:{ num: 5, name: 'Labor Productivity' },
  agent_6_estimate_summary: { num: 6, name: 'Estimate Assembly' },
  agent_7_improve:          { num: 7, name: 'IMPROVE Feedback' },
};

function providerLabel(provider) {
  if (!provider || provider === 'python') return '—';
  if (provider === 'anthropic') return 'Anthropic';
  if (provider === 'gemini')    return 'Gemini';
  if (provider === 'ollama')    return 'Ollama';
  return provider;
}

function StatusDot({ available, noKey }) {
  const color = noKey
    ? 'bg-yellow-400'
    : available
      ? 'bg-green-400'
      : 'bg-red-500';
  return <span className={`inline-block h-2 w-2 rounded-full flex-shrink-0 ${color}`} />;
}

function agentStatus(agentCfg, providerHealth) {
  const p = agentCfg?.provider;
  if (!p || p === 'python') return { label: 'N/A (Python)', available: true, noKey: false };
  const health = providerHealth?.[p];
  if (!health) return { label: 'unknown', available: false, noKey: false };
  if (!health.api_key_configured) return { label: 'no API key', available: false, noKey: true };
  return {
    label: health.available ? 'connected' : 'error',
    available: health.available,
    noKey: false,
  };
}

export default function LLMStatus() {
  const [status, setStatus] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);
  const [latencyMs, setLatencyMs] = useState(null);
  const [showPanel, setShowPanel] = useState(false);

  const check = async () => {
    const start = Date.now();
    try {
      const resp = await fetch('/api/health/llm');
      const data = await resp.json();
      setLatencyMs(Date.now() - start);
      setStatus(data);
      setLastChecked(new Date());
    } catch {
      setStatus(null);
      setLastChecked(new Date());
    }
  };

  useEffect(() => {
    check();
    const id = setInterval(check, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  // Derive overall availability from the default provider
  const defaultAvailable = status?.default_provider?.available ?? false;
  const defaultProvider = status?.default_provider?.provider ?? 'unknown';

  return (
    <div className="relative">
      <button
        onClick={() => setShowPanel((v) => !v)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-gray-800 hover:bg-gray-700 text-xs transition-colors w-full"
        title="LLM provider status"
      >
        <StatusDot available={defaultAvailable} noKey={false} />
        <span className="text-gray-300 truncate">{providerLabel(defaultProvider)}</span>
      </button>

      {showPanel && (
        <div className="absolute bottom-full left-0 mb-2 w-80 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-50 text-xs text-gray-300 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700 bg-gray-750">
            <span className="font-semibold text-gray-200">Agent LLM Providers</span>
            <div className="flex items-center gap-2 text-gray-500">
              {lastChecked && <span>{lastChecked.toLocaleTimeString()}</span>}
              {latencyMs !== null && <span>{latencyMs}ms</span>}
            </div>
          </div>

          {/* Per-agent table */}
          <table className="w-full">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700">
                <th className="text-left px-3 py-1.5 font-normal">Agent</th>
                <th className="text-left px-2 py-1.5 font-normal">Provider</th>
                <th className="text-left px-2 py-1.5 font-normal">Model</th>
                <th className="text-left px-2 py-1.5 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(AGENT_LABELS).map(([key, { num, name }]) => {
                const cfg = status?.agents?.[key];
                const { label, available, noKey } = agentStatus(cfg, status?.providers);
                const model = cfg?.model ?? '—';
                const provider = cfg?.provider;
                return (
                  <tr key={key} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                    <td className="px-3 py-1.5 whitespace-nowrap">
                      <span className="text-gray-500 mr-1">{num}.</span>{name}
                    </td>
                    <td className="px-2 py-1.5 text-gray-300">{providerLabel(provider)}</td>
                    <td className="px-2 py-1.5 text-gray-400 truncate max-w-[90px]" title={model}>
                      {model === '—' ? '—' : model.length > 16 ? model.slice(0, 14) + '…' : model}
                    </td>
                    <td className="px-2 py-1.5">
                      <span className="flex items-center gap-1">
                        <StatusDot available={available} noKey={noKey} />
                        <span className={
                          noKey ? 'text-yellow-400' :
                          available ? 'text-green-400' : 'text-red-400'
                        }>{label}</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Footer */}
          <div className="flex items-center justify-between px-3 py-2 border-t border-gray-700 text-gray-500">
            <span>
              <span className="inline-block h-2 w-2 rounded-full bg-green-400 mr-1" />connected
              <span className="inline-block h-2 w-2 rounded-full bg-yellow-400 mx-1 ml-3" />no key
              <span className="inline-block h-2 w-2 rounded-full bg-red-500 mx-1 ml-3" />error
            </span>
            <button
              onClick={(e) => { e.stopPropagation(); check(); }}
              className="hover:text-gray-300"
            >
              refresh
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setShowPanel(false); }}
              className="hover:text-gray-300"
            >
              close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
