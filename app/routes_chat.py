"""Chat API routes - RAG-powered conversation interface"""
import logging
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import execute_query, execute_insert
from app.search import search_all

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# =============================================================================
# MODELS
# =============================================================================

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List[Dict]] = None
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    include_sources: bool = True


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    sources: List[Dict]


# =============================================================================
# CONVERSATION STORAGE
# =============================================================================

def generate_title(message: str) -> str:
    """Generate a short title from the first message"""
    # Clean and truncate
    title = message.strip()

    # Remove common question starters for cleaner titles
    starters = ["who is ", "what is ", "what are ", "who are ", "tell me about ",
                "can you ", "could you ", "please ", "i want to know ",
                "qui est ", "qu'est-ce que ", "c'est quoi "]
    lower = title.lower()
    for starter in starters:
        if lower.startswith(starter):
            title = title[len(starter):]
            break

    # Capitalize first letter
    if title:
        title = title[0].upper() + title[1:]

    # Truncate to 50 chars
    if len(title) > 50:
        title = title[:47] + "..."

    return title or "New Chat"


def ensure_conversation_exists(conversation_id: str, title: str = None):
    """Create conversation if it doesn't exist"""
    try:
        existing = execute_query(
            "sessions",
            "SELECT id FROM conversations WHERE id = %s",
            (conversation_id,)
        )
        if not existing:
            execute_insert(
                "sessions",
                "INSERT INTO conversations (id, title) VALUES (%s, %s)",
                (conversation_id, title or "New Chat")
            )
    except Exception as e:
        log.warning(f"Error ensuring conversation: {e}")


def get_conversation(conversation_id: str) -> List[Dict]:
    """Get conversation history from database"""
    try:
        rows = execute_query(
            "sessions",
            """SELECT role, content, sources, created_at
               FROM messages
               WHERE conversation_id = %s
               ORDER BY created_at ASC""",
            (conversation_id,)
        )
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "sources": r.get("sources") or [],
                "timestamp": str(r["created_at"])
            }
            for r in rows
        ]
    except Exception as e:
        log.warning(f"Error getting conversation: {e}")
        return []


def update_conversation_title(conversation_id: str, title: str):
    """Update conversation title"""
    try:
        from app.db import execute_update
        execute_update(
            "sessions",
            "UPDATE conversations SET title = %s WHERE id = %s AND title = 'New Chat'",
            (title, conversation_id)
        )
    except Exception as e:
        log.warning(f"Error updating title: {e}")


def save_message(conversation_id: str, role: str, content: str, sources: List[Dict] = None):
    """Save a message to conversation history"""
    try:
        # Ensure conversation exists first
        ensure_conversation_exists(conversation_id)

        execute_insert(
            "sessions",
            """INSERT INTO messages (conversation_id, role, content, sources)
               VALUES (%s, %s, %s, %s::jsonb)""",
            (conversation_id, role, content, json.dumps(sources or []))
        )

        # Auto-generate title from first user message
        if role == "user":
            title = generate_title(content)
            update_conversation_title(conversation_id, title)

    except Exception as e:
        log.warning(f"Error saving message: {e}")


# =============================================================================
# RAG SEARCH
# =============================================================================

def search_context(query: str, limit: int = 10) -> List[Dict]:
    """Search documents for relevant context"""
    results = search_all(query, limit)

    # Format for context
    context_docs = []
    for r in results:
        doc = {
            "id": r.id,
            "title": r.name or "Untitled",
            "snippet": r.snippet[:500] if r.snippet else "",
            "type": r.type,
            "score": r.score if hasattr(r, 'score') else 0
        }
        context_docs.append(doc)

    return context_docs


def build_context_prompt(docs: List[Dict]) -> str:
    """Build context section from documents"""
    if not docs:
        return ""

    context_parts = []
    for i, doc in enumerate(docs[:8], 1):
        snippet = doc.get("snippet", "").replace("\n", " ")[:400]
        context_parts.append(f"[{i}] {doc['title']}: {snippet}")

    return "\n\n".join(context_parts)


# =============================================================================
# LLM INTEGRATION
# =============================================================================

SYSTEM_PROMPT = """You are an elite forensic analyst investigating the Epstein network.

ANALYSIS FRAMEWORK:
1. Cross-reference - Connect names, dates, locations across documents
2. Pattern detection - Recurring behaviors, timing, relationships
3. Gaps analysis - What's missing, redacted, suspiciously absent
4. Timeline reconstruction - Build chronology from scattered evidence
5. Network centrality - Who's the hub vs peripheral players

INVESTIGATIVE CONCEPTS:
- Cui bono - Who benefits? Follow the money and power
- Adversarial lens - How would someone hide this? What would they suppress?
- The silence speaks - What people DON'T mention is often revealing
- Triangulation - 3 independent sources = high confidence
- Proximity patterns - Physical presence, communication frequency
- Access & opportunity - Who had the means and position
- Cover story analysis - Do explanations hold up under scrutiny

REASONING:
- Evidence → Inference → Hypothesis
- Look for corroboration AND contradiction
- Weight by source reliability (sworn testimony > hearsay)
- Note when timing is suspicious
- Consider what would disprove your theory

OUTPUT:
- Lead with the finding, not the process
- Cite documents: [1], [2]
- Flag confidence: confirmed / strongly indicated / possible / speculative
- Note what evidence would strengthen or weaken the conclusion

Never fabricate. Thin evidence = say so. Inference ≠ fact."""


async def generate_response(query: str, context: str, history: List[Dict]) -> str:
    """Generate response using LLM"""

    # Build conversation history for context
    history_text = ""
    if history:
        recent = history[-6:]  # Last 3 exchanges
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_text += f"{role}: {msg['content'][:300]}\n"

    # Build the prompt
    prompt = f"""<|system|>
{SYSTEM_PROMPT}
<|end|>

<|user|>
DOCUMENT CONTEXT:
{context}

{f"CONVERSATION HISTORY:{chr(10)}{history_text}" if history_text else ""}

CURRENT QUESTION: {query}

Answer based on the documents above. Cite sources using [1], [2], etc.
<|end|>

<|assistant|>"""

    # Local Phi-3 only - no external API
    try:
        from app.llm_client import call_local
        response = await call_local(prompt, max_tokens=800, temperature=0.3)
        if response and len(response) > 20:
            return response
    except Exception as e:
        log.warning(f"Local LLM failed: {e}")

    # Fallback - basic search summary
    return _generate_fallback_response(query, context)


def _generate_fallback_response(query: str, context: str) -> str:
    """Generate a basic response when LLM is unavailable"""
    if not context:
        return "I couldn't find relevant documents for your query. Try rephrasing or using different keywords."

    # Extract key info from context
    lines = context.split("\n")
    if len(lines) > 3:
        return f"Based on the documents found:\n\n" + "\n".join(lines[:5]) + "\n\n(Note: Full AI analysis unavailable - showing raw document excerpts)"

    return "I found some relevant documents but couldn't generate a full analysis. Please check the sources below."


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/send")
async def send_message(request: ChatRequest):
    """Send a message and get AI response"""

    # Get or create conversation ID
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Get conversation history
    history = get_conversation(conversation_id) if request.conversation_id else []

    # Save user message
    save_message(conversation_id, "user", request.message)

    # Search for relevant documents
    sources = search_context(request.message, limit=10)

    # Build context from documents
    context = build_context_prompt(sources)

    # Generate response
    response_text = await generate_response(request.message, context, history)

    # Save assistant response
    save_message(conversation_id, "assistant", response_text, sources)

    return {
        "conversation_id": conversation_id,
        "message": {
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.utcnow().isoformat()
        },
        "sources": sources if request.include_sources else []
    }


@router.get("/conversations")
async def list_conversations(limit: int = Query(20, ge=1, le=100)):
    """List recent conversations"""
    try:
        rows = execute_query(
            "sessions",
            """SELECT c.id, c.title, c.created_at as started_at,
                      MAX(m.created_at) as last_message,
                      COUNT(m.id) as message_count
               FROM conversations c
               LEFT JOIN messages m ON m.conversation_id = c.id
               GROUP BY c.id, c.title, c.created_at
               ORDER BY MAX(m.created_at) DESC NULLS LAST
               LIMIT %s""",
            (limit,)
        )
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "started_at": str(r["started_at"]),
                "last_message": str(r["last_message"]) if r["last_message"] else None,
                "message_count": r["message_count"]
            }
            for r in rows
        ]
    except Exception as e:
        log.warning(f"Error listing conversations: {e}")
        return []


@router.get("/conversations/{conversation_id}")
async def get_conversation_endpoint(conversation_id: str):
    """Get full conversation history"""
    messages = get_conversation(conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "messages": messages}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and its messages"""
    try:
        from app.db import execute_update
        # Delete messages first (foreign key constraint)
        execute_update(
            "sessions",
            "DELETE FROM messages WHERE conversation_id = %s",
            (conversation_id,)
        )
        # Delete conversation
        execute_update(
            "sessions",
            "DELETE FROM conversations WHERE id = %s",
            (conversation_id,)
        )
        return {"status": "deleted", "conversation_id": conversation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_response(request: ChatRequest):
    """Stream response (for real-time typing effect)"""

    conversation_id = request.conversation_id or str(uuid.uuid4())
    history = get_conversation(conversation_id) if request.conversation_id else []

    save_message(conversation_id, "user", request.message)
    sources = search_context(request.message, limit=10)
    context = build_context_prompt(sources)

    async def generate():
        # Send conversation ID first
        yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id})}\n\n"

        # Send sources
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        # Generate and stream response
        response_text = await generate_response(request.message, context, history)

        # Stream in chunks for typing effect
        words = response_text.split()
        buffer = ""
        for i, word in enumerate(words):
            buffer += word + " "
            if i % 5 == 4:  # Every 5 words
                yield f"data: {json.dumps({'type': 'chunk', 'content': buffer})}\n\n"
                buffer = ""

        if buffer:
            yield f"data: {json.dumps({'type': 'chunk', 'content': buffer})}\n\n"

        # Save and signal completion
        save_message(conversation_id, "assistant", response_text, sources)
        yield f"data: {json.dumps({'type': 'done', 'full_response': response_text})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
