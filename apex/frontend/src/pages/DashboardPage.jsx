import React, { useEffect, useState, useMemo } from 'react';
import { ToastProvider, useToast } from '../components/Toast';
import { Link } from 'react-router-dom';
import { listProjects, createProject, deleteProject, cloneProject } from '../api';
import {
  FolderKanban,
  DollarSign,
  Clock,
  ArrowRight,
  Plus,
  X,
  Trash2,
  Copy,
} from 'lucide-react';

const STATUS_COLORS = {
  estimating: 'bg-blue-100 text-blue-800',
  bid_submitted: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  archived: 'bg-gray-100 text-gray-800',
};

function fmt$(val) {
  if (!val) return '$0';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

const EMPTY_FORM = {
  name: '',
  project_number: '',
  project_type: 'commercial',
  mode: 'shadow',
  location: '',
  square_footage: '',
  bid_date: '',
  description: '',
};

function DashboardPageInner() {
  const { addToast } = useToast();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [cloningId, setCloningId] = useState(null);

  const loadProjects = () => {
    setLoading(true);
    setError('');
    listProjects()
      .then((data) => setProjects(data || []))
      .catch((err) => setError(err.message || 'Failed to load projects'))
      .finally(() => setLoading(false));
  };

  useEffect(loadProjects, []);

  const filtered = useMemo(() =>
    search
      ? projects.filter((p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          (p.project_number || '').toLowerCase().includes(search.toLowerCase()) ||
          (p.location || '').toLowerCase().includes(search.toLowerCase())
        )
      : projects,
    [projects, search]
  );

  const stats = useMemo(() => ({
    total: projects.length,
    estimating: projects.filter((p) => p.status === 'estimating').length,
    bid_submitted: projects.filter((p) => p.status === 'bid_submitted').length,
    completed: projects.filter((p) => p.status === 'completed').length,
    totalValue: projects.reduce((s, p) => s + (p.estimated_value || 0), 0),
  }), [projects]);

  const openModal = () => {
    setForm(EMPTY_FORM);
    setFormError('');
    setShowModal(true);
  };

  const closeModal = () => setShowModal(false);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setFormError('Project name is required.'); return; }
    setSaving(true);
    setFormError('');
    try {
      const newProject = await createProject({
        ...form,
        square_footage: form.square_footage ? Number(form.square_footage) : undefined,
        mode: form.mode,
      });
      setProjects((prev) => [newProject, ...prev]);
      closeModal();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (e, projectId) => {
    e.preventDefault();
    if (!window.confirm('Are you sure? This can be undone by an admin.')) return;
    setDeletingId(projectId);
    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch (err) {
      addToast('error', `Delete failed: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleClone = async (e, projectId) => {
    e.preventDefault();
    setCloningId(projectId);
    try {
      const cloned = await cloneProject(projectId);
      setProjects((prev) => [cloned, ...prev]);
    } catch (err) {
      addToast('error', `Clone failed: ${err.message}`);
    } finally {
      setCloningId(null);
    }
  };

  const field = (key) => ({
    value: form[key],
    onChange: (e) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Project Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Manage your estimating pipeline</p>
        </div>
        <button onClick={openModal} className="btn-primary flex items-center gap-2">
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Projects" value={stats.total} icon={FolderKanban} color="text-apex-600" />
        <StatCard label="In Estimating" value={stats.estimating} icon={Clock} color="text-blue-600" />
        <StatCard label="Bids Submitted" value={stats.bid_submitted} icon={ArrowRight} color="text-yellow-600" />
        <StatCard label="Pipeline Value" value={fmt$(stats.totalValue)} icon={DollarSign} color="text-green-600" />
      </div>

      {/* Search bar */}
      {!loading && projects.length > 0 && (
        <div className="mb-6">
          <input
            type="text"
            className="input w-full max-w-sm"
            placeholder="Search projects by name, number, or location..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      )}

      {/* Project cards */}
      {loading ? (
        <div className="text-center py-16 text-gray-400">Loading projects...</div>
      ) : error ? (
        <div className="text-center py-16 text-red-500">{error}<button onClick={loadProjects} className="ml-3 text-sm underline">Retry</button></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-400">{search ? 'No matching projects.' : 'No projects yet.'}</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {filtered.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="card hover:shadow-md transition-shadow group relative">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="text-xs font-mono text-gray-400">{p.project_number}</span>
                  <h3 className="font-semibold text-lg leading-tight mt-1 group-hover:text-apex-600 transition-colors">
                    {p.name}
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  {p.mode === 'shadow' && (
                    <span className="text-xs font-medium px-2.5 py-0.5 rounded-full whitespace-nowrap bg-amber-100 text-amber-800">
                      shadow
                    </span>
                  )}
                  <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full whitespace-nowrap ${STATUS_COLORS[p.status] || 'bg-gray-100 text-gray-800'}`}>
                    {p.status?.replace('_', ' ')}
                  </span>
                  <button
                    onClick={(e) => handleClone(e, p.id)}
                    disabled={cloningId === p.id}
                    className="p-1 rounded text-gray-300 hover:text-apex-500 hover:bg-apex-50 transition-colors disabled:opacity-50"
                    title="Clone project"
                  >
                    <Copy className="h-4 w-4" />
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, p.id)}
                    disabled={deletingId === p.id}
                    className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                    title="Delete project"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <p className="text-sm text-gray-500 mb-4 line-clamp-2">{p.description}</p>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-400">Type</span>
                  <p className="font-medium capitalize">{p.project_type}</p>
                </div>
                <div>
                  <span className="text-gray-400">Location</span>
                  <p className="font-medium">{p.location}</p>
                </div>
                <div>
                  <span className="text-gray-400">Size</span>
                  <p className="font-medium">{(p.square_footage || 0).toLocaleString()} SF</p>
                </div>
                <div>
                  <span className="text-gray-400">Est. Value</span>
                  <p className="font-medium">{fmt$(p.estimated_value)}</p>
                </div>
              </div>

              {p.bid_date && (
                <div className="mt-4 pt-3 border-t border-gray-100 text-xs text-gray-400">
                  Bid date: {p.bid_date}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}

      {/* New Project Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={closeModal}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold">New Project</h2>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Project Name *</label>
                  <input className="input w-full" placeholder="e.g. Riverside Medical Center" required {...field('name')} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Project Number</label>
                  <input className="input w-full" placeholder="e.g. PRJ-2025-001" {...field('project_number')} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                  <select className="input w-full" {...field('project_type')}>
                    <option value="commercial">Commercial</option>
                    <option value="healthcare">Healthcare</option>
                    <option value="industrial">Industrial</option>
                    <option value="residential">Residential</option>
                    <option value="education">Education</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                  <input className="input w-full" placeholder="City, State" {...field('location')} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Square Footage</label>
                  <input className="input w-full" type="number" placeholder="e.g. 45000" {...field('square_footage')} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bid Date</label>
                  <input className="input w-full" type="date" {...field('bid_date')} />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <textarea className="input w-full" rows={3} placeholder="Brief project description..." {...field('description')} />
                </div>
                <div className="col-span-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.mode === 'shadow'}
                      onChange={(e) => setForm((f) => ({ ...f, mode: e.target.checked ? 'shadow' : 'production' }))}
                      className="h-4 w-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm font-medium text-gray-700">Shadow Mode</span>
                    <span className="text-xs text-gray-400">— run alongside human estimate for comparison</span>
                  </label>
                </div>
              </div>

              {formError && <p className="text-sm text-red-600">{formError}</p>}

              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={closeModal} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={saving} className="btn-primary">
                  {saving ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`p-3 rounded-xl bg-gray-50 ${color}`}>
        <Icon className="h-6 w-6" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-xl font-bold">{value}</p>
      </div>
    </div>
  );
}

function DashboardPage() {
  return (
    <ToastProvider>
      <DashboardPageInner />
    </ToastProvider>
  );
}

export default React.memo(DashboardPage);
