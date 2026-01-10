const API = '/api'
const API_V2 = '/api/v2'

// Generic fetch wrapper
async function request(url, options = {}) {
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error('API Error:', err)
    throw err
  }
}

// Search
export async function search(query, engine = 'blood', limit = 30) {
  if (engine === 'blood') {
    return request(`${API}/search/blood?q=${encodeURIComponent(query)}&limit=${limit}`)
  }
  return request(`${API}/search?q=${encodeURIComponent(query)}&limit=${limit}`)
}

// Investigate (polyglot flow)
export async function investigate(query) {
  return request(`${API}/investigate`, {
    method: 'POST',
    body: JSON.stringify({ query })
  })
}

// Chat
export async function getConversations() {
  return request(`${API_V2}/chat/conversations`)
}

export async function getConversation(id) {
  return request(`${API_V2}/chat/conversations/${id}`)
}

export async function sendMessage(message, conversationId = null) {
  return request(`${API_V2}/chat/send`, {
    method: 'POST',
    body: JSON.stringify({ message, conversation_id: conversationId })
  })
}

// Stream chat (SSE)
export function streamChat(message, conversationId, onChunk, onDone, onError) {
  const body = JSON.stringify({ message, conversation_id: conversationId })

  fetch(`${API_V2}/chat/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body
  }).then(res => {
    const reader = res.body.getReader()
    const decoder = new TextDecoder()

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { onDone(); return }
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              onChunk(data)
            } catch (e) {}
          }
        }
        read()
      }).catch(onError)
    }
    read()
  }).catch(onError)
}

// Stats
export async function getStats() {
  return request(`${API_V2}/stats`)
}

// Graph
export async function getGraph(nodeId = null, limit = 100) {
  const url = nodeId
    ? `${API_V2}/graph/network?node_id=${nodeId}&limit=${limit}`
    : `${API_V2}/graph/network?limit=${limit}`
  return request(url)
}

// Document/Email
export async function getDocument(id) {
  return request(`${API}/document/${id}`)
}

// Notifications
export async function getNotifications() {
  return request(`${API}/notifications`)
}

// Timeline
export async function getTimeline() {
  return request(`${API}/timeline`)
}
