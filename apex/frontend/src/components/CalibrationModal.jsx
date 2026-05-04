import { useState, useEffect } from 'react';
import { X, Ruler } from 'lucide-react';

const QUICK_SCALES = ["1/8\" = 1'", "1/4\" = 1'", "1/2\" = 1'", "1\" = 1'", "1:50", "1:100", "NTS"];

export default function CalibrationModal({ open, sheet, onClose, onSaved }) {
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (sheet) setValue(sheet.confirmed_scale || sheet.detected_scale || '');
  }, [sheet]);

  if (!open || !sheet) return null;

  const handleSave = async () => {
    if (!value.trim()) return;
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`/api/plan-sheets/${sheet.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('apex_token')}`,
        },
        body: JSON.stringify({ confirmed_scale: value.trim() }),
      });
      if (!res.ok) throw new Error('Failed to save calibration');
      const updated = await res.json();
      onSaved?.(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div className="flex items-center gap-2">
            <Ruler className="h-5 w-5 text-apex-600" />
            <h2 className="font-bold text-gray-800">Calibrate Scale</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="h-5 w-5" /></button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-0.5">Sheet</p>
            <p className="text-sm text-gray-600">
              {sheet.sheet_number ? `${sheet.sheet_number} — ` : ''}{sheet.sheet_name || `Sheet ${sheet.id}`}
            </p>
          </div>

          <div>
            <p className="text-sm font-medium text-gray-700 mb-0.5">Detected Scale</p>
            <p className="text-sm text-gray-500">{sheet.detected_scale || 'Not detected'}</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Confirmed Scale</label>
            <input
              className="input w-full"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="e.g. 1/8&quot; = 1'-0&quot;"
              autoFocus
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {QUICK_SCALES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setValue(s)}
                  className={`px-2.5 py-1 rounded-md text-xs border transition-colors
                    ${value === s
                      ? 'bg-apex-600 text-white border-apex-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-apex-400'}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded p-2">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-gray-100 px-6 py-4">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button
            onClick={handleSave}
            disabled={!value.trim() || saving}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Saving…' : 'Save Calibration'}
          </button>
        </div>
      </div>
    </div>
  );
}
