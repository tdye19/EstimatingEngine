import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listProjects } from '../api';
import {
  FolderKanban,
  Building2,
  DollarSign,
  Clock,
  ArrowRight,
  Plus,
} from 'lucide-react';

const STATUS_COLORS = {
  estimating: 'bg-blue-100 text-blue-800',
  bid_submitted: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  archived: 'bg-gray-100 text-gray-800',
};

const TYPE_ICONS = {
  healthcare: Building2,
  industrial: Building2,
  commercial: Building2,
};

function fmt$(val) {
  if (!val) return '$0';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function DashboardPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listProjects()
      .then(data => setProjects(Array.isArray(data) ? data : data.projects || []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  const stats = {
    total: projects.length,
    estimating: projects.filter((p) => p.status === 'estimating').length,
    bid_submitted: projects.filter((p) => p.status === 'bid_submitted').length,
    completed: projects.filter((p) => p.status === 'completed').length,
    totalValue: projects.reduce((s, p) => s + (p.estimated_value || 0), 0),
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Project Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Manage your estimating pipeline</p>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Projects" value={stats.total} icon={FolderKanban} color="text-apex-600" />
        <StatCard label="In Estimating" value={stats.estimating} icon={Clock} color="text-blue-600" />
        <StatCard label="Bids Submitted" value={stats.bid_submitted} icon={ArrowRight} color="text-yellow-600" />
        <StatCard label="Pipeline Value" value={fmt$(stats.totalValue)} icon={DollarSign} color="text-green-600" />
      </div>

      {/* Project cards */}
      {loading ? (
        <div className="text-center py-16 text-gray-400">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No projects yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {projects.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="card hover:shadow-md transition-shadow group">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="text-xs font-mono text-gray-400">{p.project_number}</span>
                  <h3 className="font-semibold text-lg leading-tight mt-1 group-hover:text-apex-600 transition-colors">
                    {p.name}
                  </h3>
                </div>
                <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full whitespace-nowrap ${STATUS_COLORS[p.status] || 'bg-gray-100 text-gray-800'}`}>
                  {p.status?.replace('_', ' ')}
                </span>
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
