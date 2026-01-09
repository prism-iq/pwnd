<script>
  import { createEventDispatcher } from 'svelte';

  export let results = [];

  const dispatch = createEventDispatcher();

  function handleSuggestionClick(query) {
    dispatch('suggestion', query);
  }
</script>

<div class="results">
  {#each results as result}
    {#if result.type === 'response'}
      <article class="response">
        <div class="response-content">
          {@html formatResponse(result.text)}
        </div>
      </article>
    {:else if result.type === 'sources'}
      <div class="sources">
        <span class="sources-label">Sources:</span>
        {#each result.ids.slice(0, 10) as id}
          <a href="/api/email/{id}" class="source-link" target="_blank">#{id}</a>
        {/each}
        {#if result.ids.length > 10}
          <span class="more">+{result.ids.length - 10} more</span>
        {/if}
      </div>
    {:else if result.type === 'suggestions'}
      <div class="suggestions">
        <span class="suggestions-label">Related queries:</span>
        <div class="suggestion-chips">
          {#each result.queries as query}
            <button
              class="suggestion-chip"
              on:click={() => handleSuggestionClick(query)}
            >
              {query}
            </button>
          {/each}
        </div>
      </div>
    {:else if result.type === 'error'}
      <div class="error">
        <span class="error-icon">!</span>
        {result.text}
      </div>
    {/if}
  {/each}
</div>

<script context="module">
  function formatResponse(text) {
    // Convert markdown-like formatting
    return text
      // Bold
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      // Email IDs
      .replace(/#(\d+)/g, '<a href="/api/email/$1" class="email-ref" target="_blank">#$1</a>')
      // Confidence markers
      .replace(/\[confirmed\]/gi, '<span class="confidence confirmed">confirmed</span>')
      .replace(/\[likely\]/gi, '<span class="confidence likely">likely</span>')
      .replace(/\[possible\]/gi, '<span class="confidence possible">possible</span>')
      .replace(/\[speculative\]/gi, '<span class="confidence speculative">speculative</span>')
      // Line breaks
      .replace(/\n/g, '<br>');
  }
</script>

<style>
  .results {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .response {
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 1.25rem;
  }

  .response-content {
    line-height: 1.8;
    color: #d0d0d0;
  }

  .response-content :global(strong) {
    color: #fff;
    font-weight: 600;
  }

  .response-content :global(.email-ref) {
    color: #667eea;
    text-decoration: none;
    font-weight: 500;
  }

  .response-content :global(.email-ref:hover) {
    text-decoration: underline;
  }

  .response-content :global(.confidence) {
    font-size: 0.75rem;
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-weight: 500;
    text-transform: uppercase;
  }

  .response-content :global(.confidence.confirmed) {
    background: rgba(46, 213, 115, 0.2);
    color: #2ed573;
  }

  .response-content :global(.confidence.likely) {
    background: rgba(255, 193, 7, 0.2);
    color: #ffc107;
  }

  .response-content :global(.confidence.possible) {
    background: rgba(255, 152, 0, 0.2);
    color: #ff9800;
  }

  .response-content :global(.confidence.speculative) {
    background: rgba(255, 82, 82, 0.2);
    color: #ff5252;
  }

  .sources {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: #12121a;
    border-radius: 6px;
  }

  .sources-label {
    color: #888;
    font-size: 0.875rem;
  }

  .source-link {
    font-size: 0.875rem;
    color: #667eea;
    text-decoration: none;
    padding: 0.25rem 0.5rem;
    background: rgba(102, 126, 234, 0.1);
    border-radius: 4px;
    transition: background 0.15s;
  }

  .source-link:hover {
    background: rgba(102, 126, 234, 0.2);
  }

  .more {
    color: #666;
    font-size: 0.875rem;
  }

  .suggestions {
    padding: 1rem;
    background: #12121a;
    border-radius: 8px;
  }

  .suggestions-label {
    display: block;
    color: #888;
    font-size: 0.875rem;
    margin-bottom: 0.75rem;
  }

  .suggestion-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .suggestion-chip {
    padding: 0.5rem 1rem;
    background: #2a2a4a;
    border: 1px solid #3a3a5a;
    border-radius: 20px;
    color: #e0e0e0;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .suggestion-chip:hover {
    background: #3a3a5a;
    border-color: #667eea;
    color: #fff;
  }

  .error {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    background: rgba(255, 82, 82, 0.1);
    border: 1px solid rgba(255, 82, 82, 0.3);
    border-radius: 8px;
    color: #ff5252;
  }

  .error-icon {
    width: 24px;
    height: 24px;
    background: #ff5252;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
  }
</style>
