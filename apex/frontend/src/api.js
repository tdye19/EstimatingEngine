/**
 * Thin API wrapper — all calls go through the Vite proxy to /api.
 */

const BASE = '/api';

async function request(path, options = {}) {
  const token = localStorage.getItem('apex_token');
  const headers = { ...options.headers };

  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('apex_token');
    window.location.href = '/login';
    return;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }

  if (res.status === 204) return null;
  const json = await res.json();
  // Unwrap APIResponse envelope { success, message, data, error } used by all
  // endpoints except /auth/login (which returns TokenResponse directly).
  if (json !== null && typeof json === 'object' && 'success' in json) {
    return json.data !== undefined ? json.data : null;
  }
  return json;
}

// ── Auth ──────────────────────────────────────────────
export const login = (email, password) =>
  request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });

export const register = (data) =>
  request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });

// ── Projects ──────────────────────────────────────────
export const listProjects = () => request('/projects');

export const getProject = (id) => request(`/projects/${id}`);

export const createProject = (data) =>
  request('/projects', { method: 'POST', body: JSON.stringify(data) });

export const updateProject = (id, data) =>
  request(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) });

// ── Documents ─────────────────────────────────────────
export const listDocuments = (projectId) =>
  request(`/projects/${projectId}/documents`);

export const uploadDocument = (projectId, file) => {
  const form = new FormData();
  form.append('file', file);
  return request(`/projects/${projectId}/documents`, {
    method: 'POST',
    body: form,
  });
};

// ── Chunked Upload ─────────────────────────────────────
export const initChunkedUpload = (projectId, filename, fileSize, contentType) =>
  request(`/projects/${projectId}/documents/upload/init`, {
    method: 'POST',
    body: JSON.stringify({ filename, file_size: fileSize, content_type: contentType }),
  });

export const uploadChunk = (projectId, uploadId, chunkNumber, chunkBlob) => {
  const form = new FormData();
  form.append('chunk', chunkBlob, `chunk_${chunkNumber}`);
  return request(
    `/projects/${projectId}/documents/upload/${uploadId}/chunk?chunk_number=${chunkNumber}`,
    { method: 'POST', body: form },
  );
};

export const completeChunkedUpload = (projectId, uploadId) =>
  request(`/projects/${projectId}/documents/upload/${uploadId}/complete`, { method: 'POST' });

// ── Delete ────────────────────────────────────────────
export const deleteProject = (id) =>
  request(`/projects/${id}`, { method: 'DELETE' });

export const deleteDocument = (projectId, docId) =>
  request(`/projects/${projectId}/documents/${docId}`, { method: 'DELETE' });

// ── Agent Pipeline ────────────────────────────────────
export const runAgents = (projectId) =>
  request(`/projects/${projectId}/run-agents`, { method: 'POST' });

export const runAgent = (projectId, agentNumber) =>
  request(`/projects/${projectId}/agents/${agentNumber}/run`, { method: 'POST' });

export const getAgentLogs = (projectId) =>
  request(`/projects/${projectId}/agent-logs`);

export const runPipeline = (projectId, documentId = null) => {
  const qs = documentId ? `?document_id=${documentId}` : '';
  return request(`/projects/${projectId}/pipeline/run${qs}`, { method: 'POST' });
};

export const getPipelineStatus = (projectId) =>
  fetch(`${BASE}/projects/${projectId}/pipeline/status`, {
    headers: (() => {
      const token = localStorage.getItem('apex_token');
      return token ? { Authorization: `Bearer ${token}` } : {};
    })(),
  }).then((res) => {
    if (!res.ok) throw new Error('Failed to fetch pipeline status');
    return res.json();
  });

// ── Reports ───────────────────────────────────────────
export const getGapReport = (projectId) =>
  request(`/projects/${projectId}/gap-report`);

export const getTakeoff = (projectId) =>
  request(`/projects/${projectId}/takeoff`);

export const updateTakeoffItem = (projectId, itemId, data) =>
  request(`/projects/${projectId}/takeoff/${itemId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });

export const getLaborEstimates = (projectId) =>
  request(`/projects/${projectId}/labor-estimates`);

export const getEstimate = (projectId) =>
  request(`/projects/${projectId}/estimate`);

export const getVariance = (projectId) =>
  request(`/projects/${projectId}/variance`);

// ── Actuals ───────────────────────────────────────────
export const uploadActuals = (projectId, file) => {
  const form = new FormData();
  form.append('file', file);
  return request(`/projects/${projectId}/actuals`, {
    method: 'POST',
    body: form,
  });
};

// ── Spec Sections ─────────────────────────────────────
export const getSpecSections = (projectId) =>
  request(`/projects/${projectId}/spec-sections`);

// ── Exports (blob downloads) ──────────────────────────
async function downloadBlob(path, filename) {
  const token = localStorage.getItem('apex_token');
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { headers });
  if (res.status === 401) {
    localStorage.removeItem('apex_token');
    window.location.href = '/login';
    return;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Download failed');
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export const exportEstimatePdf = (projectId, projectNumber) =>
  downloadBlob(`/exports/projects/${projectId}/estimate/pdf`, `${projectNumber}_estimate.pdf`);

export const exportEstimateXlsx = (projectId, projectNumber) =>
  downloadBlob(`/exports/projects/${projectId}/estimate/xlsx`, `${projectNumber}_estimate.xlsx`);

// ── Token Usage / Cost Tracking ───────────────────────
export const getProjectTokenUsage = (projectId) =>
  request(`/projects/${projectId}/token-usage`);

export const getTokenUsageSummary = (projectId = null) => {
  const qs = projectId ? `?project_id=${projectId}` : '';
  return request(`/token-usage/summary${qs}`);
};

// ── Productivity Library ──────────────────────────────
export const getProductivityLibrary = (params) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/productivity-library${qs ? `?${qs}` : ''}`);
};

export const updateProductivityRate = (csiCode, data) =>
  request(`/productivity-library/${csiCode}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
