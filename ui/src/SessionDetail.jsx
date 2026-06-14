import { useEffect, useState } from 'react'
import { api } from './api'

export default function SessionDetail({ id, onBack, onOpenBug }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setData(await api.getSession(id)) } catch (e) { setError(e.message) }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 3000) // poll while processing
    return () => clearInterval(t)
  }, [id])

  if (!data) return <p className="muted">Loading...</p>
  const { meta, drafts } = data

  return (
    <div className="panel">
      <button className="link" onClick={onBack}>← Back</button>
      <h2>Session {id} <span className={`status status-${meta.status}`}>{meta.status}</span></h2>
      <p className="muted">{drafts.length} bugs processed / {meta.markers?.length || 0} marked</p>
      {meta.error && <div className="error">{meta.error}</div>}

      {drafts.map((d) => (
        <div key={d.id} className="session-row" onClick={() => onOpenBug(d.id)}>
          <span>{d.type === 'capture' ? '📷' : '📹'} Bug #{d.id + 1} — {d.issue?.title || '(no title yet)'}</span>
          {d.status === 'pushed'
            ? <span className="status status-done">✓ {d.jira_key}</span>
            : <span className="status status-recorded">draft</span>}
        </div>
      ))}
      {error && <div className="error">{error}</div>}
    </div>
  )
}
