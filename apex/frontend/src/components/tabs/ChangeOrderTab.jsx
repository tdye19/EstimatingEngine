import { useEffect, useState } from 'react';
import {
  Plus, Edit2, Check, X, Clock, AlertTriangle, TrendingUp, Calendar,
} from 'lucide-react';
import {
  getChangeOrders, createChangeOrder, updateChangeOrder, deleteChangeOrder,
  getChangeOrderSummary,
} from '../../api';

const STATUS_CONFIG = {
  pending: { label: 'Pending', color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  approved: { label: 'Approved', color: 'bg-green-100 text-green-800', icon: Check },
  rejected: { label: 'Rejected', color: 'bg-red-100 text-red-800', icon: X },
  on_hold: { label: 'On Hold', color: 'bg-gray-100 text-gray-700', icon: AlertTriangle },
};

const TYPE_LABELS = { addition: 'Addition', deletion: 'Deletion', modification: 'Modification' };

const FMT_DOLLAR = (v) =>
  v === undefined || v === null
    ? '$0'
    : `${v >= 0 ? '+' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const BLANK_FORM = {
  title: '', description: '', csi_code: '', change_type: 'addition',
  requested_by: '', cost_impact: '', schedule_impact_days: '', status: 'pending',
};

export default function ChangeOrderTab({ projectId, refreshKey }) {
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(BLANK_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    Promise.all([getChangeOrders(projectId), getChangeOrderSummary(projectId)])
      .then(([cos, sum]) => {
        setOrders(cos || []);
        setSummary(sum);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId, refreshKey]);

  const openCreate = () => {
    setEditingId(null);
    setForm(BLANK_FORM);
    setError('');
    setShowForm(true);
  };

  const openEdit = (co) => {
    setEditingId(co.id);
    setForm({
      title: co.title,
      description: co.description || '',
      csi_code: co.csi_code || '',
      change_type: co.change_type,
      requested_by: co.requested_by || '',
      cost_impact: co.cost_impact ?? '',
      schedule_impact_days: co.schedule_impact_days ?? '',
      status: co.status,
    });
    setError('');
    setShowForm(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = {
      ...form,
      cost_impact: form.cost_impact !== '' ? Number(form.cost_impact) : 0,
      schedule_impact_days: form.schedule_impact_days !== '' ? Number(form.schedule_impact_days) : 0,
    };
    try {
      if (editingId) {
        await updateChangeOrder(projectId, editingId, payload);
      } else {
        await createChangeOrder(projectId, payload);
      }
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (co, newStatus) => {
    await updateChangeOrder(projectId, co.id, { status: newStatus }).catch(() => {});
    load();
  };

  if (loading) return <div className="text-gray-400 py-8">Loading change orders...</div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Change Orders</h2>
          <p className="text-sm text-gray-500 mt-0.5">Track scope changes and their cost/schedule impact.</p>
        </div>
        <button onClick={openCreate} className="btn-primary flex items-center gap-2">
          <Plus className="h-4 w-4" />
          New Change Order
        </button>
      </div>

      {/* Summary strip */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryCard label="Total COs" value={summary.total_orders} unit="" />
          <SummaryCard label="Approved Cost Impact" value={`$${Number(summary.total_approved_cost || 0).toLocaleString()}`} unit="" color="text-green-700" />
          <SummaryCard label="Pending Cost Exposure" value={`$${Number(summary.total_pending_cost || 0).toLocaleString()}`} unit="" color="text-yellow-700" />
          <SummaryCard label="Schedule Impact" value={summary.total_schedule_impact_days} unit="days" color="text-blue-700" />
        </div>
      )}

      {orders.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-gray-500">
          <TrendingUp className="h-10 w-10 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No change orders yet</p>
          <p className="text-sm mt-1">Add change orders to track scope changes after the initial estimate.</p>
        </div>
      )}

      {/* Table */}
      {orders.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                <th className="px-4 py-3 text-left">CO #</th>
                <th className="px-4 py-3 text-left">Title</th>
                <th className="px-4 py-3 text-left">Type</th>
                <th className="px-4 py-3 text-left">Requested By</th>
                <th className="px-4 py-3 text-right">Cost Impact</th>
                <th className="px-4 py-3 text-right">Sched Days</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {orders.map((co) => {
                const sc = STATUS_CONFIG[co.status] || STATUS_CONFIG.pending;
                const Icon = sc.icon;
                return (
                  <tr key={co.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono font-semibold text-xs">{co.co_number}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{co.title}</div>
                      {co.csi_code && <div className="text-xs text-gray-400">{co.csi_code}</div>}
                    </td>
                    <td className="px-4 py-3 capitalize text-gray-600">{TYPE_LABELS[co.change_type] || co.change_type}</td>
                    <td className="px-4 py-3 text-gray-500">{co.requested_by || '—'}</td>
                    <td className={`px-4 py-3 text-right font-mono font-semibold ${co.cost_impact > 0 ? 'text-red-600' : co.cost_impact < 0 ? 'text-green-600' : ''}`}>
                      {FMT_DOLLAR(co.cost_impact)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {co.schedule_impact_days > 0 ? `+${co.schedule_impact_days}` : co.schedule_impact_days}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${sc.color}`}>
                        <Icon className="h-3 w-3" />
                        {sc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end">
                        {co.status === 'pending' && (
                          <>
                            <button
                              onClick={() => handleStatusChange(co, 'approved')}
                              className="text-xs text-green-600 hover:text-green-800 font-medium"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => handleStatusChange(co, 'rejected')}
                              className="text-xs text-red-500 hover:text-red-700 font-medium"
                            >
                              Reject
                            </button>
                          </>
                        )}
                        <button onClick={() => openEdit(co)} className="text-gray-400 hover:text-gray-600">
                          <Edit2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setShowForm(false)}
        >
          <div
            className="w-full max-w-xl rounded-xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-bold">
                {editingId ? 'Edit Change Order' : 'New Change Order'}
              </h2>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
                <input
                  className="input w-full"
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                  <select
                    className="input w-full"
                    value={form.change_type}
                    onChange={(e) => setForm((f) => ({ ...f, change_type: e.target.value }))}
                  >
                    <option value="addition">Addition</option>
                    <option value="deletion">Deletion</option>
                    <option value="modification">Modification</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                  <select
                    className="input w-full"
                    value={form.status}
                    onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
                  >
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                    <option value="on_hold">On Hold</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">CSI Code</label>
                  <input
                    className="input w-full"
                    placeholder="e.g. 03 30 00"
                    value={form.csi_code}
                    onChange={(e) => setForm((f) => ({ ...f, csi_code: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Requested By</label>
                  <input
                    className="input w-full"
                    value={form.requested_by}
                    onChange={(e) => setForm((f) => ({ ...f, requested_by: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Cost Impact ($)</label>
                  <input
                    type="number"
                    step="any"
                    className="input w-full"
                    placeholder="+/- amount"
                    value={form.cost_impact}
                    onChange={(e) => setForm((f) => ({ ...f, cost_impact: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Schedule Impact (days)</label>
                  <input
                    type="number"
                    className="input w-full"
                    placeholder="+/- days"
                    value={form.schedule_impact_days}
                    onChange={(e) => setForm((f) => ({ ...f, schedule_impact_days: e.target.value }))}
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <textarea
                    className="input w-full"
                    rows={3}
                    value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  />
                </div>
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={saving} className="btn-primary">
                  {saving ? 'Saving...' : editingId ? 'Save Changes' : 'Create CO'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, unit, color = 'text-gray-900' }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <p className="text-xs text-gray-500 font-medium">{label}</p>
      <p className={`text-xl font-bold mt-1 ${color}`}>
        {value}{unit && <span className="text-sm font-normal text-gray-500 ml-1">{unit}</span>}
      </p>
    </div>
  );
}
