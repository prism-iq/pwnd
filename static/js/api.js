// API.js - API client

const API = {
    baseUrl: '',

    async request(endpoint, options = {}) {
        const url = this.baseUrl + endpoint;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Request failed');
            }

            return data;
        } catch (error) {
            console.error(`API error: ${endpoint}`, error);
            throw error;
        }
    },

    // Health check
    async health() {
        return this.request('/api/health');
    },

    // Get stats
    async stats() {
        return this.request('/api/stats');
    },

    // Send chat message (non-streaming)
    async chat(message, sessionId = null) {
        return this.request('/api/chat', {
            method: 'POST',
            body: JSON.stringify({
                message,
                session_id: sessionId
            })
        });
    },

    // Search documents
    async search(query, limit = 10) {
        return this.request(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`);
    },

    // List documents
    async listDocuments() {
        return this.request('/api/documents');
    },

    // Get document by ID
    async getDocument(id) {
        return this.request(`/api/documents/${id}`);
    },

    // Get session
    async getSession(id) {
        return this.request(`/api/sessions/${id}`);
    },

    // List sessions
    async listSessions() {
        return this.request('/api/sessions');
    }
};
