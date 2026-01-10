<script>
  import { onMount } from 'svelte'
  import { activeTab, notifications, stats, wsConnected } from './stores/app.js'
  import { connect } from './lib/websocket.js'
  import { getStats, getNotifications } from './lib/api.js'
  import { notify } from './stores/app.js'

  import Sidebar from './components/Sidebar.svelte'
  import Chat from './components/Chat.svelte'
  import Search from './components/Search.svelte'
  import Graph from './components/Graph.svelte'
  import Notifications from './components/Notifications.svelte'

  onMount(async () => {
    // Connect WebSocket
    connect()

    // Load stats
    try {
      const s = await getStats()
      stats.set(s)
    } catch (e) {
      console.error('Failed to load stats:', e)
    }

    // Check for notifications
    try {
      const notifs = await getNotifications()
      if (notifs.length > 0) {
        notify(notifs[0].message, notifs[0].type)
      }
    } catch (e) {}
  })
</script>

<Notifications />

<div class="app">
  <Sidebar />

  <main class="main">
    {#if $activeTab === 'chat'}
      <Chat />
    {:else if $activeTab === 'search'}
      <Search />
    {:else if $activeTab === 'graph'}
      <Graph />
    {/if}
  </main>
</div>

<style>
  :global(*) {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0a0a;
    color: #e5e5e5;
    line-height: 1.5;
    height: 100vh;
    overflow: hidden;
  }

  .app {
    display: flex;
    height: 100vh;
  }

  .main {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>
