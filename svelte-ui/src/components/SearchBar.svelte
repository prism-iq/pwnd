<script>
  import { createEventDispatcher } from 'svelte';

  export let isLoading = false;

  const dispatch = createEventDispatcher();
  let query = '';
  let suggestions = [];
  let showSuggestions = false;
  let debounceTimer;

  async function handleInput(e) {
    query = e.target.value;

    // Debounced live search suggestions
    clearTimeout(debounceTimer);
    if (query.length >= 2) {
      debounceTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=5`);
          const data = await res.json();
          suggestions = data.slice(0, 5);
          showSuggestions = suggestions.length > 0;
        } catch (e) {
          suggestions = [];
        }
      }, 150);
    } else {
      suggestions = [];
      showSuggestions = false;
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (query.trim()) {
      dispatch('search', { query: query.trim() });
      showSuggestions = false;
    }
  }

  function selectSuggestion(suggestion) {
    query = suggestion.name || suggestion.text || '';
    dispatch('search', { query });
    showSuggestions = false;
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      showSuggestions = false;
    }
  }
</script>

<form class="search-bar" on:submit={handleSubmit}>
  <div class="search-input-wrapper">
    <input
      type="text"
      bind:value={query}
      on:input={handleInput}
      on:focus={() => suggestions.length > 0 && (showSuggestions = true)}
      on:keydown={handleKeydown}
      placeholder="Search emails, entities, relationships..."
      disabled={isLoading}
      class="search-input"
    />

    {#if showSuggestions}
      <div class="suggestions">
        {#each suggestions as suggestion}
          <button
            type="button"
            class="suggestion"
            on:click={() => selectSuggestion(suggestion)}
          >
            <span class="suggestion-type">{suggestion.type || 'email'}</span>
            <span class="suggestion-text">{suggestion.name || suggestion.text || 'Untitled'}</span>
          </button>
        {/each}
      </div>
    {/if}
  </div>

  <button type="submit" disabled={isLoading} class="search-button">
    {#if isLoading}
      <span class="spinner"></span>
    {:else}
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
    {/if}
  </button>
</form>

<style>
  .search-bar {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }

  .search-input-wrapper {
    flex: 1;
    position: relative;
  }

  .search-input {
    width: 100%;
    padding: 0.875rem 1rem;
    background: #1a1a2e;
    border: 1px solid #3a3a5a;
    border-radius: 8px;
    color: #e0e0e0;
    font-size: 1rem;
    transition: all 0.2s;
  }

  .search-input:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
  }

  .search-input::placeholder {
    color: #666;
  }

  .search-input:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .suggestions {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #1a1a2e;
    border: 1px solid #3a3a5a;
    border-top: none;
    border-radius: 0 0 8px 8px;
    max-height: 300px;
    overflow-y: auto;
    z-index: 100;
  }

  .suggestion {
    width: 100%;
    padding: 0.75rem 1rem;
    background: transparent;
    border: none;
    color: #e0e0e0;
    text-align: left;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    transition: background 0.15s;
  }

  .suggestion:hover {
    background: #2a2a4a;
  }

  .suggestion-type {
    font-size: 0.75rem;
    padding: 0.125rem 0.5rem;
    background: #3a3a5a;
    border-radius: 4px;
    text-transform: uppercase;
    color: #888;
  }

  .suggestion-text {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .search-button {
    padding: 0 1.25rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    border-radius: 8px;
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s, box-shadow 0.2s;
  }

  .search-button:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  .search-button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .spinner {
    width: 20px;
    height: 20px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
