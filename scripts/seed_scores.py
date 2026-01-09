#!/usr/bin/env python3
"""
Seed scores for the Epstein corpus.
Populates scores.db with suspicion, pertinence, anomaly based on known patterns.
"""

import sqlite3
import re
from pathlib import Path

DB_DIR = Path("/opt/rag/db")
SOURCES_DB = DB_DIR / "sources.db"
GRAPH_DB = DB_DIR / "graph.db"
SCORES_DB = DB_DIR / "scores.db"

# =============================================================================
# SCORING RULES
# =============================================================================

# High-suspicion names (case-insensitive matching)
HIGH_SUSPICION_NAMES = [
    "epstein", "maxwell", "wexner", "clinton", "prince andrew",
    "dershowitz", "brunel", "dubin", "black", "staley",
    "giuffre", "roberts", "farmer", "wild", "marcinkova",
    "kellen", "groff", "alfredo", "nadia", "eva",
    "les", "ghislaine", "jeffrey", "bill", "hillary"
]

# Medium suspicion - associates
MEDIUM_SUSPICION_NAMES = [
    "trump", "spacey", "richardson", "mitchell", "gates",
    "ehud", "barak", "joi", "ito", "summers"
]

# Interesting domains (partial match)
INTERESTING_DOMAINS = [
    ".gov", "law", "bank", "fund", "capital", "invest",
    "trust", "foundation", "management", "virgin", "island"
]

# Key dates (YYYY-MM prefix match)
KEY_DATES = {
    "2019-07": 40,  # Arrest
    "2019-08": 40,  # Death
    "2006-": 30,    # First investigation
    "2007-": 25,    # Plea deal prep
    "2008-": 35,    # Plea deal signed
    "2005-": 20,    # Abuse period
    "2015-": 15,    # Giuffre lawsuit
    "2018-": 15,    # Miami Herald
}

# Suspicious keywords in content
SUSPICIOUS_KEYWORDS = [
    "massage", "girl", "young", "model", "flight", "island",
    "lolita", "palm beach", "little st", "zorro", "ranch",
    "recruitment", "cash", "wire", "transfer", "nda"
]


def connect_db(path):
    """Connect to SQLite database"""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_scores_db():
    """Ensure scores table exists"""
    conn = connect_db(SCORES_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            confidence INTEGER DEFAULT 50,
            source_count INTEGER DEFAULT 0,
            source_diversity INTEGER DEFAULT 50,
            pertinence INTEGER DEFAULT 50,
            centrality INTEGER DEFAULT 0,
            uniqueness INTEGER DEFAULT 50,
            suspicion INTEGER DEFAULT 0,
            anomaly INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            frequency REAL DEFAULT 0,
            decay REAL DEFAULT 1.0,
            status TEXT DEFAULT 'raw',
            needs_review INTEGER DEFAULT 0,
            review_priority INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0,
            conflict_severity INTEGER DEFAULT 0,
            touch_count INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(target_type, target_id)
        )
    """)
    conn.commit()
    return conn


def score_node(node, edges_count=0):
    """Calculate scores for a node"""
    name = (node['name'] or '').lower()
    node_type = node['type'] or ''

    suspicion = 0
    pertinence = 50
    confidence = 50
    anomaly = 0

    # Name matching
    for sus_name in HIGH_SUSPICION_NAMES:
        if sus_name in name:
            suspicion += 35
            pertinence += 20
            break

    for med_name in MEDIUM_SUSPICION_NAMES:
        if med_name in name:
            suspicion += 20
            pertinence += 10
            break

    # Domain matching (for email addresses)
    for domain in INTERESTING_DOMAINS:
        if domain in name:
            pertinence += 15
            if domain in ['.gov', 'law']:
                suspicion += 10
            break

    # Type-based confidence
    if node_type == 'person':
        # Full name = higher confidence
        if ' ' in name and len(name) > 5:
            confidence = 80
        else:
            confidence = 50
    elif node_type == 'email_address':
        if '@' in name and '.' in name:
            confidence = 90
        else:
            confidence = 40
    elif node_type in ['company', 'organization']:
        confidence = 70
    elif node_type in ['date', 'amount']:
        confidence = 85
    elif node_type == 'location':
        if any(x in name for x in ['island', 'beach', 'ranch', 'new york', 'florida']):
            pertinence += 15
        confidence = 60
    else:
        confidence = 45

    # Edge count = centrality
    centrality = min(edges_count * 5, 100)

    # Cap values
    suspicion = min(suspicion, 100)
    pertinence = min(pertinence, 100)

    return {
        'suspicion': suspicion,
        'pertinence': pertinence,
        'confidence': confidence,
        'anomaly': anomaly,
        'centrality': centrality
    }


def score_email(email):
    """Calculate scores for an email"""
    subject = (email['subject'] or '').lower()
    sender = (email['sender_email'] or '').lower()
    date = str(email['date_sent'] or '')[:10]
    body = (email['body_text'] or '')[:2000].lower()

    suspicion = 0
    pertinence = 50
    confidence = 70  # Emails are generally reliable
    anomaly = 0

    # Check sender domain
    for domain in INTERESTING_DOMAINS:
        if domain in sender:
            pertinence += 15
            break

    # Check date
    for date_prefix, score in KEY_DATES.items():
        if date.startswith(date_prefix):
            anomaly += score
            pertinence += 10
            break

    # Check subject + body for suspicious keywords
    text = subject + ' ' + body
    keyword_hits = 0
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword in text:
            keyword_hits += 1
            suspicion += 8

    # Check for high-suspicion names in content
    for sus_name in HIGH_SUSPICION_NAMES[:15]:  # Top 15
        if sus_name in text:
            suspicion += 12
            pertinence += 5

    # Cap values
    suspicion = min(suspicion, 100)
    pertinence = min(pertinence, 100)
    anomaly = min(anomaly, 100)

    return {
        'suspicion': suspicion,
        'pertinence': pertinence,
        'confidence': confidence,
        'anomaly': anomaly,
        'centrality': 0
    }


def propagate_suspicion(scores_conn, graph_conn):
    """Propagate suspicion through edges (1 hop)"""
    print("\n[4/4] Propagating suspicion through graph...")

    # Get high-suspicion nodes
    high_sus = scores_conn.execute("""
        SELECT target_id FROM scores
        WHERE target_type = 'node' AND suspicion >= 30
    """).fetchall()

    high_sus_ids = set(row['target_id'] for row in high_sus)
    print(f"      Found {len(high_sus_ids)} high-suspicion nodes")

    # Find connected nodes
    propagated = 0
    for node_id in high_sus_ids:
        # Get connected nodes
        edges = graph_conn.execute("""
            SELECT to_node_id FROM edges WHERE from_node_id = ?
            UNION
            SELECT from_node_id FROM edges WHERE to_node_id = ?
        """, (node_id, node_id)).fetchall()

        for edge in edges:
            connected_id = edge[0]
            if connected_id not in high_sus_ids:
                # Add propagation bonus
                scores_conn.execute("""
                    UPDATE scores
                    SET suspicion = MIN(suspicion + 15, 100),
                        pertinence = MIN(pertinence + 10, 100)
                    WHERE target_type = 'node' AND target_id = ?
                """, (connected_id,))
                propagated += 1

    scores_conn.commit()
    print(f"      Propagated to {propagated} connected nodes")


def main():
    print("=" * 60)
    print("SEEDING SCORES DATABASE")
    print("=" * 60)

    # Connect to databases
    scores_conn = init_scores_db()
    graph_conn = connect_db(GRAPH_DB)
    sources_conn = connect_db(SOURCES_DB)

    # Clear existing scores
    scores_conn.execute("DELETE FROM scores")
    scores_conn.commit()
    print("\nCleared existing scores")

    # ==========================================================================
    # SCORE NODES
    # ==========================================================================
    print("\n[1/4] Scoring nodes...")

    nodes = graph_conn.execute("SELECT * FROM nodes").fetchall()
    print(f"      Processing {len(nodes)} nodes...")

    # Get edge counts
    edge_counts = {}
    edges = graph_conn.execute("""
        SELECT from_node_id, COUNT(*) as cnt FROM edges GROUP BY from_node_id
        UNION ALL
        SELECT to_node_id, COUNT(*) as cnt FROM edges GROUP BY to_node_id
    """).fetchall()
    for row in edges:
        edge_counts[row[0]] = edge_counts.get(row[0], 0) + row[1]

    node_scores = []
    for node in nodes:
        scores = score_node(dict(node), edge_counts.get(node['id'], 0))
        node_scores.append((
            'node', node['id'],
            scores['confidence'], 0, 50,
            scores['pertinence'], scores['centrality'], 50,
            scores['suspicion'], scores['anomaly']
        ))

    scores_conn.executemany("""
        INSERT INTO scores (
            target_type, target_id, confidence, source_count, source_diversity,
            pertinence, centrality, uniqueness, suspicion, anomaly
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, node_scores)
    scores_conn.commit()

    high_sus_nodes = sum(1 for s in node_scores if s[8] >= 30)
    print(f"      -> {high_sus_nodes} high-suspicion nodes (>=30)")

    # ==========================================================================
    # SCORE EMAILS
    # ==========================================================================
    print("\n[2/4] Scoring emails...")

    emails = sources_conn.execute("""
        SELECT doc_id, subject, sender_email, date_sent, body_text
        FROM emails
    """).fetchall()
    print(f"      Processing {len(emails)} emails...")

    email_scores = []
    for email in emails:
        scores = score_email(dict(email))
        email_scores.append((
            'email', email['doc_id'],
            scores['confidence'], 0, 50,
            scores['pertinence'], scores['centrality'], 50,
            scores['suspicion'], scores['anomaly']
        ))

    scores_conn.executemany("""
        INSERT INTO scores (
            target_type, target_id, confidence, source_count, source_diversity,
            pertinence, centrality, uniqueness, suspicion, anomaly
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, email_scores)
    scores_conn.commit()

    high_sus_emails = sum(1 for s in email_scores if s[8] >= 30)
    high_anomaly_emails = sum(1 for s in email_scores if s[9] >= 25)
    print(f"      -> {high_sus_emails} high-suspicion emails (>=30)")
    print(f"      -> {high_anomaly_emails} high-anomaly emails (>=25)")

    # ==========================================================================
    # PROPAGATE SUSPICION
    # ==========================================================================
    propagate_suspicion(scores_conn, graph_conn)

    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 60)
    print("SCORING COMPLETE")
    print("=" * 60)

    stats = scores_conn.execute("""
        SELECT
            target_type,
            COUNT(*) as total,
            SUM(CASE WHEN suspicion >= 30 THEN 1 ELSE 0 END) as high_sus,
            SUM(CASE WHEN pertinence >= 60 THEN 1 ELSE 0 END) as high_pert,
            AVG(suspicion) as avg_sus,
            AVG(pertinence) as avg_pert
        FROM scores
        GROUP BY target_type
    """).fetchall()

    print("\nTarget Type    | Total   | High Sus | High Pert | Avg Sus | Avg Pert")
    print("-" * 75)
    for row in stats:
        print(f"{row['target_type']:14} | {row['total']:7} | {row['high_sus']:8} | {row['high_pert']:9} | {row['avg_sus']:7.1f} | {row['avg_pert']:7.1f}")

    # Top suspicious entities
    print("\n" + "-" * 60)
    print("TOP 15 SUSPICIOUS NODES:")
    print("-" * 60)

    top_sus = scores_conn.execute("""
        SELECT target_id, suspicion, pertinence
        FROM scores
        WHERE target_type = 'node'
        ORDER BY suspicion DESC, pertinence DESC
        LIMIT 15
    """).fetchall()

    for row in top_sus:
        node = graph_conn.execute(
            "SELECT name, type FROM nodes WHERE id = ?",
            (row['target_id'],)
        ).fetchone()
        if node:
            print(f"  [{row['suspicion']:3}] {node['name'][:40]:40} ({node['type']})")

    print("\n" + "-" * 60)
    print("TOP 10 SUSPICIOUS EMAILS:")
    print("-" * 60)

    top_emails = scores_conn.execute("""
        SELECT target_id, suspicion, anomaly, pertinence
        FROM scores
        WHERE target_type = 'email'
        ORDER BY suspicion DESC, anomaly DESC
        LIMIT 10
    """).fetchall()

    for row in top_emails:
        email = sources_conn.execute(
            "SELECT subject, date_sent FROM emails WHERE doc_id = ?",
            (row['target_id'],)
        ).fetchone()
        if email:
            subj = (email['subject'] or '(no subject)')[:45]
            date = str(email['date_sent'] or '')[:10]
            print(f"  [{row['suspicion']:3}|A:{row['anomaly']:2}] #{row['target_id']} {date} {subj}")

    # Close connections
    scores_conn.close()
    graph_conn.close()
    sources_conn.close()

    print("\nDone!")


if __name__ == "__main__":
    main()
