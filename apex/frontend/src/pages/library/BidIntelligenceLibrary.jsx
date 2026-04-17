import BidIntelligenceTab from '../../components/tabs/BidIntelligenceTab';

export default function BidIntelligenceLibrary() {
  return (
    <div className="max-w-7xl mx-auto p-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Bid Intelligence</h1>
        <p className="text-gray-600 mt-2">
          Historical bid outcomes, hit rates by market sector, and comparable-project trends.
        </p>
      </header>
      <BidIntelligenceTab />
    </div>
  );
}
