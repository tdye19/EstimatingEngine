import { useState, useEffect, useCallback } from 'react';

const fmt = (val) =>
  val != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val)
    : '—';

const EXAMPLE_CSV = `CIP Concrete Foundation,120,CY,03 30 00
Formwork — Foundation,3600,SF,03 10 00
Rebar — Foundations,4.2,TON,03 20 00
Excavation — Machine,450,CY,31 23 00
Backfill,280,CY,31 23 00
Vapor Barrier,14000,SF,07 26 00`;

const CONFIDENCE_COLORS = {
  high: 'bg-green-900/40 text-green-300 border border-green-700',
  medium: 'bg-yellow-900/40 text-yellow-300 border border-yellow-700',
  low: 'bg-orange-900/40 text-orange-300 border border-orange-700',
  very_low: 'bg-red-900/40 text-red-300 border border-red-700',
};

const SEVERITY_COLORS = {
  low: 'bg-blue-900/40 text-blue-300',
  medium: 'bg-yellow-900/40 text-yellow-300',
  high: 'bg-orange-900/40 text-orange-300',
  critical: 'bg-red-900/40 text-red-300',
};

const SUB_TABS = ['Context & Quantities', 'Estimate Lines', 'Commercial', 'Risk'];

export default function DecisionEstimateTab({ projectId }) {
  const [subTab, setSubTab] = useState('Context & Quantities');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Context form
  const [ctx, setCtx] = useState({
    project_type: '', market_sector: '', region: '',
    delivery_method: '', contract_type: '', complexity_level: '', schedule_pressure: '',
    size_sf: '', scope_types: '',
  });
  const [ctxSaving, setCtxSaving] = useState(false);
  const [ctxMsg, setCtxMsg] = useState('');

  // Quantities CSV
  const [csvText, setCsvText] = useState(EXAMPLE_CSV);

  // Results
  const [lines, setLines] = useState([]);
  const [summary, setSummary] = useState(null);
  const [costBreakdown, setCostBreakdown] = useState(null);
  const [riskItems, setRiskItems] = useState([]);

  // Override state
  const [overrideOpen, setOverrideOpen] = useState(null); // line id
  const [overrideVal, setOverrideVal] = useState('');
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideSaving, setOverrideSaving] = useState(false);

  const loadExistingLines = useCallback(async () => {
    try {
      const r = await fetch(`/api/projects/${projectId}/estimate-lines`);
      if (r.ok) setLines(await r.json());
      const cb = await fetch(`/api/projects/${projectId}/cost-breakdown`);
      if (cb.ok) setCostBreakdown(await cb.json());
      const ri = await fetch(`/api/projects/${projectId}/risk-items`);
      if (ri.ok) setRiskItems(await ri.json());
    } catch (_) {}
  }, [projectId]);

  useEffect(() => { loadExistingLines(); }, [loadExistingLines]);

  // --- Save context ---
  const saveContext = async () => {
    setCtxSaving(true); setCtxMsg('');
    try {
      const body = {};
      Object.entries(ctx).forEach(([k, v]) => { if (v !== '') body[k] = v === '' ? null : v; });
      if (body.size_sf) body.size_sf = parseFloat(body.size_sf);
      const r = await fetch(`/api/projects/${projectId}/context`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await r.text());
      setCtxMsg('Context saved.');
    } catch (e) {
      setCtxMsg(`Error: ${e.message}`);
    } finally {
      setCtxSaving(false);
    }
  };

  // --- Parse CSV and run estimate ---
  const runEstimate = async () => {
    setLoading(true); setError(null);
    try {
      const quantities = csvText.trim().split('\n')
        .filter(l => l.trim() && !l.startsWith('#'))
        .map(l => {
          const [description, quantity, unit, division_code] = l.split(',').map(s => s.trim());
          return { description, quantity: parseFloat(quantity) || 0, unit, division_code };
        })
        .filter(q => q.description && q.quantity > 0);

      if (!quantities.length) { setError('No valid quantities in CSV.'); setLoading(false); return; }

      const r = await fetch(`/api/projects/${projectId}/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantities }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setLines(data.estimate_lines || []);
      setSummary({
        direct_cost: data.direct_cost,
        final_bid_value: data.final_bid_value,
        line_count: data.line_count,
        needs_review_count: data.needs_review_count,
        low_confidence_count: data.low_confidence_count,
      });
      setCostBreakdown({ buckets: data.cost_breakdown });
      setRiskItems(data.risk_items || []);
      setSubTab('Estimate Lines');
    } catch (e) {
      setError(`Failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  // --- Override ---
  const applyOverride = async (lineId) => {
    setOverrideSaving(true);
    try {
      const r = await fetch(`/api/estimate-lines/${lineId}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          overridden_value: parseFloat(overrideVal),
          override_type: 'unit_cost',
          reason_text: overrideReason,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      setOverrideOpen(null); setOverrideVal(''); setOverrideReason('');
      await loadExistingLines();
    } catch (e) {
      alert(`Override failed: ${e.message}`);
    } finally {
      setOverrideSaving(false);
    }
  };

  const SELECT_CLS = 'bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 w-full';
  const LABEL_CLS = 'block text-xs text-gray-400 mb-1';

  return (
    <div className="p-4 space-y-4">
      {/* Sub-tab nav */}
      <div className="flex gap-1 border-b border-gray-700 pb-2">
        {SUB_TABS.map(t => (
          <button key={t} onClick={() => setSubTab(t)}
            className={`px-3 py-1.5 rounded-t text-sm font-medium transition-colors ${
              subTab === t
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
            }`}>
            {t}
          </button>
        ))}
      </div>

      {/* ── CONTEXT & QUANTITIES ── */}
      {subTab === 'Context & Quantities' && (
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-gray-300 mb-3">Project Context</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                ['project_type', 'Project Type', ['industrial','commercial','institutional','healthcare','education','data_center','infrastructure']],
                ['market_sector', 'Market Sector', ['energy','mission_critical','healthcare','education','commercial','government']],
                ['region', 'Region', ['michigan','midwest','southeast','northeast','southwest','northwest']],
                ['delivery_method', 'Delivery Method', ['cmar','design_build','hard_bid','negotiated']],
                ['contract_type', 'Contract Type', ['self_perform','subcontract','hybrid']],
                ['complexity_level', 'Complexity', ['low','medium','high']],
                ['schedule_pressure', 'Schedule Pressure', ['low','medium','high']],
              ].map(([key, label, opts]) => (
                <div key={key}>
                  <label className={LABEL_CLS}>{label}</label>
                  <select className={SELECT_CLS} value={ctx[key]}
                    onChange={e => setCtx(p => ({ ...p, [key]: e.target.value }))}>
                    <option value="">— select —</option>
                    {opts.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              ))}
              <div>
                <label className={LABEL_CLS}>Size (SF)</label>
                <input type="number" className={SELECT_CLS} placeholder="e.g. 25000"
                  value={ctx.size_sf}
                  onChange={e => setCtx(p => ({ ...p, size_sf: e.target.value }))} />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <button onClick={saveContext} disabled={ctxSaving}
                className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded disabled:opacity-50">
                {ctxSaving ? 'Saving…' : 'Save Context'}
              </button>
              {ctxMsg && <span className="text-xs text-gray-400">{ctxMsg}</span>}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-gray-300 mb-2">
              Quantities CSV <span className="text-gray-500 font-normal">(description, qty, unit, division_code)</span>
            </h3>
            <textarea
              className="w-full h-44 bg-gray-800 border border-gray-600 rounded p-3 text-sm text-gray-200 font-mono resize-y"
              value={csvText} onChange={e => setCsvText(e.target.value)} />
            {error && <p className="text-red-400 text-sm mt-1">{error}</p>}
            <button onClick={runEstimate} disabled={loading}
              className="mt-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded disabled:opacity-50 flex items-center gap-2">
              {loading && <span className="animate-spin">⟳</span>}
              {loading ? 'Running Estimate…' : 'Run Estimate'}
            </button>
          </div>
        </div>
      )}

      {/* ── ESTIMATE LINES ── */}
      {subTab === 'Estimate Lines' && (
        <div className="space-y-3">
          {summary && (
            <div className="flex flex-wrap gap-4 p-3 bg-gray-800 rounded text-sm">
              <span className="text-gray-400">Direct Total: <span className="text-white font-bold">{fmt(summary.direct_cost)}</span></span>
              <span className="text-gray-400">Lines: <span className="text-white">{summary.line_count}</span></span>
              <span className="text-gray-400">Needs Review: <span className="text-yellow-400">{summary.needs_review_count}</span></span>
              <span className="text-gray-400">Low Confidence: <span className="text-orange-400">{summary.low_confidence_count}</span></span>
              {summary.final_bid_value && (
                <span className="text-gray-400 ml-auto">Final Bid: <span className="text-green-400 font-bold">{fmt(summary.final_bid_value)}</span></span>
              )}
            </div>
          )}

          {lines.length === 0 ? (
            <p className="text-gray-500 text-sm">No estimate lines yet. Run an estimate from Context & Quantities.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="text-xs text-gray-400 border-b border-gray-700">
                    {['Work Item','Qty','Unit','Unit Cost','Total','Basis','p25','p50','p75','n','Confidence','Override'].map(h => (
                      <th key={h} className="px-2 py-2 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lines.map(line => (
                    <>
                      <tr key={line.id}
                        className={`border-b border-gray-800 hover:bg-gray-800/50 ${line.needs_review ? 'bg-yellow-950/20' : ''}`}>
                        <td className="px-2 py-2 max-w-[180px] truncate text-gray-200" title={line.description}>{line.description}</td>
                        <td className="px-2 py-2 text-gray-300">{line.quantity}</td>
                        <td className="px-2 py-2 text-gray-400">{line.unit || '—'}</td>
                        <td className="px-2 py-2 text-gray-200">{fmt(line.recommended_unit_cost)}</td>
                        <td className="px-2 py-2 text-gray-200 font-medium">{fmt(line.recommended_total_cost)}</td>
                        <td className="px-2 py-2 text-gray-500 text-xs">{line.pricing_basis}</td>
                        <td className="px-2 py-2 text-gray-400">{line.benchmark_p25 != null ? fmt(line.benchmark_p25) : '—'}</td>
                        <td className="px-2 py-2 text-blue-300">{line.benchmark_p50 != null ? fmt(line.benchmark_p50) : '—'}</td>
                        <td className="px-2 py-2 text-gray-400">{line.benchmark_p75 != null ? fmt(line.benchmark_p75) : '—'}</td>
                        <td className="px-2 py-2 text-gray-400">{line.benchmark_sample_size ?? '—'}</td>
                        <td className="px-2 py-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${CONFIDENCE_COLORS[line.confidence_level] || CONFIDENCE_COLORS.very_low}`}>
                            {line.confidence_level}
                          </span>
                        </td>
                        <td className="px-2 py-2">
                          <button onClick={() => { setOverrideOpen(overrideOpen === line.id ? null : line.id); setOverrideVal(''); setOverrideReason(''); }}
                            className="text-xs px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300">
                            Override
                          </button>
                        </td>
                      </tr>
                      {overrideOpen === line.id && (
                        <tr key={`${line.id}-override`} className="bg-gray-900 border-b border-gray-700">
                          <td colSpan={12} className="px-4 py-3">
                            <div className="flex items-end gap-3 flex-wrap">
                              <div>
                                <label className={LABEL_CLS}>New Unit Cost</label>
                                <input type="number" step="0.01" className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-white w-28"
                                  value={overrideVal} onChange={e => setOverrideVal(e.target.value)} placeholder="0.00" />
                              </div>
                              <div className="flex-1">
                                <label className={LABEL_CLS}>Reason</label>
                                <input type="text" className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-white w-full"
                                  value={overrideReason} onChange={e => setOverrideReason(e.target.value)} placeholder="e.g. local sub quote" />
                              </div>
                              <button onClick={() => applyOverride(line.id)} disabled={overrideSaving || !overrideVal}
                                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded disabled:opacity-50">
                                {overrideSaving ? 'Saving…' : 'Apply'}
                              </button>
                              <button onClick={() => setOverrideOpen(null)}
                                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded">Cancel</button>
                            </div>
                          </td>
                        </tr>
                      )}
                      {line.explanation && (
                        <tr key={`${line.id}-exp`} className="border-b border-gray-800/50">
                          <td colSpan={12} className="px-2 pb-2 pt-0">
                            <p className="text-xs text-gray-500 italic">{line.explanation}</p>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── COMMERCIAL ── */}
      {subTab === 'Commercial' && (
        <div className="space-y-4 max-w-lg">
          {!costBreakdown ? (
            <p className="text-gray-500 text-sm">Run an estimate first to see cost breakdown.</p>
          ) : (
            <>
              <div className="space-y-2">
                {(costBreakdown.buckets || []).map(b => (
                  <div key={b.id || b.bucket_type} className="flex justify-between items-center py-2 border-b border-gray-800">
                    <div>
                      <span className="text-sm text-gray-300 capitalize">{b.bucket_type.replace(/_/g, ' ')}</span>
                      {b.method && <span className="ml-2 text-xs text-gray-500">({b.method})</span>}
                    </div>
                    <span className="text-sm font-medium text-gray-200">{fmt(b.amount)}</span>
                  </div>
                ))}
              </div>
              <div className="flex justify-between items-center pt-3 border-t-2 border-blue-600">
                <span className="font-bold text-white text-base">FINAL BID VALUE</span>
                <span className="font-bold text-green-400 text-lg">
                  {fmt(costBreakdown.final_bid || (costBreakdown.buckets || []).reduce((s, b) => s + (b.amount || 0), 0))}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── RISK ── */}
      {subTab === 'Risk' && (
        <div className="space-y-3">
          {riskItems.length === 0 ? (
            <p className="text-gray-500 text-sm">Run an estimate first to generate risk register.</p>
          ) : (
            <>
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="text-xs text-gray-400 border-b border-gray-700">
                    {['Risk Name','Category','Probability','Impact','Expected Value','Severity'].map(h => (
                      <th key={h} className="px-2 py-2">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {riskItems.map(r => (
                    <tr key={r.id} className="border-b border-gray-800 hover:bg-gray-800/40">
                      <td className="px-2 py-2 text-gray-200">{r.name}</td>
                      <td className="px-2 py-2 text-gray-400 capitalize">{r.category}</td>
                      <td className="px-2 py-2 text-gray-300">{((r.probability || 0) * 100).toFixed(0)}%</td>
                      <td className="px-2 py-2 text-gray-300">{fmt(r.impact_cost)}</td>
                      <td className="px-2 py-2 text-yellow-300 font-medium">{fmt(r.expected_value)}</td>
                      <td className="px-2 py-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${SEVERITY_COLORS[r.severity] || ''}`}>
                          {r.severity}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex justify-between items-center pt-2 border-t border-gray-700 text-sm">
                <span className="text-gray-400">Total Expected Risk Exposure</span>
                <span className="font-bold text-yellow-400">
                  {fmt(riskItems.reduce((s, r) => s + (r.expected_value || 0), 0))}
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
