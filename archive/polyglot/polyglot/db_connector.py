#!/usr/bin/env python3
"""
L Investigation - Polyglot DB Connector
PostgreSQL connection for all organs (Go, Rust, Node, Python)
"""

import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import RealDictCursor
import asyncpg

# =============================================================================
# Configuration
# =============================================================================

DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': int(os.getenv('PG_PORT', 5432)),
    'database': os.getenv('PG_DATABASE', 'l_investigation'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', ''),
}

# =============================================================================
# Sync Connection (for Go/Rust FFI)
# =============================================================================

def get_sync_connection():
    """Get synchronous PostgreSQL connection"""
    return psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        cursor_factory=RealDictCursor
    )

# =============================================================================
# Async Connection Pool (for Node/Python)
# =============================================================================

_pool = None

async def get_pool():
    """Get async connection pool"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            database=DB_CONFIG['database'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            min_size=5,
            max_size=20
        )
    return _pool

async def close_pool():
    """Close connection pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

# =============================================================================
# Node Queries
# =============================================================================

async def get_node(node_id: int) -> Optional[Dict]:
    """Get node by ID"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM nodes WHERE id = $1", node_id
        )
        return dict(row) if row else None

async def search_nodes(query: str, limit: int = 20) -> List[Dict]:
    """Search nodes by name"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, type, name, properties
            FROM nodes
            WHERE name_normalized ILIKE $1
               OR name ILIKE $1
            ORDER BY id
            LIMIT $2
        """, f'%{query}%', limit)
        return [dict(r) for r in rows]

async def get_node_edges(node_id: int) -> List[Dict]:
    """Get all edges for a node"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT e.*,
                   n1.name as from_name, n1.type as from_type,
                   n2.name as to_name, n2.type as to_type
            FROM edges e
            LEFT JOIN nodes n1 ON e.from_node_id::integer = n1.id
            LEFT JOIN nodes n2 ON e.to_node_id::integer = n2.id
            WHERE e.from_node_id = $1 OR e.to_node_id = $1
        """, str(node_id))
        return [dict(r) for r in rows]

async def insert_node(node_type: str, name: str, properties: Dict = None) -> int:
    """Insert new node"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO nodes (type, name, name_normalized, properties)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, node_type, name, name.lower(), json.dumps(properties or {}))
        return row['id']

async def insert_edge(from_id: int, to_id: int, edge_type: str, excerpt: str = None) -> int:
    """Insert new edge"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO edges (from_node_id, to_node_id, type, excerpt)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (from_node_id, to_node_id, type) DO NOTHING
            RETURNING id
        """, str(from_id), str(to_id), edge_type, excerpt)
        return row['id'] if row else None

# =============================================================================
# Document Queries
# =============================================================================

async def search_documents(query: str, limit: int = 20) -> List[Dict]:
    """Full-text search documents"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, filename, title, doc_type,
                   ts_rank(content_vector, plainto_tsquery($1)) as rank
            FROM documents
            WHERE content_vector @@ plainto_tsquery($1)
            ORDER BY rank DESC
            LIMIT $2
        """, query, limit)
        return [dict(r) for r in rows]

async def get_document(doc_id: int) -> Optional[Dict]:
    """Get document by ID"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM documents WHERE id = $1", doc_id
        )
        return dict(row) if row else None

# =============================================================================
# Graph Queries
# =============================================================================

async def get_neighbors(node_id: int, depth: int = 1) -> Dict:
    """Get node neighborhood graph"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get node
        node = await get_node(node_id)
        if not node:
            return {"error": "Node not found"}

        # Get edges and connected nodes
        edges = await get_node_edges(node_id)

        neighbor_ids = set()
        for e in edges:
            neighbor_ids.add(e.get('from_node_id'))
            neighbor_ids.add(e.get('to_node_id'))
        neighbor_ids.discard(str(node_id))

        neighbors = []
        for nid in list(neighbor_ids)[:50]:  # Limit
            try:
                n = await get_node(int(nid))
                if n:
                    neighbors.append(n)
            except:
                pass

        return {
            "center": node,
            "edges": edges,
            "neighbors": neighbors,
            "depth": depth
        }

async def get_shortest_path(from_id: int, to_id: int, max_depth: int = 5) -> List[Dict]:
    """Find shortest path between two nodes (BFS)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Simple BFS - for AGE we'd use Cypher
        visited = {str(from_id)}
        queue = [(str(from_id), [from_id])]

        while queue and len(visited) < 1000:
            current_id, path = queue.pop(0)

            if current_id == str(to_id):
                # Build path details
                path_nodes = []
                for nid in path:
                    node = await get_node(int(nid))
                    if node:
                        path_nodes.append(node)
                return path_nodes

            if len(path) >= max_depth:
                continue

            # Get neighbors
            rows = await conn.fetch("""
                SELECT DISTINCT
                    CASE WHEN from_node_id = $1 THEN to_node_id ELSE from_node_id END as neighbor
                FROM edges
                WHERE from_node_id = $1 OR to_node_id = $1
            """, current_id)

            for row in rows:
                neighbor = row['neighbor']
                if neighbor not in visited:
                    visited.add(neighbor)
                    try:
                        queue.append((neighbor, path + [int(neighbor)]))
                    except:
                        pass

        return []  # No path found

# =============================================================================
# Stats
# =============================================================================

async def get_stats() -> Dict:
    """Get database statistics"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        nodes = await conn.fetchval("SELECT COUNT(*) FROM nodes")
        edges = await conn.fetchval("SELECT COUNT(*) FROM edges")
        docs = await conn.fetchval("SELECT COUNT(*) FROM documents")

        type_counts = await conn.fetch("""
            SELECT type, COUNT(*) as count
            FROM nodes
            GROUP BY type
            ORDER BY count DESC
            LIMIT 10
        """)

        return {
            "nodes": nodes,
            "edges": edges,
            "documents": docs,
            "node_types": [dict(r) for r in type_counts]
        }

# =============================================================================
# Test
# =============================================================================

async def main():
    print("=" * 60)
    print("  DB Connector Test")
    print("=" * 60)

    stats = await get_stats()
    print(f"\n  Nodes:     {stats['nodes']:,}")
    print(f"  Edges:     {stats['edges']:,}")
    print(f"  Documents: {stats['documents']:,}")

    print("\n  Node types:")
    for t in stats['node_types'][:5]:
        print(f"    - {t['type']}: {t['count']}")

    print("\n  Testing search...")
    results = await search_nodes("maxwell", limit=5)
    print(f"  Found {len(results)} nodes for 'maxwell'")
    for r in results[:3]:
        print(f"    - {r['name']} ({r['type']})")

    await close_pool()
    print("\n  [OK] DB connector ready")

if __name__ == "__main__":
    asyncio.run(main())
