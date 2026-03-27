import { useEffect, useState, memo } from 'react';
import { Download, Package, Loader } from 'lucide-react';
import { listSubcontractorPackages, downloadSubcontractorPackage } from '../../api';

const FMT = (v) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const SubcontractorPackageTab = memo(function SubcontractorPackageTab({ projectId, project, refreshKey }) {
  const [packages, setPackages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    listSubcontractorPackages(projectId)
      .then(setPackages)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId, refreshKey]);

  const handleDownload = async (trade) => {
    setDownloading(trade);
    setError('');
    try {
      const slug = trade.replace(/\s+/g, '-').toLowerCase();
      await downloadSubcontractorPackage(
        projectId,
        slug,
        `${project?.project_number || 'project'}_${slug}_bid_package.pdf`,
      );
    } catch (err) {
      setError(`Download failed: ${err.message}`);
    } finally {
      setDownloading(null);
    }
  };

  if (loading) return <div className="text-gray-400 py-8">Loading trade packages...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold">Subcontractor Bid Packages</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          The estimate has been split by CSI trade. Download a tailored PDF bid package for each sub.
        </p>
      </div>

      {error && <div className="text-sm text-red-600 bg-red-50 rounded p-3">{error}</div>}

      {packages.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-gray-500">
          <Package className="h-10 w-10 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No estimate data available</p>
          <p className="text-sm mt-1">Run the agent pipeline to generate an estimate first.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Trade</th>
                <th className="px-4 py-3 text-left">CSI Division</th>
                <th className="px-4 py-3 text-right">Line Items</th>
                <th className="px-4 py-3 text-right">Subtotal</th>
                <th className="px-4 py-3 text-right">Bid Package</th>
              </tr>
            </thead>
            <tbody>
              {packages.map((pkg) => {
                const slug = pkg.trade.replace(/\s+/g, '-').toLowerCase();
                const isDownloading = downloading === pkg.trade;
                return (
                  <tr key={pkg.trade} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 font-semibold">{pkg.trade}</td>
                    <td className="px-4 py-3 font-mono text-gray-500">{pkg.division}</td>
                    <td className="px-4 py-3 text-right text-gray-600">{pkg.items}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{FMT(pkg.total)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDownload(pkg.trade)}
                        disabled={isDownloading}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-apex-50 text-apex-700 hover:bg-apex-100 disabled:opacity-50 transition-colors"
                      >
                        {isDownloading ? (
                          <Loader className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Download className="h-3.5 w-3.5" />
                        )}
                        {isDownloading ? 'Generating...' : 'Download PDF'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="bg-gray-50 border-t-2 border-gray-200">
              <tr>
                <td className="px-4 py-3 font-bold text-gray-700" colSpan={3}>Total</td>
                <td className="px-4 py-3 text-right font-bold font-mono">
                  {FMT(packages.reduce((s, p) => s + (p.total || 0), 0))}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
});

export default SubcontractorPackageTab;
