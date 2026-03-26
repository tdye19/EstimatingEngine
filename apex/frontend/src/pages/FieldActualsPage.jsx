import { useState, useEffect } from 'react';
import { listProjects, getTakeoff, submitActualEntry } from '../api';
import { ClipboardList, CheckCircle, Plus } from 'lucide-react';

export default function FieldActualsPage() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [takeoffItems, setTakeoffItems] = useState([]);
  const [csiSuggestions, setCsiSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    csi_code: '',
    description: '',
    actual_quantity: '',
    actual_labor_hours: '',
    actual_cost: '',
    crew_type: '',
    work_type: '',
  });

  useEffect(() => {
    listProjects()
      .then((data) => setProjects(data || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setTakeoffItems([]);
      return;
    }
    getTakeoff(selectedProjectId)
      .then((data) => setTakeoffItems(data || []))
      .catch(() => setTakeoffItems([]));
  }, [selectedProjectId]);

  const handleCsiChange = (value) => {
    setForm((prev) => ({ ...prev, csi_code: value }));
    if (value.length >= 2 && takeoffItems.length > 0) {
      const lower = value.toLowerCase();
      const matches = takeoffItems
        .filter(
          (t) =>
            (t.csi_code && t.csi_code.toLowerCase().includes(lower)) ||
            (t.description && t.description.toLowerCase().includes(lower))
        )
        .slice(0, 8);
      setCsiSuggestions(matches);
      setShowSuggestions(matches.length > 0);
    } else {
      setShowSuggestions(false);
    }
  };

  const selectSuggestion = (item) => {
    setForm((prev) => ({
      ...prev,
      csi_code: item.csi_code || '',
      description: item.description || '',
    }));
    setShowSuggestions(false);
  };

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedProjectId) {
      setError('Please select a project');
      return;
    }
    if (!form.csi_code.trim()) {
      setError('CSI Code is required');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await submitActualEntry(selectedProjectId, {
        csi_code: form.csi_code,
        description: form.description,
        actual_quantity: form.actual_quantity || 0,
        actual_labor_hours: form.actual_labor_hours || 0,
        actual_cost: form.actual_cost || 0,
        crew_type: form.crew_type,
        work_type: form.work_type,
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message || 'Failed to submit entry');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddAnother = () => {
    setSuccess(false);
    setForm({
      csi_code: '',
      description: '',
      actual_quantity: '',
      actual_labor_hours: '',
      actual_cost: '',
      crew_type: '',
      work_type: '',
    });
  };

  if (success) {
    return (
      <div className="p-4 sm:p-8 max-w-lg mx-auto">
        <div className="card text-center py-12 space-y-4">
          <CheckCircle className="h-16 w-16 text-green-500 mx-auto" />
          <h2 className="text-xl font-bold text-gray-800">Entry Recorded</h2>
          <p className="text-gray-500">The field actual has been saved successfully.</p>
          <button
            onClick={handleAddAnother}
            className="btn-primary inline-flex items-center gap-2 text-base px-6 py-3 mt-4"
          >
            <Plus className="h-5 w-5" />
            Add Another
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-8 max-w-lg mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <ClipboardList className="h-7 w-7 text-apex-600" />
        <h1 className="text-2xl font-bold">Field Actuals Entry</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Project Selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Project</label>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="input w-full text-base py-3"
          >
            <option value="">-- Select Project --</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.project_number} — {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* CSI Code with autocomplete */}
        <div className="relative">
          <label className="block text-sm font-medium text-gray-700 mb-1">CSI Code *</label>
          <input
            type="text"
            value={form.csi_code}
            onChange={(e) => handleCsiChange(e.target.value)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            onFocus={() => form.csi_code.length >= 2 && csiSuggestions.length > 0 && setShowSuggestions(true)}
            placeholder="e.g. 03 30 00"
            className="input w-full text-base py-3"
            autoComplete="off"
          />
          {showSuggestions && (
            <ul className="absolute z-10 w-full bg-white border border-gray-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
              {csiSuggestions.map((item, idx) => (
                <li
                  key={idx}
                  onMouseDown={() => selectSuggestion(item)}
                  className="px-4 py-3 hover:bg-apex-50 cursor-pointer text-sm border-b border-gray-100 last:border-0"
                >
                  <span className="font-mono font-medium text-apex-700">{item.csi_code}</span>
                  <span className="text-gray-500 ml-2">{item.description}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <input
            type="text"
            value={form.description}
            onChange={handleChange('description')}
            placeholder="Work description"
            className="input w-full text-base py-3"
          />
        </div>

        {/* Actual Quantity */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Actual Quantity</label>
          <input
            type="number"
            step="any"
            value={form.actual_quantity}
            onChange={handleChange('actual_quantity')}
            placeholder="0"
            className="input w-full text-base py-3"
            inputMode="decimal"
          />
        </div>

        {/* Actual Labor Hours */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Actual Labor Hours</label>
          <input
            type="number"
            step="any"
            value={form.actual_labor_hours}
            onChange={handleChange('actual_labor_hours')}
            placeholder="0"
            className="input w-full text-base py-3"
            inputMode="decimal"
          />
        </div>

        {/* Actual Cost */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Actual Cost ($)</label>
          <input
            type="number"
            step="any"
            value={form.actual_cost}
            onChange={handleChange('actual_cost')}
            placeholder="0.00"
            className="input w-full text-base py-3"
            inputMode="decimal"
          />
        </div>

        {/* Crew Type */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Crew Type</label>
          <input
            type="text"
            value={form.crew_type}
            onChange={handleChange('crew_type')}
            placeholder="e.g. C-1, C-2"
            className="input w-full text-base py-3"
          />
        </div>

        {/* Work Type */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Work Type</label>
          <input
            type="text"
            value={form.work_type}
            onChange={handleChange('work_type')}
            placeholder="e.g. Concrete, Framing"
            className="input w-full text-base py-3"
          />
        </div>

        {error && (
          <p className="text-red-500 text-sm">{error}</p>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary w-full text-base py-4 font-semibold mt-2"
        >
          {submitting ? 'Submitting...' : 'Submit Actual Entry'}
        </button>
      </form>
    </div>
  );
}
