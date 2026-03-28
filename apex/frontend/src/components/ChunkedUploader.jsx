import { useRef, useState } from 'react';
import { Upload, Loader2 } from 'lucide-react';
import { uploadDocument, initChunkedUpload, uploadChunk, completeChunkedUpload } from '../api';

const CHUNK_SIZE = 1024 * 1024;          // 1 MB — must match backend CHUNK_SIZE
const SMALL_FILE_THRESHOLD = 2 * 1024 * 1024; // files <= 2 MB use single-shot upload
const MAX_RETRIES = 3;
const CHUNK_UPLOAD_CONCURRENCY = 4;

/**
 * ChunkedUploader
 *
 * Renders an "Upload Document" button. For files <= 2 MB it uses the existing
 * single-POST endpoint. For larger files it splits the file into 1 MB chunks
 * and uploads them through a small worker pool, staying well under the
 * Codespaces 413 limit.
 *
 * Props:
 *   projectId  – current project ID
 *   onSuccess(doc)  – called with the DocumentOut object on each successful upload
 *   onError(msg)    – called with an error string if an upload fails
 *   disabled        – disable the button (e.g. while pipeline is running)
 *   multiple        – enable multi-file selection (default false)
 */
export default function ChunkedUploader({ projectId, onSuccess, onError, disabled, multiple = false }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);     // 0–100
  const [statusMsg, setStatusMsg] = useState('');
  const [batchProgress, setBatchProgress] = useState(null); // { current, total } during batch
  const fileInputRef = useRef(null);

  async function uploadLargeFile(file) {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    setStatusMsg('Initializing upload…');
    const session = await initChunkedUpload(
      projectId,
      file.name,
      file.size,
      file.type || 'application/octet-stream',
    );
    const { upload_id } = session;
    const queue = Array.from({ length: totalChunks }, (_, index) => index);
    const workerCount = Math.min(CHUNK_UPLOAD_CONCURRENCY, totalChunks);
    let completed = 0;
    let abortError = null;

    async function uploadChunkWithRetry(chunkIndex) {
      setStatusMsg(`Uploading chunk ${chunkIndex + 1} of ${totalChunks}…`);

      const start = chunkIndex * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunkBlob = file.slice(start, end);

      let lastErr;
      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        if (abortError) throw abortError;

        try {
          await uploadChunk(projectId, upload_id, chunkIndex, chunkBlob);
          return;
        } catch (err) {
          lastErr = err;
          if (abortError) throw abortError;
          if (attempt < MAX_RETRIES - 1) {
            setStatusMsg(
              `Chunk ${chunkIndex + 1} failed, retrying (${attempt + 1}/${MAX_RETRIES - 1})…`,
            );
            await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
          }
        }
      }

      throw lastErr;
    }

    async function worker() {
      while (!abortError) {
        const chunkIndex = queue.shift();
        if (chunkIndex === undefined) return;

        try {
          await uploadChunkWithRetry(chunkIndex);
          if (abortError) return;

          completed += 1;
          setProgress(Math.round((completed / totalChunks) * 95)); // reserve last 5% for finalize
        } catch (err) {
          abortError = abortError || err;
          return;
        }
      }
    }

    await Promise.all(Array.from({ length: workerCount }, () => worker()));
    if (abortError) throw abortError;

    setStatusMsg('Finalizing upload…');
    setProgress(99);
    const doc = await completeChunkedUpload(projectId, upload_id);
    setProgress(100);
    return doc;
  }

  async function uploadSingleFile(file) {
    setProgress(0);
    setStatusMsg(`Uploading "${file.name}"…`);
    let doc;
    if (file.size > SMALL_FILE_THRESHOLD) {
      doc = await uploadLargeFile(file);
    } else {
      setProgress(50);
      doc = await uploadDocument(projectId, file);
      setProgress(100);
    }
    return doc;
  }

  async function handleFileChange(e) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setUploading(true);
    setProgress(0);
    setStatusMsg('');

    if (files.length === 1) {
      try {
        const doc = await uploadSingleFile(files[0]);
        onSuccess?.(doc);
      } catch (err) {
        onError?.(err.message || 'Upload failed');
      } finally {
        setUploading(false);
        setStatusMsg('');
        setProgress(0);
        e.target.value = '';
      }
      return;
    }

    // Batch upload: sequential, one file at a time
    setBatchProgress({ current: 0, total: files.length });
    let successCount = 0;
    const errors = [];
    for (let i = 0; i < files.length; i++) {
      setBatchProgress({ current: i + 1, total: files.length });
      try {
        const doc = await uploadSingleFile(files[i]);
        onSuccess?.(doc);
        successCount++;
      } catch (err) {
        errors.push(`"${files[i].name}": ${err.message}`);
      }
    }
    setUploading(false);
    setBatchProgress(null);
    setStatusMsg('');
    setProgress(0);
    e.target.value = '';
    if (errors.length) {
      onError?.(`${successCount}/${files.length} uploaded. Errors: ${errors.join('; ')}`);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.est"
          className="hidden"
          multiple={multiple}
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading}
          className="btn-secondary flex items-center gap-2 text-sm"
          title={multiple ? "Upload one or more spec/estimate files" : "Upload a construction spec (PDF/DOCX) or a WinEst estimate file (.est/.xlsx)"}
        >
          {uploading
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Upload className="h-4 w-4" />}
          {uploading
            ? batchProgress
              ? `Uploading ${batchProgress.current}/${batchProgress.total}…`
              : 'Uploading…'
            : multiple
            ? 'Upload Documents'
            : 'Upload Document'}
        </button>
      </div>
      {!uploading && (
        <p className="text-xs text-gray-400">
          {multiple
            ? 'Select multiple files — specs (PDF/DOCX), WinEst (.est/.xlsx)'
            : 'Spec (PDF/DOCX) or WinEst estimate (.est\u00a0/\u00a0.xlsx)'}
        </p>
      )}

      {uploading && (
        <div className="space-y-1 min-w-[220px]">
          {statusMsg && (
            <p className="text-xs text-gray-500 truncate">{statusMsg}</p>
          )}
          {batchProgress && (
            <p className="text-xs text-gray-500">
              File {batchProgress.current} of {batchProgress.total}
            </p>
          )}
          <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-apex-600 h-1.5 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 text-right">{progress}%</p>
        </div>
      )}
    </div>
  );
}
