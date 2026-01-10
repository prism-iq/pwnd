<script>
  export let thinking = [];

  let expanded = true;

  $: latestThinking = thinking.slice(-20);
</script>

<div class="thinking-stream" class:expanded>
  <header class="stream-header" on:click={() => expanded = !expanded}>
    <span class="pulse"></span>
    <span class="title">Processing...</span>
    <span class="toggle">{expanded ? '−' : '+'}</span>
  </header>

  {#if expanded}
    <div class="stream-content">
      <pre>{latestThinking.join('')}</pre>
    </div>
  {/if}
</div>

<style>
  .thinking-stream {
    background: #0d0d14;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    margin-bottom: 1rem;
    overflow: hidden;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }

  .stream-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #12121a;
    cursor: pointer;
    user-select: none;
  }

  .pulse {
    width: 8px;
    height: 8px;
    background: #667eea;
    border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.8); }
  }

  .title {
    font-size: 0.8125rem;
    color: #888;
    flex: 1;
  }

  .toggle {
    color: #666;
    font-weight: 600;
  }

  .stream-content {
    max-height: 200px;
    overflow-y: auto;
    padding: 0.75rem 1rem;
  }

  pre {
    margin: 0;
    font-size: 0.75rem;
    color: #6a9955;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
  }

  /* Custom scrollbar */
  .stream-content::-webkit-scrollbar {
    width: 6px;
  }

  .stream-content::-webkit-scrollbar-track {
    background: #0d0d14;
  }

  .stream-content::-webkit-scrollbar-thumb {
    background: #3a3a5a;
    border-radius: 3px;
  }
</style>
