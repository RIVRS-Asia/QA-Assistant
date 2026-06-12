// Gọi backend FastAPI (qua vite proxy /api)
async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  status: () => request('/status'),
  startSession: () => request('/session/start', { method: 'POST' }),
  stopSession: () => request('/session/stop', { method: 'POST' }),
  listSessions: () => request('/sessions'),
  getSession: (id) => request(`/sessions/${id}`),
  processSession: (id) => request(`/sessions/${id}/process`, { method: 'POST' }),
  updateDraft: (id, draftId, issue) =>
    request(`/sessions/${id}/drafts/${draftId}`, { method: 'PUT', body: JSON.stringify(issue) }),
  pushDraft: (id, draftId) =>
    request(`/sessions/${id}/drafts/${draftId}/push`, { method: 'POST' }),
  fileUrl: (id, filename) => `/api/sessions/${id}/files/${filename}`,
}
