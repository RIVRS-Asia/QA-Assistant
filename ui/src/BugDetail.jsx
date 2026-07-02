import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import * as markerjs2 from 'markerjs2'
import Lightbox from 'yet-another-react-lightbox'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import 'yet-another-react-lightbox/styles.css'
import { api, fmtSession } from './api'
import { subscribe } from './ws'

export default function BugDetail() {
  const { sessionId, bugId: bugIdParam, ver: verParam } = useParams()
  const bugId = Number(bugIdParam)
  const selVer = verParam == null ? null : Number(verParam)  // requested result version (null = bug default)
  const navigate = useNavigate()
  const onBack = () => navigate(`/sessions/${sessionId}`)
  const [draft, setDraft] = useState(null)
  const [issue, setIssue] = useState(null)
  const [transcripts, setTranscripts] = useState({})  // editable QA description (sent on reprocess)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [ver, setVer] = useState({})        // cache-bust per filename after annotating
  const [lightbox, setLightbox] = useState(-1)  // open screenshot index, -1 = closed
  const [copied, setCopied] = useState(false)
  const [pushing, setPushing] = useState(false)   // spinner while POSTing to Jira
  const [pushOk, setPushOk] = useState(false)      // brief success flash after push
  const imgRefs = useRef({})
  const curVer = draft?.ver  // the actually-resolved version (selVer may be null -> default)

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

  // Apply / roll back the AI auto-mark by swapping which file this slot points to (original <-> boxed
  // copy). Non-destructive: both files stay on disk, so it's fully reversible - no overwrite, no data loss.
  const swapShot = async (from, to) => {
    setBusy(true)
    try { await api.swapScreenshot(sessionId, bugId, from, to, curVer); await load() }
    catch (e) { setError(e.message) }
    setBusy(false)
  }

  const load = async () => {
    try {
      const d = await api.getBug(sessionId, bugId, selVer)
      setDraft(d)
      setIssue(d.issue)
      setTranscripts(d.transcripts || {})
    } catch (e) { setError(e.message) }
  }

  useEffect(() => { load() }, [sessionId, bugId, selVer])

  // Re-run the AI on the existing media using the (possibly edited) transcript -> a NEW version.
  // Jump to that version's route so it's shown immediately; the default version is left unchanged.
  const reprocess = async () => {
    setBusy(true); setError('')
    try {
      const nv = await api.reprocessBug(sessionId, bugId, transcripts)
      navigate(`/sessions/${sessionId}/bugs/${bugId}/v/${nv.ver}`)
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const markDefault = async () => {
    setBusy(true)
    try { await api.setDefaultVersion(sessionId, bugId, curVer); await load() }
    catch (e) { setError(e.message) }
    setBusy(false)
  }

  // While the AI is still processing this bug, reload on every backend change so newly appended
  // images (Alt+A) and the finalized issue text show up live. Stops once it's a real draft — so it
  // never clobbers the edits you're typing into a finished draft.
  useEffect(() => {
    if (!draft?.processing) return
    return subscribe((msg) => { if (msg.type === 'state') load() })
  }, [draft?.processing])

  if (error) return <div className="panel"><button className="link" onClick={onBack}>← Back</button><div className="error">{error}</div></div>
  if (!draft) return <p className="muted">Loading...</p>

  const set = (k, v) => setIssue({ ...issue, [k]: v })

  // AI bug-region suggestions, looked up by whichever file the slot currently shows: the original
  // frame (markBySrc -> can apply) or the boxed copy (markByMarked -> can roll back).
  const markBySrc = Object.fromEntries((draft.auto_marks || []).map((m) => [m.src, m]))
  const markByMarked = Object.fromEntries((draft.auto_marks || []).map((m) => [m.marked, m]))

  const save = async () => {
    setBusy(true)
    await api.updateDraft(sessionId, bugId, issue, curVer)
    setBusy(false)
    load()
  }

  const push = async () => {
    setPushing(true); setError('')
    try {
      await api.updateDraft(sessionId, bugId, issue, curVer) // save edits before pushing
      await api.pushDraft(sessionId, bugId, curVer)
      setPushOk(true)
      setTimeout(() => setPushOk(false), 4000)
      await load()
    } catch (e) { setError(e.message) }
    setPushing(false)
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
    const esc = (s) => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const steps = issue.repro_steps || []
    const plain = [
      `Bug Display: ${issue.title || ''}`,
      'Step to reproduce:',
      ...steps.map((s, i) => `${i + 1}. ${s}`),
      'Actual Result:',
      issue.actual_result || '',
      'Expect Result:',
      issue.expected_result || '',
    ].join('\n')
    const html =
      `<p><strong>Bug Display:</strong> ${esc(issue.title)}</p>` +
      `<p><strong>Step to reproduce:</strong></p>` +
      `<ol>${steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>` +
      `<p><strong>Actual Result:</strong><br>${esc(issue.actual_result)}</p>` +
      `<p><strong>Expect Result:</strong><br>${esc(issue.expected_result)}</p>`
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([plain], { type: 'text/plain' }),
      })])
    } catch {
      await navigator.clipboard.writeText(plain)  // fallback if browser doesn't support ClipboardItem
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const removeImage = async (filename) => {
    if (!window.confirm('Remove this image from the bug? The image will be deleted permanently.')) return
    setBusy(true)
    try { await api.deleteScreenshot(sessionId, bugId, filename, curVer) } catch (e) { setError(e.message) }
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

      {/* Result versions: each "Reprocess" makes a new one. ★ = default (shown in the bugs list),
          ✎ = its transcript was edited, ✓ = pushed to Jira. Click to view; "Set as default" to pin. */}
      {!draft.processing && (
        <div className="version-bar" style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', margin: '8px 0' }}>
          <span className="muted">Versions:</span>
          {(draft.versions_meta || []).map((m) => (
            <button key={m.ver} type="button"
                    className={`ver-btn${m.ver === curVer ? ' active' : ''}`}
                    style={{
                      padding: '2px 10px', borderRadius: 6, cursor: 'pointer',
                      border: m.ver === curVer ? '2px solid #2563eb' : '1px solid #000000',
                      background: m.ver === curVer ? '#4d80c2' : '#636363', fontWeight: m.ver === curVer ? 600 : 400,
                    }}
                    title={m.created_at ? new Date(m.created_at * 1000).toLocaleString() : 'original'}
                    onClick={() => navigate(`/sessions/${sessionId}/bugs/${bugId}/v/${m.ver}`)}>
              {m.ver === draft.default_ver ? '★ ' : ''}#{m.ver + 1}{m.status === 'pushed' ? ' ✓' : ''}{m.transcript_edited ? ' ✎' : ''}
            </button>
          ))}
          {curVer !== draft.default_ver && (
            <button type="button" className="link" disabled={busy} onClick={markDefault}>★ Set as default</button>
          )}
        </div>
      )}

      {draft.processing && (
        <p className="muted">⏳ AI is still analyzing this bug — you can view and annotate the images now; the text fields fill in automatically when it finishes.</p>
      )}

      {/* Video clip (record) or image (capture) */}
      {draft.video_clip && (
        <div className="shot" style={{ display: 'block' }}>
          <video controls width="100%" src={api.fileUrl(sessionId, draft.video_clip)}
                 style={{ maxHeight: 360, background: '#000' }} />
          <a className="img-dl" style={{ right: 5 }} href={api.fileUrl(sessionId, draft.video_clip)}
             download={draft.video_clip} title="Download video" aria-label="Download">⬇</a>
        </div>
      )}
      {(draft.screenshots || []).length > 0 && (
        <p className="muted">{draft.screenshots.length} image{draft.screenshots.length !== 1 ? 's' : ''} — click the red button in the corner to remove a misattached image.</p>
      )}
      <div className="screenshots">
        {(draft.screenshots || []).map((f, i) => (
          <div key={f} className="shot">
            <img ref={(el) => { imgRefs.current[f] = el }} style={{ cursor: 'zoom-in' }}
                 onClick={() => setLightbox(i)}
                 src={`${api.fileUrl(sessionId, f)}?v=${ver[f] || 0}`} alt={f} crossOrigin="anonymous" />
            <a className="img-dl" href={`${api.fileUrl(sessionId, f)}?v=${ver[f] || 0}`}
               download={f} title="Download image" aria-label="Download">⬇</a>
            <button className="img-copy" title="Copy image to clipboard"
                    onClick={() => copyImage(f)} aria-label="Copy image">📋</button>
            {draft.status !== 'pushed' && (
              <button className="img-edit" title="Draw annotation on image" disabled={busy}
                      onClick={() => annotate(f)} aria-label="Annotate">✏️</button>
            )}
            {draft.status !== 'pushed' && (
              <button className="img-del" title="Remove this image from the bug" disabled={busy}
                      onClick={() => removeImage(f)} aria-label="Delete image">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 6h18" />
                  <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  <path d="M10 11v6M14 11v6" />
                </svg>
              </button>
            )}
            {draft.status !== 'pushed' && markByMarked[f] && (
              <div className="auto-mark" style={{ marginTop: 4 }}>
                <span className="muted" style={{ marginRight: 10 }}>✨ Using AI box</span>
                <button type="button" className="link" disabled={busy}
                        title="Revert to original image (no box)"
                        onClick={() => swapShot(f, markByMarked[f].src)}>↩ Original</button>
              </div>
            )}
            {draft.status !== 'pushed' && markBySrc[f] && (
              <div className="auto-mark" style={{ marginTop: 4 }}>
                <button type="button" className="link" disabled={busy}
                        title="Use AI image with error region marked (can be reverted)"
                        onClick={() => swapShot(f, markBySrc[f].marked)}>✨ Apply AI suggestion</button>
              </div>
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

      {/* QA verbal description: editable so QA can fix ASR mistakes, then Reprocess to re-run the
          AI on the same media into a new version. Pushed/processing versions are shown read-only. */}
      <details open>
        <summary>Transcript (QA verbal description){draft.transcript_edited ? ' - edited' : ''}</summary>
        {!draft.processing && draft.status !== 'pushed' ? (
          <>
            {(Object.keys(transcripts).length ? Object.entries(transcripts) : [['gemini', '']]).map(([engine, text]) => (
              <label key={engine} style={{ display: 'block', marginTop: 4 }}>
                <b>{engine}</b>
                <textarea rows={3} value={text}
                          onChange={(e) => setTranscripts({ ...transcripts, [engine]: e.target.value })} />
              </label>
            ))}
            <div className='row' style={{ marginTop: 6 }}>
              <button type='button' onClick={reprocess} disabled={busy}>🔄 Reprocess (create new version)</button>
            </div>
            <p className='muted'>Edit the transcript if the AI mishears, then click Reprocess - creates a new result version without overwriting the old one.</p>
          </>
        ) : (
          Object.entries(draft.transcripts || {}).map(([engine, text]) =>
            text ? <p key={engine}><b>{engine}:</b> {text}</p> : null
          )
        )}
        {(draft.audios || []).length > 0
          ? (draft.audios || []).map((a) => <audio key={a} controls src={api.fileUrl(sessionId, a)} style={{ display: 'block', marginTop: 4 }} />)
          : <p className="muted">No mic audio yet (ffmpeg is needed to extract it from the OBS clip).</p>}
      </details>

      {/* Text extracted by LLM from transcript = issue (editable) */}
      <h3 style={{ fontSize: 14, margin: '14px 0 4px', display: 'flex', alignItems: 'center' }}>
        Issue (LLM-generated from transcript)
        <button type="button" className="copy-btn" title="Copy content (without images) to paste in Jira"
                onClick={copyText} style={{ marginLeft: 'auto' }}>{copied ? '✓ Copied' : '📋 Copy'}</button>
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
              <button type="button" className="link" title="Delete this step"
                      onClick={() => set('repro_steps', issue.repro_steps.filter((_, j) => j !== i))}>✕</button>
            </li>
          ))}
        </ol>
        <button type="button" className="link"
                onClick={() => set('repro_steps', [...(issue.repro_steps || []), ''])}>+ Add step</button>
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
          <button onClick={save} disabled={busy || pushing || draft.processing}>💾 Save</button>
          <button className="start" onClick={push} disabled={busy || pushing || draft.processing}>
            {pushing ? <><span className="spinner" /> Pushing…</> : '🚀 Push Jira'}
          </button>
        </div>
      )}
      {pushOk && <div className="ok-banner">✓ Pushed to Jira successfully.</div>}
    </div>
  )
}
