import { useState, useEffect } from 'react';

const fmt$ = (val) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val || 0);

const CONFIDENCE_COLORS = {
  high: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-orange-100 text-orange-800',
  very_low: 'bg-red-100 text-red-800',
};

const DEFAULT_QUANTITIES = `Continuous Footing Forms,2400,SF,03 30 00
Place Continuous Footing Concrete - 43 meter Boom,120,CY,03 30 00
Fine Grade Slab on Grade by Hand,15000,SF,03 30 00
Sawcut Joints - 1-1/2 Depth,800,LF,03 35 00
Concrete Slab Edge Forms 2x8,600,LF,03 30 00
Expansion Joint Material - SOG,400,LF,03 30 00`;

function parseCSV(text) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(',').map((p) => p.trim());
      return {
        description: parts[0] || '',
        quantity: parseFloat(parts[1]) || 0,
        unit: parts[2] || null,
        division_code: parts[3] || null,
      };
    })
    .filter((q) => q.description && q.quantity > 0);
}

// ---------------------------------------------------------------------------
// Context & Quantities sub-tab
// ---------------------------------------------------------------------------
function ContextTab({ projectId, onEstimateComplete }) {
  const [ctx, setCtx] = useState({
    project_type: '',
    market_sector: '',
    region: '',
    delivery_method: '',
    contract_type: '',
    complexity_level: '',
    schedule_pressure: '',
  });
  const [quantities, setQuantities] = useState(DEFAULT_QUANTITIES);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState('');

  const handleSaveContext = async () => {
    setSaving(true);
    setMsg('');
    try {
      const payload = {};
      Object.entries(ctx).forEach(([k, v]) => { if (v) payload[k] = v; });
      const res = await fetch(`/api/decision/projects/${projectId}/context`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      setMsg('Context saved.');
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRunEstimate = async () => {
    const qtys = parseCSV(quantities);
    if (!qtys.length) { setMsg('No valid quantities parsed.'); return; }
    setRunning(true);
    setMsg('Running estimate...');
    try {
      const res = await fetch(`/api/decision/projects/${projectId}/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantities: qtys }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMsg(`Estimate complete: ${data.line_count} lines, direct cost ${fmt$(data.direct_cost)}`);
      onEstimateComplete(data);
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const field = (label, key, options) => (
    <div key={key}>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <select
        className="input w-full text-sm"
        value={ctx[key]}
        onChange={(e) => setCtx((c) => ({ ...c, [key]: e.target.value }))}
      >
        <option value="">— select —</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-semibold text-gray-800 mb-3">Project Context</h3>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {field('Project Type', 'project_type', [
            { value: 'commercial', label: 'Commercial' },
            { value: 'industrial', label: 'Industrial' },
            { value: 'healthcare', label: 'Healthcare' },
            { value: 'education', label: 'Education' },
            { value: 'residential', label: 'Residential' },
          ])}
          {field('Market Sector', 'market_sector', [
            { value: 'commercial', label: 'Commercial' },
            { value: 'energy', label: 'Energy' },
            { value: 'healthcare', label: 'Healthcare' },
            { value: 'industrial', label: 'Industrial' },
            { value: 'education', label: 'Education' },
          ])}
          {field('Region', 'region', [
            { value: 'michigan', label: 'Michigan' },
            { value: 'midwest', label: 'Midwest' },
            { value: 'northeast', label: 'Northeast' },
            { value: 'southeast', label: 'Southeast' },
            { value: 'west', label: 'West' },
          ])}
          {field('Delivery Method', 'delivery_method', [
            { value: 'cmar', label: 'CM at Risk' },
            { value: 'design_build', label: 'Design-Build' },
            { value: 'hard_bid', label: 'Hard Bid' },
            { value: 'negotiated', label: 'Negotiated' },
          ])}
          {field('Contract Type', 'contract_type', [
            { value: 'self_perform', label: 'Self-Perform' },
            { value: 'subcontracted', label: 'Subcontracted' },
            { value: 'mixed', label: 'Mixed' },
          ])}
          {field('Complexity', 'complexity_level', [
            { value: 'low', label: 'Low' },
            { value: 'medium', label: 'Medium' },
            { value: 'high', label: 'High' },
          ])}
          {field('Schedule Pressure', 'schedule_pressure', [
            { value: 'low', label: 'Low' },
            { value: 'medium', label: 'Medium' },
            { value: 'high', label: 'High' },
            { value: 'critical', label: 'Critical' },
          ])}
        </div>
        <button
          onClick={handleSaveContext}
          disabled={saving}
          className="mt-3 btn-secondary text-sm"
        >
          {saving ? 'Saving...' : 'Save Context'}
        </button>
      </div>

      <div>
        <h3 className="font-semibold text-gray-800 mb-2">Quantities (CSV)</h3>
        <p className="text-xs text-gray-500 mb-2">Format: description, quantity, unit, division_code</p>
        <textarea
          className="input w-full font-mono text-xs"
          rows={10}
          value={quantities}
          onChange={(e) => setQuantities(e.target.value)}
        />
        <button
          onClick={handleRunEstimate}
          disabled={running}
          className="mt-3 btn-primary text-sm"
        >
          {running ? 'Running...' : 'Run Estimate'}
        </button>
      </div>

      {msg && (
        <div className="text-sm p-3 rounded-lg bg-blue-50 text-blue-800">{msg}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Estimate Lines sub-tab
// ---------------------------------------------------------------------------
function LinesTab({ projectId, lines: propLines }) {
  const [lines, setLines] = useState(propLines || []);
  const [loading, setLoading] = useState(!propLines);
  const [overrideTarget, setOverrideTarget] = useState(null);
  const [overrideForm, setOverrideForm] = useState({ value: '', reason_code: '', reason_text: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (propLines) { setLines(propLines); return; }
    setLoading(true);
    fetch(`/api/decision/projects/${projectId}/estimate-lines`)
      .then((r) => r.json())
      .then(setLines)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId, propLines]);

  const handleOverride = async () => {
    if (!overrideTarget || !overrideForm.value) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/decision/estimate-lines/${overrideTarget.id}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          overridden_value: parseFloat(overrideForm.value),
          override_type: 'manual',
          reason_code: overrideForm.reason_code || null,
          reason_text: overrideForm.reason_text || null,
          created_by: 'estimator',
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = await res.json();
      setLines((prev) => prev.map((ln) => (ln.id === updated.id ? updated : ln)));
      setOverrideTarget(null);
      setOverrideForm({ value: '', reason_code: '', reason_text: '' });
    } catch (e) {
      alert(`Override failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-gray-400 p-4">Loading estimate lines...</div>;
  if (!lines.length) return <div className="text-gray-400 p-4">No estimate lines yet. Run estimate first.</div>;

  const directTotal = lines.reduce((s, ln) => s + (ln.recommended_total_cost || 0), 0);
  const needsReview = lines.filter((ln) => ln.needs_review).length;
  const lowConf = lines.filter((ln) => ['low', 'very_low'].includes(ln.confidence_level)).length;

  return (
    <div>
      {/* Summary bar */}
      <div className="flex gap-6 mb-4 text-sm">
        <div><span className="text-gray-500">Direct Total: </span><strong>{fmt$(directTotal)}</strong></div>
        <div><span className="text-gray-500">Lines: </span><strong>{lines.length}</strong></div>
        <div><span className="text-gray-500">Needs Review: </span><strong className="text-amber-600">{needsReview}</strong></div>
        <div><span className="text-gray-500">Low Confidence: </span><strong className="text-red-600">{lowConf}</strong></div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 text-gray-600 uppercase tracking-wide">
              <th className="text-left p-2">Work Item</th>
              <th className="text-right p-2">Qty</th>
              <th className="p-2">Unit</th>
              <th className="text-right p-2">Unit Cost</th>
              <th className="text-right p-2">Total</th>
              <th className="p-2">Basis</th>
              <th className="text-right p-2">p25</th>
              <th className="text-right p-2">p50</th>
              <th className="text-right p-2">p75</th>
              <th className="text-right p-2">n</th>
              <th className="p-2">Confidence</th>
              <th className="p-2">Override</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((ln) => (
              <>
                <tr
                  key={ln.id}
                  className={`border-b ${ln.needs_review ? 'bg-amber-50' : 'hover:bg-gray-50'}`}
                >
                  <td className="p-2 font-medium max-w-xs truncate" title={ln.description}>
                    {ln.description}
                  </td>
                  <td className="p-2 text-right">{ln.quantity?.toLocaleString()}</td>
                  <td className="p-2 text-center text-gray-500">{ln.unit}</td>
                  <td className="p-2 text-right">{ln.recommended_unit_cost != null ? fmt$(ln.recommended_unit_cost) : '—'}</td>
                  <td className="p-2 text-right font-medium">{ln.recommended_total_cost != null ? fmt$(ln.recommended_total_cost) : '—'}</td>
                  <td className="p-2 text-gray-500">{ln.pricing_basis}</td>
                  <td className="p-2 text-right text-gray-500">{ln.benchmark_p25 != null ? fmt$(ln.benchmark_p25) : '—'}</td>
                  <td className="p-2 text-right text-gray-500">{ln.benchmark_p50 != null ? fmt$(ln.benchmark_p50) : '—'}</td>
                  <td className="p-2 text-right text-gray-500">{ln.benchmark_p75 != null ? fmt$(ln.benchmark_p75) : '—'}</td>
                  <td className="p-2 text-right">{ln.benchmark_sample_size ?? '—'}</td>
                  <td className="p-2">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${CONFIDENCE_COLORS[ln.confidence_level] || ''}`}>
                      {ln.confidence_level}
                    </span>
                  </td>
                  <td className="p-2">
                    <button
                      onClick={() => {
                        setOverrideTarget(ln);
                        setOverrideForm({ value: ln.recommended_unit_cost || '', reason_code: '', reason_text: '' });
                      }}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Override
                    </button>
                  </td>
                </tr>
                {overrideTarget?.id === ln.id && (
                  <tr key={`${ln.id}-override`} className="bg-blue-50">
                    <td colSpan={12} className="p-3">
                      <div className="flex gap-3 items-end flex-wrap">
                        <div>
                          <label className="text-xs text-gray-600 block mb-1">New Unit Cost ($)</label>
                          <input
                            type="number"
                            className="input text-sm w-32"
                            value={overrideForm.value}
                            onChange={(e) => setOverrideForm((f) => ({ ...f, value: e.target.value }))}
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-600 block mb-1">Reason Code</label>
                          <input
                            className="input text-sm w-40"
                            value={overrideForm.reason_code}
                            onChange={(e) => setOverrideForm((f) => ({ ...f, reason_code: e.target.value }))}
                          />
                        </div>
                        <div className="flex-1">
                          <label className="text-xs text-gray-600 block mb-1">Reason Text</label>
                          <input
                            className="input text-sm w-full"
                            value={overrideForm.reason_text}
                            onChange={(e) => setOverrideForm((f) => ({ ...f, reason_text: e.target.value }))}
                          />
                        </div>
                        <button onClick={handleOverride} disabled={saving} className="btn-primary text-sm">
                          {saving ? 'Saving...' : 'Apply'}
                        </button>
                        <button onClick={() => setOverrideTarget(null)} className="btn-secondary text-sm">
                          Cancel
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Explanation panel */}
      {lines.some((ln) => ln.explanation) && (
        <div className="mt-4 space-y-1">
          <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Explanations</h4>
          {lines.map((ln) =>
            ln.explanation ? (
              <div key={`${ln.id}-exp`} className="text-xs text-gray-600">
                <strong>{ln.description}:</strong> {ln.explanation}
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Commercial sub-tab
// ---------------------------------------------------------------------------
function CommercialTab({ projectId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/decision/projects/${projectId}/cost-breakdown`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 p-4">Loading...</div>;
  if (!data || !data.buckets?.length)
    return <div className="text-gray-400 p-4">No cost breakdown yet. Run estimate first.</div>;

  const rows = [
    ['Direct Cost', data.direct_cost],
    ['General Conditions', data.general_conditions],
    ['Contingency', data.contingency],
    ['Escalation', data.escalation],
    ['Overhead', data.overhead],
    ['Fee', data.fee],
  ];

  return (
    <div className="max-w-lg">
      <table className="w-full text-sm border-collapse mb-4">
        <tbody>
          {rows.map(([label, amount]) => (
            <tr key={label} className="border-b hover:bg-gray-50">
              <td className="py-2 text-gray-700">{label}</td>
              <td className="py-2 text-right font-mono">{fmt$(amount)}</td>
            </tr>
          ))}
          <tr className="border-t-2 border-gray-800">
            <td className="py-3 font-bold text-gray-900 text-base">FINAL BID VALUE</td>
            <td className="py-3 text-right font-bold text-gray-900 text-base font-mono">
              {fmt$(data.final_bid)}
            </td>
          </tr>
        </tbody>
      </table>

      <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Bucket Detail</h4>
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-50 text-gray-600 uppercase tracking-wide">
            <th className="text-left p-2">Bucket</th>
            <th className="text-right p-2">Amount</th>
            <th className="text-left p-2">Method</th>
          </tr>
        </thead>
        <tbody>
          {data.buckets.map((b) => (
            <tr key={b.id} className="border-b hover:bg-gray-50">
              <td className="p-2">{b.bucket_type}</td>
              <td className="p-2 text-right font-mono">{fmt$(b.amount)}</td>
              <td className="p-2 text-gray-500">{b.method}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk sub-tab
// ---------------------------------------------------------------------------
const SEVERITY_BADGE = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

function RiskTab({ projectId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/decision/projects/${projectId}/risk-items`)
      .then((r) => r.json())
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 p-4">Loading...</div>;
  if (!items.length)
    return <div className="text-gray-400 p-4">No risk items yet. Run estimate first.</div>;

  const totalExpected = items.reduce((s, r) => s + (r.expected_value || 0), 0);

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 text-gray-600 uppercase tracking-wide text-xs">
              <th className="text-left p-2">Risk</th>
              <th className="text-left p-2">Category</th>
              <th className="text-right p-2">Probability</th>
              <th className="text-right p-2">Impact</th>
              <th className="text-right p-2">Expected Value</th>
              <th className="text-left p-2">Severity</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} className="border-b hover:bg-gray-50">
                <td className="p-2 font-medium">{r.name}</td>
                <td className="p-2 text-gray-500">{r.category}</td>
                <td className="p-2 text-right">{((r.probability || 0) * 100).toFixed(0)}%</td>
                <td className="p-2 text-right font-mono">{fmt$(r.impact_cost)}</td>
                <td className="p-2 text-right font-mono font-medium">{fmt$(r.expected_value)}</td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_BADGE[r.severity] || ''}`}>
                    {r.severity}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 text-sm font-semibold text-right text-gray-700">
        Total Expected Risk Exposure: <span className="text-red-700">{fmt$(totalExpected)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DecisionEstimateTab
// ---------------------------------------------------------------------------
const SUB_TABS = [
  { id: 'context', label: 'Context & Quantities' },
  { id: 'lines', label: 'Estimate Lines' },
  { id: 'commercial', label: 'Commercial' },
  { id: 'risk', label: 'Risk' },
];

export default function DecisionEstimateTab({ projectId }) {
  const [activeTab, setActiveTab] = useState('context');
  const [estimateLines, setEstimateLines] = useState(null);

  const handleEstimateComplete = (data) => {
    setEstimateLines(data.estimate_lines || null);
    setActiveTab('lines');
  };

  return (
    <div>
      {/* Sub-tab navigation */}
      <div className="flex gap-1 border-b border-gray-200 mb-5">
        {SUB_TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === id
                ? 'border-apex-600 text-apex-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'context' && (
        <ContextTab projectId={projectId} onEstimateComplete={handleEstimateComplete} />
      )}
      {activeTab === 'lines' && (
        <LinesTab projectId={projectId} lines={estimateLines} />
      )}
      {activeTab === 'commercial' && <CommercialTab projectId={projectId} />}
      {activeTab === 'risk' && <RiskTab projectId={projectId} />}
    </div>
  );
}
