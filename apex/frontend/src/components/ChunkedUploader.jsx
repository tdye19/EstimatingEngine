import { useRef, useState } from 'react';
import { Upload, Loader2 } from 'lucide-react';
import { uploadDocument, initChunkedUpload, uploadChunk, completeChunkedUpload } from '../api';

const CHUNK_SIZE = 1024 * 1024;          // 1 MB — must match backend CHUNK_SIZE
const SMALL_FILE_THRESHOLD = 2 * 1024 * 1024; // files <= 2 MB use single-shot upload
const MAX_RETRIES = 3;

/**
 * ChunkedUploader
 *
 * Renders an "Upload Document" button. For files <= 2 MB it uses the existing
 * single-POST endpoint. For larger files it splits the file into 1 MB chunks
 * and uploads them sequentially, staying well under the Codespaces 413 limit.
 *
 * Props:
 *   projectId  – current project ID
 *   onSuccess(doc)  – called with the DocumentOut object on completion
 *   onError(msg)    – called with an error string if the upload fails
 *   disabled        – disable the button (e.g. while pipeline is running)
 */
export default function ChunkedUploader({ projectId, onSuccess, onError, disabled }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);     // 0–100
  const [statusMsg, setStatusMsg] = useState('');
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

    for (let i = 0; i < totalChunks; i++) {
      setStatusMsg(`Uploading chunk ${i + 1} of ${totalChunks}…`);
      setProgress(Math.round((i / totalChunks) * 95)); // reserve last 5% for finalize

      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunkBlob = file.slice(start, end);

      let lastErr;
      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        try {
          await uploadChunk(projectId, upload_id, i, chunkBlob);
          lastErr = null;
          break;
        } catch (err) {
          lastErr = err;
          if (attempt < MAX_RETRIES - 1) {
            setStatusMsg(
              `Chunk ${i + 1} failed, retrying (${attempt + 1}/${MAX_RETRIES - 1})…`,
            );
            await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
          }
        }
      }
      if (lastErr) throw lastErr;
    }

    setStatusMsg('Finalizing upload…');
    setProgress(99);
    const doc = await completeChunkedUpload(projectId, upload_id);
    setProgress(100);
    return doc;
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setProgress(0);
    setStatusMsg('');

    try {
      let doc;
      if (file.size > SMALL_FILE_THRESHOLD) {
        doc = await uploadLargeFile(file);
      } else {
        setStatusMsg('Uploading…');
        setProgress(50);
        doc = await uploadDocument(projectId, file);
        setProgress(100);
      }
      onSuccess?.(doc);
    } catch (err) {
      onError?.(err.message || 'Upload failed');
    } finally {
      setUploading(false);
      setStatusMsg('');
      setProgress(0);
      e.target.value = '';
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt"
          className="hidden"
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          {uploading
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Upload className="h-4 w-4" />}
          {uploading ? 'Uploading…' : 'Upload Document'}
        </button>
      </div>

      {uploading && (
        <div className="space-y-1 min-w-[220px]">
          {statusMsg && (
            <p className="text-xs text-gray-500 truncate">{statusMsg}</p>
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
