import { useEffect, useState } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { api, fmtSession } from './api'
import { subscribe } from './ws'
import SessionDetail from './SessionDetail'
import BugDetail from './BugDetail'
import Panel from './Panel'

export default function App() {
  // /panel = the compact always-on-top window (pywebview); everything else = the full review UI.
  const loc = useLocation()
  if (loc.pathname === '/panel') return <Panel />
  return <FullApp />
}

function FullApp() {
  const [status, setStatus] = useState(null)
  const [sessions, setSessions] = useState([])
  const [bugs, setBugs] = useState([])
  const [error, setError] = useState('')

  // Live state via WebSocket - the backend pushes a full snapshot on connect and on every change.
  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type !== 'state') return
      setStatus(msg.status)
      setSessions(msg.sessions)
      setBugs(msg.bugs)
    })
  }, [])

  const act = async (fn) => {
    setError('')
    try {
      await fn()  // the resulting change is pushed back over the WebSocket
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="app">
      <h1>🎮 Roblox QA Assistant <span className="badge">POC</span></h1>
      {error && <div className="error">{error}</div>}

      {/* ===== Session control ===== */}
      <div className="panel">
        <div className="row">
          <Dot ok={status?.obs_connected} label={status?.obs_connected ? 'OBS connected' : 'OBS not connected'} />
          <Dot ok={status?.asr_engines?.gemini} label="Gemini" />
          <Dot ok={status?.asr_engines?.groq} label="Groq" />
          <Dot ok={status?.asr_engines?.openai} label="OpenAI" />
          <span className="muted">Jira: {status?.jira_mode}</span>
        </div>

        {status?.recording ? (
          <div className="recording">
            <p>🔴 Recording — session <b>{status.active_session}</b></p>
            <p>New bug → describe it verbally then press <kbd>{status.record_hotkey}</kbd> (video) or <kbd>{status.capture_hotkey}</kbd> (screenshot). Same bug, extra screenshot → <kbd>{status.append_hotkey}</kbd>. End bug → process with AI → <kbd>{status.end_hotkey}</kbd>. Marked: <b>{status.marker_count}</b> bug(s)</p>
            <p className="muted">🔊 Listen for the beep: two rising notes = new bug saved, one note = image added, low buzz = save failed (try again).</p>
            <button className="stop" onClick={() => act(api.stopSession)}>⏹ End session</button>
          </div>
        ) : (
          <button
            className="start"
            disabled={!status?.obs_connected}
            onClick={() => act(api.startSession)}
          >
            ⏺ Start test session
          </button>
        )}
      </div>

      {/* ===== Detail views / home ===== */}
      <Routes>
        <Route path="/" element={<Home sessions={sessions} bugs={bugs} />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
        <Route path="/sessions/:sessionId/bugs/:bugId" element={<BugDetail />} />
        <Route path="/sessions/:sessionId/bugs/:bugId/v/:ver" element={<BugDetail />} />
      </Routes>
    </div>
  )
}

const PAGE_SIZE = 10

function usePage(items) {
  const [page, setPage] = useState(1)
  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const p = Math.min(page, pageCount)  // clamp when the list shrinks under us
  const slice = items.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE)
  return { slice, page: p, pageCount, setPage }
}

function Pager({ page, pageCount, setPage }) {
  if (pageCount <= 1) return null
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => setPage(page - 1)}>← Back</button>
      {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
        <button key={n} className={n === page ? 'pg-active' : ''} onClick={() => setPage(n)}>{n}</button>
      ))}
      <button disabled={page >= pageCount} onClick={() => setPage(page + 1)}>Next →</button>
    </div>
  )
}

function Home({ sessions, bugs }) {
  const navigate = useNavigate()
  const bp = usePage(bugs)
  const sp = usePage(sessions)
  return (
    <>
      {/* Bugs table (global) */}
      <div className="panel">
        <h2>Bugs</h2>
        {bugs.length === 0 && <p className="muted">No bugs yet. Start a session and press the hotkey when you encounter a bug — bugs will appear here automatically.</p>}
        {bp.slice.map((b) => (
          <div key={`${b.session_id}-${b.id}`} className="session-row"
               onClick={() => navigate(`/sessions/${b.session_id}/bugs/${b.id}`)}>
            <span>{b.type === 'capture' ? '📷' : '📹'} {b.title || '(no title yet)'}{b.image_count > 1 ? ` (${b.image_count} images)` : ''}</span>
            <span className="muted">{fmtSession(b.session_id)}</span>
            {b.status === 'pushed'
              ? <span className="status status-done">✓ {b.jira_key}</span>
              : <span className="status status-recorded">draft</span>}
          </div>
        ))}
        <Pager page={bp.page} pageCount={bp.pageCount} setPage={bp.setPage} />
      </div>

      {/* Sessions table */}
      <div className="panel">
        <h2>Sessions</h2>
        {sessions.length === 0 && <p className="muted">No sessions yet.</p>}
        {sp.slice.map((s) => (
          <div key={s.id} className="session-row" onClick={() => navigate(`/sessions/${s.id}`)}>
            <b>{fmtSession(s.id)}</b>
            <span>{s.draft_count} bug</span>
            <span className={`status status-${s.status}`}>{s.status}</span>
          </div>
        ))}
        <Pager page={sp.page} pageCount={sp.pageCount} setPage={sp.setPage} />
      </div>
    </>
  )
}

function Dot({ ok, label }) {
  return <span className="dot-label"><span className={ok ? 'dot ok' : 'dot'} />{label}</span>
}
