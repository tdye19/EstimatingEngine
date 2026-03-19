import { useEffect, useRef, useState } from 'react';
import { useParams, NavLink, Routes, Route, Navigate } from 'react-router-dom';
import { getProject, runAgents, uploadDocument } from '../api';
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
} from 'lucide-react';
import { Link } from 'react-router-dom';
import GapReportTab from '../components/tabs/GapReportTab';
import TakeoffTab from '../components/tabs/TakeoffTab';
import LaborTab from '../components/tabs/LaborTab';
import EstimateTab from '../components/tabs/EstimateTab';
import VarianceTab from '../components/tabs/VarianceTab';
import AgentLogsTab from '../components/tabs/AgentLogsTab';

const TABS = [
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
  const fileInputRef = useRef(null);

  useEffect(() => {
    getProject(id).then((response) => setProject(response.data)).catch(() => {});
  }, [id]);

  const handleRun = async () => {
    setRunning(true);
    setRunMsg('');
    try {
      const res = await runAgents(id);
      setRunMsg(res.message || 'Agent pipeline started');
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
      const response = await uploadDocument(id, file);
      setRunMsg(response.message || `Document "${file.name}" uploaded successfully.`);
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
        <Route path="gap-report" element={<GapReportTab projectId={id} />} />
        <Route path="takeoff" element={<TakeoffTab projectId={id} />} />
        <Route path="labor" element={<LaborTab projectId={id} />} />
        <Route path="estimate" element={<EstimateTab projectId={id} />} />
        <Route path="variance" element={<VarianceTab projectId={id} />} />
        <Route path="agents" element={<AgentLogsTab projectId={id} />} />
        <Route index element={<Navigate to="gap-report" replace />} />
      </Routes>
    </div>
  );
}
