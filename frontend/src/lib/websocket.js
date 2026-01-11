import { io } from 'socket.io-client'
import { wsConnected, notify, stats } from '../stores/app.js'

let socket = null
const handlers = new Map()

export function connect() {
  if (socket?.connected) return

  // Connect via same origin - Caddy proxies /socket.io to Node Lungs
  socket = io({
    path: '/socket.io',
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: Infinity
  })

  socket.on('connect', () => {
    console.log('Socket.IO connected')
    wsConnected.set(true)
  })

  socket.on('disconnect', () => {
    console.log('Socket.IO disconnected')
    wsConnected.set(false)
  })

  socket.on('connect_error', (err) => {
    console.log('Socket.IO connection error:', err.message)
    wsConnected.set(false)
  })

  // Built-in events
  socket.on('notification', (data) => {
    notify(data.message, data.level || 'info')
  })

  socket.on('refresh', () => {
    location.reload()
  })

  socket.on('stats', (data) => {
    stats.set(data)
  })

  // Investigation progress
  socket.on('session:progress', (data) => {
    const handler = handlers.get('progress')
    if (handler) handler(data)
  })

  // Generic event handler
  socket.onAny((eventName, data) => {
    const handler = handlers.get(eventName)
    if (handler) handler(data)
  })
}

export function send(type, data = {}) {
  if (socket?.connected) {
    socket.emit(type, data)
  }
}

export function on(type, handler) {
  handlers.set(type, handler)
  if (socket) {
    socket.on(type, handler)
  }
}

export function off(type) {
  handlers.delete(type)
  if (socket) {
    socket.off(type)
  }
}

export function disconnect() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}

// Join a session for real-time updates
export function joinSession(sessionId) {
  if (socket?.connected) {
    socket.emit('join', { sessionId })
  }
}

export function leaveSession(sessionId) {
  if (socket?.connected) {
    socket.emit('leave', { sessionId })
  }
}
