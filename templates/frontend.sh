#!/bin/bash
# templates/frontend.sh - Generates frontend files (ChatGPT/Claude style)

set -e

echo "Generating frontend files..."

# static/index.html
cat > /opt/rag/static/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>pwnd.icu - dig deeper</title>
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <!-- Mobile menu overlay -->
    <div id="mobileOverlay" class="mobile-overlay"></div>

    <!-- Sidebar -->
    <aside id="sidebar" class="sidebar">
        <div class="sidebar-header">
            <h1 class="site-title">pwnd.icu</h1>
            <p class="tagline">dig deeper</p>
            <button id="newChatBtn" class="new-chat-btn">
                <span class="icon">+</span> New Chat
            </button>
        </div>

        <div id="conversationList" class="conversation-list">
            <!-- Conversations loaded here -->
        </div>

        <div class="sidebar-footer">
            <button id="settingsBtn" class="footer-btn">
                <span class="icon">⚙</span> Settings
            </button>
        </div>
    </aside>

    <!-- Main chat area -->
    <main class="main-content">
        <!-- Mobile header -->
        <div class="mobile-header">
            <button id="mobileMenuBtn" class="mobile-menu-btn">
                <span class="hamburger"></span>
            </button>
            <span class="mobile-title">pwnd.icu</span>
        </div>

        <!-- Messages container -->
        <div id="messages" class="messages-container">
            <div class="welcome-screen">
                <h1 class="welcome-title">pwnd.icu</h1>
                <p class="welcome-subtitle">An OSINT investigation framework analyzing 13,009 emails</p>
                <div class="welcome-examples">
                    <p class="examples-label">Try asking:</p>
                    <button class="example-btn">"Who is Jeffrey Epstein?"</button>
                    <button class="example-btn">"Search for Trump connections"</button>
                    <button class="example-btn">"Find patterns in payments"</button>
                </div>
            </div>
        </div>

        <!-- Input area -->
        <div class="input-container">
            <div class="input-wrapper">
                <textarea
                    id="messageInput"
                    placeholder="Message L..."
                    rows="1"
                    maxlength="10000"
                ></textarea>
                <button id="sendBtn" class="send-btn" disabled>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                        <path d="M7 11L12 6L17 11M12 18V7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
            <div class="input-footer">
                <span class="model-indicator">L (Mistral 7B)</span>
                <label class="auto-investigate-toggle">
                    <input type="checkbox" id="autoInvestigate">
                    <span>Auto-investigate</span>
                </label>
            </div>
        </div>
    </main>

    <!-- Settings Modal -->
    <div id="settingsModal" class="modal hidden">
        <div class="modal-backdrop" onclick="closeSettings()"></div>
        <div class="modal-content">
            <div class="modal-header">
                <h2>Settings</h2>
                <button class="modal-close" onclick="closeSettings()">×</button>
            </div>
            <div class="modal-body">
                <div class="setting-group">
                    <label>Theme</label>
                    <select id="themeSetting">
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                    </select>
                </div>
                <div class="setting-group">
                    <label>Language</label>
                    <select id="languageSetting">
                        <option value="fr">Français</option>
                        <option value="en">English</option>
                    </select>
                </div>
                <div class="setting-group">
                    <label>Max auto-queries</label>
                    <input type="number" id="maxAutoQueries" min="1" max="50" value="20">
                </div>
                <div class="setting-group checkbox-group">
                    <label>
                        <input type="checkbox" id="showConfidence" checked>
                        Show confidence scores
                    </label>
                </div>
                <div class="setting-group checkbox-group">
                    <label>
                        <input type="checkbox" id="showSources" checked>
                        Show sources
                    </label>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="closeSettings()">Cancel</button>
                <button class="btn-primary" onclick="saveSettings()">Save</button>
            </div>
        </div>
    </div>

    <script src="/app.js"></script>
</body>
</html>
HTMLEOF

# static/style.css
cat > /opt/rag/static/style.css << 'CSSEOF'
/* Variables */
:root {
    --sidebar-bg: #202123;
    --main-bg: #343541;
    --message-bg: #444654;
    --user-message-bg: #2563eb;
    --border: #565869;
    --text-primary: #ececf1;
    --text-secondary: #9a9b9f;
    --accent: #10a37f;
    --accent-hover: #0d8f6f;
    --danger: #ef4444;
}

[data-theme="light"] {
    --sidebar-bg: #f7f7f8;
    --main-bg: #ffffff;
    --message-bg: #f7f7f8;
    --user-message-bg: #2563eb;
    --border: #e5e5e5;
    --text-primary: #202123;
    --text-secondary: #6e6e80;
}

/* Reset & Base */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--main-bg);
    color: var(--text-primary);
    display: flex;
    height: 100vh;
    overflow: hidden;
    line-height: 1.6;
}

/* Sidebar */
.sidebar {
    width: 260px;
    background: var(--sidebar-bg);
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border);
    transition: transform 0.3s ease;
}

.sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
}

.site-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 4px;
    color: var(--text-primary);
}

.tagline {
    font-size: 12px;
    color: var(--text-secondary);
    font-style: italic;
    margin-bottom: 12px;
}

.new-chat-btn {
    width: 100%;
    padding: 12px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.2s;
}

.new-chat-btn:hover {
    background: rgba(255, 255, 255, 0.05);
}

.new-chat-btn .icon {
    font-size: 18px;
}

.conversation-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.conversation-item {
    padding: 12px;
    margin-bottom: 4px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    color: var(--text-secondary);
    transition: all 0.2s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.conversation-item:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
}

.conversation-item.active {
    background: var(--message-bg);
    color: var(--text-primary);
}

.sidebar-footer {
    padding: 12px;
    border-top: 1px solid var(--border);
}

.footer-btn {
    width: 100%;
    padding: 12px;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.2s;
}

.footer-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
}

/* Main Content */
.main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.mobile-header {
    display: none;
    padding: 12px 16px;
    background: var(--sidebar-bg);
    border-bottom: 1px solid var(--border);
    align-items: center;
    gap: 12px;
}

.mobile-menu-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 8px;
}

.hamburger {
    display: block;
    width: 20px;
    height: 2px;
    background: var(--text-primary);
    position: relative;
}

.hamburger::before,
.hamburger::after {
    content: '';
    position: absolute;
    width: 20px;
    height: 2px;
    background: var(--text-primary);
    left: 0;
}

.hamburger::before { top: -6px; }
.hamburger::after { top: 6px; }

.mobile-title {
    font-size: 16px;
    font-weight: 600;
}

/* Messages Container */
.messages-container {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    scroll-behavior: smooth;
}

.welcome-screen {
    max-width: 600px;
    margin: 60px auto;
    text-align: center;
}

.welcome-title {
    font-size: 36px;
    font-weight: 600;
    margin-bottom: 8px;
}

.welcome-subtitle {
    font-size: 16px;
    color: var(--text-secondary);
    margin-bottom: 40px;
}

.welcome-examples {
    margin-top: 32px;
}

.examples-label {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 12px;
}

.example-btn {
    display: block;
    width: 100%;
    max-width: 400px;
    margin: 8px auto;
    padding: 14px 20px;
    background: var(--message-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text-primary);
    font-size: 15px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
}

.example-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: var(--accent);
}

/* Messages */
.message {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
    max-width: 800px;
}

.message.user {
    margin-left: auto;
    flex-direction: row-reverse;
}

.message-avatar {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 600;
    flex-shrink: 0;
}

.message.user .message-avatar {
    background: var(--user-message-bg);
}

.message.assistant .message-avatar {
    background: var(--accent);
}

.message-content {
    flex: 1;
    padding: 16px 20px;
    border-radius: 12px;
    font-size: 15px;
    line-height: 1.6;
}

.message.user .message-content {
    background: var(--user-message-bg);
    color: white;
}

.message.assistant .message-content {
    background: var(--message-bg);
}

.message-content p {
    margin-bottom: 12px;
}

.message-content p:last-child {
    margin-bottom: 0;
}

.sources {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    font-size: 13px;
    color: rgba(255, 255, 255, 0.7);
}

.source-link {
    color: rgba(255, 255, 255, 0.9);
    text-decoration: none;
    margin-right: 8px;
}

.source-link:hover {
    text-decoration: underline;
}

.status-message {
    text-align: center;
    padding: 12px;
    margin: 16px auto;
    max-width: 600px;
    background: var(--message-bg);
    border-radius: 12px;
    font-size: 14px;
    color: var(--text-secondary);
    font-style: italic;
}

.typing-indicator {
    display: inline-flex;
    gap: 4px;
}

.typing-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-secondary);
    animation: typing 1.4s infinite;
}

.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
    0%, 60%, 100% { opacity: 0.3; }
    30% { opacity: 1; }
}

/* Input Container */
.input-container {
    padding: 20px;
    border-top: 1px solid var(--border);
}

.input-wrapper {
    max-width: 800px;
    margin: 0 auto;
    position: relative;
    background: var(--message-bg);
    border-radius: 12px;
    padding: 12px 52px 12px 16px;
    border: 1px solid var(--border);
    transition: border-color 0.2s;
}

.input-wrapper:focus-within {
    border-color: var(--accent);
}

#messageInput {
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 15px;
    resize: none;
    max-height: 200px;
    outline: none;
}

#messageInput::placeholder {
    color: var(--text-secondary);
}

.send-btn {
    position: absolute;
    right: 12px;
    bottom: 12px;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: var(--accent);
    border: none;
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    opacity: 0;
    transform: scale(0.8);
}

.send-btn:not(:disabled) {
    opacity: 1;
    transform: scale(1);
}

.send-btn:hover:not(:disabled) {
    background: var(--accent-hover);
}

.send-btn:disabled {
    cursor: not-allowed;
}

.input-footer {
    max-width: 800px;
    margin: 12px auto 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: var(--text-secondary);
}

.model-indicator {
    font-weight: 500;
}

.auto-investigate-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
}

.auto-investigate-toggle input {
    cursor: pointer;
}

/* Modal */
.modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal.hidden {
    display: none;
}

.modal-backdrop {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
}

.modal-content {
    position: relative;
    background: var(--sidebar-bg);
    border-radius: 12px;
    width: 90%;
    max-width: 480px;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
    padding: 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.modal-header h2 {
    font-size: 18px;
    font-weight: 600;
}

.modal-close {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 28px;
    cursor: pointer;
    padding: 0;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    transition: all 0.2s;
}

.modal-close:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
}

.modal-body {
    padding: 20px;
}

.setting-group {
    margin-bottom: 20px;
}

.setting-group label {
    display: block;
    margin-bottom: 8px;
    font-size: 14px;
    font-weight: 500;
}

.setting-group select,
.setting-group input[type="number"] {
    width: 100%;
    padding: 10px 12px;
    background: var(--message-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 14px;
}

.setting-group.checkbox-group label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
}

.modal-footer {
    padding: 20px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
    gap: 12px;
}

.btn-primary,
.btn-secondary {
    padding: 10px 20px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary {
    background: var(--accent);
    border: none;
    color: white;
}

.btn-primary:hover {
    background: var(--accent-hover);
}

.btn-secondary {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-primary);
}

.btn-secondary:hover {
    background: rgba(255, 255, 255, 0.05);
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.2);
}

/* Mobile Responsive */
.mobile-overlay {
    display: none;
}

@media (max-width: 768px) {
    .sidebar {
        position: fixed;
        top: 0;
        left: 0;
        bottom: 0;
        z-index: 100;
        transform: translateX(-100%);
    }

    .sidebar.open {
        transform: translateX(0);
    }

    .mobile-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 99;
    }

    .mobile-overlay.active {
        display: block;
    }

    .mobile-header {
        display: flex;
    }

    .messages-container {
        padding: 12px;
    }

    .welcome-screen {
        margin: 40px auto;
    }

    .welcome-title {
        font-size: 28px;
    }

    .message {
        max-width: 100%;
    }

    .input-container {
        padding: 12px;
    }
}
CSSEOF

# static/app.js - CONTINUE IN NEXT FILE DUE TO LENGTH
cat > /opt/rag/static/app.js << 'JSEOF'
// State
let currentConversationId = null;
let autoInvestigateEnabled = false;
let eventSource = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadConversations();
    attachEventListeners();
});

// Event listeners
function attachEventListeners() {
    const sendBtn = document.getElementById('sendBtn');
    const messageInput = document.getElementById('messageInput');

    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';

        // Enable/disable send button
        sendBtn.disabled = !messageInput.value.trim();
    });

    document.getElementById('newChatBtn').addEventListener('click', createNewConversation);
    document.getElementById('settingsBtn').addEventListener('click', openSettings);
    document.getElementById('autoInvestigate').addEventListener('change', (e) => {
        autoInvestigateEnabled = e.target.checked;
    });

    // Mobile menu
    document.getElementById('mobileMenuBtn').addEventListener('click', toggleMobileMenu);
    document.getElementById('mobileOverlay').addEventListener('click', closeMobileMenu);

    // Example buttons
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            messageInput.value = btn.textContent.replace(/"/g, '');
            sendMessage();
        });
    });
}

// Mobile menu
function toggleMobileMenu() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('mobileOverlay').classList.toggle('active');
}

function closeMobileMenu() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('mobileOverlay').classList.remove('active');
}

// Conversations
async function loadConversations() {
    try {
        const response = await fetch('/api/conversations');
        const conversations = await response.json();

        const list = document.getElementById('conversationList');
        list.innerHTML = '';

        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            item.textContent = conv.title || 'Untitled';
            item.onclick = () => loadConversation(conv.id);
            if (conv.id === currentConversationId) {
                item.classList.add('active');
            }
            list.appendChild(item);
        });
    } catch (error) {
        console.error('Failed to load conversations:', error);
    }
}

async function createNewConversation() {
    try {
        const response = await fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New Investigation' })
        });
        const data = await response.json();
        currentConversationId = data.id;
        await loadConversations();
        clearMessages();
        closeMobileMenu();
    } catch (error) {
        console.error('Failed to create conversation:', error);
    }
}

async function loadConversation(id) {
    currentConversationId = id;
    clearMessages();

    try {
        const response = await fetch(`/api/conversations/${id}/messages`);
        const messages = await response.json();

        messages.forEach(msg => {
            appendMessage(msg.role, msg.content);
        });

        await loadConversations(); // Refresh to update active state
        closeMobileMenu();
    } catch (error) {
        console.error('Failed to load conversation:', error);
    }
}

// Messages
function clearMessages() {
    const messagesDiv = document.getElementById('messages');
    messagesDiv.innerHTML = '';
}

function appendMessage(role, content, sources = []) {
    const messagesDiv = document.getElementById('messages');

    // Remove welcome screen if exists
    const welcome = messagesDiv.querySelector('.welcome-screen');
    if (welcome) welcome.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? 'U' : 'L';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(contentDiv);

    if (sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'sources';
        sourcesDiv.innerHTML = 'Sources: ' + sources.map(id =>
            `<a href="#" class="source-link" onclick="viewSource(${id}); return false;">[${id}]</a>`
        ).join(' ');
        contentDiv.appendChild(sourcesDiv);
    }

    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function appendStatus(msg) {
    const messagesDiv = document.getElementById('messages');

    // Remove welcome screen
    const welcome = messagesDiv.querySelector('.welcome-screen');
    if (welcome) welcome.remove();

    const statusDiv = document.createElement('div');
    statusDiv.className = 'status-message';
    statusDiv.innerHTML = `<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div> ${msg}`;
    messagesDiv.appendChild(statusDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return statusDiv;
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message) return;

    // Append user message
    appendMessage('user', message);
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;

    try {
        await processQuery(message);
    } catch (error) {
        appendStatus('Error: ' + error.message);
    }
}

async function processQuery(query) {
    const url = `/api/ask?q=${encodeURIComponent(query)}${currentConversationId ? `&conversation_id=${currentConversationId}` : ''}`;

    let assistantMessage = '';
    let sources = [];
    let statusDiv = null;
    let messageDiv = null;

    eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'status') {
            if (statusDiv) statusDiv.remove();
            statusDiv = appendStatus(data.msg);
        } else if (data.type === 'chunk') {
            if (statusDiv) {
                statusDiv.remove();
                statusDiv = null;
            }
            assistantMessage += data.text;
            updateLastMessage(assistantMessage, sources);
        } else if (data.type === 'sources') {
            sources = data.ids;
            updateLastMessage(assistantMessage, sources);
        } else if (data.type === 'done') {
            if (statusDiv) statusDiv.remove();
            eventSource.close();
            eventSource = null;
        }
    };

    eventSource.onerror = () => {
        if (statusDiv) statusDiv.remove();
        eventSource.close();
        eventSource = null;
    };

    function updateLastMessage(content, sources) {
        const messages = document.querySelectorAll('.message.assistant');
        let lastMessage = messages[messages.length - 1];

        if (!lastMessage) {
            appendMessage('assistant', content, sources);
        } else {
            const contentDiv = lastMessage.querySelector('.message-content');
            contentDiv.textContent = content;

            if (sources.length > 0) {
                let sourcesDiv = contentDiv.querySelector('.sources');
                if (!sourcesDiv) {
                    sourcesDiv = document.createElement('div');
                    sourcesDiv.className = 'sources';
                    contentDiv.appendChild(sourcesDiv);
                }
                sourcesDiv.innerHTML = 'Sources: ' + sources.map(id =>
                    `<a href="#" class="source-link" onclick="viewSource(${id}); return false;">[${id}]</a>`
                ).join(' ');
            }
        }
    }
}

// Settings
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();

        document.getElementById('themeSetting').value = settings.theme || 'dark';
        document.getElementById('languageSetting').value = settings.language || 'fr';
        document.getElementById('showConfidence').checked = settings.show_confidence === '1';
        document.getElementById('showSources').checked = settings.show_sources === '1';
        document.getElementById('maxAutoQueries').value = settings.auto_max_queries || '20';

        applyTheme(settings.theme || 'dark');
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

function openSettings() {
    document.getElementById('settingsModal').classList.remove('hidden');
}

function closeSettings() {
    document.getElementById('settingsModal').classList.add('hidden');
}

async function saveSettings() {
    const settings = {
        theme: document.getElementById('themeSetting').value,
        language: document.getElementById('languageSetting').value,
        show_confidence: document.getElementById('showConfidence').checked ? '1' : '0',
        show_sources: document.getElementById('showSources').checked ? '1' : '0',
        auto_max_queries: document.getElementById('maxAutoQueries').value
    };

    try {
        await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        applyTheme(settings.theme);
        closeSettings();
    } catch (error) {
        console.error('Failed to save settings:', error);
    }
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
}

function viewSource(id) {
    console.log('View source:', id);
    // TODO: Implement source viewer modal
}
JSEOF

echo "✓ Frontend files generated"
