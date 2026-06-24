// Session id "20260618_143022" (machine time, VN timezone) -> "18/06/2026 14:30:22"
export function fmtSession(id) {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(id || '')
  if (!m) return id
  const [, y, mo, d, h, mi, s] = m
  return `${d}/${mo}/${y} ${h}:${mi}:${s}`
}

// Call FastAPI backend (via vite proxy /api)
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
  listBugs: () => request('/bugs'),
  getSession: (id) => request(`/sessions/${id}`),
  // ver (optional) selects a result version; omitted -> the bug's default version
  getBug: (id, bugId, ver) => request(`/sessions/${id}/bugs/${bugId}${ver == null ? '' : `?ver=${ver}`}`),
  updateDraft: (id, draftId, issue, ver) =>
    request(`/sessions/${id}/drafts/${draftId}${ver == null ? '' : `?ver=${ver}`}`, { method: 'PUT', body: JSON.stringify(issue) }),
  pushDraft: (id, draftId, ver) =>
    request(`/sessions/${id}/drafts/${draftId}/push${ver == null ? '' : `?ver=${ver}`}`, { method: 'POST' }),
  deleteScreenshot: (id, draftId, filename, ver) =>
    request(`/sessions/${id}/drafts/${draftId}/screenshots/${filename}${ver == null ? '' : `?ver=${ver}`}`, { method: 'DELETE' }),
  swapScreenshot: (id, draftId, filename, to, ver) =>
    request(`/sessions/${id}/drafts/${draftId}/screenshots/${filename}/swap${ver == null ? '' : `?ver=${ver}`}`, { method: 'PUT', body: JSON.stringify({ to }) }),
  mergeDraft: (id, draftId, intoId) =>
    request(`/sessions/${id}/drafts/${draftId}/merge`, { method: 'POST', body: JSON.stringify({ into_id: intoId }) }),
  reprocessBug: (id, draftId, transcripts) =>
    request(`/sessions/${id}/drafts/${draftId}/reprocess`, { method: 'POST', body: JSON.stringify({ transcripts }) }),
  setDefaultVersion: (id, draftId, ver) =>
    request(`/sessions/${id}/drafts/${draftId}/default`, { method: 'PUT', body: JSON.stringify({ ver }) }),
  fileUrl: (id, filename) => `/api/sessions/${id}/files/${filename}`,
  saveAnnotation: (id, filename, dataUrl) =>
    request(`/sessions/${id}/files/${filename}/annotate`, { method: 'PUT', body: JSON.stringify({ dataUrl }) }),
}
