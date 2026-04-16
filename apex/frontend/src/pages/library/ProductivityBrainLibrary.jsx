import { Suspense, lazy } from 'react';
import ErrorBoundary from '../../components/ErrorBoundary';

const ProductivityBrainTab = lazy(() => import('../../components/tabs/ProductivityBrainTab'));

export default function ProductivityBrainLibrary() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Productivity Brain</h1>
      <ErrorBoundary>
        <Suspense fallback={<div className="text-gray-400">Loading...</div>}>
          <ProductivityBrainTab />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
