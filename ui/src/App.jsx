import { useEffect, useState } from 'react'
import { api } from './api'
import SessionDetail from './SessionDetail'
import BugDetail from './BugDetail'

export default function App() {
  const [status, setStatus] = useState(null)
  const [sessions, setSessions] = useState([])
  const [bugs, setBugs] = useState([])
  const [view, setView] = useState(null) // null=home | {kind:'session',id} | {kind:'bug',sessionId,bugId}
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      setStatus(await api.status())
      setSessions(await api.listSessions())
      setBugs(await api.listBugs())
    } catch (e) {
      setError('Could not connect to backend (uvicorn main:app --port 8000)')
    }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 2000) // poll status every 2s
    return () => clearInterval(t)
  }, [])

  const act = async (fn) => {
    setError('')
    try {
      await fn()
      await refresh()
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
            <p>Encounter a bug → describe it verbally then press <kbd>{status.record_hotkey}</kbd> (video) or <kbd>{status.capture_hotkey}</kbd> (screenshot). Marked: <b>{status.marker_count}</b> bug(s)</p>
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
      {view?.kind === 'session' ? (
        <SessionDetail id={view.id} onBack={() => { setView(null); refresh() }} onOpenBug={(bugId) => setView({ kind: 'bug', sessionId: view.id, bugId })} />
      ) : view?.kind === 'bug' ? (
        <BugDetail sessionId={view.sessionId} bugId={view.bugId} onBack={() => { setView(null); refresh() }} />
      ) : (
        <>
          {/* Bugs table (global) */}
          <div className="panel">
            <h2>Bugs</h2>
            {bugs.length === 0 && <p className="muted">No bugs yet. Start a session and press the hotkey when you encounter a bug — bugs will appear here automatically.</p>}
            {bugs.map((b) => (
              <div key={`${b.session_id}-${b.id}`} className="session-row"
                   onClick={() => setView({ kind: 'bug', sessionId: b.session_id, bugId: b.id })}>
                <span>{b.type === 'capture' ? '📷' : '📹'} {b.title || '(no title yet)'}</span>
                <span className="muted">{b.session_id}</span>
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
              <div key={s.id} className="session-row" onClick={() => setView({ kind: 'session', id: s.id })}>
                <b>{s.id}</b>
                <span>{s.draft_count} bug</span>
                <span className={`status status-${s.status}`}>{s.status}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function Dot({ ok, label }) {
  return <span className="dot-label"><span className={ok ? 'dot ok' : 'dot'} />{label}</span>
}
