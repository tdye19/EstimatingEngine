import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  Plus, Trash2, BarChart2, Upload, X, ChevronDown, ChevronUp,
} from 'lucide-react';
import {
  getBidComparisons, createBidComparison, deleteBidComparison, getBidComparisonOverlay,
} from '../../api';

const SOURCE_COLORS = ['#1e40af', '#16a34a', '#dc2626', '#f59e0b', '#7c3aed', '#0891b2'];

const FMT = (v) => (v === undefined || v === null ? '—' : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);

export default function BidComparisonTab({ projectId, refreshKey }) {
  const [comparisons, setComparisons] = useState([]);
  const [overlay, setOverlay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', source_type: 'competitor', bid_date: '', total_bid_amount: '', notes: '', items: [] });
  const [formItems, setFormItems] = useState([{ division_number: '03', description: '', amount: '' }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      getBidComparisons(projectId),
      getBidComparisonOverlay(projectId),
    ])
      .then(([comps, ov]) => {
        setComparisons(comps || []);
        setOverlay(ov);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId, refreshKey]);

  const handleAddItem = () =>
    setFormItems((prev) => [...prev, { division_number: '', description: '', amount: '' }]);

  const handleRemoveItem = (idx) =>
    setFormItems((prev) => prev.filter((_, i) => i !== idx));

  const handleItemChange = (idx, field, value) =>
    setFormItems((prev) => prev.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = {
        ...form,
        total_bid_amount: form.total_bid_amount ? Number(form.total_bid_amount) : null,
        items: formItems
          .filter((it) => it.division_number && it.amount !== '')
          .map((it) => ({
            ...it,
            amount: Number(it.amount) || 0,
          })),
      };
      await createBidComparison(projectId, payload);
      setShowForm(false);
      setForm({ name: '', source_type: 'competitor', bid_date: '', total_bid_amount: '', notes: '', items: [] });
      setFormItems([{ division_number: '03', description: '', amount: '' }]);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this comparison?')) return;
    await deleteBidComparison(projectId, id).catch(() => {});
    load();
  };

  if (loading) return <div className="text-gray-400 py-8">Loading bid comparisons...</div>;

  const chartData = overlay?.chart_rows || [];
  const dataKeys = overlay
    ? ['apex_estimate', ...(overlay.comparisons || []).map((c) => c.name)]
    : ['apex_estimate'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Bid Comparison Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Upload competitor bids or historical actuals to overlay against this estimate.
          </p>
        </div>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2">
          <Plus className="h-4 w-4" />
          Add Comparison
        </button>
      </div>

      {/* Totals summary strip */}
      {(comparisons.length > 0 || overlay?.apex_total) && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <TotalCard
            label="APEX Estimate"
            value={overlay?.apex_total}
            color="text-apex-600"
          />
          {comparisons.slice(0, 3).map((c) => (
            <TotalCard
              key={c.id}
              label={c.name}
              value={c.total_bid_amount}
              color="text-gray-700"
            />
          ))}
        </div>
      )}

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-apex-600" />
            Cost by CSI Division
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="division" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => FMT(v)} />
              <Legend />
              {dataKeys.map((key, idx) => (
                <Bar key={key} dataKey={key} fill={SOURCE_COLORS[idx % SOURCE_COLORS.length]} radius={[2, 2, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {comparisons.length === 0 && !showForm && (
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-gray-500">
          <BarChart2 className="h-10 w-10 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No comparisons yet</p>
          <p className="text-sm mt-1">Add a competitor bid or historical actual to start comparing.</p>
        </div>
      )}

      {/* Comparison list */}
      {comparisons.map((c) => (
        <div key={c.id} className="border border-gray-200 rounded-xl overflow-hidden">
          <div
            className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50"
            onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
          >
            <div className="flex items-center gap-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium capitalize">
                {c.source_type}
              </span>
              <span className="font-semibold">{c.name}</span>
              {c.bid_date && <span className="text-sm text-gray-400">{c.bid_date}</span>}
            </div>
            <div className="flex items-center gap-4">
              <span className="font-mono text-sm font-semibold">{FMT(c.total_bid_amount)}</span>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(c.id); }}
                className="text-gray-400 hover:text-red-500 p-1"
              >
                <Trash2 className="h-4 w-4" />
              </button>
              {expandedId === c.id ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
            </div>
          </div>
          {expandedId === c.id && c.items?.length > 0 && (
            <div className="border-t border-gray-100 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="px-4 py-2 text-left">Division</th>
                    <th className="px-4 py-2 text-left">CSI Code</th>
                    <th className="px-4 py-2 text-left">Description</th>
                    <th className="px-4 py-2 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {c.items.map((item) => (
                    <tr key={item.id} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono">{item.division_number}</td>
                      <td className="px-4 py-2 text-gray-500">{item.csi_code || '—'}</td>
                      <td className="px-4 py-2">{item.description || '—'}</td>
                      <td className="px-4 py-2 text-right font-mono">{FMT(item.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}

      {/* Add comparison modal */}
      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setShowForm(false)}
        >
          <div
            className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-bold">Add Bid Comparison</h2>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
                  <input
                    className="input w-full"
                    placeholder="e.g. Competitor A, 2023 Awarded Bid"
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Source Type</label>
                  <select
                    className="input w-full"
                    value={form.source_type}
                    onChange={(e) => setForm((f) => ({ ...f, source_type: e.target.value }))}
                  >
                    <option value="competitor">Competitor</option>
                    <option value="historical">Historical Actual</option>
                    <option value="internal">Internal Budget</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bid Date</label>
                  <input
                    type="date"
                    className="input w-full"
                    value={form.bid_date}
                    onChange={(e) => setForm((f) => ({ ...f, bid_date: e.target.value }))}
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Total Bid Amount</label>
                  <input
                    type="number"
                    className="input w-full"
                    placeholder="Leave blank if entering by division"
                    value={form.total_bid_amount}
                    onChange={(e) => setForm((f) => ({ ...f, total_bid_amount: e.target.value }))}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-700">Line Items by Division</label>
                  <button type="button" onClick={handleAddItem} className="text-xs text-apex-600 hover:text-apex-800 flex items-center gap-1">
                    <Plus className="h-3 w-3" /> Add Row
                  </button>
                </div>
                <div className="space-y-2">
                  {formItems.map((item, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-2 items-start">
                      <div className="col-span-2">
                        <input
                          className="input w-full text-xs"
                          placeholder="Div"
                          value={item.division_number}
                          onChange={(e) => handleItemChange(idx, 'division_number', e.target.value)}
                        />
                      </div>
                      <div className="col-span-6">
                        <input
                          className="input w-full text-xs"
                          placeholder="Description"
                          value={item.description}
                          onChange={(e) => handleItemChange(idx, 'description', e.target.value)}
                        />
                      </div>
                      <div className="col-span-3">
                        <input
                          type="number"
                          className="input w-full text-xs"
                          placeholder="Amount"
                          value={item.amount}
                          onChange={(e) => handleItemChange(idx, 'amount', e.target.value)}
                        />
                      </div>
                      <div className="col-span-1 flex items-center justify-center">
                        <button type="button" onClick={() => handleRemoveItem(idx)} className="text-gray-400 hover:text-red-500">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={saving} className="btn-primary">
                  {saving ? 'Saving...' : 'Save Comparison'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function TotalCard({ label, value, color }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <p className="text-xs text-gray-500 font-medium">{label}</p>
      <p className={`text-xl font-bold mt-1 ${color}`}>
        {value ? `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
      </p>
    </div>
  );
}
