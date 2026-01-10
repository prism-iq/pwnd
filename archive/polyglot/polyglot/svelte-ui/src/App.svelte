<script>
  import { onMount } from 'svelte';
  import { io } from 'socket.io-client';

  let query = '';
  let results = [];
  let status = 'idle';
  let organs = {};
  let sessionId = null;
  let socket = null;

  // Connect to lungs (Node.js) via WebSocket
  onMount(() => {
    socket = io('http://127.0.0.1:3000');

    socket.on('connect', () => {
      status = 'connected';
      checkHealth();
    });

    socket.on('session', (data) => {
      sessionId = data.sessionId;
    });

    socket.on('update', (data) => {
      results = [...results, { phase: data.phase, ...data }];
    });

    socket.on('complete', (data) => {
      status = 'complete';
      results = [...results, { phase: 'done', data }];
    });

    socket.on('error', (data) => {
      status = 'error';
      results = [...results, { phase: 'error', error: data.message }];
    });

    socket.on('disconnect', () => {
      status = 'disconnected';
    });

    return () => socket?.disconnect();
  });

  async function checkHealth() {
    try {
      const resp = await fetch('http://127.0.0.1:3000/health');
      const data = await resp.json();
      organs = data.organs || {};
    } catch (e) {
      organs = { error: e.message };
    }
  }

  function investigate() {
    if (!query.trim()) return;

    status = 'investigating';
    results = [];

    socket.emit('investigate', { query, domain: 'pwnd.icu' });
  }

  function getOrganColor(name) {
    const colors = {
      brain: '#ff6b6b',
      cells: '#ffd93d',
      veins: '#6bcb77',
      blood: '#4d96ff',
      lungs: '#c9b1ff',
    };
    return colors[name] || '#888';
  }
</script>

<main>
  <header>
    <h1>L Investigation</h1>
    <p class="subtitle">Polyglot Search Engine</p>
  </header>

  <div class="organs">
    {#each Object.entries(organs) as [name, data]}
      <div class="organ" style="--color: {getOrganColor(name)}">
        <span class="name">{name}</span>
        <span class="status {data.status}">{data.status || 'unknown'}</span>
        {#if data.latency >= 0}
          <span class="latency">{data.latency}ms</span>
        {/if}
      </div>
    {/each}
  </div>

  <div class="search-box">
    <input
      type="text"
      bind:value={query}
      placeholder="Ask a question about pwnd.icu..."
      on:keydown={(e) => e.key === 'Enter' && investigate()}
    />
    <button on:click={investigate} disabled={status === 'investigating'}>
      {status === 'investigating' ? 'Thinking...' : 'Investigate'}
    </button>
  </div>

  <div class="results">
    {#each results as result}
      <div class="result {result.phase}">
        <span class="phase">{result.phase}</span>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </div>
    {/each}
  </div>

  <footer>
    <span class="status-dot {status}"></span>
    Status: {status} | Session: {sessionId || 'none'}
  </footer>
</main>

<style>
  main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
  }

  header {
    text-align: center;
    margin-bottom: 2rem;
  }

  h1 {
    color: #00ff88;
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
  }

  .subtitle {
    color: #666;
    font-size: 1rem;
  }

  .organs {
    display: flex;
    gap: 1rem;
    justify-content: center;
    margin-bottom: 2rem;
    flex-wrap: wrap;
  }

  .organ {
    background: #12121a;
    padding: 0.75rem 1.25rem;
    border-radius: 8px;
    border-left: 3px solid var(--color);
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .organ .name {
    color: var(--color);
    font-weight: bold;
    text-transform: capitalize;
  }

  .organ .status {
    font-size: 0.8rem;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    background: #1a1a24;
  }

  .organ .status.healthy { color: #00ff88; }
  .organ .status.offline { color: #ff4444; }
  .organ .status.degraded { color: #ffaa00; }

  .organ .latency {
    color: #666;
    font-size: 0.8rem;
  }

  .search-box {
    display: flex;
    gap: 1rem;
    margin-bottom: 2rem;
  }

  input {
    flex: 1;
    padding: 1rem;
    font-size: 1rem;
    font-family: inherit;
    background: #12121a;
    border: 1px solid #333;
    border-radius: 8px;
    color: #fff;
  }

  input:focus {
    outline: none;
    border-color: #00ff88;
  }

  button {
    padding: 1rem 2rem;
    font-size: 1rem;
    font-family: inherit;
    background: #00ff88;
    color: #000;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-weight: bold;
  }

  button:hover {
    background: #00cc6a;
  }

  button:disabled {
    background: #333;
    color: #666;
    cursor: not-allowed;
  }

  .results {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .result {
    background: #12121a;
    padding: 1rem;
    border-radius: 8px;
    border-left: 3px solid #333;
  }

  .result.strategy { border-color: #ff6b6b; }
  .result.extraction { border-color: #ffd93d; }
  .result.synthesis { border-color: #6bcb77; }
  .result.error { border-color: #ff4444; }
  .result.done { border-color: #00ff88; }

  .phase {
    display: inline-block;
    background: #1a1a24;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    margin-bottom: 0.5rem;
    text-transform: uppercase;
  }

  pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
    font-size: 0.85rem;
    color: #888;
    max-height: 300px;
    overflow-y: auto;
  }

  footer {
    margin-top: 2rem;
    text-align: center;
    color: #666;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #666;
  }

  .status-dot.connected { background: #00ff88; }
  .status-dot.investigating { background: #ffd93d; animation: pulse 1s infinite; }
  .status-dot.complete { background: #6bcb77; }
  .status-dot.error { background: #ff4444; }
  .status-dot.disconnected { background: #ff4444; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
</style>
