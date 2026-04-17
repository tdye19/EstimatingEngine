import BenchmarkDashboardTab from '../../components/tabs/BenchmarkDashboardTab';

export default function BenchmarksLibrary() {
  return (
    <div className="max-w-7xl mx-auto p-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Benchmarks</h1>
        <p className="text-gray-600 mt-2">
          Aggregated productivity benchmarks by CSI activity. Computed from completed projects
          and used by APEX for line-item validation.
        </p>
      </header>
      <BenchmarkDashboardTab />
    </div>
  );
}
