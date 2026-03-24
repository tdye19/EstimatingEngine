import { useEffect, useState } from 'react';

const POLL_INTERVAL_MS = 60_000;

export default function LLMStatus() {
  const [status, setStatus] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);
  const [latencyMs, setLatencyMs] = useState(null);
  const [showTooltip, setShowTooltip] = useState(false);

  const check = async () => {
    const start = Date.now();
    try {
      const resp = await fetch('/api/health/llm');
      const data = await resp.json();
      setLatencyMs(Date.now() - start);
      setStatus(data);
      setLastChecked(new Date());
    } catch {
      setStatus({ provider: 'unknown', model: 'unknown', available: false });
      setLastChecked(new Date());
    }
  };

  useEffect(() => {
    check();
    const id = setInterval(check, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  if (!status) return null;

  const providerLabel =
    status.provider === 'anthropic' ? 'Claude API' :
    status.provider === 'ollama'    ? 'Ollama'     :
    status.provider;

  return (
    <div className="relative">
      <button
        onClick={() => setShowTooltip((v) => !v)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-gray-800 hover:bg-gray-700 text-xs transition-colors w-full"
        title="LLM provider status"
      >
        <span
          className={`h-2 w-2 rounded-full flex-shrink-0 ${
            status.available ? 'bg-green-400' : 'bg-red-500'
          }`}
        />
        <span className="text-gray-300 truncate">{providerLabel}</span>
      </button>

      {showTooltip && (
        <div className="absolute bottom-full left-0 mb-2 w-56 bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg z-50 text-xs text-gray-300 space-y-1">
          <div className="flex justify-between">
            <span className="text-gray-400">Provider</span>
            <span>{status.provider}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Model</span>
            <span className="truncate ml-2 text-right">{status.model}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Status</span>
            <span className={status.available ? 'text-green-400' : 'text-red-400'}>
              {status.available ? 'Available' : 'Offline'}
            </span>
          </div>
          {latencyMs !== null && (
            <div className="flex justify-between">
              <span className="text-gray-400">Latency</span>
              <span>{latencyMs}ms</span>
            </div>
          )}
          {lastChecked && (
            <div className="flex justify-between">
              <span className="text-gray-400">Last check</span>
              <span>{lastChecked.toLocaleTimeString()}</span>
            </div>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setShowTooltip(false); }}
            className="mt-1 text-gray-500 hover:text-gray-300 w-full text-center"
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
