import { useEffect, useState } from 'react'
import { api } from './api'
import SessionDetail from './SessionDetail'

export default function App() {
  const [status, setStatus] = useState(null)
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      setStatus(await api.status())
      setSessions(await api.listSessions())
    } catch (e) {
      setError('Không kết nối được backend (uvicorn main:app --port 8000)')
    }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 2000) // poll trạng thái mỗi 2s
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
          <Dot ok={status?.obs_connected} label={status?.obs_connected ? 'OBS đã kết nối' : 'OBS chưa kết nối'} />
          <Dot ok={status?.asr_engines?.gemini} label="Gemini" />
          <Dot ok={status?.asr_engines?.groq} label="Groq" />
          <Dot ok={status?.asr_engines?.openai} label="OpenAI" />
          <span className="muted">Jira: {status?.jira_mode}</span>
        </div>

        {status?.recording ? (
          <div className="recording">
            <p>🔴 Đang ghi — session <b>{status.active_session}</b></p>
            <p>Nhấn <kbd>{status.hotkey}</kbd> khi gặp bug rồi mô tả bằng lời. Đã đánh dấu: <b>{status.marker_count}</b> bug</p>
            <button className="stop" onClick={() => act(api.stopSession)}>⏹ Kết thúc session</button>
          </div>
        ) : (
          <button
            className="start"
            disabled={!status?.obs_connected}
            onClick={() => act(api.startSession)}
          >
            ⏺ Bắt đầu session test
          </button>
        )}
      </div>

      {/* ===== Sessions list / detail ===== */}
      {selected ? (
        <SessionDetail id={selected} onBack={() => { setSelected(null); refresh() }} />
      ) : (
        <div className="panel">
          <h2>Sessions</h2>
          {sessions.length === 0 && <p className="muted">Chưa có session nào.</p>}
          {sessions.map((s) => (
            <div key={s.id} className="session-row" onClick={() => setSelected(s.id)}>
              <b>{s.id}</b>
              <span>{s.draft_count} bug</span>
              <span className={`status status-${s.status}`}>{s.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Dot({ ok, label }) {
  return <span className="dot-label"><span className={ok ? 'dot ok' : 'dot'} />{label}</span>
}
