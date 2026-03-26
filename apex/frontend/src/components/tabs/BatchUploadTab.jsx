import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Upload,
  FileArchive,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Loader,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import {
  uploadBatchZip,
  getBatchGroups,
  getBatchGroup,
  processBatchGroup,
  updateDocumentAssociation,
} from '../../api';

const DOCUMENT_ROLES = [
  'spec',
  'winest',
  'rfi',
  'drawing',
  'schedule',
  'addendum',
  'other',
];

function statusIcon(status) {
  switch (status) {
    case 'complete':
    case 'completed': return <CheckCircle className="h-4 w-4 text-green-500" />;
    case 'failed':
    case 'error':    return <XCircle className="h-4 w-4 text-red-500" />;
    case 'processing':
    case 'running':  return <Loader className="h-4 w-4 text-blue-500 animate-spin" />;
    default:         return <Clock className="h-4 w-4 text-gray-400" />;
  }
}

// ── Drop zone ──────────────────────────────────────────────────────────────

function DropZone({ onFile, disabled }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`flex flex-col items-center justify-center gap-3 p-12 rounded-xl border-2 border-dashed transition-colors cursor-pointer select-none ${
        disabled
          ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
          : dragging
          ? 'border-apex-500 bg-apex-50'
          : 'border-gray-300 hover:border-apex-400 hover:bg-gray-50'
      }`}
    >
      <FileArchive className={`h-12 w-12 ${dragging ? 'text-apex-500' : 'text-gray-300'}`} />
      <div className="text-center">
        <p className="font-medium text-gray-700">Drop a .zip file here</p>
        <p className="text-sm text-gray-400 mt-1">or click to browse</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".zip"
        className="hidden"
        disabled={disabled}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ''; }}
      />
    </div>
  );
}

// ── Upload progress ────────────────────────────────────────────────────────

function ProgressBar({ value }) {
  return (
    <div className="w-full bg-gray-200 rounded-full h-2.5">
      <div
        className="bg-apex-600 h-2.5 rounded-full transition-all duration-200"
        style={{ width: `${value}%` }}
      />
    </div>
  );
}

// ── File type counts ────────────────────────────────────────────────────────

function FileTypeSummary({ counts }) {
  if (!counts || Object.keys(counts).length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3 mt-3">
      {Object.entries(counts).map(([type, count]) => (
        <div key={type} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-lg">
          <span className="text-xs font-medium uppercase text-gray-500">{type}</span>
          <span className="text-sm font-bold text-gray-900">{count}</span>
        </div>
      ))}
    </div>
  );
}

// ── WebSocket processing status ─────────────────────────────────────────────

function useGroupWebSocket(groupId, onUpdate) {
  const wsRef = useRef(null);
  const heartbeatRef = useRef(null);
  const [wsMode, setWsMode] = useState('disconnected'); // 'live' | 'polling' | 'disconnected'

  useEffect(() => {
    if (!groupId) return;

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${window.location.host}/ws/batch-import/${groupId}`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;
    } catch (_) {
      setWsMode('polling');
      return;
    }

    ws.onopen = () => {
      setWsMode('live');
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== 'ping' && msg.type !== 'pong') onUpdate(msg);
      } catch (_) {}
    };

    ws.onerror = () => setWsMode('polling');
    ws.onclose = () => {
      setWsMode('disconnected');
      clearInterval(heartbeatRef.current);
    };

    return () => {
      clearInterval(heartbeatRef.current);
      ws.close();
    };
  }, [groupId, onUpdate]);

  return wsMode;
}

// ── Group detail view ──────────────────────────────────────────────────────

function GroupDetail({ groupId, onClose }) {
  const [group, setGroup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [err, setErr] = useState('');
  const [processingStatus, setProcessingStatus] = useState({});

  const load = useCallback(() => {
    setLoading(true);
    getBatchGroup(groupId)
      .then(setGroup)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [groupId]);

  useEffect(() => { load(); }, [load]);

  const handleWsUpdate = useCallback((msg) => {
    setProcessingStatus((prev) => ({ ...prev, ...msg }));
    // Refresh group data on completion
    if (msg.status === 'complete' || msg.status === 'completed') load();
  }, [load]);

  const wsMode = useGroupWebSocket(processing ? groupId : null, handleWsUpdate);

  const handleRoleChange = async (assocId, role) => {
    try {
      await updateDocumentAssociation(assocId, { role });
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const handleProcess = async () => {
    setProcessing(true);
    setErr('');
    try {
      await processBatchGroup(groupId);
    } catch (e) {
      setErr(e.message);
      setProcessing(false);
    }
  };

  return (
    <div className="card p-4 mt-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">
          Group Detail
          {group && <span className="ml-2 text-gray-400 font-normal text-sm">— {group.name}</span>}
        </h3>
        <div className="flex items-center gap-2">
          {processing && (
            <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full ${
              wsMode === 'live' ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'
            }`}>
              {wsMode === 'live' ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {wsMode === 'live' ? 'Live' : 'Polling'}
            </span>
          )}
          <button onClick={load} className="btn-secondary p-1.5">
            <RefreshCw className="h-4 w-4" />
          </button>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {err && <p className="text-red-600 text-sm mb-3">{err}</p>}

      {loading ? (
        <p className="text-gray-400 text-sm">Loading…</p>
      ) : group && (
        <>
          {/* Processing status from WS */}
          {processing && processingStatus.message && (
            <div className="mb-4 p-3 bg-blue-50 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Loader className="h-4 w-4 text-blue-600 animate-spin" />
                <span className="text-sm font-medium text-blue-800">Processing…</span>
              </div>
              {processingStatus.progress != null && (
                <ProgressBar value={processingStatus.progress} />
              )}
              <p className="text-xs text-blue-600 mt-1">{processingStatus.message}</p>
            </div>
          )}

          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-200">
                  <th className="pb-2 pr-4">Filename</th>
                  <th className="pb-2 pr-4">Detected Role</th>
                  <th className="pb-2 pr-4">Reclassify</th>
                  <th className="pb-2">Parse Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(group.documents ?? []).map((doc) => (
                  <tr key={doc.id || doc.filename}>
                    <td className="py-2 pr-4 font-medium text-gray-800 max-w-xs truncate">
                      {doc.filename}
                    </td>
                    <td className="py-2 pr-4 text-gray-600 capitalize">
                      {doc.role ?? '—'}
                    </td>
                    <td className="py-2 pr-4">
                      <select
                        className="input text-xs py-1 w-32"
                        value={doc.role ?? ''}
                        onChange={(e) => handleRoleChange(doc.association_id ?? doc.id, e.target.value)}
                      >
                        <option value="">— keep —</option>
                        {DOCUMENT_ROLES.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2">
                      <span className="flex items-center gap-1.5 capitalize">
                        {statusIcon(doc.parse_status)}
                        <span className="text-xs text-gray-600">{doc.parse_status ?? 'pending'}</span>
                      </span>
                    </td>
                  </tr>
                ))}
                {(group.documents ?? []).length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-4 text-center text-gray-400">No documents in this group</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <button
            onClick={handleProcess}
            disabled={processing}
            className="btn-primary flex items-center gap-2"
          >
            {processing ? (
              <><Loader className="h-4 w-4 animate-spin" /> Processing…</>
            ) : (
              <><RefreshCw className="h-4 w-4" /> Process Group</>
            )}
          </button>
        </>
      )}
    </div>
  );
}

// ── Groups table ───────────────────────────────────────────────────────────

function GroupsTable({ groups, selectedGroupId, onSelect }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="font-semibold text-gray-900">Document Groups</h3>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Group Name</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Files</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Parse Status</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {groups.map((g) => (
            <tr
              key={g.id}
              className={`cursor-pointer hover:bg-gray-50 ${selectedGroupId === g.id ? 'bg-apex-50' : ''}`}
              onClick={() => onSelect(selectedGroupId === g.id ? null : g.id)}
            >
              <td className="px-4 py-2.5 font-medium text-gray-900 flex items-center gap-2">
                {selectedGroupId === g.id
                  ? <ChevronDown className="h-4 w-4 text-apex-600" />
                  : <ChevronRight className="h-4 w-4 text-gray-400" />
                }
                {g.name}
              </td>
              <td className="px-4 py-2.5 text-gray-600">{g.file_count ?? g.document_count ?? '—'}</td>
              <td className="px-4 py-2.5">
                <span className="flex items-center gap-1.5">
                  {statusIcon(g.parse_status)}
                  <span className="capitalize text-xs text-gray-600">{g.parse_status ?? 'pending'}</span>
                </span>
              </td>
              <td className="px-4 py-2.5 text-gray-500 text-xs">
                {g.created_at ? new Date(g.created_at).toLocaleString() : '—'}
              </td>
            </tr>
          ))}
          {groups.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-gray-400">No groups yet</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function BatchUploadTab() {
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadErr, setUploadErr] = useState('');

  const [groups, setGroups] = useState([]);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [selectedGroupId, setSelectedGroupId] = useState(null);

  const loadGroups = useCallback(() => {
    setLoadingGroups(true);
    getBatchGroups()
      .then((data) => setGroups(Array.isArray(data) ? data : data?.items ?? []))
      .catch(() => {})
      .finally(() => setLoadingGroups(false));
  }, []);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const handleFile = async (file) => {
    if (!file.name.endsWith('.zip')) {
      setUploadErr('Only .zip files are supported.');
      return;
    }
    setUploading(true);
    setUploadErr('');
    setUploadResult(null);
    setUploadProgress(0);

    try {
      const result = await uploadBatchZip(file, setUploadProgress);
      setUploadResult(result);
      loadGroups();
    } catch (e) {
      setUploadErr(e.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Upload zone */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">Batch Import</h2>
        <p className="text-sm text-gray-500 mb-4">
          Upload a .zip archive containing specs, WinEst exports, RFIs, drawings, or other project documents.
          Files will be automatically grouped and classified.
        </p>

        <DropZone onFile={handleFile} disabled={uploading} />

        {uploading && (
          <div className="mt-4 space-y-2">
            <div className="flex justify-between text-sm text-gray-600">
              <span>Uploading…</span>
              <span>{uploadProgress}%</span>
            </div>
            <ProgressBar value={uploadProgress} />
          </div>
        )}

        {uploadErr && (
          <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{uploadErr}</div>
        )}

        {uploadResult && (
          <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <span className="font-medium text-green-800">Upload complete</span>
            </div>
            {uploadResult.groups_created != null && (
              <p className="text-sm text-green-700">
                {uploadResult.groups_created} group{uploadResult.groups_created !== 1 ? 's' : ''} created
              </p>
            )}
            {uploadResult.file_counts && (
              <>
                <p className="text-sm text-green-700 mt-1">Files detected by type:</p>
                <FileTypeSummary counts={uploadResult.file_counts} />
              </>
            )}
          </div>
        )}
      </div>

      {/* Groups table */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Import Groups</h2>
        <button
          onClick={loadGroups}
          disabled={loadingGroups}
          className="btn-secondary flex items-center gap-1.5 text-sm"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loadingGroups ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <GroupsTable
        groups={groups}
        selectedGroupId={selectedGroupId}
        onSelect={setSelectedGroupId}
      />

      {selectedGroupId && (
        <GroupDetail
          groupId={selectedGroupId}
          onClose={() => setSelectedGroupId(null)}
        />
      )}
    </div>
  );
}
