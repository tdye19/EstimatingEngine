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
    throw new Error('Session expired — please log in again');
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

export function getDocumentFileUrl(projectId, docId) {
  const token = localStorage.getItem('apex_token');
  return `${BASE}/projects/${projectId}/documents/${docId}/file?token=${token}`;
}

// ── Delete ────────────────────────────────────────────
export const deleteProject = (id) =>
  request(`/projects/${id}`, { method: 'DELETE' });

export const deleteDocument = (projectId, docId) =>
  request(`/projects/${projectId}/documents/${docId}`, { method: 'DELETE' });

export async function bulkDeleteDocuments(projectId, documentIds) {
  return request(`/projects/${projectId}/documents/bulk-delete`, {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

export async function bulkUpdateTakeoff(projectId, itemIds, updates) {
  return request(`/projects/${projectId}/takeoff/bulk-update`, {
    method: 'PUT',
    body: JSON.stringify({ item_ids: itemIds, updates }),
  });
}

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

export async function updateEstimateMarkups(projectId, estimateId, data) {
  return request(`/projects/${projectId}/estimate/${estimateId}/markups`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export const getVariance = (projectId) =>
  request(`/projects/${projectId}/variance`);

export async function getEstimateVersions(projectId) {
  return request(`/projects/${projectId}/estimates`);
}
export async function getEstimateByVersion(projectId, version) {
  return request(`/projects/${projectId}/estimates/${version}`);
}

export async function cloneProject(projectId) {
  return request(`/projects/${projectId}/clone`, { method: 'POST' });
}

// ── Actuals ───────────────────────────────────────────
export const uploadActuals = (projectId, file) => {
  const form = new FormData();
  form.append('file', file);
  return request(`/projects/${projectId}/actuals`, {
    method: 'POST',
    body: form,
  });
};

export async function submitActualEntry(projectId, data) {
  return request(`/projects/${projectId}/actuals/entry`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

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
    throw new Error('Session expired — please log in again');
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

export const exportEstimateCsv = (projectId, projectNumber) =>
  downloadBlob(`/exports/projects/${projectId}/estimate/csv`, `${projectNumber}_estimate.csv`);

export const exportEstimateQb = (projectId, projectNumber) =>
  downloadBlob(`/exports/projects/${projectId}/estimate/qb`, `${projectNumber}_estimate.iif`);

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

// ── Admin - Users ────────────────────────────────────
export async function listUsers(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/admin/users${query ? '?' + query : ''}`);
}
export async function updateUser(userId, data) {
  return request(`/admin/users/${userId}`, { method: 'PUT', body: JSON.stringify(data) });
}

// ── Admin - Organizations ────────────────────────────
export async function listOrganizations() {
  return request('/admin/organizations');
}
export async function createOrganization(data) {
  return request('/admin/organizations', { method: 'POST', body: JSON.stringify(data) });
}
export async function updateOrganization(orgId, data) {
  return request(`/admin/organizations/${orgId}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function deleteOrganization(orgId) {
  return request(`/admin/organizations/${orgId}`, { method: 'DELETE' });
}

// ── Material Prices ──────────────────────────────────
export async function getMaterialPrices(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/material-prices${query ? '?' + query : ''}`);
}
export async function createMaterialPrice(data) {
  return request('/material-prices', { method: 'POST', body: JSON.stringify(data) });
}
export async function updateMaterialPrice(priceId, data) {
  return request(`/material-prices/${priceId}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function deleteMaterialPrice(priceId) {
  return request(`/material-prices/${priceId}`, { method: 'DELETE' });
}

// ── Bid Comparisons ────────────────────────────────────
export const getBidComparisons = (projectId) =>
  request(`/projects/${projectId}/bid-comparisons`);

export const createBidComparison = (projectId, data) =>
  request(`/projects/${projectId}/bid-comparisons`, {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const deleteBidComparison = (projectId, compId) =>
  request(`/projects/${projectId}/bid-comparisons/${compId}`, { method: 'DELETE' });

export const getBidComparisonOverlay = (projectId) =>
  request(`/projects/${projectId}/bid-comparisons/overlay`);

// ── Change Orders ──────────────────────────────────────
export const getChangeOrders = (projectId) =>
  request(`/projects/${projectId}/change-orders`);

export const createChangeOrder = (projectId, data) =>
  request(`/projects/${projectId}/change-orders`, {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const updateChangeOrder = (projectId, coId, data) =>
  request(`/projects/${projectId}/change-orders/${coId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });

export const deleteChangeOrder = (projectId, coId) =>
  request(`/projects/${projectId}/change-orders/${coId}`, { method: 'DELETE' });

export const getChangeOrderSummary = (projectId) =>
  request(`/projects/${projectId}/change-orders/summary`);

// ── Estimate Versioning ────────────────────────────────
export const getEstimateVersion = (projectId, version) =>
  request(`/projects/${projectId}/estimate/versions/${version}`);

export const snapshotEstimate = (projectId) =>
  request(`/projects/${projectId}/estimate/snapshot`, { method: 'POST' });

// ── Subcontractor Packages ────────────────────────────
export const listSubcontractorPackages = (projectId) =>
  request(`/exports/projects/${projectId}/subcontractor-packages/list`)
    .then((d) => d?.data ?? d);

export const downloadSubcontractorPackage = (projectId, trade, filename) =>
  downloadBlob(`/exports/projects/${projectId}/subcontractor-packages/${trade}`, filename);

// ── Material Price Lookup & Benchmarks ────────────────
export const lookupMaterialPrice = (csiCode, description, unit) =>
  request('/material-prices/lookup', {
    method: 'POST',
    body: JSON.stringify({ csi_code: csiCode, description, unit }),
  });

export const getMaterialBenchmarks = () => request('/material-prices/benchmarks');

export const getProjectMaterialCosts = (projectId) =>
  request(`/material-prices/projects/${projectId}/material-costs`);

// ── Benchmarking ─────────────────────────────────────
export const getBenchmarkProjects = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/benchmarking/projects${qs ? `?${qs}` : ''}`);
};

export const getDivisionTrends = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/benchmarking/division-trends${qs ? `?${qs}` : ''}`);
};

// ── User Profile & Roles ──────────────────────────────
export const getMe = () => request('/users/me');

export const updateUserRole = (userId, role) =>
  request(`/users/${userId}/role`, {
    method: 'PUT',
    body: JSON.stringify({ role }),
  });

export const deactivateUser = (userId) =>
  request(`/users/${userId}`, { method: 'DELETE' });

// ── Notifications ─────────────────────────────────────
export const getNotificationSettings = () => request('/notifications/settings');

export const sendTestNotification = () =>
  request('/notifications/test', { method: 'POST' });

// ── Estimate Library ──────────────────────────────────
export const getEstimateLibrary = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/estimate-library/${qs ? `?${qs}` : ''}`);
};

export const getEstimateLibraryEntry = (entryId) =>
  request(`/estimate-library/${entryId}`);

export const createEstimateLibraryEntry = (data) =>
  request('/estimate-library/', { method: 'POST', body: JSON.stringify(data) });

export const updateEstimateLibraryEntry = (entryId, data) =>
  request(`/estimate-library/${entryId}`, { method: 'PUT', body: JSON.stringify(data) });

export const deleteEstimateLibraryEntry = (entryId) =>
  request(`/estimate-library/${entryId}`, { method: 'DELETE' });

export const getEstimateLibraryStats = () =>
  request('/estimate-library/stats/summary');

export const compareEstimates = (ids) =>
  request(`/estimate-library/compare?ids=${ids.join(',')}`);

// ── Batch Import ──────────────────────────────────────
export const uploadBatchZip = (file, onProgress) => {
  const form = new FormData();
  form.append('file', file);
  return new Promise((resolve, reject) => {
    const token = localStorage.getItem('apex_token');
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/batch-import/upload-zip`);
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status === 401) {
        localStorage.removeItem('apex_token');
        window.location.href = '/login';
        reject(new Error('Session expired — please log in again'));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        const json = JSON.parse(xhr.responseText);
        resolve(json.data !== undefined ? json.data : json);
      } else {
        let err = {};
        try { err = JSON.parse(xhr.responseText); } catch (_) {}
        reject(new Error(err.detail || 'Upload failed'));
      }
    };
    xhr.onerror = () => reject(new Error('Network error'));
    xhr.send(form);
  });
};

export const getBatchGroups = () => request('/batch-import/groups');

export const getBatchGroup = (groupId) => request(`/batch-import/groups/${groupId}`);

export const processBatchGroup = (groupId) =>
  request(`/batch-import/process-group/${groupId}`, { method: 'POST' });

export const updateDocumentAssociation = (assocId, data) =>
  request(`/batch-import/associations/${assocId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });

export const processWinest = (assocId) =>
  request(`/batch-import/process-winest/${assocId}`, { method: 'POST' });

// ── Benchmarks ────────────────────────────────────────
export const getBenchmarks = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/benchmarks/${qs ? `?${qs}` : ''}`);
};

export const getBenchmarkSummary = () => request('/benchmarks/summary');

export const getBenchmarkDetail = (csiCode) =>
  request(`/benchmarks/${encodeURIComponent(csiCode)}`);

export const recomputeBenchmarks = () =>
  request('/benchmarks/compute', { method: 'POST' });
