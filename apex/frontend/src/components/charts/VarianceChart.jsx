import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

export default function VarianceChart({ chartData }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
        <Tooltip formatter={(v) => `${v.toFixed(1)}%`} />
        <ReferenceLine y={0} stroke="#666" />
        <Bar dataKey="variance" radius={[4, 4, 0, 0]} label={false}>
          {chartData.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.variance > 0 ? '#ef4444' : '#10b981'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
