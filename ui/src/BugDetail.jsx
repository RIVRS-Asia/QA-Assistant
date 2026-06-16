import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from './api'

export default function BugDetail() {
  const { sessionId, bugId: bugIdParam } = useParams()
  const bugId = Number(bugIdParam)
  const navigate = useNavigate()
  const onBack = () => navigate(`/sessions/${sessionId}`)
  const [draft, setDraft] = useState(null)
  const [issue, setIssue] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const d = await api.getBug(sessionId, bugId)
      setDraft(d)
      setIssue(d.issue)
    } catch (e) { setError(e.message) }
  }

  useEffect(() => { load() }, [sessionId, bugId])

  if (error) return <div className="panel"><button className="link" onClick={onBack}>← Back</button><div className="error">{error}</div></div>
  if (!draft) return <p className="muted">Loading...</p>

  const set = (k, v) => setIssue({ ...issue, [k]: v })

  const save = async () => {
    setBusy(true)
    await api.updateDraft(sessionId, bugId, issue)
    setBusy(false)
    load()
  }

  const push = async () => {
    setBusy(true)
    await api.updateDraft(sessionId, bugId, issue) // save edits before pushing
    await api.pushDraft(sessionId, bugId)
    setBusy(false)
    load()
  }

  const removeImage = async (filename) => {
    if (!window.confirm('Gỡ ảnh này khỏi bug? Ảnh sẽ bị xóa và không khôi phục được.')) return
    setBusy(true)
    try { await api.deleteScreenshot(sessionId, bugId, filename) } catch (e) { setError(e.message) }
    setBusy(false)
    load()
  }

  return (
    <div className="panel">
      <button className="link" onClick={onBack}>← Back</button>
      <h2>
        {draft.type === 'capture' ? '📷' : '📹'} Bug #{bugId + 1}
        {draft.status === 'pushed'
          ? (draft.jira_url
              ? <a className="status status-done" href={draft.jira_url} target="_blank" rel="noreferrer" style={{ marginLeft: 8 }}>✓ {draft.jira_key}</a>
              : <span className="status status-done" style={{ marginLeft: 8 }}>✓ {draft.jira_key}</span>)
          : <span className="status status-recorded" style={{ marginLeft: 8 }}>draft</span>}
      </h2>
      <p className="muted">Session {sessionId}</p>

      {/* Video clip (record) or image (capture) */}
      {draft.video_clip && (
        <video controls width="100%" src={api.fileUrl(sessionId, draft.video_clip)}
               style={{ maxHeight: 360, background: '#000' }} />
      )}
      {(draft.screenshots || []).length > 0 && (
        <p className="muted">{draft.screenshots.length} ảnh — bấm nút đỏ ở góc ảnh để gỡ ảnh gắn nhầm.</p>
      )}
      <div className="screenshots">
        {(draft.screenshots || []).map((f) => (
          <div key={f} className="shot">
            <a href={api.fileUrl(sessionId, f)} target="_blank" rel="noreferrer">
              <img src={api.fileUrl(sessionId, f)} alt={f} />
            </a>
            {draft.status !== 'pushed' && (
              <button className="img-del" title="Gỡ ảnh này khỏi bug" disabled={busy}
                      onClick={() => removeImage(f)} aria-label="Xóa ảnh">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 6h18" />
                  <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  <path d="M10 11v6M14 11v6" />
                </svg>
              </button>
            )}
          </div>
        ))}
      </div>
      {!draft.video_clip && (draft.screenshots || []).length === 0 && (
        <p className="muted">No {draft.type === 'capture' ? 'image' : 'video'} yet — check that ffmpeg is installed & in PATH.</p>
      )}

      {/* Raw transcript (engine comparison) */}
      <details open>
        <summary>Transcript (QA verbal description)</summary>
        {Object.entries(draft.transcripts || {}).map(([engine, text]) =>
          text ? <p key={engine}><b>{engine}:</b> {text}</p> : null
        )}
        {(draft.audios || []).length > 0
          ? (draft.audios || []).map((a) => <audio key={a} controls src={api.fileUrl(sessionId, a)} style={{ display: 'block', marginTop: 4 }} />)
          : <p className="muted">No mic audio yet (ffmpeg is needed to extract it from the OBS clip).</p>}
      </details>

      {/* Text extracted by LLM from transcript = issue (editable) */}
      <h3 style={{ fontSize: 14, margin: '14px 0 4px' }}>Issue (LLM-generated from transcript)</h3>
      <label>Title
        <input value={issue.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      {issue.repro_steps?.length > 0 && (
        <details open>
          <summary>Steps to reproduce</summary>
          <ol>{issue.repro_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </details>
      )}
      <label>Actual Result
        <textarea rows={3} value={issue.actual_result || ''} onChange={(e) => set('actual_result', e.target.value)} />
      </label>
      <label>Expected Result
        <textarea rows={3} value={issue.expected_result || ''} onChange={(e) => set('expected_result', e.target.value)} />
      </label>
      <label>Priority
        <select value={issue.priority || 'Medium'} onChange={(e) => set('priority', e.target.value)}>
          {['Low', 'Medium', 'High'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
      {issue.labels?.length > 0 && (
        <p className="muted">🏷 {issue.labels.join(', ')}</p>
      )}
      {issue.transcript_summary_vi && <p className="muted">🗣 {issue.transcript_summary_vi}</p>}

      {draft.status !== 'pushed' && (
        <div className="row">
          <button onClick={save} disabled={busy}>💾 Save</button>
          <button className="start" onClick={push} disabled={busy}>🚀 Push Jira</button>
        </div>
      )}
    </div>
  )
}
