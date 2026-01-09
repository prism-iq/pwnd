/**
 * Live Frontend System
 * - Hot-reload via SSE
 * - Chain upload with progress tracking
 * - Auto-reconnect on disconnect
 */

class LiveSystem {
    constructor() {
        this.hotReloadEnabled = true;
        this.uploadQueue = [];
        this.activeJobs = new Map();
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;

        this.init();
    }

    init() {
        if (this.hotReloadEnabled) {
            this.connectHotReload();
        }

        console.log('[Live] System initialized');
    }

    // ===== HOT RELOAD =====

    connectHotReload() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        console.log('[HotReload] Connecting to /api/live...');

        this.eventSource = new EventSource('/api/live');

        this.eventSource.onopen = () => {
            console.log('[HotReload] Connected ✓');
            this.reconnectAttempts = 0;
        };

        this.eventSource.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                this.handleHotReloadEvent(data);
            } catch (err) {
                console.error('[HotReload] Parse error:', err);
            }
        };

        this.eventSource.onerror = () => {
            console.warn('[HotReload] Connection lost, reconnecting...');
            this.eventSource.close();

            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                setTimeout(() => this.connectHotReload(), 2000);
            } else {
                console.error('[HotReload] Max reconnect attempts reached');
            }
        };
    }

    handleHotReloadEvent(data) {
        const { event, file, path } = data;

        console.log(`[HotReload] ${event}: ${file}`);

        switch (event) {
            case 'connected':
                this.showNotification('Hot-reload connected', 'success');
                break;

            case 'reload-css':
                this.reloadCSS(path);
                this.showNotification(`CSS updated: ${file}`, 'info');
                break;

            case 'reload-js':
                this.reloadJS(path);
                this.showNotification(`JS updated: ${file}`, 'info');
                break;

            case 'reload-html':
            case 'reload-page':
                this.reloadPage();
                break;
        }
    }

    reloadCSS(path) {
        // Find all CSS links and reload them
        const links = document.querySelectorAll('link[rel="stylesheet"]');

        links.forEach(link => {
            if (!path || link.href.includes(path)) {
                const href = link.href.split('?')[0];
                link.href = `${href}?t=${Date.now()}`;
            }
        });
    }

    reloadJS(path) {
        // For JS, we need to reload the page (can't hot-swap modules easily)
        console.log('[HotReload] JS changed, reloading page...');
        setTimeout(() => window.location.reload(), 500);
    }

    reloadPage() {
        console.log('[HotReload] HTML changed, reloading page...');
        window.location.reload();
    }

    // ===== CHAIN UPLOAD =====

    async uploadFiles(files, options = {}) {
        const {
            extractEntities = false,
            onProgress = null,
            onComplete = null,
            onError = null
        } = options;

        console.log(`[Upload] Starting chain upload: ${files.length} files`);

        const results = [];

        for (let i = 0; i < files.length; i++) {
            const file = files[i];

            try {
                const result = await this.uploadSingleFile(file, extractEntities, (progress) => {
                    if (onProgress) {
                        onProgress(i, file.name, progress);
                    }
                });

                results.push({
                    file: file.name,
                    success: true,
                    result
                });

                console.log(`[Upload] ✓ ${file.name} (${i + 1}/${files.length})`);

            } catch (error) {
                results.push({
                    file: file.name,
                    success: false,
                    error: error.message
                });

                console.error(`[Upload] ✗ ${file.name}:`, error);

                if (onError) {
                    onError(i, file.name, error);
                }
            }
        }

        if (onComplete) {
            onComplete(results);
        }

        return results;
    }

    async uploadSingleFile(file, extractEntities, onProgress) {
        // Create FormData
        const formData = new FormData();
        formData.append('file', file);
        formData.append('extract_entities', extractEntities);

        // Upload and get job_id
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const { job_id, filename } = await response.json();

        console.log(`[Upload] Job created: ${job_id} for ${filename}`);

        // Track progress via SSE
        return new Promise((resolve, reject) => {
            const progressSource = new EventSource(`/api/upload/progress/${job_id}`);
            this.activeJobs.set(job_id, progressSource);

            progressSource.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    const { event: eventType, job } = data;

                    if (job) {
                        const { status, progress, error, result } = job;

                        // Call progress callback
                        if (onProgress) {
                            onProgress({
                                status,
                                progress,
                                total: 100
                            });
                        }

                        // Handle completion
                        if (status === 'done') {
                            progressSource.close();
                            this.activeJobs.delete(job_id);
                            resolve(result);
                        } else if (status === 'error') {
                            progressSource.close();
                            this.activeJobs.delete(job_id);
                            reject(new Error(error || 'Processing failed'));
                        }
                    }

                } catch (err) {
                    console.error('[Upload] Progress parse error:', err);
                }
            };

            progressSource.onerror = () => {
                progressSource.close();
                this.activeJobs.delete(job_id);
                reject(new Error('Progress stream lost'));
            };
        });
    }

    async getJobs() {
        const response = await fetch('/api/jobs');
        const data = await response.json();
        return data.jobs;
    }

    async getJob(jobId) {
        const response = await fetch(`/api/jobs/${jobId}`);
        return await response.json();
    }

    // ===== NOTIFICATIONS =====

    showNotification(message, type = 'info') {
        // Simple console notification
        // In production, use toast/snackbar UI
        const emoji = {
            success: '✓',
            info: 'ℹ',
            warning: '⚠',
            error: '✗'
        }[type] || 'ℹ';

        console.log(`[Notification] ${emoji} ${message}`);

        // Dispatch custom event for UI to catch
        window.dispatchEvent(new CustomEvent('live:notification', {
            detail: { message, type }
        }));
    }

    // ===== CLEANUP =====

    destroy() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.activeJobs.forEach(source => source.close());
        this.activeJobs.clear();

        console.log('[Live] System destroyed');
    }
}

// Global instance
const liveSystem = new LiveSystem();

// Expose to window
window.liveSystem = liveSystem;

// Auto-cleanup on unload
window.addEventListener('beforeunload', () => {
    liveSystem.destroy();
});

// Listen for notifications and show in UI
window.addEventListener('live:notification', (e) => {
    const { message, type } = e.detail;

    // Create toast notification (if UI supports it)
    const toast = document.getElementById('live-toast');
    if (toast) {
        toast.textContent = message;
        toast.className = `toast toast-${type}`;
        toast.style.display = 'block';

        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }
});

console.log('[Live] live.js loaded ✓');
