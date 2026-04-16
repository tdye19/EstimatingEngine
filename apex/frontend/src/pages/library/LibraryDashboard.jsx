import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, ClipboardList, Target, BarChart2, ArrowRight } from 'lucide-react';
import { pbGetStats, faGetStats, biGetStats, getBenchmarkSummary } from '../../api';

function StatCard({ title, icon: Icon, description, to, stats, loading }) {
  return (
    <Link
      to={to}
      className="block bg-white rounded-xl border border-gray-200 p-6 hover:border-apex-400 hover:shadow-md transition-all"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-apex-50 rounded-lg">
            <Icon className="h-6 w-6 text-apex-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        </div>
        <ArrowRight className="h-5 w-5 text-gray-400" />
      </div>
      <p className="text-sm text-gray-500 mb-4">{description}</p>
      {loading ? (
        <div className="text-sm text-gray-400">Loading...</div>
      ) : (
        <div className="space-y-1">
          {stats.map(({ label, value }) => (
            <div key={label} className="flex justify-between text-sm">
              <span className="text-gray-500">{label}</span>
              <span className="font-medium text-gray-900">{value ?? '—'}</span>
            </div>
          ))}
        </div>
      )}
    </Link>
  );
}

export default function LibraryDashboard() {
  const [pbStats, setPbStats] = useState(null);
  const [faStats, setFaStats] = useState(null);
  const [biStats, setBiStats] = useState(null);
  const [bmStats, setBmStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([pbGetStats(), faGetStats(), biGetStats(), getBenchmarkSummary()]).then(
      ([pb, fa, bi, bm]) => {
        if (pb.status === 'fulfilled') setPbStats(pb.value?.data);
        if (fa.status === 'fulfilled') setFaStats(fa.value?.data);
        if (bi.status === 'fulfilled') setBiStats(bi.value?.data);
        if (bm.status === 'fulfilled') setBmStats(bm.value?.data);
        setLoading(false);
      }
    );
  }, []);

  const cards = [
    {
      title: 'Productivity Brain',
      icon: Brain,
      description: 'Historical production rates from completed projects.',
      to: '/library/productivity-brain',
      stats: [
        { label: 'Projects', value: pbStats?.project_count },
        { label: 'Activities', value: pbStats?.activity_count },
        { label: 'Line Items', value: pbStats?.line_item_count },
      ],
    },
    {
      title: 'Field Actuals',
      icon: ClipboardList,
      description: 'Close-out data from completed field operations.',
      to: '/library/field-actuals',
      stats: [
        { label: 'Projects', value: faStats?.project_count },
        { label: 'Line Items', value: faStats?.line_item_count },
      ],
    },
    {
      title: 'Bid Intelligence',
      icon: Target,
      description: 'Historical bid data, hit rates, and cost benchmarks.',
      to: '/library/bid-intelligence',
      stats: [
        { label: 'Historical Bids', value: biStats?.total_estimates },
        { label: 'Win Rate', value: biStats?.hit_rate_pct != null ? `${biStats.hit_rate_pct}%` : null },
      ],
    },
    {
      title: 'Benchmarks',
      icon: BarChart2,
      description: 'Aggregated activity benchmarks by CSI division.',
      to: '/library/benchmarks',
      stats: [
        { label: 'Benchmark Records', value: bmStats?.total_benchmarks },
        { label: 'CSI Divisions', value: bmStats?.divisions_covered },
        { label: 'Avg Sample Size', value: bmStats?.avg_sample_size },
      ],
    },
  ];

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Intelligence Library</h1>
        <p className="text-sm text-gray-500 mt-1">
          Organization-wide historical data powering your estimates.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {cards.map((card) => (
          <StatCard key={card.to} {...card} loading={loading} />
        ))}
      </div>
    </div>
  );
}
