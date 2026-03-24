import { useEffect, useRef, useState } from 'react';
import { useParams, NavLink, Routes, Route, Navigate } from 'react-router-dom';
import { getProject, runAgents, uploadDocument, updateProject } from '../api';
import {
  ArrowLeft,
  Play,
  AlertTriangle,
  Ruler,
  HardHat,
  Calculator,
  TrendingUp,
  Activity,
  Upload,
  Files,
  Pencil,
  X,
  Save,
  BookOpen,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import GapReportTab from '../components/tabs/GapReportTab';
import TakeoffTab from '../components/tabs/TakeoffTab';
import LaborTab from '../components/tabs/LaborTab';
import EstimateTab from '../components/tabs/EstimateTab';
import VarianceTab from '../components/tabs/VarianceTab';
import AgentLogsTab from '../components/tabs/AgentLogsTab';
import DocumentsTab from '../components/tabs/DocumentsTab';
import SpecSectionsTab from '../components/tabs/SpecSectionsTab';

const TABS = [
  { path: 'documents', label: 'Documents', icon: Files },
  { path: 'spec-sections', label: 'Spec Sections', icon: BookOpen },
  { path: 'gap-report', label: 'Gap Report', icon: AlertTriangle },
  { path: 'takeoff', label: 'Takeoff', icon: Ruler },
  { path: 'labor', label: 'Labor', icon: HardHat },
  { path: 'estimate', label: 'Estimate', icon: Calculator },
  { path: 'variance', label: 'Variance', icon: TrendingUp },
  { path: 'agents', label: 'Agent Logs', icon: Activity },
];

export default function ProjectDetailPage() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState('');
  const [uploading, setUploading] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [savingProject, setSavingProject] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [documentsRefreshKey, setDocumentsRefreshKey] = useState(0);
  const fileInputRef = useRef(null);

  const loadProject = () => {
    getProject(id).then(setProject).catch(() => {});
  };

  useEffect(() => {
    loadProject();
  }, [id]);

  const handleRun = async () => {
    setRunning(true);
    setRunMsg('');
    try {
      await runAgents(id);
      setRunMsg('Agent pipeline started');
    } catch (err) {
      setRunMsg(`Error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setRunMsg('');
    try {
      await uploadDocument(id, file);
      setRunMsg(`Document "${file.name}" uploaded successfully.`);
      setDocumentsRefreshKey((key) => key + 1);
    } catch (err) {
      setRunMsg(`Upload error: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  if (!project) {
    return <div className="p-8 text-gray-400">Loading project...</div>;
  }

  const openEditModal = () => {
    setEditForm({
      name: project.name || '',
      project_type: project.project_type || 'commercial',
      status: project.status || 'draft',
      location: project.location || '',
      square_footage: project.square_footage ?? '',
      estimated_value: project.estimated_value ?? '',
      bid_date: project.bid_date || '',
      description: project.description || '',
    });
    setShowEditModal(true);
  };

  const updateField = (key, value) => setEditForm((current) => ({ ...current, [key]: value }));

  const handleSaveProject = async (event) => {
    event.preventDefault();
    setSavingProject(true);
    setRunMsg('');
    try {
      const updated = await updateProject(id, {
        ...editForm,
        square_footage: editForm.square_footage === '' ? null : Number(editForm.square_footage),
        estimated_value: editForm.estimated_value === '' ? null : Number(editForm.estimated_value),
      });
      setProject(updated);
      setRunMsg('Project updated');
      setShowEditModal(false);
    } catch (err) {
      setRunMsg(`Update error: ${err.message}`);
    } finally {
      setSavingProject(false);
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <span className="text-xs font-mono text-gray-400">{project.project_number}</span>
            <h1 className="text-2xl font-bold">{project.name}</h1>
            <p className="text-sm text-gray-500 mt-1">
              {project.project_type} &middot; {project.location} &middot;{' '}
              {(project.square_footage || 0).toLocaleString()} SF
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={openEditModal} className="btn-secondary flex items-center gap-2">
            <Pencil className="h-4 w-4" />
            Edit Project
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-secondary flex items-center gap-2"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Document'}
          </button>
          <button onClick={handleRun} disabled={running} className="btn-primary flex items-center gap-2">
            <Play className="h-4 w-4" />
            {running ? 'Running...' : 'Run Agent Pipeline'}
          </button>
        </div>
      </div>

      {runMsg && (
        <div className="mb-4 bg-apex-50 text-apex-800 text-sm p-3 rounded-lg">{runMsg}</div>
      )}

      {/* Tabs nav */}
      <div className="flex gap-1 border-b border-gray-200 mb-6 overflow-x-auto">
        {TABS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={`/projects/${id}/${path}`}
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                isActive
                  ? 'border-apex-600 text-apex-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </div>

      {/* Tab content */}
      <Routes>
        <Route
          path="documents"
          element={
            <DocumentsTab
              projectId={id}
              refreshKey={documentsRefreshKey}
              onUploaded={() => setDocumentsRefreshKey((key) => key + 1)}
            />
          }
        />
        <Route path="spec-sections" element={<SpecSectionsTab projectId={id} />} />
        <Route path="gap-report" element={<GapReportTab projectId={id} />} />
        <Route path="takeoff" element={<TakeoffTab projectId={id} />} />
        <Route path="labor" element={<LaborTab projectId={id} />} />
        <Route path="estimate" element={<EstimateTab projectId={id} project={project} />} />
        <Route path="variance" element={<VarianceTab projectId={id} />} />
        <Route path="agents" element={<AgentLogsTab projectId={id} />} />
        <Route index element={<Navigate to="documents" replace />} />
      </Routes>

      {showEditModal && editForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setShowEditModal(false)}
        >
          <div
            className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold">Edit Project</h2>
                <p className="text-sm text-gray-500">Update project details and estimating status.</p>
              </div>
              <button onClick={() => setShowEditModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleSaveProject} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="md:col-span-2">
                  <label className="mb-1 block text-sm font-medium text-gray-700">Project Name</label>
                  <input
                    className="input w-full"
                    value={editForm.name}
                    onChange={(e) => updateField('name', e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Project Type</label>
                  <select
                    className="input w-full"
                    value={editForm.project_type}
                    onChange={(e) => updateField('project_type', e.target.value)}
                  >
                    <option value="commercial">Commercial</option>
                    <option value="healthcare">Healthcare</option>
                    <option value="industrial">Industrial</option>
                    <option value="residential">Residential</option>
                    <option value="education">Education</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Status</label>
                  <select
                    className="input w-full"
                    value={editForm.status}
                    onChange={(e) => updateField('status', e.target.value)}
                  >
                    <option value="draft">Draft</option>
                    <option value="estimating">Estimating</option>
                    <option value="bid_submitted">Bid Submitted</option>
                    <option value="completed">Completed</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Location</label>
                  <input
                    className="input w-full"
                    value={editForm.location}
                    onChange={(e) => updateField('location', e.target.value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Bid Date</label>
                  <input
                    className="input w-full"
                    type="date"
                    value={editForm.bid_date}
                    onChange={(e) => updateField('bid_date', e.target.value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Square Footage</label>
                  <input
                    className="input w-full"
                    type="number"
                    value={editForm.square_footage}
                    onChange={(e) => updateField('square_footage', e.target.value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Estimated Value</label>
                  <input
                    className="input w-full"
                    type="number"
                    value={editForm.estimated_value}
                    onChange={(e) => updateField('estimated_value', e.target.value)}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="mb-1 block text-sm font-medium text-gray-700">Description</label>
                  <textarea
                    className="input w-full"
                    rows={4}
                    value={editForm.description}
                    onChange={(e) => updateField('description', e.target.value)}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowEditModal(false)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={savingProject} className="btn-primary flex items-center gap-2">
                  <Save className="h-4 w-4" />
                  {savingProject ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
