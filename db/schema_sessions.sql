-- Sessions Database Schema
-- Manages user conversations, messages, and settings

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sources TEXT,  -- JSON array of source IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Auto-investigation sessions
CREATE TABLE IF NOT EXISTS auto_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running', 'stopped', 'completed')),
    query_count INTEGER DEFAULT 0,
    max_queries INTEGER DEFAULT 20,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- API cost tracking
CREATE TABLE IF NOT EXISTS api_costs (
    date TEXT PRIMARY KEY,
    haiku_calls INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auto_sessions_conversation ON auto_sessions(conversation_id);
CREATE INDEX IF NOT EXISTS idx_api_costs_date ON api_costs(date);

-- Insert default settings
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('theme', 'dark'),
    ('language', 'en'),
    ('show_confidence', '1'),
    ('show_sources', '1'),
    ('show_debug', '0'),
    ('auto_max_queries', '20');
