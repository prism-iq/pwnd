// App.js - Application initialization

let chatUI;

async function initApp() {
    console.log('HybridCore 2.0 initializing...');

    // Initialize chat UI
    chatUI = new ChatUI();

    // Load stats
    await loadStats();

    // Periodic stats refresh
    setInterval(loadStats, 30000);
}

async function loadStats() {
    try {
        const stats = await API.stats();

        // Update document count
        const docsEl = document.getElementById('stat-docs');
        if (docsEl) {
            docsEl.textContent = `${stats.documents || 0} docs`;
        }

        // Update LLM status
        const llmEl = document.getElementById('stat-llm');
        if (llmEl) {
            if (stats.llm_ready) {
                llmEl.textContent = 'LLM: Online';
                llmEl.classList.add('online');
                llmEl.classList.remove('offline');
            } else {
                llmEl.textContent = 'LLM: Offline';
                llmEl.classList.add('offline');
                llmEl.classList.remove('online');
            }
        }
    } catch (err) {
        console.error('Failed to load stats:', err);

        const llmEl = document.getElementById('stat-llm');
        if (llmEl) {
            llmEl.textContent = 'API: Error';
            llmEl.classList.add('offline');
        }
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', initApp);
