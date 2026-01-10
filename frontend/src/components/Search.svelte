<script>
  import { searchQuery, searchEngine, searchResults, searchLoading, investigateResults } from '../stores/app.js'
  import { search, investigate } from '../lib/api.js'
  import { notify } from '../stores/app.js'

  let stats = { time: 0, count: 0 }

  async function doSearch() {
    if (!$searchQuery.trim()) return

    searchLoading.set(true)
    searchResults.set([])
    investigateResults.set(null)

    const start = performance.now()

    try {
      const data = await search($searchQuery, $searchEngine)
      const items = $searchEngine === 'blood' ? (data.results || []) : data

      stats = {
        time: Math.round(performance.now() - start),
        count: items.length
      }

      searchResults.set(items)
    } catch (e) {
      notify('Search failed: ' + e.message, 'error')
    } finally {
      searchLoading.set(false)
    }
  }

  async function doInvestigate() {
    if (!$searchQuery.trim()) return

    searchLoading.set(true)
    searchResults.set([])
    investigateResults.set(null)

    const start = performance.now()

    try {
      const data = await investigate($searchQuery)

      stats = {
        time: Math.round(performance.now() - start),
        count: data.search?.total || 0
      }

      investigateResults.set(data)
    } catch (e) {
      notify('Investigation failed: ' + e.message, 'error')
    } finally {
      searchLoading.set(false)
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Enter') doSearch()
  }
</script>

<div class="search-container">
  <div class="search-header">
    <input
      type="text"
      class="search-input"
      placeholder="Search documents, emails, entities..."
      bind:value={$searchQuery}
      on:keydown={handleKeydown}
    />

    <button class="btn primary" on:click={doSearch}>Search</button>
    <button class="btn danger" on:click={doInvestigate}>Investigate</button>

    <div class="engine-toggle">
      <button
        class="toggle-btn"
        class:active={$searchEngine === 'pg'}
        on:click={() => searchEngine.set('pg')}
      >PostgreSQL</button>
      <button
        class="toggle-btn"
        class:active={$searchEngine === 'blood'}
        on:click={() => searchEngine.set('blood')}
      >Blood (C++)</button>
    </div>
  </div>

  {#if stats.count > 0 || $searchLoading}
    <div class="stats">
      {#if $searchLoading}
        Searching...
      {:else}
        {stats.count} results in {stats.time}ms ({$searchEngine === 'blood' ? 'Blood C++' : 'PostgreSQL'})
      {/if}
    </div>
  {/if}

  <div class="results">
    {#if $searchLoading}
      <div class="loading">Searching...</div>
    {:else if $investigateResults}
      <!-- Investigate Results -->
      {#if $investigateResults.entities?.total_count > 0}
        <div class="section entities">
          <h3>Entities Extracted (Rust Cells)</h3>
          {#if $investigateResults.entities.persons?.length}
            <div><span class="label">Persons:</span> {$investigateResults.entities.persons.map(p => p.value).join(', ')}</div>
          {/if}
          {#if $investigateResults.entities.organizations?.length}
            <div><span class="label">Organizations:</span> {$investigateResults.entities.organizations.map(o => o.value).join(', ')}</div>
          {/if}
          {#if $investigateResults.entities.locations?.length}
            <div><span class="label">Locations:</span> {$investigateResults.entities.locations.map(l => l.value).join(', ')}</div>
          {/if}
        </div>
      {/if}

      {#if $investigateResults.search?.results?.length}
        <div class="section">
          <h3>Search Results (C++ Blood)</h3>
          {#each $investigateResults.search.results as r}
            <div class="result">
              <div class="result-header">
                <span class="score">{r.score?.toFixed(2)}</span>
                <span class="title">{r.title}</span>
              </div>
              <div class="snippet">{r.snippet?.substring(0, 200)}...</div>
            </div>
          {/each}
        </div>
      {/if}

    {:else if $searchResults.length > 0}
      <!-- Normal Search Results -->
      {#each $searchResults as r}
        <div class="result">
          <div class="result-header">
            <span class="type">{r.type || r.doc_type || 'doc'}</span>
            <span class="score">score:{(r.score || 0).toFixed(2)}</span>
            {#if r.metadata?.pertinence > 70}
              <span class="badge success">HIGH RELEVANCE</span>
            {/if}
            {#if r.metadata?.suspicion > 50}
              <span class="badge danger">SUSPICIOUS</span>
            {/if}
            <span class="title">{r.name || r.title || 'Untitled'}</span>
          </div>
          <div class="snippet">{(r.snippet || '').substring(0, 250)}...</div>
          {#if r.metadata}
            <div class="meta">pert:{r.metadata.pertinence || 0} susp:{r.metadata.suspicion || 0}</div>
          {/if}
        </div>
      {/each}
    {:else}
      <div class="empty">Enter a search query</div>
    {/if}
  </div>
</div>

<style>
  .search-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 20px;
  }

  .search-header {
    display: flex;
    gap: 10px;
    margin-bottom: 15px;
    flex-wrap: wrap;
  }

  .search-input {
    flex: 1;
    min-width: 200px;
    padding: 12px 15px;
    border: 1px solid #333;
    border-radius: 8px;
    background: #1a1a1a;
    color: #e5e5e5;
    font-size: 14px;
  }

  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
  }

  .btn {
    padding: 12px 20px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 500;
  }

  .btn.primary { background: #3b82f6; color: white; }
  .btn.danger { background: #e74c3c; color: white; }
  .btn:hover { opacity: 0.9; }

  .engine-toggle {
    display: flex;
    gap: 5px;
  }

  .toggle-btn {
    padding: 8px 12px;
    border: 1px solid #333;
    background: transparent;
    color: #888;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
  }

  .toggle-btn.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .stats {
    font-size: 12px;
    color: #888;
    margin-bottom: 10px;
  }

  .results {
    flex: 1;
    overflow-y: auto;
  }

  .section {
    margin-bottom: 20px;
  }

  .section h3 {
    color: #e74c3c;
    font-size: 14px;
    margin-bottom: 10px;
  }

  .section.entities {
    background: #1a1a2e;
    padding: 15px;
    border-radius: 8px;
  }

  .label { color: #3b82f6; }

  .result {
    background: #141414;
    border: 1px solid #252525;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 10px;
    cursor: pointer;
  }

  .result:hover { border-color: #3b82f6; }

  .result-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  .type {
    background: #3b82f6;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
  }

  .score {
    color: #888;
    font-size: 11px;
  }

  .badge {
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10px;
  }

  .badge.success { background: #22c55e; }
  .badge.danger { background: #e74c3c; }

  .title {
    font-weight: 500;
  }

  .snippet {
    font-size: 13px;
    color: #888;
    line-height: 1.4;
  }

  .meta {
    font-size: 11px;
    color: #666;
    margin-top: 5px;
  }

  .loading, .empty {
    text-align: center;
    color: #666;
    padding: 40px;
  }
</style>
