<script>
  import { notifications } from '../stores/app.js'

  function dismiss(id) {
    notifications.update(n => n.filter(x => x.id !== id))
  }
</script>

{#if $notifications.length > 0}
  <div class="notifications">
    {#each $notifications as notif (notif.id)}
      <div class="notification {notif.type}" on:click={() => dismiss(notif.id)}>
        <span>{notif.message}</span>
        <button class="close">×</button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .notifications {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding: 10px;
  }

  .notification {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    border-radius: 8px;
    cursor: pointer;
    animation: slideIn 0.3s ease;
  }

  @keyframes slideIn {
    from { transform: translateY(-100%); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .notification.info { background: #3b82f6; }
  .notification.success { background: #22c55e; }
  .notification.error { background: #ef4444; }
  .notification.warning { background: #f59e0b; }

  .close {
    background: none;
    border: none;
    color: white;
    font-size: 20px;
    cursor: pointer;
    padding: 0 5px;
  }
</style>
