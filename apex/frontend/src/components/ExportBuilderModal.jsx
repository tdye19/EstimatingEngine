import { useEffect, useState } from 'react';
import { Download, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';

const FORMATS = [
  { id: 'xlsx', label: 'Excel Estimate Workbook', ext: '.xlsx' },
  { id: 'pdf', label: 'PDF Estimate Summary', ext: '.pdf' },
  { id: 'csv', label: 'CSV Export', ext: '.csv' },
];

const GROUP_OPTIONS = [
  { value: 'trade', label: 'Trade' },
  { value: 'csi', label: 'CSI Division' },
  { value: 'scope_package', label: 'Scope Package' },
];

function downloadBlob(url, filename) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function buildExportUrl(projectId, format) {
  const base = '/api/exports';
  if (format === 'pdf') return `${base}/projects/${projectId}/estimate/pdf`;
  if (format === 'csv') return `${base}/projects/${projectId}/estimate/csv`;
  return `${base}/projects/${projectId}/estimate/xlsx`;
}

export default function ExportBuilderModal({ projectId, standalone }) {
  const [format, setFormat] = useState('xlsx');
  const [includeAssumptions, setIncludeAssumptions] = useState(true);
  const [includeExclusions, setIncludeExclusions] = useState(true);
  const [includeScopeGaps, setIncludeScopeGaps] = useState(false);
  const [groupBy, setGroupBy] = useState('trade');
  const [showBranding, setShowBranding] = useState(false);
  const [logoUrl, setLogoUrl] = useState('');
  const [headerText, setHeaderText] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);

  // Load saved export profile
  useEffect(() => {
    const token = localStorage.getItem('apex_token');
    fetch('/api/export-profile', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.ok ? r.json() : null)
      .then((profile) => {
        if (profile) {
          setIncludeAssumptions(profile.include_assumptions ?? true);
          setIncludeExclusions(profile.include_exclusions ?? true);
          setGroupBy(profile.group_by || 'trade');
          setLogoUrl(profile.logo_url || '');
          setHeaderText(profile.header_text || '');
        }
      })
      .catch(() => {});
  }, []);

  const saveProfile = async (updates) => {
    setProfileSaving(true);
    try {
      await fetch('/api/export-profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('apex_token')}`,
        },
        body: JSON.stringify({
          include_assumptions: includeAssumptions,
          include_exclusions: includeExclusions,
          group_by: groupBy,
          logo_url: logoUrl || null,
          header_text: headerText || null,
          ...updates,
        }),
      });
    } catch (_) {
      // non-critical
    } finally {
      setProfileSaving(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError('');
    try {
      const token = localStorage.getItem('apex_token');
      const url = buildExportUrl(projectId, format);
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const selected = FORMATS.find((f) => f.id === format);
      downloadBlob(objectUrl, `estimate-${projectId}${selected?.ext || ''}`);
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setExportError(err.message);
    } finally {
      setExporting(false);
    }
  };

  const content = (
    <div className="space-y-6">
      {/* Format */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-2">Export Format</h4>
        <div className="space-y-2">
          {FORMATS.map((f) => (
            <label key={f.id} className="flex items-center gap-3 cursor-pointer">
              <input
                type="radio"
                name="export-format"
                value={f.id}
                checked={format === f.id}
                onChange={() => setFormat(f.id)}
                className="text-apex-600"
              />
              <span className="text-sm text-gray-700">{f.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Include */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-2">Include</h4>
        <div className="space-y-2">
          {[
            { id: 'assumptions', label: 'Assumptions', value: includeAssumptions, set: (v) => { setIncludeAssumptions(v); saveProfile({ include_assumptions: v }); } },
            { id: 'exclusions', label: 'Exclusions', value: includeExclusions, set: (v) => { setIncludeExclusions(v); saveProfile({ include_exclusions: v }); } },
            { id: 'scope-gaps', label: 'Scope Gaps', value: includeScopeGaps, set: setIncludeScopeGaps },
          ].map(({ id, label, value, set }) => (
            <label key={id} className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={value}
                onChange={(e) => set(e.target.checked)}
                className="rounded text-apex-600"
              />
              <span className="text-sm text-gray-700">{label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Group by */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-2">Group By</h4>
        <div className="flex gap-3">
          {GROUP_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="group-by"
                value={opt.value}
                checked={groupBy === opt.value}
                onChange={() => { setGroupBy(opt.value); saveProfile({ group_by: opt.value }); }}
                className="text-apex-600"
              />
              <span className="text-sm text-gray-700">{opt.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Company Branding */}
      <div>
        <button
          type="button"
          onClick={() => setShowBranding((v) => !v)}
          className="flex items-center gap-1 text-sm font-semibold text-gray-700"
        >
          Company Branding
          {showBranding ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
        {showBranding && (
          <div className="mt-3 space-y-3 pl-1">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Logo URL</label>
              <input
                className="input w-full text-sm"
                placeholder="https://..."
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                onBlur={() => saveProfile({ logo_url: logoUrl || null })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Header Text</label>
              <input
                className="input w-full text-sm"
                placeholder="Company name, address, etc."
                value={headerText}
                onChange={(e) => setHeaderText(e.target.value)}
                onBlur={() => saveProfile({ header_text: headerText || null })}
              />
            </div>
          </div>
        )}
      </div>

      {exportError && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2">{exportError}</p>
      )}

      <button
        onClick={handleExport}
        disabled={exporting}
        className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {exporting ? 'Exporting…' : `Export ${FORMATS.find((f) => f.id === format)?.label}`}
      </button>
    </div>
  );

  if (standalone) {
    return (
      <div className="max-w-lg">
        <h3 className="font-semibold text-gray-800 mb-5">Export Estimate</h3>
        {content}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="font-bold text-gray-800">Export Estimate</h2>
          <Download className="h-5 w-5 text-apex-600" />
        </div>
        <div className="px-6 py-5">{content}</div>
      </div>
    </div>
  );
}
