import { useEffect, useRef, useState } from 'react';
import { listDocuments, deleteDocument, bulkDeleteDocuments, runPipeline, getPipelineStatus, getDocumentFileUrl } from '../../api';
import { FileText, Clock, CheckCircle2, XCircle, Loader2, Trash2, Play, Eye } from 'lucide-react';
import ChunkedUploader from '../ChunkedUploader';
import PdfViewer from '../PdfViewer';

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
  const [uploadMsg, setUploadMsg] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [lastUploadedDocId, setLastUploadedDocId] = useState(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState('');
  const pollRef = useRef(null);

  const [error, setError] = useState('');
  const [viewingDoc, setViewingDoc] = useState(null);

  // Bulk selection state
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectAll, setSelectAll] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const loadDocs = () => {
    setLoading(true);
    setError('');
    listDocuments(projectId)
      .then((data) => {
        setDocs(data || []);
        setSelectedIds(new Set());
        setSelectAll(false);
      })
      .catch((err) => setError(err.message || 'Failed to load documents'))
      .finally(() => setLoading(false));
  };

  useEffect(loadDocs, [projectId, refreshKey]);

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
    if (!window.confirm('Run the AI pipeline? This will use LLM API credits.')) return;
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

  const handleUploadSuccess = (doc) => {
    setUploadMsg(`"${doc.filename}" uploaded successfully.`);
    setLastUploadedDocId(doc.id);
    onUploaded?.();
    // Backend auto-triggers pipeline after upload — start polling immediately
    setPipelineRunning(true);
    setPipelineMsg('Pipeline started — running agents…');
    startPolling();
  };

  const handleUploadError = (msg) => {
    setUploadMsg(`Upload error: ${msg}`);
  };

  const handleDelete = async (docId) => {
    if (!window.confirm('Are you sure? This can be undone by an admin.')) return;
    setDeletingId(docId);
    try {
      await deleteDocument(projectId, docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    } catch (err) {
      setUploadMsg(`Delete failed: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const toggleSelect = (docId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectAll) {
      setSelectedIds(new Set());
      setSelectAll(false);
    } else {
      setSelectedIds(new Set(docs.map((d) => d.id)));
      setSelectAll(true);
    }
  };

  // Keep selectAll in sync
  useEffect(() => {
    if (docs.length > 0 && selectedIds.size === docs.length) {
      setSelectAll(true);
    } else {
      setSelectAll(false);
    }
  }, [selectedIds, docs]);

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`Delete ${selectedIds.size} selected document(s)?`)) return;
    setBulkDeleting(true);
    try {
      await bulkDeleteDocuments(projectId, [...selectedIds]);
      setSelectedIds(new Set());
      setSelectAll(false);
      loadDocs();
    } catch (err) {
      setUploadMsg(`Bulk delete failed: ${err.message}`);
    } finally {
      setBulkDeleting(false);
    }
  };

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading documents...</div>;
  if (error) return <div className="text-red-500 py-8 text-center">{error}<button onClick={loadDocs} className="ml-3 text-sm underline">Retry</button></div>;

  const hasDocuments = docs.length > 0;

  return (
    <div className="space-y-4">
      {viewingDoc && (
        <PdfViewer
          url={getDocumentFileUrl(projectId, viewingDoc.id)}
          filename={viewingDoc.filename}
          onClose={() => setViewingDoc(null)}
        />
      )}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{docs.length} document{docs.length !== 1 ? 's' : ''}</p>
        <div className="flex items-center gap-2">
          <ChunkedUploader
            projectId={projectId}
            onSuccess={handleUploadSuccess}
            onError={handleUploadError}
            disabled={pipelineRunning}
          />
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

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-4 bg-apex-50 border border-apex-200 rounded-lg px-4 py-2 text-sm">
          <span className="font-medium text-apex-700">{selectedIds.size} selected</span>
          <button
            onClick={handleBulkDelete}
            disabled={bulkDeleting}
            className="flex items-center gap-1 text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            {bulkDeleting ? 'Deleting…' : 'Delete Selected'}
          </button>
          <button
            onClick={() => { setSelectedIds(new Set()); setSelectAll(false); }}
            className="text-gray-500 hover:text-gray-700 font-medium"
          >
            Cancel
          </button>
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
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={selectAll}
                    onChange={toggleSelectAll}
                    className="rounded border-gray-300"
                  />
                </th>
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
                  <tr key={doc.id} className={`hover:bg-gray-50 ${selectedIds.has(doc.id) ? 'bg-apex-50' : ''}`}>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(doc.id)}
                        onChange={() => toggleSelect(doc.id)}
                        className="rounded border-gray-300"
                      />
                    </td>
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
                    <td className="px-4 py-3 flex items-center gap-1">
                      {doc.file_type === 'pdf' && (
                        <button
                          onClick={() => setViewingDoc({ id: doc.id, filename: doc.filename })}
                          className="p-1 rounded text-gray-300 hover:text-apex-600 hover:bg-apex-50 transition-colors"
                          title="View document"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                      )}
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
