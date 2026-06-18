import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import * as markerjs2 from 'markerjs2'
import Lightbox from 'yet-another-react-lightbox'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import 'yet-another-react-lightbox/styles.css'
import { api, fmtSession } from './api'

export default function BugDetail() {
  const { sessionId, bugId: bugIdParam } = useParams()
  const bugId = Number(bugIdParam)
  const navigate = useNavigate()
  const onBack = () => navigate(`/sessions/${sessionId}`)
  const [draft, setDraft] = useState(null)
  const [issue, setIssue] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [ver, setVer] = useState({})        // cache-bust per filename after annotating
  const [lightbox, setLightbox] = useState(-1)  // open screenshot index, -1 = closed
  const [copied, setCopied] = useState(false)
  const imgRefs = useRef({})

  const annotate = (f) => {
    const img = imgRefs.current[f]
    if (!img) return
    const ma = new markerjs2.MarkerArea(img)
    ma.settings.displayMode = 'popup'
    ma.renderAtNaturalSize = true        // export at original resolution, not the scaled-down on-screen size
    ma.renderImageType = 'image/png'     // lossless
    ma.addEventListener('render', async (ev) => {
      try { await api.saveAnnotation(sessionId, f, ev.dataUrl) } catch (e) { setError(e.message) }
      setVer((v) => ({ ...v, [f]: (v[f] || 0) + 1 }))  // force <img> reload
    })
    ma.show()
  }

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

  const copyImage = async (f) => {
    try {
      const blob = await (await fetch(`${api.fileUrl(sessionId, f)}?v=${ver[f] || 0}`)).blob()
      // ponytail: clipboard only accepts png; convert via canvas if the source isn't already png
      const png = blob.type === 'image/png' ? blob : await new Promise((res) => {
        const img = new Image(); img.crossOrigin = 'anonymous'
        img.onload = () => {
          const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight
          c.getContext('2d').drawImage(img, 0, 0); c.toBlob(res, 'image/png')
        }
        img.src = URL.createObjectURL(blob)
      })
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })])
    } catch (e) { setError(e.message) }
  }

  const copyText = async () => {
    const lines = [
      `Bug Display: ${issue.title || ''}`,
      'Step to reproduce:',
      ...(issue.repro_steps || []).map((s, i) => `${i + 1}. ${s}`),
      'Actual Result:',
      issue.actual_result || '',
      'Expect Result:',
      issue.expected_result || '',
    ]
    await navigator.clipboard.writeText(lines.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
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
      <p className="muted">Session {fmtSession(sessionId)}</p>

      {/* Video clip (record) or image (capture) */}
      {draft.video_clip && (
        <div className="shot" style={{ display: 'block' }}>
          <video controls width="100%" src={api.fileUrl(sessionId, draft.video_clip)}
                 style={{ maxHeight: 360, background: '#000' }} />
          <a className="img-dl" style={{ right: 5 }} href={api.fileUrl(sessionId, draft.video_clip)}
             download={draft.video_clip} title="Tải video về" aria-label="Download">⬇</a>
        </div>
      )}
      {(draft.screenshots || []).length > 0 && (
        <p className="muted">{draft.screenshots.length} ảnh — bấm nút đỏ ở góc ảnh để gỡ ảnh gắn nhầm.</p>
      )}
      <div className="screenshots">
        {(draft.screenshots || []).map((f, i) => (
          <div key={f} className="shot">
            <img ref={(el) => { imgRefs.current[f] = el }} style={{ cursor: 'zoom-in' }}
                 onClick={() => setLightbox(i)}
                 src={`${api.fileUrl(sessionId, f)}?v=${ver[f] || 0}`} alt={f} crossOrigin="anonymous" />
            <a className="img-dl" href={`${api.fileUrl(sessionId, f)}?v=${ver[f] || 0}`}
               download={f} title="Tải ảnh về" aria-label="Download">⬇</a>
            <button className="img-copy" title="Copy ảnh vào clipboard"
                    onClick={() => copyImage(f)} aria-label="Copy image">📋</button>
            {draft.status !== 'pushed' && (
              <button className="img-edit" title="Vẽ chú thích lên ảnh" disabled={busy}
                      onClick={() => annotate(f)} aria-label="Annotate">✏️</button>
            )}
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
      <Lightbox open={lightbox >= 0} index={Math.max(0, lightbox)} close={() => setLightbox(-1)}
                plugins={[Zoom]}
                slides={(draft.screenshots || []).map((f) => ({ src: `${api.fileUrl(sessionId, f)}?v=${ver[f] || 0}` }))} />
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
      <h3 style={{ fontSize: 14, margin: '14px 0 4px', display: 'flex', alignItems: 'center' }}>
        Issue (LLM-generated from transcript)
        <button type="button" className="copy-btn" title="Copy nội dung (không gồm ảnh) để dán vào Jira"
                onClick={copyText} style={{ marginLeft: 'auto' }}>{copied ? '✓ Đã copy' : '📋 Copy'}</button>
      </h3>
      <label>Title
        <input value={issue.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      <details open>
        <summary>Steps to reproduce</summary>
        <ol className="repro-steps">
          {(issue.repro_steps || []).map((s, i) => (
            <li key={i}>
              <input value={s} onChange={(e) => {
                const next = [...issue.repro_steps]; next[i] = e.target.value; set('repro_steps', next)
              }} />
              <button type="button" className="link" title="Xóa bước này"
                      onClick={() => set('repro_steps', issue.repro_steps.filter((_, j) => j !== i))}>✕</button>
            </li>
          ))}
        </ol>
        <button type="button" className="link"
                onClick={() => set('repro_steps', [...(issue.repro_steps || []), ''])}>+ Thêm bước</button>
      </details>
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
        <p className="muted">Label: {issue.labels.join(', ')}</p>
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
