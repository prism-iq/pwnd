/**
 * AJAX Engine - L Investigation Framework
 * Pure vanilla JS, no frameworks, maximum control
 *
 * Features:
 * - Live search with debounce
 * - Infinite scroll
 * - SSE streaming
 * - Background sync
 * - Request queuing
 * - Retry with backoff
 * - Cache layer
 * - Optimistic updates
 */

// =============================================================================
// AJAX CORE
// =============================================================================

const AJAX = {
    baseURL: '/api',
    timeout: 30000,
    retries: 3,
    cache: new Map(),
    cacheTTL: 60000, // 1 minute
    pending: new Map(),
    queue: [],
    maxConcurrent: 6,
    active: 0,

    /**
     * Core request method with all the bells and whistles
     */
    async request(method, endpoint, data = null, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const cacheKey = `${method}:${url}:${JSON.stringify(data)}`;

        // Check cache for GET requests
        if (method === 'GET' && !options.noCache) {
            const cached = this.getCache(cacheKey);
            if (cached) return cached;
        }

        // Dedupe identical pending requests
        if (this.pending.has(cacheKey)) {
            return this.pending.get(cacheKey);
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), options.timeout || this.timeout);

        const config = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                ...options.headers
            },
            signal: controller.signal
        };

        if (data && method !== 'GET') {
            config.body = JSON.stringify(data);
        }

        const promise = this._executeWithRetry(url, config, options.retries || this.retries)
            .then(response => {
                clearTimeout(timeoutId);
                this.pending.delete(cacheKey);

                // Cache successful GET requests
                if (method === 'GET' && !options.noCache) {
                    this.setCache(cacheKey, response);
                }

                return response;
            })
            .catch(err => {
                clearTimeout(timeoutId);
                this.pending.delete(cacheKey);
                throw err;
            });

        this.pending.set(cacheKey, promise);
        return promise;
    },

    async _executeWithRetry(url, config, retriesLeft) {
        try {
            const response = await fetch(url, config);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        } catch (err) {
            if (retriesLeft > 0 && !err.name?.includes('Abort')) {
                await this.sleep(1000 * (this.retries - retriesLeft + 1)); // Exponential backoff
                return this._executeWithRetry(url, config, retriesLeft - 1);
            }
            throw err;
        }
    },

    // Convenience methods
    get: (endpoint, options) => AJAX.request('GET', endpoint, null, options),
    post: (endpoint, data, options) => AJAX.request('POST', endpoint, data, options),
    put: (endpoint, data, options) => AJAX.request('PUT', endpoint, data, options),
    delete: (endpoint, options) => AJAX.request('DELETE', endpoint, null, options),

    // Cache management
    getCache(key) {
        const item = this.cache.get(key);
        if (!item) return null;
        if (Date.now() > item.expires) {
            this.cache.delete(key);
            return null;
        }
        return item.data;
    },

    setCache(key, data) {
        this.cache.set(key, {
            data,
            expires: Date.now() + this.cacheTTL
        });
    },

    clearCache() {
        this.cache.clear();
    },

    sleep: (ms) => new Promise(r => setTimeout(r, ms))
};


// =============================================================================
// SSE STREAMING
// =============================================================================

class SSEStream {
    constructor(url, handlers = {}) {
        this.url = url;
        this.handlers = handlers;
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnects = 5;
        this.reconnectDelay = 1000;
    }

    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.eventSource = new EventSource(this.url);

        this.eventSource.onopen = () => {
            this.reconnectAttempts = 0;
            this.handlers.onOpen?.();
        };

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handlers.onMessage?.(data);

                // Route to specific handlers
                if (data.type && this.handlers[`on${data.type.charAt(0).toUpperCase() + data.type.slice(1)}`]) {
                    this.handlers[`on${data.type.charAt(0).toUpperCase() + data.type.slice(1)}`](data);
                }
            } catch (e) {
                this.handlers.onError?.(e);
            }
        };

        this.eventSource.onerror = (err) => {
            this.handlers.onError?.(err);

            if (this.reconnectAttempts < this.maxReconnects) {
                this.reconnectAttempts++;
                setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts);
            } else {
                this.handlers.onMaxReconnects?.();
            }
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


// =============================================================================
// LIVE SEARCH
// =============================================================================

class LiveSearch {
    constructor(inputEl, resultsEl, options = {}) {
        this.input = typeof inputEl === 'string' ? document.querySelector(inputEl) : inputEl;
        this.results = typeof resultsEl === 'string' ? document.querySelector(resultsEl) : resultsEl;
        this.options = {
            debounce: 150,
            minChars: 2,
            endpoint: '/search',
            renderItem: (item) => `<div class="search-item">${item.name || item.text}</div>`,
            onSelect: () => {},
            ...options
        };

        this.debounceTimer = null;
        this.currentQuery = '';
        this.selectedIndex = -1;
        this.items = [];

        this._bindEvents();
    }

    _bindEvents() {
        // Input events
        this.input.addEventListener('input', (e) => this._onInput(e));
        this.input.addEventListener('keydown', (e) => this._onKeydown(e));
        this.input.addEventListener('focus', () => this._onFocus());
        this.input.addEventListener('blur', () => setTimeout(() => this._hideResults(), 200));

        // Results click
        this.results.addEventListener('click', (e) => {
            const item = e.target.closest('.search-item');
            if (item) {
                const index = parseInt(item.dataset.index);
                this._selectItem(index);
            }
        });
    }

    _onInput(e) {
        const query = e.target.value.trim();

        clearTimeout(this.debounceTimer);

        if (query.length < this.options.minChars) {
            this._hideResults();
            return;
        }

        this.debounceTimer = setTimeout(() => this._search(query), this.options.debounce);
    }

    async _search(query) {
        if (query === this.currentQuery) return;
        this.currentQuery = query;

        this.results.innerHTML = '<div class="search-loading">Searching...</div>';
        this._showResults();

        try {
            const data = await AJAX.get(`${this.options.endpoint}?q=${encodeURIComponent(query)}`);
            this.items = Array.isArray(data) ? data : data.results || [];
            this._renderResults();
        } catch (err) {
            this.results.innerHTML = '<div class="search-error">Search failed</div>';
        }
    }

    _renderResults() {
        if (this.items.length === 0) {
            this.results.innerHTML = '<div class="search-empty">No results</div>';
            return;
        }

        this.results.innerHTML = this.items.map((item, i) =>
            `<div class="search-item" data-index="${i}">${this.options.renderItem(item)}</div>`
        ).join('');

        this.selectedIndex = -1;
    }

    _onKeydown(e) {
        const items = this.results.querySelectorAll('.search-item');

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
                this._highlightItem(items);
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
                this._highlightItem(items);
                break;
            case 'Enter':
                e.preventDefault();
                if (this.selectedIndex >= 0) {
                    this._selectItem(this.selectedIndex);
                }
                break;
            case 'Escape':
                this._hideResults();
                break;
        }
    }

    _highlightItem(items) {
        items.forEach((item, i) => {
            item.classList.toggle('selected', i === this.selectedIndex);
        });
        items[this.selectedIndex]?.scrollIntoView({ block: 'nearest' });
    }

    _selectItem(index) {
        const item = this.items[index];
        if (item) {
            this.input.value = item.name || item.text || '';
            this.options.onSelect(item);
            this._hideResults();
        }
    }

    _showResults() {
        this.results.classList.add('visible');
    }

    _hideResults() {
        this.results.classList.remove('visible');
    }

    _onFocus() {
        if (this.items.length > 0) {
            this._showResults();
        }
    }
}


// =============================================================================
// INFINITE SCROLL
// =============================================================================

class InfiniteScroll {
    constructor(containerEl, options = {}) {
        this.container = typeof containerEl === 'string' ? document.querySelector(containerEl) : containerEl;
        this.options = {
            threshold: 200,
            endpoint: '/items',
            pageSize: 20,
            renderItem: (item) => `<div class="item">${JSON.stringify(item)}</div>`,
            onLoad: () => {},
            ...options
        };

        this.page = 0;
        this.loading = false;
        this.hasMore = true;
        this.items = [];

        this._bindEvents();
    }

    _bindEvents() {
        // Use IntersectionObserver for better performance
        this.sentinel = document.createElement('div');
        this.sentinel.className = 'scroll-sentinel';
        this.container.appendChild(this.sentinel);

        this.observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !this.loading && this.hasMore) {
                this.loadMore();
            }
        }, { rootMargin: `${this.options.threshold}px` });

        this.observer.observe(this.sentinel);
    }

    async loadMore() {
        if (this.loading || !this.hasMore) return;

        this.loading = true;
        this._showLoader();

        try {
            const data = await AJAX.get(
                `${this.options.endpoint}?page=${this.page}&limit=${this.options.pageSize}`,
                { noCache: true }
            );

            const newItems = Array.isArray(data) ? data : data.items || [];
            this.items = [...this.items, ...newItems];
            this.hasMore = newItems.length === this.options.pageSize;
            this.page++;

            this._renderItems(newItems);
            this.options.onLoad(newItems, this.items);
        } catch (err) {
            console.error('Failed to load more:', err);
        } finally {
            this.loading = false;
            this._hideLoader();
        }
    }

    _renderItems(items) {
        const fragment = document.createDocumentFragment();
        items.forEach(item => {
            const div = document.createElement('div');
            div.innerHTML = this.options.renderItem(item);
            fragment.appendChild(div.firstChild);
        });
        this.container.insertBefore(fragment, this.sentinel);
    }

    _showLoader() {
        this.sentinel.innerHTML = '<div class="loading-spinner"></div>';
    }

    _hideLoader() {
        this.sentinel.innerHTML = '';
    }

    reset() {
        this.page = 0;
        this.items = [];
        this.hasMore = true;
        this.container.innerHTML = '';
        this.container.appendChild(this.sentinel);
    }

    destroy() {
        this.observer.disconnect();
    }
}


// =============================================================================
// BACKGROUND SYNC
// =============================================================================

class BackgroundSync {
    constructor(options = {}) {
        this.options = {
            interval: 30000,
            endpoints: [],
            onUpdate: () => {},
            ...options
        };

        this.timers = [];
        this.lastSync = {};
    }

    start() {
        this.options.endpoints.forEach(config => {
            const timer = setInterval(() => this._sync(config), config.interval || this.options.interval);
            this.timers.push(timer);

            // Initial sync
            this._sync(config);
        });
    }

    async _sync(config) {
        try {
            const data = await AJAX.get(config.endpoint, { noCache: true });
            const lastData = this.lastSync[config.endpoint];

            if (JSON.stringify(data) !== JSON.stringify(lastData)) {
                this.lastSync[config.endpoint] = data;
                config.onUpdate?.(data);
                this.options.onUpdate(config.endpoint, data);
            }
        } catch (err) {
            console.error(`Sync failed for ${config.endpoint}:`, err);
        }
    }

    stop() {
        this.timers.forEach(timer => clearInterval(timer));
        this.timers = [];
    }

    forceSync(endpoint) {
        const config = this.options.endpoints.find(e => e.endpoint === endpoint);
        if (config) this._sync(config);
    }
}


// =============================================================================
// POLLING
// =============================================================================

class Poller {
    constructor(endpoint, options = {}) {
        this.endpoint = endpoint;
        this.options = {
            interval: 5000,
            onData: () => {},
            onError: () => {},
            condition: () => true,
            ...options
        };

        this.timer = null;
        this.running = false;
    }

    start() {
        if (this.running) return;
        this.running = true;
        this._poll();
    }

    async _poll() {
        if (!this.running) return;

        try {
            const data = await AJAX.get(this.endpoint, { noCache: true });
            this.options.onData(data);

            if (this.options.condition(data)) {
                this.timer = setTimeout(() => this._poll(), this.options.interval);
            } else {
                this.stop();
            }
        } catch (err) {
            this.options.onError(err);
            if (this.running) {
                this.timer = setTimeout(() => this._poll(), this.options.interval * 2);
            }
        }
    }

    stop() {
        this.running = false;
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }
}


// =============================================================================
// REQUEST QUEUE (for rate limiting)
// =============================================================================

class RequestQueue {
    constructor(options = {}) {
        this.options = {
            maxConcurrent: 4,
            rateLimit: 100, // ms between requests
            ...options
        };

        this.queue = [];
        this.active = 0;
        this.lastRequest = 0;
    }

    add(requestFn) {
        return new Promise((resolve, reject) => {
            this.queue.push({ requestFn, resolve, reject });
            this._process();
        });
    }

    async _process() {
        if (this.active >= this.options.maxConcurrent || this.queue.length === 0) return;

        const timeSinceLastRequest = Date.now() - this.lastRequest;
        if (timeSinceLastRequest < this.options.rateLimit) {
            setTimeout(() => this._process(), this.options.rateLimit - timeSinceLastRequest);
            return;
        }

        const { requestFn, resolve, reject } = this.queue.shift();
        this.active++;
        this.lastRequest = Date.now();

        try {
            const result = await requestFn();
            resolve(result);
        } catch (err) {
            reject(err);
        } finally {
            this.active--;
            this._process();
        }
    }

    clear() {
        this.queue.forEach(({ reject }) => reject(new Error('Queue cleared')));
        this.queue = [];
    }
}


// =============================================================================
// OPTIMISTIC UPDATES
// =============================================================================

class OptimisticUpdate {
    constructor() {
        this.pending = new Map();
    }

    async execute(key, optimisticFn, serverFn, rollbackFn) {
        // Apply optimistic update immediately
        const previousState = optimisticFn();
        this.pending.set(key, previousState);

        try {
            // Execute server request
            const result = await serverFn();
            this.pending.delete(key);
            return result;
        } catch (err) {
            // Rollback on failure
            rollbackFn(previousState);
            this.pending.delete(key);
            throw err;
        }
    }
}


// =============================================================================
// L INVESTIGATION SPECIFIC AJAX
// =============================================================================

const LInvestigation = {
    // Stream a query with SSE
    streamQuery(query, conversationId, handlers = {}) {
        const url = `/api/ask?q=${encodeURIComponent(query)}${conversationId ? `&conversation_id=${conversationId}` : ''}`;
        return new SSEStream(url, {
            onMessage: handlers.onMessage,
            onStatus: handlers.onStatus,
            onThinking: handlers.onThinking,
            onChunk: handlers.onChunk,
            onSources: handlers.onSources,
            onSuggestions: handlers.onSuggestions,
            onDone: (data) => {
                handlers.onDone?.(data);
            },
            onError: handlers.onError
        }).connect();
    },

    // Parallel entity extraction
    async extractEntities(text, query = '', entityTypes = null) {
        const params = new URLSearchParams({ text, query });
        if (entityTypes) params.set('entity_types', entityTypes.join(','));

        return AJAX.post('/extract?' + params.toString());
    },

    // Live email search
    createEmailSearch(inputEl, resultsEl) {
        return new LiveSearch(inputEl, resultsEl, {
            endpoint: '/search/emails',
            debounce: 200,
            renderItem: (email) => `
                <div class="email-result">
                    <div class="email-subject">${email.name || 'No subject'}</div>
                    <div class="email-meta">
                        <span class="email-from">${email.sender_email || 'Unknown'}</span>
                        <span class="email-date">${email.date?.slice(0, 10) || ''}</span>
                    </div>
                </div>
            `
        });
    },

    // Live node search
    createNodeSearch(inputEl, resultsEl) {
        return new LiveSearch(inputEl, resultsEl, {
            endpoint: '/search/nodes',
            debounce: 150,
            renderItem: (node) => `
                <div class="node-result">
                    <span class="node-type ${node.type}">${node.type}</span>
                    <span class="node-name">${node.name}</span>
                </div>
            `
        });
    },

    // Infinite scroll for emails
    createEmailScroll(containerEl, query = '') {
        return new InfiniteScroll(containerEl, {
            endpoint: `/search/emails?q=${encodeURIComponent(query)}`,
            pageSize: 25,
            renderItem: (email) => `
                <article class="email-card" data-id="${email.id}">
                    <header>
                        <h3>${email.name || 'No subject'}</h3>
                        <time>${email.date?.slice(0, 10) || ''}</time>
                    </header>
                    <div class="email-body">
                        <p class="from">From: ${email.sender_email || 'Unknown'}</p>
                        <p class="snippet">${email.snippet?.slice(0, 200) || ''}...</p>
                    </div>
                </article>
            `
        });
    },

    // Background sync for stats
    createStatsSync(onUpdate) {
        return new BackgroundSync({
            interval: 30000,
            endpoints: [
                { endpoint: '/stats', onUpdate },
                { endpoint: '/extract/stats', onUpdate: (data) => onUpdate({ workers: data }) }
            ]
        });
    },

    // Poll for auto-investigation status
    pollAutoStatus(conversationId, onStatus) {
        return new Poller(`/auto/status?conversation_id=${conversationId}`, {
            interval: 2000,
            onData: onStatus,
            condition: (data) => data.running
        });
    }
};


// =============================================================================
// EXPORT
// =============================================================================

window.AJAX = AJAX;
window.SSEStream = SSEStream;
window.LiveSearch = LiveSearch;
window.InfiniteScroll = InfiniteScroll;
window.BackgroundSync = BackgroundSync;
window.Poller = Poller;
window.RequestQueue = RequestQueue;
window.OptimisticUpdate = OptimisticUpdate;
window.LInvestigation = LInvestigation;

console.log('AJAX Engine loaded - L Investigation Framework');
