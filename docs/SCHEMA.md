# Database Schema - L Investigation Framework

## Overview

The L Investigation Framework uses 3 SQLite databases for separation of concerns:

1. **sources.db** (948MB) - Immutable email corpus
2. **graph.db** (3.7MB) - Derived entity graph
3. **sessions.db** (48KB) - User sessions and settings

---

## sources.db - Email Corpus

### emails table

Primary table containing all email data.

```sql
CREATE TABLE emails (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,               -- RFC5322 Message-ID header
    subject TEXT,
    date_sent DATETIME,            -- ISO 8601 format
    sender_email TEXT,
    sender_name TEXT,
    recipients_to JSON,            -- Array of {name, email}
    recipients_cc JSON,
    recipients_bcc JSON,
    reply_to TEXT,
    in_reply_to TEXT,              -- For threading
    thread_id TEXT,                -- Conversation grouping
    body_text TEXT,                -- Plain text content
    body_html TEXT,                -- HTML content
    has_attachments BOOLEAN DEFAULT FALSE,
    attachment_count INTEGER DEFAULT 0,
    domains_extracted JSON,        -- Array of domains from URLs
    urls_extracted JSON,           -- Array of URLs
    ips_extracted JSON,            -- Array of IP addresses
    extraction_quality REAL DEFAULT 1.0,  -- Quality score (0-1)
    parsed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
```sql
CREATE INDEX idx_emails_date ON emails(date_sent);
CREATE INDEX idx_emails_sender ON emails(sender_email);
CREATE INDEX idx_emails_thread ON emails(thread_id);
```

**Example row:**
```sql
doc_id: 7837
message_id: <abc123@example.com>
subject: "Re: Property transfer"
date_sent: 2015-03-15T14:30:00Z
sender_email: jeffrey@epstein.com
sender_name: Jeffrey Epstein
recipients_to: [{"name": "Maxwell", "email": "gm@example.com"}]
body_text: "The island transfer is complete..."
```

---

### emails_fts table

Full-text search index (FTS5) on subject + body_text.

```sql
CREATE VIRTUAL TABLE emails_fts USING fts5(
    subject,
    body_text,
    content=emails,
    content_rowid=doc_id
);
```

**Usage:**
```sql
-- Basic search
SELECT doc_id, subject, snippet(emails_fts, 1, '<mark>', '</mark>', '...', 50) AS snippet
FROM emails_fts
WHERE emails_fts MATCH 'epstein'
ORDER BY rank
LIMIT 10;

-- Advanced search with operators
WHERE emails_fts MATCH 'epstein AND maxwell'  -- Both terms
WHERE emails_fts MATCH 'epstein OR trump'     -- Either term
WHERE emails_fts MATCH 'epstein NOT spam'     -- Exclude term
WHERE emails_fts MATCH '"little st james"'    -- Phrase search
```

---

### domains table

Extracted domains from email URLs.

```sql
CREATE TABLE domains (
    id INTEGER PRIMARY KEY,
    domain TEXT UNIQUE,
    first_seen DATETIME,
    occurrence_count INTEGER DEFAULT 1
);
```

---

## graph.db - Entity Relationship Graph

### nodes table

Entities extracted from emails (persons, organizations, locations, etc.).

```sql
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,            -- person, org, location, date, amount, etc.
    name TEXT NOT NULL,
    name_normalized TEXT,          -- Lowercase for matching
    source_db TEXT,                -- "sources"
    source_id INTEGER,             -- doc_id in emails table
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'  -- 'system', 'haiku_extraction', etc.
);
```

**Node Types:**
```
person (2,560)         - Jeffrey Epstein, Donald Trump
organization (591)     - Trump Organization, Epstein Foundation
location (1,840)       - Little St. James, Mar-a-Lago
date (1,950)           - 2003-05-15, June 2010
amount (1,737)         - $15M, €500K
email_address (...)    - jeffrey@epstein.com
phone (...)            - +1-555-0123
document (598)         - Contract #7837
event (532)            - Meeting at Trump Tower
object (1,453)         - Private jet, island property
unknown (378)          - Uncategorized
```

**Indexes:**
```sql
CREATE INDEX idx_nodes_type ON nodes(type);
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_nodes_normalized ON nodes(name_normalized);
CREATE INDEX idx_nodes_source ON nodes(source_db, source_id);
```

**Example row:**
```sql
id: 9
type: person
name: Jeffrey Epstein
name_normalized: jeffrey epstein
source_db: sources
source_id: 7837
created_by: haiku_extraction
```

---

### edges table

Relationships between nodes.

```sql
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,            -- Relationship type
    directed BOOLEAN DEFAULT TRUE,  -- TRUE for A→B, FALSE for A↔B
    source_node_id INTEGER,        -- Email node that evidences this
    excerpt TEXT,                  -- Quote from email supporting relationship
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'
);
```

**Edge Types:**
```
sent_email_to          - A sent email to B
knows                  - A knows B
works_for              - A works for B (org)
owns_property          - A owns B (property)
associated_with        - A is associated with B
mentioned_with         - A mentioned in same context as B
attended               - A attended B (event)
signed                 - A signed B (document)
transferred_money      - A transferred money to B
connection_invite      - A invited B to connect
has_email              - A has email address B
owns_account           - A owns account B
```

**Indexes:**
```sql
CREATE INDEX idx_edges_from ON edges(from_node_id);
CREATE INDEX idx_edges_to ON edges(to_node_id);
CREATE INDEX idx_edges_type ON edges(type);
CREATE INDEX idx_edges_both ON edges(from_node_id, to_node_id);
```

**Example row:**
```sql
id: 251
from_node_id: 9  (Jeffrey Epstein)
to_node_id: 1251  (Little St. James)
type: owns_property
excerpt: "Epstein purchased the island in 1998"
source_node_id: 7837
```

---

### aliases table

Name variations for entity deduplication.

```sql
CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    alias_name TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,   -- 0-1, how sure we are this is same entity
    created_at TEXT DEFAULT (datetime('now'))
);
```

**Example:**
```sql
canonical_node_id: 9  (Jeffrey Epstein)
alias_name: Jeff Epstein
confidence: 0.95

canonical_node_id: 9
alias_name: J. Epstein
confidence: 0.85
```

---

### nodes_fts table

Full-text search on node names.

```sql
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    name,
    type,
    content=nodes,
    content_rowid=id
);
```

---

## sessions.db - User Sessions

### conversations table

```sql
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,  -- UUID
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### messages table

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSON DEFAULT '{}',    -- {sources: [1,2,3], confidence: "high"}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### settings table

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Example entries:**
```sql
key: auto_investigate_enabled
value: true

key: max_auto_queries
value: 5
```

---

### auto_sessions table

Tracks auto-investigation sessions.

```sql
CREATE TABLE auto_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'stopped', 'completed')),
    max_queries INTEGER DEFAULT 5,
    queries_executed INTEGER DEFAULT 0,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    stopped_at DATETIME,
    completed_at DATETIME
);
```

---

## Common Queries

### Find all emails from person
```sql
SELECT e.doc_id, e.subject, e.date_sent, e.body_text
FROM emails e
WHERE e.sender_email IN (
    SELECT alias_name FROM aliases WHERE canonical_node_id = 9
    UNION
    SELECT name FROM nodes WHERE id = 9
)
ORDER BY e.date_sent DESC;
```

### Find all connections for entity
```sql
SELECT
    n1.name AS from_entity,
    e.type AS relationship,
    n2.name AS to_entity,
    e.excerpt
FROM edges e
JOIN nodes n1 ON e.from_node_id = n1.id
JOIN nodes n2 ON e.to_node_id = n2.id
WHERE e.from_node_id = 9 OR e.to_node_id = 9
LIMIT 50;
```

### Find path between two entities (2 hops)
```sql
WITH RECURSIVE path AS (
    -- Start node
    SELECT 9 AS node_id, 9 AS start_id, 0 AS depth, '' AS path

    UNION ALL

    -- Traverse edges
    SELECT
        e.to_node_id,
        p.start_id,
        p.depth + 1,
        p.path || ' -> ' || n.name
    FROM path p
    JOIN edges e ON p.node_id = e.from_node_id
    JOIN nodes n ON e.to_node_id = n.id
    WHERE p.depth < 2
)
SELECT DISTINCT path FROM path WHERE node_id = 3427 AND depth > 0;
```

### Timeline of events for entity
```sql
SELECT
    e.date_sent,
    e.subject,
    e.sender_name,
    n.name AS mentioned_entity,
    n.type
FROM emails e
JOIN nodes n ON n.source_id = e.doc_id AND n.source_db = 'sources'
WHERE n.name LIKE '%epstein%'
ORDER BY e.date_sent ASC;
```

### Most connected entities
```sql
SELECT
    n.name,
    n.type,
    COUNT(e.id) AS connection_count
FROM nodes n
LEFT JOIN edges e ON n.id = e.from_node_id OR n.id = e.to_node_id
GROUP BY n.id
ORDER BY connection_count DESC
LIMIT 20;
```

### Search emails and enrich with graph data
```sql
SELECT
    e.doc_id,
    e.subject,
    e.date_sent,
    snippet(emails_fts, 1, '<mark>', '</mark>', '...', 50) AS snippet,
    GROUP_CONCAT(n.name, ', ') AS entities
FROM emails_fts
JOIN emails e ON emails_fts.rowid = e.doc_id
LEFT JOIN nodes n ON n.source_id = e.doc_id AND n.source_db = 'sources'
WHERE emails_fts MATCH 'epstein AND maxwell'
GROUP BY e.doc_id
ORDER BY e.date_sent DESC
LIMIT 10;
```

---

## Migration to PostgreSQL

Prepared script: `/opt/rag/scripts/migrate_to_postgres.sh`

**Schema mapping:**

| SQLite | PostgreSQL |
|--------|------------|
| TEXT | TEXT |
| INTEGER | BIGINT |
| REAL | DOUBLE PRECISION |
| BOOLEAN | BOOLEAN |
| DATETIME | TIMESTAMP |
| JSON | JSONB |
| FTS5 | ts_vector + GIN index |

**Improvements:**
- `tsvector` for better FTS
- `pg_trgm` for fuzzy string matching
- `JSONB` for flexible querying
- Foreign key constraints enforced
- Connection pooling

---

**TL;DR:**

3 databases: sources (emails), graph (entities), sessions (user data). emails_fts for full-text search. nodes + edges for graph. Use parameterized queries for all user input. See TROUBLESHOOTING.md for common query issues.

**Read next:** `/opt/rag/docs/ROADMAP.md` for future plans.
