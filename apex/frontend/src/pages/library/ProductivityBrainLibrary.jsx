import ProductivityBrainTab from '../../components/tabs/ProductivityBrainTab';

export default function ProductivityBrainLibrary() {
  return (
    <div className="max-w-7xl mx-auto p-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Productivity Brain</h1>
        <p className="text-gray-600 mt-2">
          Historical productivity rates across projects. APEX consults this data to validate
          estimator line-item rates.
        </p>
      </header>
      <ProductivityBrainTab />
    </div>
  );
}
