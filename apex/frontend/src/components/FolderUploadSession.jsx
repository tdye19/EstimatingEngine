/*
 * FolderUploadSession — live progress panel for a folder upload job.
 *
 * Manual test plan:
 * 1. Pick a folder with 10 files including 2 .dwg files.
 *    Expect: 8 upload, 2 skipped with reason "Extension not parseable by APEX".
 * 2. Pick a folder containing a file larger than 500 MB.
 *    Expect: that file is skipped with reason "Exceeds 500 MB limit".
 * 3. Pick a folder containing hidden files (.DS_Store, ~$doc.docx).
 *    Expect: skipped with reason "Hidden / system file".
 * 4. Start a 20-file upload, click "Cancel remaining" after 3–4 files finish.
 *    Expect: in-flight files complete, pending files never start.
 * 5. Force a network failure mid-upload (Chrome DevTools → Network → Offline).
 *    Expect: affected file shows "failed" with error, other files continue,
 *            "Retry failed" button appears after the pool finishes.
 * 6. Pick a 100-file folder. Watch the Network tab.
 *    Expect: no more than 3 upload sessions in-flight at any time.
 */

import { useState } from 'react';
import {
  CheckCircle2, XCircle, Clock, Loader2,
  ChevronDown, ChevronRight, RotateCcw, StopCircle,
} from 'lucide-react';

const SKIP_REASON_LABELS = {
  filtered_extension: 'Extension not parseable by APEX',
  hidden_file: 'Hidden / system file',
  over_500mb: 'Exceeds 500 MB limit',
  cancelled: 'Cancelled',
};

function StatusIcon({ status }) {
  switch (status) {
    case 'pending':   return <Clock className="h-3.5 w-3.5 shrink-0 text-gray-400" />;
    case 'uploading': return <Loader2 className="h-3.5 w-3.5 shrink-0 text-blue-500 animate-spin" />;
    case 'done':      return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-500" />;
    case 'failed':    return <XCircle className="h-3.5 w-3.5 shrink-0 text-red-500" />;
    default:          return <span className="h-3.5 w-3.5 shrink-0 text-xs text-gray-300 flex items-center justify-center">—</span>;
  }
}

export default function FolderUploadSession({ session, onCancel, onRetryFailed, onDismiss }) {
  const [skippedExpanded, setSkippedExpanded] = useState(false);

  const { queue, totalBytes, uploadedBytes, finished } = session;
  const uploadable = queue.filter(q => q.status !== 'skipped');
  const skipped    = queue.filter(q => q.status === 'skipped');
  const done       = uploadable.filter(q => q.status === 'done').length;
  const failed     = uploadable.filter(q => q.status === 'failed').length;
  const total      = uploadable.length;

  const bytePct = totalBytes > 0
    ? Math.min(100, Math.round((uploadedBytes / totalBytes) * 100))
    : 0;

  return (
    <div className="border border-blue-200 rounded-lg bg-blue-50 overflow-hidden text-sm">

      {/* ── Header ── */}
      <div className="px-4 py-2.5 flex items-center justify-between bg-blue-100 border-b border-blue-200">
        <span className="font-medium text-blue-800">
          {finished
            ? `Folder upload complete — ${done} uploaded, ${failed} failed, ${skipped.length} skipped`
            : `Uploading folder — ${done} of ${total} files (${skipped.length} skipped)`}
        </span>
        <div className="flex items-center gap-3">
          {!finished && (
            <button
              onClick={onCancel}
              className="flex items-center gap-1 text-xs text-red-600 hover:text-red-800 font-medium"
            >
              <StopCircle className="h-3.5 w-3.5" />
              Cancel remaining
            </button>
          )}
          {finished && failed > 0 && (
            <button
              onClick={onRetryFailed}
              className="flex items-center gap-1 text-xs text-amber-700 hover:text-amber-900 font-medium"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Retry failed
            </button>
          )}
          {finished && (
            <button onClick={onDismiss} className="text-xs text-gray-500 hover:text-gray-700 font-medium">
              Dismiss
            </button>
          )}
        </div>
      </div>

      {/* ── Progress bar ── */}
      {!finished && (
        <div className="px-4 pt-2 pb-1">
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-blue-200 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-blue-600 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${bytePct}%` }}
              />
            </div>
            <span className="text-xs text-blue-600 tabular-nums w-8 text-right">{bytePct}%</span>
          </div>
        </div>
      )}

      {/* ── Uploadable file list ── */}
      {uploadable.length > 0 && (
        <div className="max-h-48 overflow-y-auto px-4 py-2 space-y-0.5">
          {uploadable.map((item, i) => (
            <div key={i} className="flex items-center gap-2 py-0.5 min-w-0">
              <StatusIcon status={item.status} />
              <span className="text-xs text-gray-700 truncate flex-1 min-w-0" title={item.relativePath}>
                {item.relativePath}
              </span>
              {item.status === 'uploading' && (
                <span className="text-xs text-blue-600 tabular-nums w-10 shrink-0 text-right">
                  {Math.round(item.progress * 100)}%
                </span>
              )}
              {item.status === 'failed' && (
                <span className="text-xs text-red-500 truncate max-w-[180px] shrink-0" title={item.error}>
                  {item.error}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Skipped files — collapsible ── */}
      {skipped.length > 0 && (
        <div className="border-t border-blue-200">
          <button
            className="w-full px-4 py-2 flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 text-left"
            onClick={() => setSkippedExpanded(v => !v)}
          >
            {skippedExpanded
              ? <ChevronDown className="h-3 w-3 shrink-0" />
              : <ChevronRight className="h-3 w-3 shrink-0" />}
            {skipped.length} skipped file{skipped.length !== 1 ? 's' : ''} — click to {skippedExpanded ? 'hide' : 'show'}
          </button>
          {skippedExpanded && (
            <div className="max-h-40 overflow-y-auto px-4 pb-2 space-y-0.5">
              {skipped.map((item, i) => (
                <div key={i} className="flex items-center gap-2 py-0.5 min-w-0">
                  <span className="text-xs text-gray-300 shrink-0">—</span>
                  <span className="text-xs text-gray-500 truncate flex-1 min-w-0" title={item.relativePath}>
                    {item.relativePath}
                  </span>
                  <span className="text-xs text-gray-400 shrink-0 whitespace-nowrap">
                    {SKIP_REASON_LABELS[item.skipReason] ?? item.skipReason}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
