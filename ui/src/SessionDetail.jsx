import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from './api'
import { subscribe } from './ws'

export default function SessionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setData(await api.getSession(id)) } catch (e) { setError(e.message) }
  }

  // Load once, then re-load whenever the backend pushes a state change (no polling).
  useEffect(() => {
    load()
    return subscribe(() => load())
  }, [id])

  if (!data) return <p className="muted">Loading...</p>
  const { meta, drafts, failed_markers = [] } = data

  const merge = async (draftId, intoId) => {
    setError('')
    try { await api.mergeDraft(id, draftId, intoId) } catch (e) { setError(e.message) }
  }

  return (
    <div className="panel">
      <button className="link" onClick={() => navigate('/')}>← Back</button>
      <h2>Session {id} <span className={`status status-${meta.status}`}>{meta.status}</span></h2>
      <p className="muted">{drafts.length} bugs processed / {meta.markers?.length || 0} marker(s)</p>
      {meta.error && <div className="error">{meta.error}</div>}
      {failed_markers.length > 0 && (
        <div className="error">⚠ {failed_markers.length} marker(s) failed to save a clip — that footage was lost. Re-capture those bugs if needed.</div>
      )}

      {drafts.map((d, i) => (
        <div key={d.id} className="session-row">
          <span style={{ cursor: 'pointer', flex: 1 }} onClick={() => navigate(`/sessions/${id}/bugs/${d.id}`)}>
            {d.type === 'capture' ? '📷' : '📹'} Bug #{d.id + 1} — {d.issue?.title || '(no title yet)'}
            {(d.screenshots?.length || 0) > 1 ? ` (${d.screenshots.length} ảnh)` : ''}
          </span>
          {/* merge into the previous bug - safety net for a bug that was split by mistake */}
          {i > 0 && d.status !== 'pushed' && (
            <button className="merge-btn" title={`Gộp vào Bug #${drafts[i - 1].id + 1}`}
                    onClick={() => merge(d.id, drafts[i - 1].id)}>⤴ gộp vào #{drafts[i - 1].id + 1}</button>
          )}
          {d.status === 'pushed'
            ? <span className="status status-done">✓ {d.jira_key}</span>
            : <span className="status status-recorded">draft</span>}
        </div>
      ))}
      {error && <div className="error">{error}</div>}
    </div>
  )
}
