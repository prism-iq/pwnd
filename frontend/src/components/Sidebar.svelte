<script>
  import { activeTab, stats, wsConnected, conversations } from '../stores/app.js'
  import { getConversations } from '../lib/api.js'
  import { onMount } from 'svelte'

  onMount(async () => {
    try {
      const convs = await getConversations()
      conversations.set(convs)
    } catch (e) {}
  })

  function setTab(tab) {
    activeTab.set(tab)
  }
</script>

<aside class="sidebar">
  <div class="header">
    <div class="logo">PWND.ICU</div>
    <div class="status" class:connected={$wsConnected}>
      {$wsConnected ? 'Live' : 'Offline'}
    </div>
  </div>

  <nav class="nav">
    <button class="nav-item" class:active={$activeTab === 'chat'} on:click={() => setTab('chat')}>
      Chat
    </button>
    <button class="nav-item" class:active={$activeTab === 'search'} on:click={() => setTab('search')}>
      Search
    </button>
    <button class="nav-item" class:active={$activeTab === 'graph'} on:click={() => setTab('graph')}>
      Graph
    </button>
  </nav>

  <div class="stats">
    <div class="stat">
      <span class="stat-value">{$stats.documents?.toLocaleString() || 0}</span>
      <span class="stat-label">Documents</span>
    </div>
    <div class="stat">
      <span class="stat-value">{$stats.nodes?.toLocaleString() || 0}</span>
      <span class="stat-label">Entities</span>
    </div>
  </div>

  {#if $activeTab === 'chat'}
    <div class="conversations">
      <div class="conv-header">Conversations</div>
      {#each $conversations.slice(0, 10) as conv}
        <div class="conv-item">{conv.title || 'Untitled'}</div>
      {/each}
    </div>
  {/if}
</aside>

<style>
  .sidebar {
    width: 260px;
    background: #141414;
    border-right: 1px solid #252525;
    display: flex;
    flex-direction: column;
  }

  .header {
    padding: 20px;
    border-bottom: 1px solid #252525;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .logo {
    font-size: 1.4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .status {
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
    background: #ef4444;
  }
  .status.connected { background: #22c55e; }

  .nav {
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .nav-item {
    padding: 12px 15px;
    border: none;
    background: transparent;
    color: #888;
    text-align: left;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
  }

  .nav-item:hover { background: #1a1a1a; color: #e5e5e5; }
  .nav-item.active { background: #1a1a1a; color: #3b82f6; }

  .stats {
    display: flex;
    gap: 10px;
    padding: 15px;
    border-bottom: 1px solid #252525;
  }

  .stat {
    flex: 1;
    background: #1a1a1a;
    padding: 10px;
    border-radius: 8px;
    text-align: center;
  }

  .stat-value {
    display: block;
    font-size: 1.2rem;
    font-weight: 600;
    color: #3b82f6;
  }

  .stat-label {
    font-size: 11px;
    color: #666;
  }

  .conversations {
    flex: 1;
    overflow-y: auto;
    padding: 10px;
  }

  .conv-header {
    font-size: 12px;
    color: #666;
    padding: 10px 5px;
    text-transform: uppercase;
  }

  .conv-item {
    padding: 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    color: #888;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .conv-item:hover { background: #1a1a1a; color: #e5e5e5; }
</style>
