import { wsConnected, notify } from '../stores/app.js'

let ws = null
let reconnectTimer = null
const handlers = new Map()

export function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.host}/ws`)

  ws.onopen = () => {
    console.log('WebSocket connected')
    wsConnected.set(true)
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)

      // Handle built-in events
      if (data.type === 'notification') {
        notify(data.message, data.level || 'info')
      }
      if (data.type === 'refresh') {
        location.reload()
      }

      // Call registered handlers
      const handler = handlers.get(data.type)
      if (handler) handler(data)

    } catch (err) {
      console.log('WS raw message:', event.data)
    }
  }

  ws.onclose = () => {
    console.log('WebSocket disconnected')
    wsConnected.set(false)
    reconnectTimer = setTimeout(connect, 3000)
  }

  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
    ws.close()
  }
}

export function send(type, data = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, ...data }))
  }
}

export function on(type, handler) {
  handlers.set(type, handler)
}

export function off(type) {
  handlers.delete(type)
}

export function disconnect() {
  if (ws) {
    ws.close()
    ws = null
  }
}
