import { Suspense, lazy } from 'react';
import ErrorBoundary from '../../components/ErrorBoundary';

const BidIntelligenceTab = lazy(() => import('../../components/tabs/BidIntelligenceTab'));

export default function BidIntelligenceLibrary() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Bid Intelligence</h1>
      <ErrorBoundary>
        <Suspense fallback={<div className="text-gray-400">Loading...</div>}>
          <BidIntelligenceTab />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
