<script>
  export let stats = null;
</script>

<div class="stats-bar">
  {#if stats}
    <div class="stat">
      <span class="stat-value">{stats.sources?.toLocaleString() || '0'}</span>
      <span class="stat-label">Emails</span>
    </div>
    <div class="stat">
      <span class="stat-value">{stats.nodes?.toLocaleString() || '0'}</span>
      <span class="stat-label">Nodes</span>
    </div>
    <div class="stat">
      <span class="stat-value">{stats.edges?.toLocaleString() || '0'}</span>
      <span class="stat-label">Edges</span>
    </div>
    {#if stats.workers?.workers}
      <div class="stat workers">
        <span class="stat-value">{stats.workers.workers.filter(w => !w.busy).length}/{stats.workers.workers.length}</span>
        <span class="stat-label">Workers</span>
      </div>
    {/if}
  {:else}
    <div class="stat loading">
      <span class="stat-value">...</span>
      <span class="stat-label">Loading</span>
    </div>
  {/if}
</div>

<style>
  .stats-bar {
    display: flex;
    gap: 1.5rem;
  }

  .stat {
    text-align: center;
  }

  .stat-value {
    display: block;
    font-size: 1.125rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .stat-label {
    display: block;
    font-size: 0.6875rem;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .stat.workers .stat-value {
    color: #2ed573;
  }

  .stat.loading .stat-value {
    animation: blink 1s ease-in-out infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  @media (max-width: 768px) {
    .stats-bar {
      display: none;
    }
  }
</style>
