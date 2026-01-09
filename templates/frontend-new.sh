#!/bin/bash
# Generate complete frontend with detective theme + working auto mode

set -e

echo "Generating detective-themed frontend..."

# index.html - Main interface
cat > /opt/rag/static/index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>L Investigation Framework</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', monospace;
            background: #000;
            color: #0f0;
            line-height: 1.6;
            overflow: hidden;
        }

        .container {
            display: grid;
            grid-template-columns: 300px 1fr;
            height: 100vh;
        }

        /* Sidebar */
        .sidebar {
            background: #0a0a0a;
            border-right: 1px solid #0f0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .sidebar-header {
            padding: 20px;
            border-bottom: 1px solid #0f0;
        }

        .logo {
            font-size: 1.5em;
            font-weight: bold;
            margin-bottom: 5px;
            letter-spacing: 2px;
        }

        .tagline {
            font-size: 0.8em;
            color: #0a0;
            opacity: 0.7;
        }

        .new-btn {
            width: 100%;
            padding: 12px;
            background: #001a00;
            border: 1px solid #0f0;
            color: #0f0;
            cursor: pointer;
            margin-top: 15px;
            font-family: 'Courier New', monospace;
            transition: all 0.2s;
        }

        .new-btn:hover {
            background: #0f0;
            color: #000;
        }

        .conversations {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
        }

        .conv-item {
            padding: 10px;
            margin-bottom: 5px;
            border: 1px solid #003300;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.9em;
        }

        .conv-item:hover, .conv-item.active {
            background: #001a00;
            border-color: #0f0;
        }

        .stats {
            padding: 15px;
            border-top: 1px solid #0f0;
            font-size: 0.85em;
        }

        .stat-line {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .stat-value {
            color: #0a0;
        }

        /* Main area */
        .main {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        .header {
            padding: 15px 20px;
            border-bottom: 1px solid #0f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header-title {
            font-size: 1.2em;
        }

        .auto-toggle {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .toggle-label {
            font-size: 0.9em;
            color: #0a0;
        }

        .toggle-switch {
            position: relative;
            width: 50px;
            height: 24px;
            background: #001a00;
            border: 1px solid #0f0;
            cursor: pointer;
            transition: all 0.3s;
        }

        .toggle-switch.active {
            background: #0f0;
        }

        .toggle-slider {
            position: absolute;
            top: 2px;
            left: 2px;
            width: 18px;
            height: 18px;
            background: #0f0;
            transition: all 0.3s;
        }

        .toggle-switch.active .toggle-slider {
            left: 28px;
            background: #000;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .message {
            margin-bottom: 25px;
            animation: fadeIn 0.3s;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }

        .message-role {
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.85em;
        }

        .message-role.user {
            color: #0ff;
        }

        .message-role.assistant {
            color: #0f0;
        }

        .message-auto {
            font-size: 0.75em;
            color: #f90;
            background: #221100;
            padding: 2px 6px;
            border: 1px solid #f90;
        }

        .message-content {
            padding-left: 20px;
            line-height: 1.8;
        }

        .message-content p {
            margin-bottom: 12px;
        }

        .source-link {
            color: #0ff;
            text-decoration: none;
            border-bottom: 1px dashed #0ff;
            padding: 0 2px;
        }

        .source-link:hover {
            background: #001a1a;
        }

        .thinking {
            display: inline-block;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .input-area {
            padding: 15px 20px;
            border-top: 1px solid #0f0;
            background: #0a0a0a;
        }

        .input-wrapper {
            display: flex;
            gap: 10px;
        }

        .input-box {
            flex: 1;
            padding: 12px 15px;
            background: #000;
            border: 1px solid #0f0;
            color: #0f0;
            font-family: 'Courier New', monospace;
            font-size: 1em;
            outline: none;
            resize: none;
            min-height: 50px;
            max-height: 150px;
        }

        .input-box:focus {
            border-color: #0ff;
            box-shadow: 0 0 10px rgba(0, 255, 255, 0.2);
        }

        .send-btn {
            padding: 12px 25px;
            background: #001a00;
            border: 1px solid #0f0;
            color: #0f0;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            transition: all 0.2s;
        }

        .send-btn:hover:not(:disabled) {
            background: #0f0;
            color: #000;
        }

        .send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .auto-status {
            margin-top: 10px;
            padding: 10px;
            background: #110800;
            border: 1px solid #f90;
            color: #f90;
            font-size: 0.85em;
            display: none;
        }

        .auto-status.active {
            display: block;
        }

        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: #000;
        }

        ::-webkit-scrollbar-thumb {
            background: #0f0;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #0ff;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="logo">L</div>
                <div class="tagline">Investigation Framework</div>
                <button class="new-btn" onclick="newConversation()">NEW INVESTIGATION</button>
            </div>

            <div class="conversations" id="conversations">
                <!-- Loaded dynamically -->
            </div>

            <div class="stats">
                <div class="stat-line">
                    <span>Corpus:</span>
                    <span class="stat-value" id="statEmails">13,009</span>
                </div>
                <div class="stat-line">
                    <span>Nodes:</span>
                    <span class="stat-value" id="statNodes">-</span>
                </div>
                <div class="stat-line">
                    <span>Edges:</span>
                    <span class="stat-value" id="statEdges">-</span>
                </div>
            </div>
        </div>

        <!-- Main -->
        <div class="main">
            <div class="header">
                <div class="header-title">Detective Analysis</div>
                <div class="auto-toggle">
                    <span class="toggle-label">AUTO-INVESTIGATE</span>
                    <div class="toggle-switch" id="autoToggle" onclick="toggleAuto()">
                        <div class="toggle-slider"></div>
                    </div>
                </div>
            </div>

            <div class="messages" id="messages">
                <div class="message">
                    <div class="message-header">
                        <span class="message-role assistant">L</span>
                    </div>
                    <div class="message-content">
                        <p>Investigation system online. 13,009 documents in corpus. Ask anything. I'll tell you what the data shows.</p>
                    </div>
                </div>
            </div>

            <div class="input-area">
                <div class="auto-status" id="autoStatus">
                    AUTO MODE: <span id="autoStatusText">Inactive</span>
                </div>
                <div class="input-wrapper">
                    <textarea
                        class="input-box"
                        id="input"
                        placeholder="Ask about patterns, connections, names..."
                        rows="1"
                        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage();}"
                    ></textarea>
                    <button class="send-btn" id="sendBtn" onclick="sendMessage()">SEND</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentConvId = null;
        let autoEnabled = false;
        let autoRunning = false;
        let eventSource = null;

        // Load stats
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('statEmails').textContent = data.sources.toLocaleString();
                document.getElementById('statNodes').textContent = data.nodes.toLocaleString();
                document.getElementById('statEdges').textContent = data.edges.toLocaleString();
            } catch (e) {
                console.error('Failed to load stats:', e);
            }
        }

        // Load conversations
        async function loadConversations() {
            try {
                const res = await fetch('/api/conversations');
                const convs = await res.json();
                const container = document.getElementById('conversations');
                container.innerHTML = convs.map(c => `
                    <div class="conv-item ${c.id === currentConvId ? 'active' : ''}"
                         onclick="loadConversation('${c.id}')">
                        ${c.title || 'Investigation ' + c.id.slice(0, 8)}
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load conversations:', e);
            }
        }

        // New conversation
        async function newConversation() {
            try {
                const res = await fetch('/api/conversations', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({title: 'New Investigation'})
                });
                const conv = await res.json();
                currentConvId = conv.id;
                document.getElementById('messages').innerHTML = `
                    <div class="message">
                        <div class="message-header">
                            <span class="message-role assistant">L</span>
                        </div>
                        <div class="message-content">
                            <p>Investigation system online. 13,009 documents in corpus. Ask anything. I'll tell you what the data shows.</p>
                        </div>
                    </div>
                `;
                await loadConversations();
            } catch (e) {
                console.error('Failed to create conversation:', e);
            }
        }

        // Load conversation
        async function loadConversation(convId) {
            currentConvId = convId;
            try {
                const res = await fetch(`/api/conversations/${convId}/messages`);
                const msgs = await res.json();
                const container = document.getElementById('messages');
                container.innerHTML = msgs.map(m => `
                    <div class="message">
                        <div class="message-header">
                            <span class="message-role ${m.role}">${m.role === 'user' ? 'YOU' : 'L'}</span>
                            ${m.is_auto ? '<span class="message-auto">AUTO</span>' : ''}
                        </div>
                        <div class="message-content">
                            ${formatMessage(m.content)}
                        </div>
                    </div>
                `).join('');
                scrollToBottom();
                await loadConversations();
            } catch (e) {
                console.error('Failed to load conversation:', e);
            }
        }

        // Format message
        function formatMessage(content) {
            // Convert [#ID] to links
            content = content.replace(/\[#(\d+)\]/g, '<a href="/source/$1" class="source-link" target="_blank">[#$1]</a>');
            // Paragraphs
            return content.split('\n\n').map(p => `<p>${p}</p>`).join('');
        }

        // Toggle auto mode
        function toggleAuto() {
            autoEnabled = !autoEnabled;
            const toggle = document.getElementById('autoToggle');
            const status = document.getElementById('autoStatus');

            if (autoEnabled) {
                toggle.classList.add('active');
                status.classList.add('active');
                document.getElementById('autoStatusText').textContent = 'Ready';
            } else {
                toggle.classList.remove('active');
                status.classList.remove('active');
                autoRunning = false;
            }
        }

        // Send message
        async function sendMessage() {
            const input = document.getElementById('input');
            const query = input.value.trim();
            if (!query) return;

            if (!currentConvId) await newConversation();

            // Add user message
            addMessage('user', query);
            input.value = '';
            document.getElementById('sendBtn').disabled = true;

            // Query
            await streamQuery(query);

            // Auto-investigate if enabled and not already running
            if (autoEnabled && !autoRunning) {
                autoRunning = true;
                document.getElementById('autoStatusText').textContent = 'Running...';
                await startAutoInvestigate();
                autoRunning = false;
                document.getElementById('autoStatusText').textContent = 'Ready';
            }

            document.getElementById('sendBtn').disabled = false;
        }

        // Stream query
        async function streamQuery(query, isAuto = false) {
            const msgDiv = addMessage('assistant', '<span class="thinking">Analyzing...</span>', isAuto);
            const contentDiv = msgDiv.querySelector('.message-content');

            try {
                const url = `/api/ask?q=${encodeURIComponent(query)}${currentConvId ? '&conversation_id=' + currentConvId : ''}`;
                const response = await fetch(url);
                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                let fullText = '';

                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));

                                if (data.type === 'chunk') {
                                    fullText += data.text;
                                    contentDiv.innerHTML = formatMessage(fullText);
                                    scrollToBottom();
                                }
                            } catch (e) {
                                // Ignore parse errors
                            }
                        }
                    }
                }
            } catch (e) {
                contentDiv.innerHTML = '<p style="color:#f00;">Error: ' + e.message + '</p>';
            }
        }

        // Start auto-investigate
        async function startAutoInvestigate() {
            if (!currentConvId) return;

            try {
                const response = await fetch('/api/auto/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        conversation_id: currentConvId,
                        max_queries: 10
                    })
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (autoRunning) {
                    const {done, value} = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));

                                if (data.type === 'auto_query') {
                                    addMessage('user', data.query, true);
                                    await streamQuery(data.query, true);
                                } else if (data.type === 'auto_complete') {
                                    console.log('Auto-investigate complete:', data);
                                    return;
                                }
                            } catch (e) {
                                console.error('Parse error:', e);
                            }
                        }
                    }
                }
            } catch (e) {
                console.error('Auto-investigate error:', e);
            }
        }

        // Add message to UI
        function addMessage(role, content, isAuto = false) {
            const container = document.getElementById('messages');
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message';
            msgDiv.innerHTML = `
                <div class="message-header">
                    <span class="message-role ${role}">${role === 'user' ? 'YOU' : 'L'}</span>
                    ${isAuto ? '<span class="message-auto">AUTO</span>' : ''}
                </div>
                <div class="message-content">
                    ${formatMessage(content)}
                </div>
            `;
            container.appendChild(msgDiv);
            scrollToBottom();
            return msgDiv;
        }

        // Scroll to bottom
        function scrollToBottom() {
            const container = document.getElementById('messages');
            container.scrollTop = container.scrollHeight;
        }

        // Init
        loadStats();
        loadConversations();
        newConversation();
    </script>
</body>
</html>
EOF

echo "✓ Frontend generated successfully"
