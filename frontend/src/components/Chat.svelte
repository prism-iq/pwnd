<script>
  import { messages, chatLoading, currentConvId } from '../stores/app.js'
  import { streamChat } from '../lib/api.js'
  import { notify } from '../stores/app.js'
  import { onMount, afterUpdate } from 'svelte'

  let input = ''
  let messagesEl

  afterUpdate(() => {
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight
    }
  })

  async function send() {
    if (!input.trim() || $chatLoading) return

    const userMessage = input.trim()
    input = ''

    // Add user message
    messages.update(m => [...m, { role: 'user', content: userMessage }])

    // Add placeholder for assistant
    messages.update(m => [...m, { role: 'assistant', content: '', loading: true }])

    chatLoading.set(true)

    let responseText = ''

    streamChat(
      userMessage,
      $currentConvId,
      // onChunk
      (data) => {
        if (data.type === 'conv_id') {
          currentConvId.set(data.id)
        }
        if (data.type === 'chunk') {
          responseText += data.text
          messages.update(m => {
            const last = m[m.length - 1]
            if (last.role === 'assistant') {
              last.content = responseText
              last.loading = false
            }
            return m
          })
        }
        if (data.type === 'sources') {
          messages.update(m => {
            const last = m[m.length - 1]
            if (last.role === 'assistant') {
              last.sources = data.ids
            }
            return m
          })
        }
      },
      // onDone
      () => {
        chatLoading.set(false)
      },
      // onError
      (err) => {
        chatLoading.set(false)
        notify('Chat error: ' + err.message, 'error')
      }
    )
  }

  function handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }
</script>

<div class="chat-container">
  <div class="messages" bind:this={messagesEl}>
    {#if $messages.length === 0}
      <div class="empty">
        <h2>PWND.ICU Investigation</h2>
        <p>Ask questions about the Epstein documents</p>
        <div class="suggestions">
          <button on:click={() => { input = 'Who is Jeffrey Epstein?'; send() }}>Who is Jeffrey Epstein?</button>
          <button on:click={() => { input = 'What are the flight logs?'; send() }}>What are the flight logs?</button>
          <button on:click={() => { input = 'Who is Ghislaine Maxwell?'; send() }}>Who is Ghislaine Maxwell?</button>
        </div>
      </div>
    {:else}
      {#each $messages as msg}
        <div class="message {msg.role}">
          {#if msg.loading}
            <span class="typing">Thinking...</span>
          {:else}
            {msg.content}
          {/if}
          {#if msg.sources?.length}
            <div class="sources">
              Sources: {msg.sources.join(', ')}
            </div>
          {/if}
        </div>
      {/each}
    {/if}
  </div>

  <div class="input-area">
    <textarea
      placeholder="Ask about the investigation..."
      bind:value={input}
      on:keydown={handleKeydown}
      disabled={$chatLoading}
    ></textarea>
    <button class="send-btn" on:click={send} disabled={$chatLoading}>
      {$chatLoading ? '...' : 'Send'}
    </button>
  </div>
</div>

<style>
  .chat-container {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }

  .empty {
    text-align: center;
    padding: 60px 20px;
  }

  .empty h2 {
    margin-bottom: 10px;
    color: #3b82f6;
  }

  .empty p {
    color: #888;
    margin-bottom: 30px;
  }

  .suggestions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    justify-content: center;
  }

  .suggestions button {
    padding: 10px 15px;
    border: 1px solid #333;
    background: #1a1a1a;
    color: #e5e5e5;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
  }

  .suggestions button:hover {
    border-color: #3b82f6;
  }

  .message {
    max-width: 80%;
    padding: 12px 16px;
    border-radius: 12px;
    margin-bottom: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
  }

  .message.user {
    background: #3b82f6;
    margin-left: auto;
  }

  .message.assistant {
    background: #1a1a1a;
    border: 1px solid #252525;
  }

  .typing {
    color: #888;
    font-style: italic;
  }

  .sources {
    font-size: 11px;
    color: #666;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #333;
  }

  .input-area {
    padding: 20px;
    border-top: 1px solid #252525;
    display: flex;
    gap: 10px;
  }

  textarea {
    flex: 1;
    padding: 12px;
    border: 1px solid #333;
    border-radius: 8px;
    background: #1a1a1a;
    color: #e5e5e5;
    resize: none;
    min-height: 50px;
    max-height: 150px;
    font-family: inherit;
  }

  textarea:focus {
    outline: none;
    border-color: #3b82f6;
  }

  .send-btn {
    padding: 12px 24px;
    background: #3b82f6;
    border: none;
    border-radius: 8px;
    color: white;
    cursor: pointer;
    font-weight: 500;
  }

  .send-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
