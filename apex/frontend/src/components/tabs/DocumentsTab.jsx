import { useEffect, useRef, useState } from 'react';
import { listDocuments, uploadDocument, deleteDocument } from '../../api';
import { FileText, Upload, Clock, CheckCircle2, XCircle, Loader2, Trash2 } from 'lucide-react';

const STATUS_CONFIG = {
  pending:    { icon: Clock,         color: 'text-gray-400',  label: 'Pending' },
  processing: { icon: Loader2,       color: 'text-blue-500 animate-spin', label: 'Processing' },
  processed:  { icon: CheckCircle2,  color: 'text-green-500', label: 'Processed' },
  failed:     { icon: XCircle,       color: 'text-red-500',   label: 'Failed' },
};

function fmtBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsTab({ projectId, refreshKey, onUploaded }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    listDocuments(projectId)
      .then((data) => setDocs(data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId, refreshKey]);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg('');
    try {
      await uploadDocument(projectId, file);
      setUploadMsg(`"${file.name}" uploaded successfully.`);
      onUploaded?.();
    } catch (err) {
      setUploadMsg(`Upload error: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (docId, filename) => {
    if (!window.confirm('Are you sure? This can be undone by an admin.')) return;
    setDeletingId(docId);
    try {
      await deleteDocument(projectId, docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      setUploadMsg(`Delete failed: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading documents...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{docs.length} document{docs.length !== 1 ? 's' : ''}</p>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Document'}
          </button>
        </div>
      </div>

      {uploadMsg && (
        <p className="text-sm text-apex-700">{uploadMsg}</p>
      )}

      {docs.length === 0 ? (
        <div className="card text-center py-16 text-gray-400">
          <FileText className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p>No documents uploaded yet.</p>
          <p className="text-xs mt-1">Upload plans, specs, or CSV files to begin estimating.</p>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">File</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Classification</th>
                <th className="px-4 py-3 text-right">Size</th>
                <th className="px-4 py-3 text-right">Pages</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Uploaded</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {docs.map((doc) => {
                const st = STATUS_CONFIG[doc.processing_status] || STATUS_CONFIG.pending;
                const Icon = st.icon;
                return (
                  <tr key={doc.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium flex items-center gap-2">
                      <FileText className="h-4 w-4 text-gray-400 shrink-0" />
                      {doc.filename}
                    </td>
                    <td className="px-4 py-3 uppercase text-xs text-gray-500">{doc.file_type}</td>
                    <td className="px-4 py-3 text-gray-600">{doc.classification || '—'}</td>
                    <td className="px-4 py-3 text-right text-gray-500">{fmtBytes(doc.file_size_bytes)}</td>
                    <td className="px-4 py-3 text-right text-gray-500">{doc.page_count ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`flex items-center gap-1.5 ${st.color}`}>
                        <Icon className="h-4 w-4" />
                        {st.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(doc.id, doc.filename)}
                        disabled={deletingId === doc.id}
                        className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                        title="Delete document"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
