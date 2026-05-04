import { useEffect, useState } from 'react';
import { CheckCircle, AlertCircle, Ruler } from 'lucide-react';
import CalibrationModal from '../CalibrationModal';

export default function SheetsTab({ projectId }) {
  const [planSets, setPlanSets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedSheet, setSelectedSheet] = useState(null);

  const load = () => {
    setLoading(true);
    fetch(`/api/projects/${projectId}/plan-sets`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('apex_token')}` },
    })
      .then((r) => r.json())
      .then((data) => { setPlanSets(Array.isArray(data) ? data : []); })
      .catch(() => setError('Failed to load sheets.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId]);

  const allSheets = planSets.flatMap((ps) =>
    (ps.sheets || []).map((s) => ({ ...s, planSetLabel: ps.version_label || ps.source_filename || `Set ${ps.id}` }))
  );

  if (loading) return <div className="p-8 text-gray-400">Loading sheets...</div>;
  if (error) return <div className="p-8 text-red-500">{error}</div>;
  if (allSheets.length === 0) {
    return (
      <div className="p-8 text-center text-gray-400">
        <Ruler className="h-12 w-12 mx-auto mb-3 text-gray-300" />
        <p className="font-medium">No sheets found.</p>
        <p className="text-sm mt-1">Upload a drawing set in Plans &amp; Specs to get started.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-800">Sheet Index</h3>
          <p className="text-sm text-gray-500">{allSheets.length} sheet{allSheets.length !== 1 ? 's' : ''} across {planSets.length} set{planSets.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1"><CheckCircle className="h-3.5 w-3.5 text-green-500" /> Calibrated</span>
          <span className="flex items-center gap-1"><AlertCircle className="h-3.5 w-3.5 text-amber-400" /> Needs calibration</span>
        </div>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Sheet #</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Discipline</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Detected Scale</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Confirmed Scale</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {allSheets.map((sheet) => {
              const calibrated = Boolean(sheet.confirmed_scale);
              return (
                <tr key={sheet.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-gray-700">{sheet.sheet_number || '—'}</td>
                  <td className="px-4 py-3 text-gray-800">{sheet.sheet_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{sheet.discipline || '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{sheet.detected_scale || '—'}</td>
                  <td className="px-4 py-3">
                    {sheet.confirmed_scale ? (
                      <span className="font-medium text-gray-800">{sheet.confirmed_scale}</span>
                    ) : sheet.detected_scale ? (
                      <span className="text-amber-600">{sheet.detected_scale} <span className="text-xs font-normal">(unconfirmed)</span></span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {calibrated ? (
                      <span className="inline-flex items-center gap-1 text-green-700 bg-green-50 px-2 py-0.5 rounded-full text-xs font-medium">
                        <CheckCircle className="h-3 w-3" /> Calibrated
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full text-xs font-medium">
                        <AlertCircle className="h-3 w-3" /> Needs calibration
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setSelectedSheet(sheet)}
                      className="text-apex-600 hover:text-apex-800 text-xs font-medium"
                    >
                      Calibrate
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <CalibrationModal
        open={Boolean(selectedSheet)}
        sheet={selectedSheet}
        onClose={() => setSelectedSheet(null)}
        onSaved={(updated) => {
          setPlanSets((prev) =>
            prev.map((ps) => ({
              ...ps,
              sheets: (ps.sheets || []).map((s) => (s.id === updated.id ? { ...s, ...updated } : s)),
            }))
          );
          setSelectedSheet(null);
        }}
      />
    </div>
  );
}
