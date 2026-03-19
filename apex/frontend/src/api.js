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
  return res.json();
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

// ── Agent Pipeline ────────────────────────────────────
export const runAgents = (projectId) =>
  request(`/projects/${projectId}/run-agents`, { method: 'POST' });

export const getAgentLogs = (projectId) =>
  request(`/projects/${projectId}/agent-logs`);

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
