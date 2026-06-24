// Compact always-on-top panel (rendered by pywebview at /panel).
// Live flow during a session:
//   capture/append hotkey -> a row appears instantly (preview fills in once the clip is saved)
//   end hotkey            -> row flips to "analyzing (AI)…"
//   AI done               -> row becomes a green "ready" draft; click it to mark/edit in the browser.
import { useEffect, useState } from 'react'
import { api } from './api'
import { subscribe } from './ws'

const EXPANDED = [340, 520]
const COLLAPSED = [340, 44]

const inPywebview = () => typeof window !== 'undefined' && !!window.pywebview

// Send the roomy views (annotate / review) to the default browser; the panel stays small.
function openExternal(path) {
  const url = location.origin + path
  if (inPywebview()) window.pywebview.api.open_external(url)
  else window.open(url, '_blank')
}

export default function Panel() {
  const [status, setStatus] = useState(null)
  const [bugs, setBugs] = useState([])
  const [inflight, setInflight] = useState([])
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => subscribe((msg) => {
    if (msg.type !== 'state') return
    setStatus(msg.status)
    setBugs(msg.bugs)
    setInflight(msg.inflight || [])
  }), [])

  const act = async (fn) => { setError(''); try { await fn() } catch (e) { setError(e.message) } }

  const toggleCollapse = () => {
    const next = !collapsed
    setCollapsed(next)
    if (inPywebview()) window.pywebview.api.resize(...(next ? COLLAPSED : EXPANDED))
  }

  const recording = status?.recording
  const activeId = status?.active_session
  const activeDrafts = bugs.filter((b) => b.session_id === activeId)
  const draftRows = recording ? activeDrafts : bugs.slice(0, 12)
  const total = inflight.length + (recording ? activeDrafts.length : 0)

  return (
    <div className={`qa-panel${collapsed ? ' collapsed' : ''}`}>
      <header className="qp-bar">
        <span className="qp-title pywebview-drag-region">{recording ? '🔴 REC' : '🎮 QA'}</span>
        <span className="qp-spacer pywebview-drag-region" />
        <button className="qp-win" title={collapsed ? 'Expand' : 'Collapse'} onClick={toggleCollapse}>{collapsed ? '▴' : '▾'}</button>
        {inPywebview() && (
          <>
            <button className="qp-win" title="Minimize" onClick={() => window.pywebview.api.minimize()}>—</button>
            <button className="qp-win" title="Close" onClick={() => window.pywebview.api.close()}>✕</button>
          </>
        )}
      </header>

      {error && <div className="qp-err">{error}</div>}

      <div className="qp-status">
        <Dot ok={status?.obs_connected} label="OBS" />
        {recording
          ? <button className="qp-go stop" onClick={() => act(api.stopSession)}>■ Stop</button>
          : <button className="qp-go start" disabled={!status?.obs_connected} onClick={() => act(api.startSession)}>▶ Start</button>}
        {recording && <span className="qp-count">{total} bug{total !== 1 ? 's' : ''}</span>}
      </div>

      {recording && (
        <div className="qp-keys">
          <span><kbd>{status.capture_hotkey}</kbd> shot</span>
          <span><kbd>{status.record_hotkey}</kbd> video</span>
          <span><kbd>{status.append_hotkey}</kbd> +img</span>
          <span><kbd>{status.end_hotkey}</kbd> end</span>
        </div>
      )}

      <div className="qp-list">
        {inflight.length === 0 && draftRows.length === 0 && (
          <p className="qp-empty">
            {recording ? 'Found a bug? Talk + press the hotkey — it shows up here.' : 'No bugs yet.'}
          </p>
        )}
        {inflight.map((b) => <LiveRow key={`live-${b.bug_id}`} b={b} />)}
        {draftRows.map((b) => <DraftRow key={`${b.session_id}-${b.id}`} b={b} />)}
      </div>

      <footer className="qp-foot">
        <button className="qp-link" onClick={() => openExternal('/')}>Open Bugs board ↗</button>
      </footer>
    </div>
  )
}

function Thumb({ b }) {
  return (
    <span className="qp-thumb">
      {b.thumb
        ? <img src={api.fileUrl(b.session_id, b.thumb)} alt="" />
        : <span className="qp-thumb-ph">{b.type === 'capture' ? '📷' : '📹'}</span>}
    </span>
  )
}

// Not-yet-finalized bug: capturing (waiting for the clip) or analyzing (AI running).
// Clickable — opens the detail page to view/annotate the images captured so far while it processes.
function LiveRow({ b }) {
  const capturing = b.status !== 'processing'
  return (
    <button className="qp-item" title="Open to view / mark images (AI still running)"
      onClick={() => openExternal(`/sessions/${b.session_id}/bugs/${b.bug_id}`)}>
      <Thumb b={b} />
      <span className="qp-meta">
        <span className="qp-bt">Bug #{b.bug_id} · {b.img_count} shot{b.img_count !== 1 ? 's' : ''}</span>
        <span className="qp-bs">
          <span className={`qp-sd ${capturing ? 'capturing' : 'processing'}`} />
          {capturing ? 'capturing…' : 'analyzing (AI)…'}
        </span>
      </span>
    </button>
  )
}

// Finalized draft: AI done. Click to open the roomy BugDetail page (mark / edit / push).
function DraftRow({ b }) {
  return (
    <button className="qp-item" title="Open to mark / edit"
      onClick={() => openExternal(`/sessions/${b.session_id}/bugs/${b.id}`)}>
      <Thumb b={b} />
      <span className="qp-meta">
        <span className="qp-bt">{b.title || `Bug #${b.id}`}</span>
        <span className="qp-bs">
          <span className="qp-sd done" />
          {b.status === 'pushed' ? `✓ ${b.jira_key}` : 'ready'}
          {b.image_count > 1 ? ` · ${b.image_count} imgs` : ''}
        </span>
      </span>
    </button>
  )
}

function Dot({ ok, label }) {
  return <span className="qp-dot-label"><span className={ok ? 'qp-dot ok' : 'qp-dot'} />{label}</span>
}
