// Live updates over WebSocket - replaces the old setInterval polling of /api/status etc.
// The backend pushes a full {status, sessions, bugs} snapshot on connect and on every change.
// Components subscribe(); detail views just re-fetch their own endpoint when a message arrives.

let socket = null
const listeners = new Set()
let lastMessage = null

function connect() {
  if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${proto}://${location.host}/api/ws`)
  socket.onmessage = (e) => {
    try {
      lastMessage = JSON.parse(e.data)
      listeners.forEach((fn) => fn(lastMessage))
    } catch { /* ignore malformed frames */ }
  }
  socket.onclose = () => { socket = null; setTimeout(connect, 1500) } // auto-reconnect
  socket.onerror = () => { try { socket.close() } catch { /* noop */ } }
}

// fn receives every snapshot. Returns an unsubscribe function.
export function subscribe(fn) {
  connect()
  listeners.add(fn)
  if (lastMessage) fn(lastMessage) // hand the newest snapshot to a late subscriber immediately
  return () => listeners.delete(fn)
}
