import { useEffect, useState } from 'react'
import { api } from './api'

export default function SessionDetail({ id, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setData(await api.getSession(id)) } catch (e) { setError(e.message) }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 3000) // poll khi đang processing
    return () => clearInterval(t)
  }, [id])

  if (!data) return <p className="muted">Đang tải...</p>
  const { meta, drafts } = data

  return (
    <div className="panel">
      <button className="link" onClick={onBack}>← Quay lại</button>
      <h2>Session {id} <span className={`status status-${meta.status}`}>{meta.status}</span></h2>
      <p className="muted">{meta.markers?.length || 0} bug được đánh dấu · video: {meta.video_path}</p>
      {meta.error && <div className="error">{meta.error}</div>}

      {meta.video_path && (
        <video controls width="100%" src={api.videoUrl(id)} style={{ maxHeight: 420, background: '#000' }} />
      )}

      {meta.status === 'recorded' && (
        <button className="start" onClick={async () => { await api.processSession(id); load() }}>
          ▶ Xử lý session (transcript + tạo issue)
        </button>
      )}
      {meta.status === 'processing' && <p>⏳ Đang xử lý... (tự refresh)</p>}

      {drafts.map((d) => (
        <DraftCard key={d.id} sessionId={id} draft={d} onChanged={load} />
      ))}
      {error && <div className="error">{error}</div>}
    </div>
  )
}

function DraftCard({ sessionId, draft, onChanged }) {
  const [issue, setIssue] = useState(draft.issue)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setIssue({ ...issue, [k]: v })

  const save = async () => {
    setBusy(true)
    await api.updateDraft(sessionId, draft.id, issue)
    setBusy(false)
    onChanged()
  }

  const push = async () => {
    setBusy(true)
    await api.updateDraft(sessionId, draft.id, issue) // lưu chỉnh sửa trước khi push
    await api.pushDraft(sessionId, draft.id)
    setBusy(false)
    onChanged()
  }

  return (
    <div className="draft">
      <div className="row">
        <b>Bug #{draft.id + 1}</b>
        <span className="muted">tại {draft.marker_offset}s</span>
        {draft.status === 'pushed'
          ? <span className="status status-done">✓ {draft.jira_key}</span>
          : <span className="status status-recorded">draft</span>}
      </div>

      {/* Screenshots */}
      <div className="screenshots">
        {draft.screenshots.map((f) => (
          <a key={f} href={api.fileUrl(sessionId, f)} target="_blank" rel="noreferrer">
            <img src={api.fileUrl(sessionId, f)} alt={f} />
          </a>
        ))}
      </div>

      {/* So sánh transcript 2 engine */}
      <details>
        <summary>Transcript (so sánh engine)</summary>
        {Object.entries(draft.transcripts).map(([engine, text]) =>
          text ? <p key={engine}><b>{engine}:</b> {text}</p> : null
        )}
        <audio controls src={api.fileUrl(sessionId, `bug${draft.id}.wav`)} />
      </details>

      {/* Issue có thể sửa */}
      <label>Title
        <input value={issue.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      <label>Description
        <textarea rows={4} value={issue.description} onChange={(e) => set('description', e.target.value)} />
      </label>
      <label>Severity
        <select value={issue.severity} onChange={(e) => set('severity', e.target.value)}>
          {['low', 'medium', 'high', 'critical'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
      {issue.transcript_summary_vi && <p className="muted">🗣 {issue.transcript_summary_vi}</p>}

      {draft.status !== 'pushed' && (
        <div className="row">
          <button onClick={save} disabled={busy}>💾 Lưu</button>
          <button className="start" onClick={push} disabled={busy}>🚀 Push Jira</button>
        </div>
      )}
    </div>
  )
}
