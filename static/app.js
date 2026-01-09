// ========================================
// State Management
// ========================================
let currentConversationId = null;
let autoInvestigateEnabled = false;
let eventSource = null;
let autoQueryCount = 0;
let maxAutoQueries = 20;
let isProcessing = false; // Prevent multiple concurrent queries

// ========================================
// Initialization
// ========================================
document.addEventListener('DOMContentLoaded', () => {
    initializeMarked();
    loadStats();
    loadSettings();
    loadConversations();
    attachEventListeners();
});

// Configure markdown renderer
function initializeMarked() {
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: false,
            mangle: false
        });
    }
}

// Load system stats
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        document.getElementById('statsEmails').textContent = stats.sources.toLocaleString();
        document.getElementById('statsNodes').textContent = stats.nodes.toLocaleString();
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// ========================================
// Event Listeners
// ========================================
function attachEventListeners() {
    const sendBtn = document.getElementById('sendBtn');
    const messageInput = document.getElementById('messageInput');
    const autoInvestigate = document.getElementById('autoInvestigate');

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
        // Disable send button if empty OR processing
        sendBtn.disabled = !messageInput.value.trim() || isProcessing;
    });

    document.getElementById('newChatBtn').addEventListener('click', createNewConversation);
    document.getElementById('settingsBtn').addEventListener('click', openSettings);

    autoInvestigate.addEventListener('change', (e) => {
        autoInvestigateEnabled = e.target.checked;
        if (!autoInvestigateEnabled) {
            hideAutoInvestigateBanner();
            localStorage.setItem('autoQueryCount', '0');
            autoQueryCount = 0;
        }
    });

    document.getElementById('stopAutoInvestigate')?.addEventListener('click', () => {
        autoInvestigateEnabled = false;
        document.getElementById('autoInvestigate').checked = false;
        hideAutoInvestigateBanner();
        localStorage.setItem('autoQueryCount', '0');
        autoQueryCount = 0;

        // Close current EventSource if running
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        isProcessing = false;
        enableInput();
    });

    // Mobile menu
    document.getElementById('mobileMenuBtn').addEventListener('click', toggleMobileMenu);
    document.getElementById('mobileOverlay').addEventListener('click', closeMobileMenu);

    // Example buttons
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (!isProcessing) {
                messageInput.value = btn.textContent;
                sendMessage();
            }
        });
    });
}

// ========================================
// Mobile Menu
// ========================================
function toggleMobileMenu() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('mobileOverlay').classList.toggle('active');
}

function closeMobileMenu() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('mobileOverlay').classList.remove('active');
}

// ========================================
// Conversations
// ========================================
async function loadConversations() {
    try {
        const response = await fetch('/api/conversations');
        const conversations = await response.json();

        const list = document.getElementById('conversationList');
        list.innerHTML = '';

        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            item.textContent = conv.title || 'Untitled Investigation';
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
    if (isProcessing) return; // Don't allow during processing

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
    if (isProcessing) return; // Don't allow during processing

    currentConversationId = id;
    clearMessages();

    try {
        const response = await fetch(`/api/conversations/${id}/messages`);
        const messages = await response.json();

        messages.forEach(msg => {
            appendMessage(msg.role, msg.content, msg.sources || []);
        });

        await loadConversations();
        closeMobileMenu();
    } catch (error) {
        console.error('Failed to load conversation:', error);
    }
}

// ========================================
// Messages
// ========================================
function clearMessages() {
    const messagesDiv = document.getElementById('messages');
    messagesDiv.innerHTML = '';
}

function appendMessage(role, content, sources = []) {
    const messagesDiv = document.getElementById('messages');

    // Remove welcome screen
    const welcome = messagesDiv.querySelector('.welcome-screen');
    if (welcome) welcome.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.setAttribute('data-message-id', Date.now() + Math.random()); // Unique ID

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? 'U' : 'L';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Render markdown for assistant messages
    if (role === 'assistant' && typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.textContent = content;
    }

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(contentDiv);

    // Add sources if available
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

    return messageDiv; // Return for tracking
}

function appendStatus(msg) {
    const messagesDiv = document.getElementById('messages');

    // Remove welcome screen
    const welcome = messagesDiv.querySelector('.welcome-screen');
    if (welcome) welcome.remove();

    const statusDiv = document.createElement('div');
    statusDiv.className = 'status-message';
    statusDiv.innerHTML = `
        <div class="typing-indicator">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
        </div>
        ${escapeHtml(msg)}
    `;
    messagesDiv.appendChild(statusDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return statusDiv;
}

function disableInput() {
    const sendBtn = document.getElementById('sendBtn');
    const messageInput = document.getElementById('messageInput');
    sendBtn.disabled = true;
    messageInput.disabled = true;
    isProcessing = true;
}

function enableInput() {
    const sendBtn = document.getElementById('sendBtn');
    const messageInput = document.getElementById('messageInput');
    messageInput.disabled = false;
    sendBtn.disabled = !messageInput.value.trim();
    isProcessing = false;
}

async function sendMessage() {
    if (isProcessing) return; // Prevent multiple concurrent queries

    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message) return;

    // Disable input during processing
    disableInput();

    // Append user message
    appendMessage('user', message);
    input.value = '';
    input.style.height = 'auto';

    try {
        await processQuery(message);
    } catch (error) {
        console.error('Error processing query:', error);
        appendStatus('Error: ' + error.message);
        enableInput();
    }
}

async function processQuery(query) {
    // Close any existing EventSource first
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    const url = `/api/ask?q=${encodeURIComponent(query)}${currentConversationId ? `&conversation_id=${currentConversationId}` : ''}`;

    let assistantMessage = '';
    let sources = [];
    let statusDiv = null;
    let suggestedQueries = [];
    let currentMessageDiv = null; // Track the current assistant message

    // Update auto-investigate counter and banner
    if (autoInvestigateEnabled) {
        autoQueryCount = parseInt(localStorage.getItem('autoQueryCount') || '0');
        showAutoInvestigateBanner(autoQueryCount + 1, maxAutoQueries);
    }

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
            updateCurrentMessage(assistantMessage, sources);
        } else if (data.type === 'sources') {
            sources = data.ids;
            updateCurrentMessage(assistantMessage, sources);
        } else if (data.type === 'suggestions') {
            // Extract suggested queries for auto-investigation
            suggestedQueries = data.queries || [];
        } else if (data.type === 'debug' && data.haiku_analysis) {
            // Legacy: Extract suggested queries from debug
            suggestedQueries = data.haiku_analysis.suggested_queries || [];
        } else if (data.type === 'done') {
            if (statusDiv) statusDiv.remove();
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }

            // Enable input after query completes
            enableInput();

            // Auto-investigation: trigger next query if enabled
            if (autoInvestigateEnabled && suggestedQueries.length > 0 && autoQueryCount < maxAutoQueries) {
                // Increment counter AFTER successful query
                autoQueryCount++;
                localStorage.setItem('autoQueryCount', autoQueryCount.toString());

                // Pick first suggested query
                const nextQuery = suggestedQueries[0];

                // Delay before auto-query
                setTimeout(() => {
                    if (!autoInvestigateEnabled) return; // User might have disabled it

                    disableInput(); // Disable for next query
                    showAutoInvestigateBanner(autoQueryCount + 1, maxAutoQueries);

                    const statusMsg = appendStatus(`Auto-investigating (${autoQueryCount}/${maxAutoQueries}): ${nextQuery}`);
                    setTimeout(() => {
                        if (statusMsg && statusMsg.parentNode) statusMsg.remove();
                        processQuery(nextQuery);
                    }, 1500);
                }, 2000);
            } else {
                // Reset counter when done
                localStorage.setItem('autoQueryCount', '0');
                autoQueryCount = 0;
                hideAutoInvestigateBanner();
            }
        }
    };

    eventSource.onerror = (error) => {
        console.error('EventSource error:', error);
        if (statusDiv) statusDiv.remove();
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        enableInput();
        appendStatus('Connection error. Please try again.');
    };

    function updateCurrentMessage(content, sources) {
        // Get the last assistant message or create new one
        const messages = document.querySelectorAll('.message.assistant');
        let lastMessage = messages[messages.length - 1];

        if (!lastMessage || lastMessage !== currentMessageDiv) {
            // Create new message if needed
            currentMessageDiv = appendMessage('assistant', content, sources);
            return; // FIX: Return after creating to avoid double update
        }
        
        // Update existing message
        const contentDiv = lastMessage.querySelector('.message-content');
        
        // Clear old content first
        contentDiv.innerHTML = '';

        // Render markdown
        if (typeof marked !== 'undefined' && content) {
            contentDiv.innerHTML = marked.parse(content);
        } else {
            contentDiv.textContent = content;
        }

        // Update sources
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
            const messagesContainer = document.getElementById('messages');
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
}

// ========================================
// Auto-Investigate Banner
// ========================================
function showAutoInvestigateBanner(current, max) {
    const banner = document.getElementById('autoInvestigateBanner');
    const progress = document.getElementById('autoInvestigateProgress');

    if (banner && progress) {
        progress.textContent = `Query ${current} of ${max}`;
        banner.classList.remove('hidden');
    }
}

function hideAutoInvestigateBanner() {
    const banner = document.getElementById('autoInvestigateBanner');
    if (banner) {
        banner.classList.add('hidden');
    }
}

// ========================================
// Source Viewer
// ========================================
function viewSource(id) {
    // Open source viewer in new tab
    window.open(`/source.html?id=${id}`, '_blank');
}

function createSourceModal() {
    const modal = document.createElement('div');
    modal.id = 'sourceModal';
    modal.className = 'modal hidden';
    modal.innerHTML = `
        <div class="modal-backdrop" onclick="closeSourceModal()"></div>
        <div class="modal-content source-modal-content">
            <div class="modal-header">
                <h2>Source</h2>
                <button class="modal-close" onclick="closeSourceModal()">×</button>
            </div>
            <div class="modal-body source-modal-body"></div>
        </div>
    `;
    document.body.appendChild(modal);
    return modal;
}

function closeSourceModal() {
    const modal = document.getElementById('sourceModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// ========================================
// Settings
// ========================================
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();

        document.getElementById('themeSetting').value = settings.theme || 'dark';
        document.getElementById('languageSetting').value = settings.language || 'en';
        document.getElementById('showConfidence').checked = settings.show_confidence === '1';
        document.getElementById('showSources').checked = settings.show_sources === '1';
        document.getElementById('showDebug').checked = settings.show_debug === '1';

        maxAutoQueries = parseInt(settings.auto_max_queries || '20');
        document.getElementById('maxAutoQueries').value = maxAutoQueries;

        applyTheme(settings.theme || 'dark');
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

async function saveSettings() {
    const settings = {
        theme: document.getElementById('themeSetting').value,
        language: document.getElementById('languageSetting').value,
        show_confidence: document.getElementById('showConfidence').checked ? '1' : '0',
        show_sources: document.getElementById('showSources').checked ? '1' : '0',
        show_debug: document.getElementById('showDebug').checked ? '1' : '0',
        auto_max_queries: document.getElementById('maxAutoQueries').value
    };

    try {
        await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        maxAutoQueries = parseInt(settings.auto_max_queries);
        applyTheme(settings.theme);
        closeSettings();
    } catch (error) {
        console.error('Failed to save settings:', error);
        alert('Failed to save settings');
    }
}

function openSettings() {
    document.getElementById('settingsModal').classList.remove('hidden');
}

function closeSettings() {
    document.getElementById('settingsModal').classList.add('hidden');
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
}

// ========================================
// Utilities
// ========================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
