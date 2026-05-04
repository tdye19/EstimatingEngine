import { useState, useRef } from 'react';
import { X, ChevronRight, ChevronLeft, CheckCircle, Loader2, Upload } from 'lucide-react';
import { createProject, runPipeline } from '../api';

const TRADES = [
  'General Conditions', 'Concrete', 'Masonry', 'Steel', 'Carpentry',
  'Roofing', 'MEP', 'Finishes', 'Sitework', 'Other',
];

const PROJECT_TYPES = [
  'Commercial', 'Industrial', 'Healthcare', 'Education',
  'Residential', 'Infrastructure', 'Other',
];

const PROGRESS_STEPS = [
  'Uploading plans',
  'Parsing sheets',
  'Detecting scales',
  'Extracting scope signals',
  'Ready for review',
];

export default function NewJobWizard({ open, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ name: '', clientName: '', tradePackage: '', projectType: '' });
  const [planFiles, setPlanFiles] = useState([]);
  const [specFiles, setSpecFiles] = useState([]);
  const [progressStep, setProgressStep] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [createdProjectId, setCreatedProjectId] = useState(null);
  const planInputRef = useRef(null);
  const specInputRef = useRef(null);

  if (!open) return null;

  const reset = () => {
    setStep(1);
    setForm({ name: '', clientName: '', tradePackage: '', projectType: '' });
    setPlanFiles([]);
    setSpecFiles([]);
    setProgressStep(0);
    setDone(false);
    setError('');
    setCreatedProjectId(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const field = (key) => ({
    value: form[key],
    onChange: (e) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  const advance = async () => {
    if (step < 3) { setStep(step + 1); return; }
    // Step 3 → step 4: create project + upload + run pipeline
    setStep(4);
    setError('');
    try {
      // Create project
      const project = await createProject({
        name: form.name,
        client_name: form.clientName,
        trade_focus: form.tradePackage,
        project_type: (form.projectType || 'commercial').toLowerCase(),
        mode: 'shadow',
      });
      setCreatedProjectId(project.id);
      setProgressStep(1);

      // Upload plan files
      const allFiles = [...planFiles, ...specFiles];
      if (allFiles.length > 0) {
        for (const file of allFiles) {
          const fd = new FormData();
          fd.append('file', file);
          await fetch(`/api/projects/${project.id}/documents`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${localStorage.getItem('apex_token')}` },
            body: fd,
          });
        }
      }
      setProgressStep(2);

      // Simulate intermediate steps while pipeline starts
      await delay(800);
      setProgressStep(3);
      await delay(800);
      setProgressStep(4);

      // Kick off pipeline
      try { await runPipeline(project.id); } catch (_) { /* pipeline errors are non-fatal here */ }

      await delay(600);
      setProgressStep(5);
      setDone(true);
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    }
  };

  const canAdvance =
    step === 1 ? form.name.trim() !== '' :
    step === 2 ? form.tradePackage !== '' && form.projectType !== '' :
    step === 3 ? planFiles.length > 0 :
    false;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="text-lg font-bold">New Job</h2>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Step indicators */}
        {step < 4 && (
          <div className="flex items-center gap-2 px-6 py-3 border-b border-gray-50">
            {['Job Details', 'Scope', 'Upload Plans', 'Processing'].map((label, i) => (
              <div key={label} className="flex items-center gap-1">
                <div className={`h-6 w-6 rounded-full flex items-center justify-center text-xs font-bold
                  ${i + 1 < step ? 'bg-apex-600 text-white' :
                    i + 1 === step ? 'bg-apex-100 text-apex-700 ring-2 ring-apex-600' :
                    'bg-gray-100 text-gray-400'}`}>
                  {i + 1 < step ? '✓' : i + 1}
                </div>
                <span className={`text-xs ${i + 1 === step ? 'font-medium text-gray-700' : 'text-gray-400'}`}>
                  {label}
                </span>
                {i < 3 && <span className="text-gray-200 mx-1">›</span>}
              </div>
            ))}
          </div>
        )}

        {/* Body */}
        <div className="px-6 py-5 min-h-[260px]">
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Job Name <span className="text-red-500">*</span></label>
                <input className="input w-full" placeholder="e.g. Westside Office Build-Out" {...field('name')} autoFocus />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Client / Project Name</label>
                <input className="input w-full" placeholder="e.g. Acme Corp" {...field('clientName')} />
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Trade / Scope Package <span className="text-red-500">*</span></label>
                <div className="flex flex-wrap gap-2">
                  {TRADES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, tradePackage: t }))}
                      className={`px-3 py-1.5 rounded-lg text-sm border transition-colors
                        ${form.tradePackage === t
                          ? 'bg-apex-600 text-white border-apex-600'
                          : 'bg-white text-gray-700 border-gray-300 hover:border-apex-400'}`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Project Type <span className="text-red-500">*</span></label>
                <div className="flex flex-wrap gap-2">
                  {PROJECT_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, projectType: t }))}
                      className={`px-3 py-1.5 rounded-lg text-sm border transition-colors
                        ${form.projectType === t
                          ? 'bg-apex-600 text-white border-apex-600'
                          : 'bg-white text-gray-700 border-gray-300 hover:border-apex-400'}`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Drawing Set (PDF) <span className="text-red-500">*</span>
                </label>
                <div
                  className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-apex-400 transition-colors"
                  onClick={() => planInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const dropped = Array.from(e.dataTransfer.files).filter((f) => f.type === 'application/pdf');
                    setPlanFiles((prev) => [...prev, ...dropped]);
                  }}
                >
                  <Upload className="h-8 w-8 mx-auto text-gray-400 mb-2" />
                  <p className="text-sm text-gray-600">Drag and drop PDFs, or <span className="text-apex-600 font-medium">browse</span></p>
                  <p className="text-xs text-gray-400 mt-1">Multiple sheets supported</p>
                  <input
                    ref={planInputRef}
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => setPlanFiles((prev) => [...prev, ...Array.from(e.target.files)])}
                  />
                </div>
                {planFiles.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {planFiles.map((f, i) => (
                      <li key={i} className="flex items-center justify-between text-sm text-gray-700 bg-gray-50 rounded px-3 py-1">
                        <span className="truncate">{f.name}</span>
                        <button onClick={() => setPlanFiles((prev) => prev.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-500 ml-2">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Spec Book (optional)</label>
                <div
                  className="border border-gray-200 rounded-lg p-3 text-center cursor-pointer hover:border-apex-400 transition-colors"
                  onClick={() => specInputRef.current?.click()}
                >
                  <p className="text-sm text-gray-500">Click to add spec PDF</p>
                  <input
                    ref={specInputRef}
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => setSpecFiles((prev) => [...prev, ...Array.from(e.target.files)])}
                  />
                </div>
                {specFiles.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {specFiles.map((f, i) => (
                      <li key={i} className="flex items-center justify-between text-sm text-gray-700 bg-gray-50 rounded px-3 py-1">
                        <span className="truncate">{f.name}</span>
                        <button onClick={() => setSpecFiles((prev) => prev.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-500 ml-2">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="py-4">
              {error ? (
                <div className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-4">{error}</div>
              ) : done ? (
                <div className="text-center">
                  <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                  <p className="font-semibold text-gray-800 mb-1">Ready for review</p>
                  <p className="text-sm text-gray-500">Your job has been created and the pipeline is running.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {PROGRESS_STEPS.map((label, i) => (
                    <div key={label} className="flex items-center gap-3">
                      {i < progressStep ? (
                        <CheckCircle className="h-5 w-5 text-green-500 shrink-0" />
                      ) : i === progressStep ? (
                        <Loader2 className="h-5 w-5 text-apex-600 animate-spin shrink-0" />
                      ) : (
                        <div className="h-5 w-5 rounded-full border-2 border-gray-200 shrink-0" />
                      )}
                      <span className={`text-sm ${i === progressStep ? 'text-gray-800 font-medium' : i < progressStep ? 'text-gray-500' : 'text-gray-300'}`}>
                        {label}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-100 px-6 py-4">
          {step < 4 ? (
            <>
              <button
                onClick={() => step > 1 ? setStep(step - 1) : handleClose()}
                className="btn-secondary flex items-center gap-1"
              >
                <ChevronLeft className="h-4 w-4" />
                {step > 1 ? 'Back' : 'Cancel'}
              </button>
              <button
                onClick={advance}
                disabled={!canAdvance}
                className="btn-primary flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {step === 3 ? 'Create Job' : 'Next'}
                <ChevronRight className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <div />
              {done ? (
                <button
                  onClick={() => { onCreated?.(createdProjectId); reset(); }}
                  className="btn-primary"
                >
                  Go to Project
                </button>
              ) : error ? (
                <button onClick={() => { setStep(3); setError(''); }} className="btn-secondary">
                  Back
                </button>
              ) : (
                <button disabled className="btn-primary opacity-50 cursor-not-allowed">Processing…</button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
