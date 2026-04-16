import { Suspense, lazy } from 'react';
import ErrorBoundary from '../../components/ErrorBoundary';

const BenchmarkDashboardTab = lazy(() => import('../../components/tabs/BenchmarkDashboardTab'));

export default function BenchmarksLibrary() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Benchmarks</h1>
      <ErrorBoundary>
        <Suspense fallback={<div className="text-gray-400">Loading...</div>}>
          <BenchmarkDashboardTab />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
