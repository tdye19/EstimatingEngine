import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

const SOURCE_COLORS = ['#1e40af', '#16a34a', '#dc2626', '#f59e0b', '#7c3aed', '#0891b2'];
const FMT = (v) => (v === undefined || v === null ? '—' : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);

export default function BidComparisonChart({ chartData, dataKeys }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="division" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => FMT(v)} />
        <Legend />
        {dataKeys.map((key, idx) => (
          <Bar key={key} dataKey={key} fill={SOURCE_COLORS[idx % SOURCE_COLORS.length]} radius={[2, 2, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
