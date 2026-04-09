import { lazy, Suspense, useEffect, useRef, useState } from 'react';
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
  DollarSign,
  Calendar,
  BarChart2,
  GitBranch,
  Package,
  FileDiff,
  LibraryBig,
  FolderArchive,
  Search,
  Brain,
  Target,
  Scale,
  Shield,
  TrendingDown,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import GapReportTab from '../components/tabs/GapReportTab';
import DecisionEstimateTab from '../components/tabs/DecisionEstimateTab';
import TakeoffTab from '../components/tabs/TakeoffTab';
import LaborTab from '../components/tabs/LaborTab';
import EstimateTab from '../components/tabs/EstimateTab';
import VarianceTab from '../components/tabs/VarianceTab';
import AgentLogsTab from '../components/tabs/AgentLogsTab';
import DocumentsTab from '../components/tabs/DocumentsTab';
import SpecSectionsTab from '../components/tabs/SpecSectionsTab';
import CostTrackingTab from '../components/tabs/CostTrackingTab';
import ScheduleTab from '../components/tabs/ScheduleTab';
import BidComparisonTab from '../components/tabs/BidComparisonTab';
import ChangeOrderTab from '../components/tabs/ChangeOrderTab';
import SubcontractorPackageTab from '../components/tabs/SubcontractorPackageTab';
import EstimateVersionsTab from '../components/tabs/EstimateVersionsTab';
import ShadowComparisonTab from '../components/tabs/ShadowComparisonTab';
import ErrorBoundary from '../components/ErrorBoundary';
import PipelineStatus from '../components/PipelineStatus';

const EstimateLibraryTab = lazy(() => import('../components/tabs/EstimateLibraryTab'));
const BatchUploadTab = lazy(() => import('../components/tabs/BatchUploadTab'));
const BenchmarkDashboardTab = lazy(() => import('../components/tabs/BenchmarkDashboardTab'));
const ProductivityBrainTab = lazy(() => import('../components/tabs/ProductivityBrainTab'));
const BidIntelligenceTab = lazy(() => import('../components/tabs/BidIntelligenceTab'));
const RateIntelligenceTab = lazy(() => import('../components/tabs/RateIntelligenceTab'));
const FieldCalibrationTab = lazy(() => import('../components/tabs/FieldCalibrationTab'));
const IntelligenceReportTab = lazy(() => import('../components/tabs/IntelligenceReportTab'));

const TABS = [
  { path: 'intelligence-report', label: 'Intelligence Report', icon: Shield },
  { path: 'documents', label: 'Documents', icon: Files },
  { path: 'spec-sections', label: 'Spec Sections', icon: BookOpen },
  { path: 'gap-report', label: 'Gap Report', icon: AlertTriangle },
  { path: 'rate-intelligence', label: 'Rate Intelligence', icon: Scale },
  { path: 'field-calibration', label: 'Field Calibration', icon: Activity },
  { path: 'takeoff', label: 'Takeoff', icon: Ruler },
  { path: 'labor', label: 'Labor', icon: HardHat },
  { path: 'estimate', label: 'Estimate', icon: Calculator },
  { path: 'shadow-comparison', label: 'Shadow Compare', icon: Search },
  { path: 'estimate-versions', label: 'Versions', icon: GitBranch },
  { path: 'bid-comparison', label: 'Bid Compare', icon: BarChart2 },
  { path: 'sub-packages', label: 'Sub Packages', icon: Package },
  { path: 'change-orders', label: 'Change Orders', icon: FileDiff },
  { path: 'variance', label: 'Variance', icon: TrendingUp },
  { path: 'schedule', label: 'Schedule', icon: Calendar },
  { path: 'agents', label: 'Agent Logs', icon: Activity },
  { path: 'cost-tracking', label: 'Cost Tracking', icon: DollarSign },
  { path: 'estimate-library', label: 'Estimate Library', icon: LibraryBig },
  { path: 'batch-import', label: 'Batch Import', icon: FolderArchive },
  { path: 'benchmarks', label: 'Benchmarks', icon: BarChart2 },
  { path: 'productivity-brain', label: 'Productivity Brain', icon: Brain },
  { path: 'bid-intelligence', label: 'Bid Intelligence', icon: Target },
  { path: 'decision-estimate', label: 'Decision Estimate', icon: TrendingDown },
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
  const [specRefreshKey, setSpecRefreshKey] = useState(0);
  const [gapRefreshKey, setGapRefreshKey] = useState(0);
  const [rateIntelRefreshKey, setRateIntelRefreshKey] = useState(0);
  const [fieldCalRefreshKey, setFieldCalRefreshKey] = useState(0);
  const [takeoffRefreshKey, setTakeoffRefreshKey] = useState(0);
  const [laborRefreshKey, setLaborRefreshKey] = useState(0);
  const [estimateRefreshKey, setEstimateRefreshKey] = useState(0);
  const [varianceRefreshKey, setVarianceRefreshKey] = useState(0);
  const [costRefreshKey, setCostRefreshKey] = useState(0);
  const [bidCompareRefreshKey, setBidCompareRefreshKey] = useState(0);
  const [changeOrderRefreshKey, setChangeOrderRefreshKey] = useState(0);
  const [subPackageRefreshKey, setSubPackageRefreshKey] = useState(0);
  const [versionsRefreshKey, setVersionsRefreshKey] = useState(0);
  const [comparisonRefreshKey, setComparisonRefreshKey] = useState(0);
  const [intelReportRefreshKey, setIntelReportRefreshKey] = useState(0);
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

  const refreshAllTabs = () => {
    setDocumentsRefreshKey((k) => k + 1);
    setSpecRefreshKey((k) => k + 1);
    setGapRefreshKey((k) => k + 1);
    setRateIntelRefreshKey((k) => k + 1);
    setFieldCalRefreshKey((k) => k + 1);
    setTakeoffRefreshKey((k) => k + 1);
    setLaborRefreshKey((k) => k + 1);
    setEstimateRefreshKey((k) => k + 1);
    setVarianceRefreshKey((k) => k + 1);
    setCostRefreshKey((k) => k + 1);
    setSubPackageRefreshKey((k) => k + 1);
    setVersionsRefreshKey((k) => k + 1);
    setComparisonRefreshKey((k) => k + 1);
    setIntelReportRefreshKey((k) => k + 1);
  };

  const handleAgentComplete = (agentNumber) => {
    // Refresh the relevant tab data after an agent re-run
    const refreshMap = {
      1: () => setDocumentsRefreshKey((k) => k + 1),
      2: () => setSpecRefreshKey((k) => k + 1),
      3: () => setGapRefreshKey((k) => k + 1),
      4: () => { setRateIntelRefreshKey((k) => k + 1); setTakeoffRefreshKey((k) => k + 1); },
      5: () => { setFieldCalRefreshKey((k) => k + 1); setLaborRefreshKey((k) => k + 1); },
      6: () => { setEstimateRefreshKey((k) => k + 1); setIntelReportRefreshKey((k) => k + 1); },
      7: () => setVarianceRefreshKey((k) => k + 1),
    };
    refreshMap[agentNumber]?.();
  };

  if (!project) {
    return <div className="p-8 text-gray-400">Loading project...</div>;
  }

  const openEditModal = () => {
    setEditForm({
      name: project.name || '',
      project_type: project.project_type || 'commercial',
      status: project.status || 'draft',
      mode: project.mode || 'shadow',
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
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.est"
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

      {project.mode === 'shadow' && (
        <div className="mb-4 flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-800 text-sm p-3 rounded-lg">
          <Search className="h-4 w-4 shrink-0" />
          <span className="font-medium">SHADOW MODE</span>
          <span className="text-amber-600">— This estimate is for comparison only</span>
        </div>
      )}

      {runMsg && (
        <div className="mb-4 bg-apex-50 text-apex-800 text-sm p-3 rounded-lg">{runMsg}</div>
      )}

      {/* Pipeline status bar — shown above tabs once a pipeline has run */}
      <PipelineStatus projectId={id} onComplete={refreshAllTabs} />

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
          path="intelligence-report"
          element={
            <ErrorBoundary key="intelligence-report">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading...</div>}>
                <IntelligenceReportTab projectId={id} refreshKey={intelReportRefreshKey} />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="documents"
          element={
            <ErrorBoundary key="documents">
              <DocumentsTab
                projectId={id}
                refreshKey={documentsRefreshKey}
                onUploaded={() => setDocumentsRefreshKey((key) => key + 1)}
                onPipelineComplete={refreshAllTabs}
              />
            </ErrorBoundary>
          }
        />
        <Route path="spec-sections" element={<ErrorBoundary key="spec-sections"><SpecSectionsTab projectId={id} refreshKey={specRefreshKey} /></ErrorBoundary>} />
        <Route path="gap-report" element={<ErrorBoundary key="gap-report"><GapReportTab projectId={id} refreshKey={gapRefreshKey} /></ErrorBoundary>} />
        <Route
          path="rate-intelligence"
          element={
            <ErrorBoundary key="rate-intelligence">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading...</div>}>
                <RateIntelligenceTab projectId={id} refreshKey={rateIntelRefreshKey} />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="field-calibration"
          element={
            <ErrorBoundary key="field-calibration">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading...</div>}>
                <FieldCalibrationTab projectId={id} refreshKey={fieldCalRefreshKey} />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route path="takeoff" element={<ErrorBoundary key="takeoff"><TakeoffTab projectId={id} refreshKey={takeoffRefreshKey} /></ErrorBoundary>} />
        <Route path="labor" element={<ErrorBoundary key="labor"><LaborTab projectId={id} refreshKey={laborRefreshKey} /></ErrorBoundary>} />
        <Route path="estimate" element={<ErrorBoundary key="estimate"><EstimateTab projectId={id} project={project} refreshKey={estimateRefreshKey} /></ErrorBoundary>} />
        <Route
          path="shadow-comparison"
          element={
            <ErrorBoundary key="shadow-comparison">
              <ShadowComparisonTab
                projectId={id}
                project={project}
                refreshKey={comparisonRefreshKey}
                onProjectUpdated={(updated) => setProject(updated)}
              />
            </ErrorBoundary>
          }
        />
        <Route path="estimate-versions" element={<ErrorBoundary key="estimate-versions"><EstimateVersionsTab projectId={id} refreshKey={versionsRefreshKey} /></ErrorBoundary>} />
        <Route path="bid-comparison" element={<ErrorBoundary key="bid-comparison"><BidComparisonTab projectId={id} refreshKey={bidCompareRefreshKey} /></ErrorBoundary>} />
        <Route path="sub-packages" element={<ErrorBoundary key="sub-packages"><SubcontractorPackageTab projectId={id} project={project} refreshKey={subPackageRefreshKey} /></ErrorBoundary>} />
        <Route path="change-orders" element={<ErrorBoundary key="change-orders"><ChangeOrderTab projectId={id} refreshKey={changeOrderRefreshKey} /></ErrorBoundary>} />
        <Route path="variance" element={<ErrorBoundary key="variance"><VarianceTab projectId={id} refreshKey={varianceRefreshKey} /></ErrorBoundary>} />
        <Route path="schedule" element={<ErrorBoundary key="schedule"><ScheduleTab projectId={id} /></ErrorBoundary>} />
        <Route path="agents" element={<ErrorBoundary key="agents"><AgentLogsTab projectId={id} onAgentComplete={handleAgentComplete} /></ErrorBoundary>} />
        <Route path="cost-tracking" element={<ErrorBoundary key="cost-tracking"><CostTrackingTab projectId={id} refreshKey={costRefreshKey} /></ErrorBoundary>} />
        <Route
          path="estimate-library"
          element={
            <ErrorBoundary key="estimate-library">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading…</div>}>
                <EstimateLibraryTab />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="batch-import"
          element={
            <ErrorBoundary key="batch-import">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading…</div>}>
                <BatchUploadTab />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="benchmarks"
          element={
            <ErrorBoundary key="benchmarks">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading…</div>}>
                <BenchmarkDashboardTab />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="productivity-brain"
          element={
            <ErrorBoundary key="productivity-brain">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading...</div>}>
                <ProductivityBrainTab projectId={id} />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="bid-intelligence"
          element={
            <ErrorBoundary key="bid-intelligence">
              <Suspense fallback={<div className="p-8 text-gray-400">Loading...</div>}>
                <BidIntelligenceTab />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="decision-estimate"
          element={
            <ErrorBoundary key="decision-estimate">
              <DecisionEstimateTab projectId={id} />
            </ErrorBoundary>
          }
        />
        <Route index element={<Navigate to="intelligence-report" replace />} />
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
                <div className="md:col-span-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editForm.mode === 'shadow'}
                      onChange={(e) => updateField('mode', e.target.checked ? 'shadow' : 'production')}
                      className="h-4 w-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm font-medium text-gray-700">Shadow Mode</span>
                    <span className="text-xs text-gray-400">— run alongside human estimate for comparison</span>
                  </label>
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
