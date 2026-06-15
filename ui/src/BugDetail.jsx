import { useEffect, useState } from 'react'
import { api } from './api'

export default function BugDetail({ sessionId, bugId, onBack }) {
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
      <div className="screenshots">
        {(draft.screenshots || []).map((f) => (
          <a key={f} href={api.fileUrl(sessionId, f)} target="_blank" rel="noreferrer">
            <img src={api.fileUrl(sessionId, f)} alt={f} />
          </a>
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
        {draft.audio
          ? <audio controls src={api.fileUrl(sessionId, draft.audio)} />
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
