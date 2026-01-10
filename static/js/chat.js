// Chat.js - Chat UI management

class ChatUI {
    constructor() {
        this.messagesEl = document.getElementById('messages');
        this.formEl = document.getElementById('chat-form');
        this.inputEl = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.suggestionsEl = document.getElementById('suggestions');
        this.sourcesListEl = document.getElementById('sources-list');

        this.sessionId = null;
        this.isStreaming = false;
        this.currentMessageEl = null;
        this.sseClient = null;

        this.init();
    }

    init() {
        // Form submit
        this.formEl.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Input focus
        this.inputEl.focus();

        // Initialize SSE client
        this.sseClient = new SSEClient({
            onStart: (data) => this.handleStreamStart(data),
            onChunk: (text) => this.handleStreamChunk(text),
            onSources: (sources) => this.handleSources(sources),
            onSuggestions: (queries) => this.handleSuggestions(queries),
            onDone: (data) => this.handleStreamDone(data),
            onError: (msg) => this.handleStreamError(msg)
        });
    }

    async sendMessage() {
        const message = this.inputEl.value.trim();
        if (!message || this.isStreaming) return;

        // Add user message
        this.addMessage('user', message);
        this.inputEl.value = '';
        this.clearSuggestions();

        // Show typing indicator
        this.showTyping();
        this.isStreaming = true;
        this.sendBtn.disabled = true;

        // Use SSE streaming
        this.sseClient.stream(message, this.sessionId);
    }

    handleStreamStart(data) {
        this.hideTyping();
        this.sessionId = data.session_id;
        this.currentMessageEl = this.createMessageElement('assistant', '');
        this.messagesEl.appendChild(this.currentMessageEl);
    }

    handleStreamChunk(text) {
        if (this.currentMessageEl) {
            const contentEl = this.currentMessageEl.querySelector('.content');
            const currentText = contentEl.dataset.rawText || '';
            const newText = currentText + text;
            contentEl.dataset.rawText = newText;
            contentEl.innerHTML = Utils.parseMarkdown(newText);
            Utils.scrollToBottom(this.messagesEl);
        }
    }

    handleSources(sources) {
        if (!sources || sources.length === 0) return;

        // Update sidebar
        this.updateSourcesList(sources);

        // Add sources to current message
        if (this.currentMessageEl) {
            const contentEl = this.currentMessageEl.querySelector('.content');
            const sourcesHtml = this.createSourcesHtml(sources);
            contentEl.insertAdjacentHTML('beforeend', sourcesHtml);
        }
    }

    handleSuggestions(queries) {
        if (!queries || queries.length === 0) return;
        this.showSuggestions(queries);
    }

    handleStreamDone(data) {
        this.isStreaming = false;
        this.sendBtn.disabled = false;
        this.currentMessageEl = null;
        this.inputEl.focus();

        if (data && data.session_id) {
            this.sessionId = data.session_id;
        }
    }

    handleStreamError(msg) {
        this.hideTyping();
        this.isStreaming = false;
        this.sendBtn.disabled = false;

        if (this.currentMessageEl) {
            const contentEl = this.currentMessageEl.querySelector('.content');
            contentEl.innerHTML = `<span style="color: var(--accent-red);">Erreur: ${Utils.escapeHtml(msg)}</span>`;
        } else {
            this.addMessage('assistant', `Erreur: ${msg}`);
        }
    }

    addMessage(role, content) {
        const messageEl = this.createMessageElement(role, content);
        this.messagesEl.appendChild(messageEl);
        Utils.scrollToBottom(this.messagesEl);
        return messageEl;
    }

    createMessageElement(role, content) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.innerHTML = `<div class="content">${Utils.parseMarkdown(content)}</div>`;
        return div;
    }

    createSourcesHtml(sources) {
        const tags = sources.map(s =>
            `<span class="source-tag" data-docid="${Utils.escapeHtml(s.doc_id)}">[#${Utils.escapeHtml(s.doc_id)}]</span>`
        ).join(' ');

        return `
            <div class="message-sources">
                <div class="label">Sources:</div>
                ${tags}
            </div>
        `;
    }

    showTyping() {
        const typingEl = document.createElement('div');
        typingEl.className = 'message assistant typing';
        typingEl.id = 'typing-indicator';
        typingEl.innerHTML = `
            <div class="content">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        `;
        this.messagesEl.appendChild(typingEl);
        Utils.scrollToBottom(this.messagesEl);
    }

    hideTyping() {
        const typingEl = document.getElementById('typing-indicator');
        if (typingEl) {
            typingEl.remove();
        }
    }

    showSuggestions(queries) {
        this.suggestionsEl.innerHTML = queries.map(q =>
            `<button class="suggestion-btn">${Utils.escapeHtml(q)}</button>`
        ).join('');

        // Add click handlers
        this.suggestionsEl.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.inputEl.value = btn.textContent;
                this.sendMessage();
            });
        });
    }

    clearSuggestions() {
        this.suggestionsEl.innerHTML = '';
    }

    updateSourcesList(sources) {
        if (!sources || sources.length === 0) {
            this.sourcesListEl.innerHTML = '<p class="empty">Aucune source pour l\'instant</p>';
            return;
        }

        this.sourcesListEl.innerHTML = sources.map(s => `
            <div class="source-item">
                <div class="title">${Utils.escapeHtml(s.title)}</div>
                <div class="doc-id">[#${Utils.escapeHtml(s.doc_id)}]</div>
                <div class="excerpt">${Utils.escapeHtml(Utils.truncate(s.excerpt, 100))}</div>
            </div>
        `).join('');
    }
}
