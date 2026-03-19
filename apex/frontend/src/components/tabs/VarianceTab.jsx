import { useEffect, useRef, useState } from 'react';
import { getVariance, uploadActuals } from '../../api';
import { TrendingUp, TrendingDown, Minus, Upload } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

function fmt$(val) {
  return '$' + Number(val || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function VarianceTab({ projectId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const fileInputRef = useRef(null);

  const load = () => {
    setLoading(true);
    getVariance(projectId)
      .then((response) => setData(response.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId]);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg('');
    try {
      await uploadActuals(projectId, file);
      setUploadMsg('Actuals uploaded successfully. Refreshing...');
      load();
    } catch (err) {
      setUploadMsg(`Upload error: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading variance data...</div>;

  if (!data || !(data.items || data).length) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-400 mb-4">No actuals data for this project. Upload field actuals to see the IMPROVE analysis.</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="btn-primary flex items-center gap-2 mx-auto"
        >
          <Upload className="h-4 w-4" />
          {uploading ? 'Uploading...' : 'Upload Actuals CSV'}
        </button>
        {uploadMsg && <p className="mt-3 text-sm text-apex-700">{uploadMsg}</p>}
      </div>
    );
  }

  const items = data.items || data;

  const chartData = items.slice(0, 12).map((item) => ({
    name: item.csi_code,
    variance: item.variance_pct || 0,
  }));

  const totalEstimated = items.reduce((s, i) => s + (i.estimated_cost || 0), 0);
  const totalActual = items.reduce((s, i) => s + (i.actual_cost || 0), 0);
  const totalVar = totalActual - totalEstimated;
  const totalVarPct = totalEstimated ? ((totalVar / totalEstimated) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Upload button */}
      <div className="flex justify-end">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <Upload className="h-4 w-4" />
          {uploading ? 'Uploading...' : 'Upload Actuals CSV'}
        </button>
      </div>
      {uploadMsg && <p className="text-sm text-apex-700">{uploadMsg}</p>}

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <SummaryCard label="Estimated Cost" value={fmt$(totalEstimated)} />
        <SummaryCard label="Actual Cost" value={fmt$(totalActual)} />
        <SummaryCard
          label="Variance"
          value={fmt$(Math.abs(totalVar))}
          prefix={totalVar > 0 ? '+' : totalVar < 0 ? '-' : ''}
          color={totalVar > 0 ? 'text-red-600' : totalVar < 0 ? 'text-green-600' : 'text-gray-900'}
        />
        <SummaryCard
          label="Variance %"
          value={`${totalVarPct > 0 ? '+' : ''}${totalVarPct.toFixed(1)}%`}
          color={totalVarPct > 5 ? 'text-red-600' : totalVarPct < -5 ? 'text-green-600' : 'text-gray-900'}
        />
      </div>

      {/* Variance chart */}
      <div className="card">
        <h3 className="text-sm font-semibold mb-4">Variance by CSI Code (%)</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => `${v.toFixed(1)}%`} />
            <ReferenceLine y={0} stroke="#666" />
            <Bar
              dataKey="variance"
              fill="#3b82f6"
              radius={[4, 4, 0, 0]}
              label={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Detail table */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">CSI</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3 text-right">Est Hours</th>
                <th className="px-4 py-3 text-right">Act Hours</th>
                <th className="px-4 py-3 text-right">Est Cost</th>
                <th className="px-4 py-3 text-right">Act Cost</th>
                <th className="px-4 py-3 text-right">Var $</th>
                <th className="px-4 py-3 text-right">Var %</th>
                <th className="px-4 py-3 text-center">Trend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((item) => {
                const vp = item.variance_pct || 0;
                return (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono text-xs">{item.csi_code}</td>
                    <td className="px-4 py-2 max-w-xs truncate">{item.description}</td>
                    <td className="px-4 py-2 text-right">{Number(item.estimated_labor_hours || 0).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right">{Number(item.actual_labor_hours || 0).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right">{fmt$(item.estimated_cost)}</td>
                    <td className="px-4 py-2 text-right">{fmt$(item.actual_cost)}</td>
                    <td className={`px-4 py-2 text-right font-medium ${
                      item.variance_cost > 0 ? 'text-red-600' : item.variance_cost < 0 ? 'text-green-600' : ''
                    }`}>
                      {item.variance_cost > 0 ? '+' : ''}{fmt$(item.variance_cost)}
                    </td>
                    <td className={`px-4 py-2 text-right font-medium ${
                      vp > 5 ? 'text-red-600' : vp < -5 ? 'text-green-600' : ''
                    }`}>
                      {vp > 0 ? '+' : ''}{vp.toFixed(1)}%
                    </td>
                    <td className="px-4 py-2 text-center">
                      {vp > 5 ? <TrendingUp className="h-4 w-4 text-red-500 inline" /> :
                       vp < -5 ? <TrendingDown className="h-4 w-4 text-green-500 inline" /> :
                       <Minus className="h-4 w-4 text-gray-400 inline" />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, prefix, color = 'text-gray-900' }) {
  return (
    <div className="card text-center">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{prefix}{value}</p>
    </div>
  );
}
