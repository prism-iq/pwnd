import { writable, derived } from 'svelte/store'

// Connection status
export const wsConnected = writable(false)
export const apiConnected = writable(true)

// Notifications
export const notifications = writable([])

// Current tab
export const activeTab = writable('chat')

// Search state
export const searchQuery = writable('')
export const searchEngine = writable('blood') // 'blood' or 'pg'
export const searchResults = writable([])
export const searchLoading = writable(false)

// Chat state
export const conversations = writable([])
export const currentConvId = writable(null)
export const messages = writable([])
export const chatLoading = writable(false)

// Stats
export const stats = writable({ documents: 0, nodes: 0, edges: 0 })

// Graph state
export const graphNodes = writable([])
export const graphEdges = writable([])
export const selectedNode = writable(null)

// Investigate results
export const investigateResults = writable(null)

// Add notification
export function notify(message, type = 'info', duration = 5000) {
  const id = Date.now()
  notifications.update(n => [...n, { id, message, type }])
  if (duration > 0) {
    setTimeout(() => {
      notifications.update(n => n.filter(x => x.id !== id))
    }, duration)
  }
}
