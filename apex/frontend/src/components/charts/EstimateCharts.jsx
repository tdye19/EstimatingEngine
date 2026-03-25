import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

function fmt$(val) {
  return '$' + Number(val || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

const PIE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

export default function EstimateCharts({ divData, pieData }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="card">
        <h3 className="text-sm font-semibold mb-4">Cost by Division</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={divData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="div" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => fmt$(v)} />
            <Bar dataKey="labor" stackId="a" fill="#3b82f6" name="Labor" />
            <Bar dataKey="material" stackId="a" fill="#10b981" name="Material" />
            <Bar dataKey="equipment" stackId="a" fill="#f59e0b" name="Equipment" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3 className="text-sm font-semibold mb-4">Division Breakdown</h3>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
              dataKey="value"
              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            >
              {pieData.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => fmt$(v)} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
