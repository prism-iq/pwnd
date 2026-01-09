"""Pydantic models for API"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Node(BaseModel):
    id: int
    type: str
    name: str
    name_normalized: Optional[str] = None
    source_db: Optional[str] = None
    source_id: Optional[int] = None
    created_at: str
    updated_at: str
    created_by: str = "system"

class Property(BaseModel):
    id: int
    node_id: int
    key: str
    value: str
    value_type: str = "text"
    source_node_id: Optional[int] = None
    excerpt: Optional[str] = None
    created_at: str
    created_by: str = "system"

class Edge(BaseModel):
    id: int
    from_node_id: int
    to_node_id: int
    type: str
    directed: int = 1
    source_node_id: Optional[int] = None
    excerpt: Optional[str] = None
    created_at: str
    created_by: str = "system"

class Score(BaseModel):
    target_type: str
    target_id: int
    confidence: int = 50
    source_count: int = 0
    source_diversity: int = 50
    pertinence: int = 50
    centrality: int = 0
    uniqueness: int = 50
    suspicion: int = 0
    anomaly: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    frequency: float = 0.0
    decay: float = 1.0
    status: str = "raw"
    needs_review: int = 0
    review_priority: int = 0
    locked: int = 0
    conflict_severity: int = 0
    touch_count: int = 0
    updated_at: str

class Flag(BaseModel):
    id: int
    target_type: str
    target_id: int
    flag_type: str
    description: Optional[str] = None
    severity: int = 50
    source_node_id: Optional[int] = None
    created_by: str = "system"
    active: int = 1
    created_at: str

class SearchResult(BaseModel):
    id: int
    type: str
    name: str
    snippet: str
    score: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

class QueryRequest(BaseModel):
    q: str = Field(..., max_length=10000)
    conversation_id: Optional[str] = None

class AutoSessionRequest(BaseModel):
    conversation_id: str
    max_queries: int = Field(default=20, ge=1, le=50)

class Hypothesis(BaseModel):
    statement: str
    hypothesis_type: str = "inference"
    proposed_updates: Optional[str] = None
    session_id: Optional[str] = None
    triggered_by: Optional[str] = None
    created_by: str = "haiku"

class LanguageRequest(BaseModel):
    language: str = Field(..., pattern="^(en|fr)$")
