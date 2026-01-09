// ADVANCED FEATURES FOR L INVESTIGATION FRAMEWORK
// Fast implementation - all features users want

// ========================================
// 1. KEYBOARD SHORTCUTS
// ========================================
document.addEventListener('keydown', (e) => {
    // Ctrl+K: Focus search
    if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        document.getElementById('messageInput').focus();
    }

    // Ctrl+N: New investigation
    if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        document.getElementById('newChatBtn').click();
    }

    // Ctrl+/: Show shortcuts help
    if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
        showShortcutsHelp();
    }

    // Ctrl+E: Export current investigation
    if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        exportInvestigation();
    }

    // Esc: Stop auto-investigate
    if (e.key === 'Escape' && autoInvestigateEnabled) {
        document.getElementById('stopAutoInvestigate')?.click();
    }
});

// ========================================
// 2. EXPORT FUNCTIONS
// ========================================
function exportInvestigation() {
    const messages = document.querySelectorAll('.message');
    const timestamp = new Date().toISOString().split('T')[0];

    // Export as Markdown
    let markdown = `# L Investigation - ${timestamp}\n\n`;
    markdown += `**Bound by The Code**\n\n`;

    messages.forEach(msg => {
        const role = msg.classList.contains('user-message') ? 'USER' : 'DETECTIVE';
        const content = msg.querySelector('.message-content')?.innerText || '';
        markdown += `## ${role}\n${content}\n\n`;
    });

    downloadFile(`investigation_${timestamp}.md`, markdown, 'text/markdown');
    showToast('Investigation exported as Markdown');
}

function exportAsJSON() {
    const messages = Array.from(document.querySelectorAll('.message')).map(msg => ({
        role: msg.classList.contains('user-message') ? 'user' : 'assistant',
        content: msg.querySelector('.message-content')?.innerText || '',
        timestamp: new Date().toISOString()
    }));

    const data = {
        investigation_id: currentConversationId,
        timestamp: new Date().toISOString(),
        messages: messages,
        code: "Protect the weak. Report truth. Fight evil."
    };

    downloadFile(`investigation_${Date.now()}.json`, JSON.stringify(data, null, 2), 'application/json');
    showToast('Investigation exported as JSON');
}

function downloadFile(filename, content, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// ========================================
// 3. COPY TO CLIPBOARD
// ========================================
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard');
    });
}

// Add copy button to all messages
function addCopyButtons() {
    document.querySelectorAll('.message-content').forEach(content => {
        if (content.querySelector('.copy-btn')) return; // Already has button

        const btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.innerHTML = '📋';
        btn.title = 'Copy to clipboard';
        btn.onclick = () => copyToClipboard(content.innerText);
        content.appendChild(btn);
    });
}

// ========================================
// 4. SUGGESTED QUESTIONS
// ========================================
const SUGGESTED_QUESTIONS = [
    "Who is Jeffrey Epstein?",
    "Timeline of communications",
    "Find connections to Donald Trump",
    "Search for minors mentioned",
    "Emails about money transfers",
    "Who traveled with Jeffrey Epstein?",
    "Financial transactions",
    "Suspicious patterns in emails",
    "Network of contacts",
    "Emails mentioning victims"
];

function showSuggestedQuestions() {
    const container = document.getElementById('suggestedQuestions');
    if (!container) {
        const div = document.createElement('div');
        div.id = 'suggestedQuestions';
        div.className = 'suggested-questions';
        div.innerHTML = '<h3>Suggested Questions</h3>';

        SUGGESTED_QUESTIONS.forEach(q => {
            const btn = document.createElement('button');
            btn.className = 'suggestion-btn';
            btn.textContent = q;
            btn.onclick = () => {
                document.getElementById('messageInput').value = q;
                document.getElementById('sendBtn').click();
            };
            div.appendChild(btn);
        });

        document.querySelector('.chat-messages')?.prepend(div);
    }
}

// ========================================
// 5. SEARCH HISTORY
// ========================================
function saveToHistory(query) {
    let history = JSON.parse(localStorage.getItem('searchHistory') || '[]');
    history.unshift({
        query,
        timestamp: new Date().toISOString()
    });
    history = history.slice(0, 50); // Keep last 50
    localStorage.setItem('searchHistory', JSON.stringify(history));
}

function showSearchHistory() {
    const history = JSON.parse(localStorage.getItem('searchHistory') || '[]');
    const modal = createModal('Search History', history.map(h =>
        `<div class="history-item" onclick="document.getElementById('messageInput').value='${h.query.replace(/'/g, "\\'")}'; closeModal();">
            <div class="history-query">${h.query}</div>
            <div class="history-time">${new Date(h.timestamp).toLocaleString()}</div>
        </div>`
    ).join(''));
    document.body.appendChild(modal);
}

// ========================================
// 6. BOOKMARKS
// ========================================
function bookmarkSource(sourceId) {
    let bookmarks = JSON.parse(localStorage.getItem('bookmarks') || '[]');
    if (!bookmarks.includes(sourceId)) {
        bookmarks.push(sourceId);
        localStorage.setItem('bookmarks', JSON.stringify(bookmarks));
        showToast(`Source [${sourceId}] bookmarked`);
    }
}

function showBookmarks() {
    const bookmarks = JSON.parse(localStorage.getItem('bookmarks') || '[]');
    const modal = createModal('Bookmarked Sources',
        bookmarks.length ? bookmarks.map(id =>
            `<div class="bookmark-item">
                <a href="/source.html?id=${id}" target="_blank">Source [${id}]</a>
                <button onclick="removeBookmark(${id})">Remove</button>
            </div>`
        ).join('') : '<p>No bookmarks yet</p>'
    );
    document.body.appendChild(modal);
}

function removeBookmark(sourceId) {
    let bookmarks = JSON.parse(localStorage.getItem('bookmarks') || '[]');
    bookmarks = bookmarks.filter(id => id !== sourceId);
    localStorage.setItem('bookmarks', JSON.stringify(bookmarks));
    showBookmarks(); // Refresh
}

// ========================================
// 7. TOAST NOTIFICATIONS
// ========================================
function showToast(message, duration = 3000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ========================================
// 8. MODAL HELPER
// ========================================
function createModal(title, content) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>${title}</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">${content}</div>
        </div>
    `;
    modal.onclick = (e) => {
        if (e.target === modal) closeModal();
    };
    return modal;
}

function closeModal() {
    document.querySelectorAll('.modal-overlay').forEach(m => m.remove());
}

// ========================================
// 9. SHORTCUTS HELP
// ========================================
function showShortcutsHelp() {
    const shortcuts = `
        <table class="shortcuts-table">
            <tr><td><kbd>Ctrl</kbd> + <kbd>K</kbd></td><td>Focus search</td></tr>
            <tr><td><kbd>Ctrl</kbd> + <kbd>N</kbd></td><td>New investigation</td></tr>
            <tr><td><kbd>Ctrl</kbd> + <kbd>E</kbd></td><td>Export investigation</td></tr>
            <tr><td><kbd>Ctrl</kbd> + <kbd>/</kbd></td><td>Show shortcuts</td></tr>
            <tr><td><kbd>Esc</kbd></td><td>Stop auto-investigate</td></tr>
            <tr><td><kbd>Enter</kbd></td><td>Send message</td></tr>
            <tr><td><kbd>Shift</kbd> + <kbd>Enter</kbd></td><td>New line</td></tr>
        </table>
    `;
    const modal = createModal('Keyboard Shortcuts', shortcuts);
    document.body.appendChild(modal);
}

// ========================================
// 10. QUICK ACTIONS MENU
// ========================================
function createQuickActionsMenu() {
    const menu = document.createElement('div');
    menu.id = 'quickActions';
    menu.className = 'quick-actions';
    menu.innerHTML = `
        <button onclick="exportInvestigation()" title="Export as Markdown">📄 Export MD</button>
        <button onclick="exportAsJSON()" title="Export as JSON">📦 Export JSON</button>
        <button onclick="showSearchHistory()" title="Search History">🕐 History</button>
        <button onclick="showBookmarks()" title="Bookmarked Sources">⭐ Bookmarks</button>
        <button onclick="showShortcutsHelp()" title="Keyboard Shortcuts">⌨️ Shortcuts</button>
        <button onclick="shareInvestigation()" title="Share Investigation">🔗 Share</button>
    `;
    return menu;
}

// ========================================
// 11. SHARE INVESTIGATION
// ========================================
function shareInvestigation() {
    const url = window.location.href;
    const title = 'L Investigation Framework - OSINT Analysis';

    if (navigator.share) {
        navigator.share({ title, url }).catch(() => {});
    } else {
        copyToClipboard(url);
        showToast('Investigation URL copied to clipboard');
    }
}

// ========================================
// 12. AUTO-SAVE DRAFT
// ========================================
let draftTimer;
function saveDraft() {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => {
        const input = document.getElementById('messageInput');
        if (input.value.trim()) {
            localStorage.setItem('draft', input.value);
        }
    }, 1000);
}

function loadDraft() {
    const draft = localStorage.getItem('draft');
    if (draft) {
        document.getElementById('messageInput').value = draft;
        showToast('Draft restored');
    }
}

function clearDraft() {
    localStorage.removeItem('draft');
}

// ========================================
// 13. INIT FEATURES
// ========================================
document.addEventListener('DOMContentLoaded', () => {
    // Add quick actions menu to header
    const header = document.querySelector('.mobile-header') || document.querySelector('.sidebar-header');
    if (header && !document.getElementById('quickActions')) {
        header.appendChild(createQuickActionsMenu());
    }

    // Show suggested questions on empty chat
    const messages = document.querySelectorAll('.message');
    if (messages.length === 0) {
        showSuggestedQuestions();
    }

    // Load draft
    loadDraft();

    // Auto-save drafts
    const input = document.getElementById('messageInput');
    if (input) {
        input.addEventListener('input', saveDraft);
    }

    // Add copy buttons periodically
    setInterval(addCopyButtons, 2000);

    console.log('✅ Advanced features loaded: Keyboard shortcuts, Export, History, Bookmarks, Share');
});
