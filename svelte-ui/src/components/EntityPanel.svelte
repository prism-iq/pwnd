<script>
  export let entities = {
    dates: [],
    persons: [],
    organizations: [],
    amounts: [],
    locations: []
  };

  const entityConfig = {
    persons: { icon: '👤', label: 'People', color: '#667eea' },
    organizations: { icon: '🏢', label: 'Organizations', color: '#764ba2' },
    locations: { icon: '📍', label: 'Locations', color: '#2ed573' },
    dates: { icon: '📅', label: 'Dates', color: '#ffc107' },
    amounts: { icon: '💰', label: 'Amounts', color: '#ff9800' }
  };

  $: totalEntities = Object.values(entities).flat().length;
</script>

<div class="entity-panel">
  <header class="panel-header">
    <h3>Extracted Entities</h3>
    {#if totalEntities > 0}
      <span class="total-badge">{totalEntities}</span>
    {/if}
  </header>

  {#each Object.entries(entityConfig) as [type, config]}
    {#if entities[type]?.length > 0}
      <section class="entity-section">
        <h4 class="section-title" style="--accent-color: {config.color}">
          <span class="icon">{config.icon}</span>
          {config.label}
          <span class="count">{entities[type].length}</span>
        </h4>
        <ul class="entity-list">
          {#each entities[type].slice(0, 10) as entity}
            <li class="entity-item" style="--accent-color: {config.color}">
              <span class="entity-value">{entity.value || entity.name || entity}</span>
              {#if entity.confidence}
                <span class="confidence" class:high={entity.confidence > 0.8} class:medium={entity.confidence > 0.5 && entity.confidence <= 0.8} class:low={entity.confidence <= 0.5}>
                  {Math.round(entity.confidence * 100)}%
                </span>
              {/if}
            </li>
          {/each}
          {#if entities[type].length > 10}
            <li class="more-items">+{entities[type].length - 10} more</li>
          {/if}
        </ul>
      </section>
    {/if}
  {/each}

  {#if totalEntities === 0}
    <div class="empty-state">
      <span class="empty-icon">🔍</span>
      <p>No entities extracted yet</p>
      <p class="empty-hint">Run a search to extract entities</p>
    </div>
  {/if}
</div>

<style>
  .entity-panel {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
  }

  .panel-header h3 {
    font-size: 0.875rem;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .total-badge {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.25rem 0.5rem;
    border-radius: 10px;
  }

  .entity-section {
    margin-bottom: 1rem;
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--accent-color);
    margin-bottom: 0.5rem;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid #2a2a4a;
  }

  .icon {
    font-size: 1rem;
  }

  .count {
    margin-left: auto;
    background: rgba(255, 255, 255, 0.1);
    padding: 0.125rem 0.375rem;
    border-radius: 8px;
    font-size: 0.75rem;
    color: #888;
  }

  .entity-list {
    list-style: none;
  }

  .entity-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.375rem 0.5rem;
    margin: 0.25rem 0;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 4px;
    border-left: 2px solid var(--accent-color);
    font-size: 0.8125rem;
    cursor: pointer;
    transition: background 0.15s;
  }

  .entity-item:hover {
    background: rgba(255, 255, 255, 0.05);
  }

  .entity-value {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: #d0d0d0;
  }

  .confidence {
    font-size: 0.6875rem;
    padding: 0.125rem 0.25rem;
    border-radius: 3px;
    font-weight: 500;
  }

  .confidence.high {
    background: rgba(46, 213, 115, 0.2);
    color: #2ed573;
  }

  .confidence.medium {
    background: rgba(255, 193, 7, 0.2);
    color: #ffc107;
  }

  .confidence.low {
    background: rgba(255, 82, 82, 0.2);
    color: #ff5252;
  }

  .more-items {
    font-size: 0.75rem;
    color: #666;
    padding: 0.25rem 0.5rem;
    font-style: italic;
  }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: #666;
  }

  .empty-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
    opacity: 0.5;
  }

  .empty-state p {
    margin: 0.25rem 0;
  }

  .empty-hint {
    font-size: 0.75rem;
    color: #555;
  }
</style>
