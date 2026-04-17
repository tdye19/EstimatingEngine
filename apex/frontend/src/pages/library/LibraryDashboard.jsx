import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, Target, BarChart2 } from 'lucide-react';
import { pbGetStats, biGetStats, getBenchmarkSummary } from '../../api';

function StatCard({ title, stat, href, description, icon: Icon }) {
  return (
    <Link
      to={href}
      className="block p-6 bg-white rounded-lg shadow hover:shadow-lg transition border border-gray-200"
    >
      <div className="flex items-center gap-3 mb-2">
        {Icon && <Icon className="h-6 w-6 text-apex-600" />}
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
      </div>
      <p className="text-sm text-gray-600 mb-4">{description}</p>
      <div className="text-2xl font-bold text-apex-600">{stat ?? '—'}</div>
    </Link>
  );
}

export default function LibraryDashboard() {
  const [stats, setStats] = useState({ pb: null, bi: null, bm: null });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [pb, bi, bm] = await Promise.allSettled([
        pbGetStats(),
        biGetStats(),
        getBenchmarkSummary(),
      ]);
      if (cancelled) return;
      setStats({
        pb: pb.status === 'fulfilled' ? pb.value : null,
        bi: bi.status === 'fulfilled' ? bi.value : null,
        bm: bm.status === 'fulfilled' ? bm.value : null,
      });
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const pbStat =
    stats.pb?.total_projects != null ? `${stats.pb.total_projects} projects` : null;
  const biStat =
    stats.bi?.total_estimates != null ? `${stats.bi.total_estimates} estimates` : null;
  const bmStat =
    stats.bm?.total_benchmarks != null ? `${stats.bm.total_benchmarks} benchmarks` : null;

  return (
    <div className="max-w-6xl mx-auto p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Intelligence Library</h1>
        <p className="text-gray-600 mt-2">
          Cross-project reference data. Historical productivity, bid history, and aggregated
          benchmarks consulted by APEX during each estimate.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          title="Productivity Brain"
          icon={Brain}
          description="Historical rate engine — activity-level productivity across projects"
          stat={pbStat}
          href="/library/productivity-brain"
        />
        <StatCard
          title="Bid Intelligence"
          icon={Target}
          description="Historical bid outcomes, hit rates, and trends"
          stat={biStat}
          href="/library/bid-intelligence"
        />
        <StatCard
          title="Benchmarks"
          icon={BarChart2}
          description="Aggregated productivity benchmarks by CSI activity"
          stat={bmStat}
          href="/library/benchmarks"
        />
      </div>
    </div>
  );
}
