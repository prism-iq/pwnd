<script>
  import { onMount } from 'svelte';
  import SearchBar from './components/SearchBar.svelte';
  import Results from './components/Results.svelte';
  import EntityPanel from './components/EntityPanel.svelte';
  import ThinkingStream from './components/ThinkingStream.svelte';
  import StatsBar from './components/StatsBar.svelte';
  import GraphView from './components/GraphView.svelte';

  let query = '';
  let results = [];
  let entities = { dates: [], persons: [], organizations: [], amounts: [], locations: [] };
  let thinking = [];
  let isLoading = false;
  let activeTab = 'search';
  let stats = null;
  let eventSource = null;

  onMount(async () => {
    // Fetch initial stats
    const res = await fetch('/api/stats');
    stats = await res.json();

    // Background sync every 30s
    setInterval(async () => {
      const res = await fetch('/api/stats');
      stats = await res.json();
    }, 30000);
  });

  async function handleSearch(event) {
    query = event.detail.query;
    if (!query.trim()) return;

    isLoading = true;
    thinking = [];
    results = [];

    // Close existing SSE connection
    if (eventSource) {
      eventSource.close();
    }

    // Start SSE stream
    const url = `/api/ask?q=${encodeURIComponent(query)}`;
    eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'thinking':
          thinking = [...thinking, data.text];
          break;
        case 'status':
          thinking = [...thinking, `[${data.msg}]\n`];
          break;
        case 'chunk':
          // Final response
          results = [...results, { type: 'response', text: data.text }];
          break;
        case 'sources':
          // Source IDs
          results = [...results, { type: 'sources', ids: data.ids }];
          break;
        case 'suggestions':
          results = [...results, { type: 'suggestions', queries: data.queries }];
          break;
        case 'done':
          isLoading = false;
          eventSource.close();
          break;
        case 'error':
          results = [...results, { type: 'error', text: data.msg }];
          isLoading = false;
          eventSource.close();
          break;
      }
    };

    eventSource.onerror = () => {
      isLoading = false;
      eventSource.close();
    };

    // Parallel: extract entities from query
    extractEntities(query);
  }

  async function extractEntities(text) {
    try {
      const res = await fetch('/api/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const data = await res.json();
      entities = {
        dates: data.dates || [],
        persons: data.persons || [],
        organizations: data.organizations || [],
        amounts: data.amounts || [],
        locations: data.locations || []
      };
    } catch (e) {
      console.error('Entity extraction failed:', e);
    }
  }

  function handleSuggestionClick(suggestion) {
    handleSearch({ detail: { query: suggestion } });
  }
</script>

<main class="app">
  <header class="header">
    <div class="logo">
      <span class="logo-icon">L</span>
      <span class="logo-text">Investigation</span>
    </div>
    <nav class="tabs">
      <button
        class:active={activeTab === 'search'}
        on:click={() => activeTab = 'search'}
      >
        Search
      </button>
      <button
        class:active={activeTab === 'graph'}
        on:click={() => activeTab = 'graph'}
      >
        Graph
      </button>
      <button
        class:active={activeTab === 'timeline'}
        on:click={() => activeTab = 'timeline'}
      >
        Timeline
      </button>
    </nav>
    <StatsBar {stats} />
  </header>

  <div class="container">
    <aside class="sidebar">
      <EntityPanel {entities} />
    </aside>

    <section class="main">
      <SearchBar on:search={handleSearch} {isLoading} />

      {#if thinking.length > 0}
        <ThinkingStream {thinking} />
      {/if}

      {#if activeTab === 'search'}
        <Results {results} on:suggestion={e => handleSuggestionClick(e.detail)} />
      {:else if activeTab === 'graph'}
        <GraphView />
      {/if}
    </section>
  </div>
</main>

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    line-height: 1.6;
  }

  .app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 2rem;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border-bottom: 1px solid #2a2a4a;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .logo-icon {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 1.5rem;
    color: white;
  }

  .logo-text {
    font-size: 1.25rem;
    font-weight: 600;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
  }

  .tabs button {
    background: transparent;
    border: 1px solid #3a3a5a;
    color: #888;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .tabs button:hover {
    background: #2a2a4a;
    color: #fff;
  }

  .tabs button.active {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-color: transparent;
    color: white;
  }

  .container {
    display: flex;
    flex: 1;
  }

  .sidebar {
    width: 280px;
    background: #12121a;
    border-right: 1px solid #2a2a4a;
    padding: 1rem;
    overflow-y: auto;
  }

  .main {
    flex: 1;
    padding: 1.5rem;
    overflow-y: auto;
  }

  @media (max-width: 768px) {
    .container {
      flex-direction: column;
    }

    .sidebar {
      width: 100%;
      max-height: 200px;
      border-right: none;
      border-bottom: 1px solid #2a2a4a;
    }
  }
</style>
