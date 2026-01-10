// SSE.js - Server-Sent Events handler

class SSEClient {
    constructor(options = {}) {
        this.onStart = options.onStart || (() => {});
        this.onChunk = options.onChunk || (() => {});
        this.onSources = options.onSources || (() => {});
        this.onSuggestions = options.onSuggestions || (() => {});
        this.onDone = options.onDone || (() => {});
        this.onError = options.onError || (() => {});

        this.eventSource = null;
    }

    stream(query, sessionId = null) {
        // Close existing connection
        this.close();

        // Build URL
        const params = new URLSearchParams({ q: query });
        if (sessionId) {
            params.append('session_id', sessionId);
        }
        const url = `/api/chat/stream?${params.toString()}`;

        // Create EventSource
        this.eventSource = new EventSource(url);

        // Handle events
        this.eventSource.addEventListener('start', (e) => {
            const data = JSON.parse(e.data);
            this.onStart(data);
        });

        this.eventSource.addEventListener('chunk', (e) => {
            const data = JSON.parse(e.data);
            this.onChunk(data.text);
        });

        this.eventSource.addEventListener('sources', (e) => {
            const data = JSON.parse(e.data);
            this.onSources(data.sources);
        });

        this.eventSource.addEventListener('suggestions', (e) => {
            const data = JSON.parse(e.data);
            this.onSuggestions(data.queries);
        });

        this.eventSource.addEventListener('done', (e) => {
            const data = JSON.parse(e.data);
            this.onDone(data);
            this.close();
        });

        this.eventSource.addEventListener('error', (e) => {
            if (e.data) {
                const data = JSON.parse(e.data);
                this.onError(data.message);
            } else {
                this.onError('Connection error');
            }
            this.close();
        });

        this.eventSource.onerror = () => {
            this.onError('SSE connection failed');
            this.close();
        };

        return this;
    }

    close() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}
