import { useEffect, useRef, useState } from 'react';
import { listDocuments, uploadDocument, deleteDocument, runPipeline, getPipelineStatus } from '../../api';
import { FileText, Upload, Clock, CheckCircle2, XCircle, Loader2, Trash2, Play } from 'lucide-react';

const STATUS_CONFIG = {
  pending:    { icon: Clock,         color: 'text-gray-400',  label: 'Pending' },
  processing: { icon: Loader2,       color: 'text-blue-500 animate-spin', label: 'Processing' },
  processed:  { icon: CheckCircle2,  color: 'text-green-500', label: 'Processed' },
  completed:  { icon: CheckCircle2,  color: 'text-green-500', label: 'Completed' },
  failed:     { icon: XCircle,       color: 'text-red-500',   label: 'Failed' },
};

function fmtBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsTab({ projectId, refreshKey, onUploaded, onPipelineComplete }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [lastUploadedDocId, setLastUploadedDocId] = useState(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState('');
  const pollRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    listDocuments(projectId)
      .then((data) => setDocs(data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId, refreshKey]);

  // Cleanup poll on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await getPipelineStatus(projectId);
        const overall = status?.overall;
        const agents = status?.agents || [];

        const completedCount = agents.filter((a) => a.status === 'completed').length;
        const failedAgent = agents.find((a) => a.status === 'failed');

        if (overall === 'completed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setPipelineRunning(false);
          setPipelineMsg(`Pipeline complete — ${completedCount}/6 agents succeeded.`);
          onPipelineComplete?.();
        } else if (failedAgent) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setPipelineRunning(false);
          setPipelineMsg(`Pipeline stopped at ${failedAgent.agent_name}: ${failedAgent.error_message || 'unknown error'}`);
        } else {
          const runningAgent = agents.find((a) => a.status === 'running');
          if (runningAgent) {
            setPipelineMsg(`Running ${runningAgent.agent_name}… (${completedCount}/6 complete)`);
          }
        }
      } catch {
        // silently ignore polling errors
      }
    }, 3000);
  };

  const handleRunPipeline = async () => {
    setPipelineRunning(true);
    setPipelineMsg('Starting pipeline…');
    try {
      await runPipeline(projectId, lastUploadedDocId);
      setPipelineMsg('Pipeline started — running agents…');
      startPolling();
    } catch (err) {
      setPipelineRunning(false);
      setPipelineMsg(`Pipeline error: ${err.message}`);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg('');
    try {
      const result = await uploadDocument(projectId, file);
      setUploadMsg(`"${file.name}" uploaded successfully.`);
      setLastUploadedDocId(result?.id ?? null);
      onUploaded?.();
    } catch (err) {
      setUploadMsg(`Upload error: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (docId) => {
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

  const hasDocuments = docs.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{docs.length} document{docs.length !== 1 ? 's' : ''}</p>
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
            disabled={uploading}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Document'}
          </button>
          {hasDocuments && (
            <button
              onClick={handleRunPipeline}
              disabled={pipelineRunning}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              {pipelineRunning
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Play className="h-4 w-4" />}
              {pipelineRunning ? 'Pipeline Running…' : 'Run Pipeline'}
            </button>
          )}
        </div>
      </div>

      {uploadMsg && (
        <p className="text-sm text-apex-700">{uploadMsg}</p>
      )}

      {pipelineMsg && (
        <div className={`text-sm p-3 rounded-lg ${
          pipelineMsg.includes('error') || pipelineMsg.includes('stopped')
            ? 'bg-red-50 text-red-700'
            : pipelineMsg.includes('complete')
            ? 'bg-green-50 text-green-700'
            : 'bg-blue-50 text-blue-700'
        }`}>
          {pipelineMsg}
        </div>
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
