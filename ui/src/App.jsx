import { useEffect, useState } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import { api, fmtSession } from './api'
import { subscribe } from './ws'
import SessionDetail from './SessionDetail'
import BugDetail from './BugDetail'

export default function App() {
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
            <p>New bug → describe it verbally then press <kbd>{status.record_hotkey}</kbd> (video) or <kbd>{status.capture_hotkey}</kbd> (screenshot). Same bug, extra screenshot → <kbd>{status.append_hotkey}</kbd>. Marked: <b>{status.marker_count}</b> bug(s)</p>
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
      </Routes>
    </div>
  )
}

function Home({ sessions, bugs }) {
  const navigate = useNavigate()
  return (
    <>
      {/* Bugs table (global) */}
      <div className="panel">
        <h2>Bugs</h2>
        {bugs.length === 0 && <p className="muted">No bugs yet. Start a session and press the hotkey when you encounter a bug — bugs will appear here automatically.</p>}
        {bugs.map((b) => (
          <div key={`${b.session_id}-${b.id}`} className="session-row"
               onClick={() => navigate(`/sessions/${b.session_id}/bugs/${b.id}`)}>
            <span>{b.type === 'capture' ? '📷' : '📹'} {b.title || '(no title yet)'}{b.image_count > 1 ? ` (${b.image_count} ảnh)` : ''}</span>
            <span className="muted">{fmtSession(b.session_id)}</span>
            {b.status === 'pushed'
              ? <span className="status status-done">✓ {b.jira_key}</span>
              : <span className="status status-recorded">draft</span>}
          </div>
        ))}
      </div>

      {/* Sessions table */}
      <div className="panel">
        <h2>Sessions</h2>
        {sessions.length === 0 && <p className="muted">No sessions yet.</p>}
        {sessions.map((s) => (
          <div key={s.id} className="session-row" onClick={() => navigate(`/sessions/${s.id}`)}>
            <b>{fmtSession(s.id)}</b>
            <span>{s.draft_count} bug</span>
            <span className={`status status-${s.status}`}>{s.status}</span>
          </div>
        ))}
      </div>
    </>
  )
}

function Dot({ ok, label }) {
  return <span className="dot-label"><span className={ok ? 'dot ok' : 'dot'} />{label}</span>
}
