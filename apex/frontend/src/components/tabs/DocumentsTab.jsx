import { useEffect, useMemo, useRef, useState } from 'react';
import { listDocuments, uploadDocument, getDocumentDownloadUrl } from '../../api';
import { FileText, Upload, RefreshCcw, Download } from 'lucide-react';

function fmtBytes(bytes) {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function statusClass(status) {
  const map = {
    completed: 'badge-success',
    pending: 'badge-watch',
    failed: 'badge-critical',
    processing: 'badge-moderate',
  };
  return map[status] || 'badge-watch';
}

export default function DocumentsTab({ projectId, refreshKey = 0, onUploaded }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const fileInputRef = useRef(null);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const response = await listDocuments(projectId);
      setDocuments(response.data || []);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [projectId, refreshKey]);

  const sorted = useMemo(
    () => [...documents].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)),
    [documents]
  );

  const handleUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMessage('');
    try {
      const response = await uploadDocument(projectId, file);
      setMessage(response.message || `Uploaded ${file.name}`);
      if (onUploaded) onUploaded(response);
      await loadDocuments();
    } catch (err) {
      setMessage(`Upload error: ${err.message}`);
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-lg font-semibold">Project Documents</h3>
          <p className="text-sm text-gray-500">
            Upload bid documents and review file status from one place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            type="button"
            onClick={loadDocuments}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-primary flex items-center gap-2"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Document'}
          </button>
        </div>
      </div>

      {message && (
        <div className="rounded-lg border border-apex-200 bg-apex-50 px-4 py-3 text-sm text-apex-800">
          {message}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-gray-400">Loading documents...</div>
      ) : sorted.length === 0 ? (
        <div className="card text-center text-gray-400">
          No documents uploaded yet. Add your plans, specs, addenda, or actuals files here.
        </div>
      ) : (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">File</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Uploaded</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sorted.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="rounded-lg bg-gray-100 p-2 text-gray-500">
                        <FileText className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="font-medium text-gray-900">{doc.filename}</p>
                        <p className="text-xs text-gray-400">#{doc.id}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 uppercase text-gray-500">{doc.file_type || 'unknown'}</td>
                  <td className="px-4 py-3 text-gray-500">{fmtBytes(doc.file_size_bytes)}</td>
                  <td className="px-4 py-3">
                    <span className={statusClass(doc.processing_status)}>{doc.processing_status}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {doc.created_at ? new Date(doc.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <a
                      href={getDocumentDownloadUrl(projectId, doc.id)}
                      className="inline-flex items-center gap-2 text-sm font-medium text-apex-700 hover:text-apex-900"
                    >
                      <Download className="h-4 w-4" />
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
