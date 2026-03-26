import { useState, useEffect, lazy, Suspense } from 'react';
import { Calendar, Clock, Users, Layers } from 'lucide-react';
import { getLaborEstimates } from '../../api';

const BarChart = lazy(() => import('recharts').then(m => ({ default: m.BarChart })));
const Bar = lazy(() => import('recharts').then(m => ({ default: m.Bar })));
const XAxis = lazy(() => import('recharts').then(m => ({ default: m.XAxis })));
const YAxis = lazy(() => import('recharts').then(m => ({ default: m.YAxis })));
const Tooltip = lazy(() => import('recharts').then(m => ({ default: m.Tooltip })));
const ResponsiveContainer = lazy(() => import('recharts').then(m => ({ default: m.ResponsiveContainer })));

const DIVISION_LABELS = {
  '03': 'Concrete',
  '05': 'Metals',
  '07': 'Thermal/Moisture',
  '08': 'Openings',
  '09': 'Finishes',
  '22': 'Plumbing',
  '23': 'HVAC',
  '26': 'Electrical',
  '31': 'Earthwork',
  '32': 'Exterior',
  '33': 'Utilities',
};

function getDivisionLabel(code) {
  return DIVISION_LABELS[code] || `Division ${code}`;
}

export default function ScheduleTab({ projectId }) {
  const [laborData, setLaborData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    getLaborEstimates(projectId)
      .then((data) => setLaborData(data || []))
      .catch((err) => setError(err.message || 'Failed to load labor estimates'))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading schedule data...</div>;
  if (error) return <div className="text-red-500 py-8 text-center">{error}</div>;
  if (!laborData.length) {
    return (
      <div className="card text-center py-16 text-gray-400">
        <Calendar className="h-10 w-10 mx-auto mb-3 opacity-30" />
        <p>No labor estimates available yet.</p>
        <p className="text-xs mt-1">Run the pipeline to generate labor data for schedule visualization.</p>
      </div>
    );
  }

  // Group by division (first 2 digits of CSI code)
  const divisionMap = {};
  laborData.forEach((item) => {
    const csi = item.csi_code || '';
    const divCode = csi.substring(0, 2);
    if (!divCode) return;
    if (!divisionMap[divCode]) {
      divisionMap[divCode] = { division: divCode, label: getDivisionLabel(divCode), crewDays: 0, laborHours: 0, crewTypes: new Set(), items: [] };
    }
    divisionMap[divCode].crewDays += item.crew_days || 0;
    divisionMap[divCode].laborHours += item.labor_hours || 0;
    if (item.crew_type) divisionMap[divCode].crewTypes.add(item.crew_type);
    divisionMap[divCode].items.push(item);
  });

  const chartData = Object.values(divisionMap)
    .sort((a, b) => a.division.localeCompare(b.division))
    .map((d) => ({
      name: d.label,
      'Crew Days': Math.round(d.crewDays * 10) / 10,
    }));

  const divisions = Object.values(divisionMap).sort((a, b) => a.division.localeCompare(b.division));

  const totalCrewDays = divisions.reduce((sum, d) => sum + d.crewDays, 0);
  const totalLaborHours = divisions.reduce((sum, d) => sum + d.laborHours, 0);
  // Estimate project duration assuming ~60% parallelism across divisions
  const estimatedDuration = Math.ceil(totalCrewDays * 0.6);

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3">
          <div className="p-2 bg-apex-50 rounded-lg">
            <Clock className="h-5 w-5 text-apex-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Total Crew-Days</p>
            <p className="text-xl font-bold">{Math.round(totalCrewDays).toLocaleString()}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="p-2 bg-blue-50 rounded-lg">
            <Users className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Total Labor Hours</p>
            <p className="text-xl font-bold">{Math.round(totalLaborHours).toLocaleString()}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="p-2 bg-green-50 rounded-lg">
            <Calendar className="h-5 w-5 text-green-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Est. Duration (days)</p>
            <p className="text-xl font-bold">{estimatedDuration.toLocaleString()}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="p-2 bg-purple-50 rounded-lg">
            <Layers className="h-5 w-5 text-purple-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Divisions</p>
            <p className="text-xl font-bold">{divisions.length}</p>
          </div>
        </div>
      </div>

      {/* Bar chart */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Crew-Days by Division</h3>
        <Suspense fallback={<div className="h-64 flex items-center justify-center text-gray-400">Loading chart...</div>}>
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 45)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
              <XAxis type="number" />
              <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="Crew Days" fill="#4f6d7a" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Suspense>
      </div>

      {/* Division detail table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">Division</th>
              <th className="px-4 py-3">Crew Types</th>
              <th className="px-4 py-3 text-right">Crew Days</th>
              <th className="px-4 py-3 text-right">Labor Hours</th>
              <th className="px-4 py-3 text-right">Line Items</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {divisions.map((d) => (
              <tr key={d.division} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium">
                  <span className="text-gray-400 mr-1">{d.division}</span>
                  {d.label}
                </td>
                <td className="px-4 py-3 text-gray-600 text-xs">
                  {[...d.crewTypes].join(', ') || '--'}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  {Math.round(d.crewDays * 10) / 10}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  {Math.round(d.laborHours).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right text-gray-500">
                  {d.items.length}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-gray-50 font-semibold">
              <td className="px-4 py-3">Total</td>
              <td className="px-4 py-3"></td>
              <td className="px-4 py-3 text-right font-mono">{Math.round(totalCrewDays * 10) / 10}</td>
              <td className="px-4 py-3 text-right font-mono">{Math.round(totalLaborHours).toLocaleString()}</td>
              <td className="px-4 py-3 text-right text-gray-500">{laborData.length}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
