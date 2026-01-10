<script lang="ts">
  import { parseQuery, streamQuery, fetchStats, type ParsedQuery } from '$lib';
  import { onMount } from 'svelte';

  let query = $state('');
  let parsedQuery = $state<ParsedQuery | null>(null);
  let isLoading = $state(false);
  let messages = $state<any[]>([]);
  let thinking = $state('');
  let sources = $state<number[]>([]);
  let suggestions = $state<string[]>([]);
  let stats = $state<any>(null);
  let inputEl: HTMLInputElement;

  const MAX_THINKING = 8000;
  const MAX_MESSAGES = 50;

  // Parse query as user types
  $effect(() => {
    if (query.length > 2) {
      parsedQuery = parseQuery(query);
    } else {
      parsedQuery = null;
    }
  });

  onMount(async () => {
    stats = await fetchStats();
    inputEl?.focus();
  });

  function clearChat() {
    messages = [];
    thinking = '';
    sources = [];
    suggestions = [];
  }

  async function submit() {
    if (!query.trim() || isLoading) return;

    isLoading = true;
    thinking = '';
    sources = [];
    suggestions = [];

    const userMsg = { role: 'user', content: query };
    messages = [...messages.slice(-MAX_MESSAGES + 1), userMsg];

    let responseText = '';
    const currentQuery = query;

    try {
      for await (const event of streamQuery(currentQuery)) {
        switch (event.type) {
          case 'thinking':
            if (thinking.length < MAX_THINKING) {
              thinking += event.text;
            }
            break;
          case 'chunk':
            responseText += event.text;
            break;
          case 'sources':
            sources = event.ids?.slice(0, 50) || [];
            break;
          case 'suggestions':
            suggestions = event.queries?.slice(0, 5) || [];
            break;
          case 'status':
            break;
          case 'graph':
            break;
          case 'error':
            responseText += `\n⚠️ ${event.message}`;
            break;
        }
      }

      if (responseText) {
        messages = [...messages, { role: 'assistant', content: responseText }];
      }
    } catch (e) {
      messages = [...messages, { role: 'assistant', content: 'Error: ' + e }];
    } finally {
      isLoading = false;
      query = '';
      thinking = '';
    }
  }

  function useSuggestion(s: string) {
    query = s;
    submit();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }
</script>

<div class="flex h-screen">
  <!-- Sidebar -->
  <aside class="w-64 border-r border-[#1a1a1a] p-4 flex flex-col">
    <div class="flex items-center gap-2 mb-8">
      <span class="text-2xl font-bold text-[#00ff88] glow">L</span>
      <span class="text-sm text-[#666]">Investigation</span>
    </div>

    {#if stats}
      <div class="text-xs text-[#666] space-y-1 mb-6">
        <div>{stats.sources?.toLocaleString()} emails</div>
        <div>{stats.nodes?.toLocaleString()} entities</div>
        <div>{stats.workers?.workers?.length || 0} LLM workers</div>
      </div>
    {/if}

    {#if messages.length > 0}
      <button onclick={clearChat} class="text-xs text-[#666] hover:text-[#00ff88] mb-4">
        Clear chat
      </button>
    {/if}

    <div class="mt-auto text-xs text-[#333]">
      Natural Language Query Engine
    </div>
  </aside>

  <!-- Main -->
  <main class="flex-1 flex flex-col">
    <!-- Messages -->
    <div class="flex-1 overflow-y-auto p-6 space-y-4">
      {#each messages as msg}
        <div class="max-w-3xl {msg.role === 'user' ? 'ml-auto' : ''}">
          <div class="text-xs text-[#666] mb-1">
            {msg.role === 'user' ? 'You' : 'L'}
          </div>
          <div class="{msg.role === 'user' ? 'glass' : 'bg-[#111]'} rounded-lg p-4 text-sm">
            <pre class="stream-text whitespace-pre-wrap font-sans">{msg.content}</pre>
          </div>
        </div>
      {/each}

      {#if isLoading && thinking}
        <div class="max-w-3xl">
          <div class="text-xs text-[#666] mb-1">Thinking...</div>
          <div class="bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg p-4 text-xs font-mono text-[#666]">
            <pre class="whitespace-pre-wrap">{thinking}</pre>
          </div>
        </div>
      {/if}

      {#if sources.length > 0}
        <div class="text-xs text-[#666]">
          Sources: {sources.slice(0, 10).map(s => `#${s}`).join(', ')}
          {#if sources.length > 10}+{sources.length - 10} more{/if}
        </div>
      {/if}

      {#if suggestions.length > 0}
        <div class="flex gap-2 flex-wrap">
          {#each suggestions as s}
            <button
              onclick={() => useSuggestion(s)}
              class="text-xs px-3 py-1 rounded-full border border-[#1a1a1a] hover:border-[#00ff88] hover:text-[#00ff88] transition"
            >
              {s}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Query Input -->
    <div class="border-t border-[#1a1a1a] p-4">
      {#if parsedQuery}
        <div class="flex gap-2 mb-2 text-xs">
          <span class="tag tag-org">{parsedQuery.intent}</span>
          {#each parsedQuery.entities as e}
            <span class="tag tag-person">{e}</span>
          {/each}
          {#each Object.entries(parsedQuery.filters) as [k, v]}
            <span class="tag tag-date">{k}: {v}</span>
          {/each}
        </div>
      {/if}

      <div class="flex gap-2">
        <input
          bind:this={inputEl}
          bind:value={query}
          onkeydown={handleKeydown}
          placeholder="find emails from maxwell about island in 2019..."
          class="query-input flex-1"
          disabled={isLoading}
        />
        <button
          onclick={submit}
          disabled={isLoading || !query.trim()}
          class="px-6 py-3 bg-[#00ff88] text-black font-medium rounded-lg hover:bg-[#00dd77] disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {isLoading ? '...' : '→'}
        </button>
      </div>

      <div class="mt-2 text-xs text-[#444]">
        Try: <button onclick={() => query = 'who traveled with epstein'} class="hover:text-[#00ff88]">who traveled with epstein</button>
        · <button onclick={() => query = 'connections between maxwell and clinton'} class="hover:text-[#00ff88]">connections between maxwell and clinton</button>
        · <button onclick={() => query = 'find payments over $100000'} class="hover:text-[#00ff88]">find payments over $100000</button>
      </div>
    </div>
  </main>
</div>
