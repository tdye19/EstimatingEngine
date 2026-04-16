import { useEffect, useState } from 'react';
import { faGetStats, faGetProjects, getFieldActualsStats } from '../../api';

export default function FieldActualsLibrary() {
  const [stats, setStats] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([faGetStats(), faGetProjects()]).then(([s, p]) => {
      if (s.status === 'fulfilled') setStats(s.value?.data);
      if (p.status === 'fulfilled') setProjects(p.value?.data ?? []);
      setLoading(false);
    });
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Field Actuals</h1>
      <p className="text-sm text-gray-500 mb-6">
        Close-out production data from completed field operations.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Projects</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{stats?.project_count ?? 0}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Line Items</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{stats?.line_item_count ?? 0}</p>
            </div>
          </div>

          {projects.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                  <tr>
                    <th className="px-4 py-3 text-left">Project</th>
                    <th className="px-4 py-3 text-left">Region</th>
                    <th className="px-4 py-3 text-right">Line Items</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {projects.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{p.project_name}</td>
                      <td className="px-4 py-3 text-gray-500">{p.region ?? '—'}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{p.line_item_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {projects.length === 0 && (
            <p className="text-gray-400 text-sm">No field actuals data loaded yet.</p>
          )}
        </>
      )}
    </div>
  );
}
