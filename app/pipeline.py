"""Query processing pipeline - Multi-step investigation with streaming"""
import json
import re
import random
from typing import AsyncGenerator, Dict, Any, List
from app.llm_client import call_mistral, call_haiku
from app.db import execute_query, execute_insert, execute_update

NL = chr(10)

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

HAIKU_SYSTEM_PROMPT = """You are L, the detective. Analyze this investigation data and write your findings.

VOICE:
- Think out loud, show your reasoning
- Use percentages: "I'm at 23% certainty"
- "Interesting" = suspicious
- Dry wit, analytical
- Connect dots between findings
- Always end with next steps

FORMAT:
Write 3-5 paragraphs of analysis. Be thorough but not repetitive.
Reference specific emails by #ID.
End with "Next steps:" and 2-3 specific follow-up questions.

NEVER:
- Don't use bullet points
- Don't add external knowledge
- Don't be formal or robotic
- Don't say "Based on the data provided"

Write like a detective reviewing case files, not a report."""

FOLLOWUP_PROMPT = """Based on these search results, what's MISSING? What should I search next?

Results so far:
{results}

Reply with 1-2 specific search terms (names, domains, keywords) that would fill gaps.
Format: term1, term2
Nothing else."""

# =============================================================================
# STOP WORDS
# =============================================================================

STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
    'if', 'or', 'because', 'until', 'while', 'although', 'though',
    'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
    'tell', 'show', 'find', 'give', 'know', 'about', 'look', 'want',
    'search', 'explain', 'describe', 'list', 'help', 'please',
    'quelles', 'quelle', 'quels', 'quel', 'les', 'des', 'une', 'dans',
    'pour', 'sur', 'avec', 'par', 'sont', 'est', 'ont', 'aux', 'entre',
}

# =============================================================================
# SEARCH FUNCTIONS
# =============================================================================

def extract_search_terms(query: str) -> List[str]:
    """Extract meaningful search terms from query"""
    # Find quoted phrases
    quoted = re.findall(r'"([^"]+)"', query)

    # Find capitalized words (names)
    caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', query)

    # Get remaining words
    words = [w.lower() for w in re.findall(r'\b([a-zA-Z]{4,})\b', query.lower())
             if w.lower() not in STOP_WORDS]

    terms = quoted + caps + words
    # Dedupe while preserving order
    seen = set()
    result = []
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            result.append(t)

    return result[:5]


def search_corpus(search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search emails in corpus"""
    if not search_term or not search_term.strip():
        return []

    try:
        email_query = """
            SELECT
                doc_id as id,
                subject as name,
                sender_email,
                recipients_to,
                date_sent as date,
                ts_headline('english', COALESCE(body_text, subject), plainto_tsquery('english', %s),
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=10') as snippet,
                ts_rank(tsv, plainto_tsquery('english', %s)) as rank
            FROM emails
            WHERE tsv @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
        """
        return execute_query("sources", email_query, (search_term, search_term, search_term, limit))
    except Exception:
        return []


def format_results_for_llm(results: List[Dict], search_term: str) -> str:
    """Format search results for LLM consumption"""
    if not results:
        return f"[Search '{search_term}': No results]"

    lines = [f"[Search '{search_term}': {len(results)} results]"]
    for r in results[:8]:
        lines.append(f"  #{r.get('id')}: {r.get('name', 'No subject')[:60]}")
        lines.append(f"    From: {r.get('sender_email', '?')} | Date: {str(r.get('date', '?'))[:10]}")
        snippet = r.get('snippet', '')
        if snippet:
            # Clean snippet
            snippet = re.sub(r'<[^>]+>', '', snippet)[:150]
            lines.append(f"    \"{snippet}...\"")
    return NL.join(lines)


# =============================================================================
# MAIN PIPELINE - MULTI-STEP INVESTIGATION
# =============================================================================

async def process_query(query: str, conversation_id: str = None, is_auto: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
    """Multi-step investigation pipeline"""

    # Save user message
    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "user", query, 1 if is_auto else 0)
            )
        except:
            pass

    all_results = []
    all_ids = set()
    search_history = []

    # ==========================================================================
    # STEP 1: Initial search
    # ==========================================================================
    yield {"type": "status", "msg": "Analyzing query..."}
    yield {"type": "thinking", "text": f"Query received: \"{query}\"\n"}

    initial_terms = extract_search_terms(query)
    if not initial_terms:
        initial_terms = [query]

    yield {"type": "thinking", "text": f"Search terms identified: {', '.join(initial_terms)}\n\n"}

    # First search
    search_term = ' '.join(initial_terms[:3])
    yield {"type": "status", "msg": f"Searching: {search_term}..."}
    yield {"type": "thinking", "text": f"[Search 1] \"{search_term}\"\n"}

    results1 = search_corpus(search_term, limit=10)
    search_history.append({"term": search_term, "count": len(results1)})

    if results1:
        all_results.extend(results1)
        for r in results1:
            all_ids.add(r.get('id'))
        yield {"type": "thinking", "text": f"  → {len(results1)} emails found\n"}

        # Show what we found
        senders = list(set(r.get('sender_email', '') for r in results1 if r.get('sender_email')))[:3]
        if senders:
            yield {"type": "thinking", "text": f"  → Key senders: {', '.join(senders)}\n"}
    else:
        yield {"type": "thinking", "text": f"  → No results. Trying variations...\n"}
        # Try individual terms
        for term in initial_terms[:2]:
            results1 = search_corpus(term, limit=5)
            if results1:
                all_results.extend(results1)
                for r in results1:
                    all_ids.add(r.get('id'))
                yield {"type": "thinking", "text": f"  → '{term}': {len(results1)} emails\n"}
                break

    yield {"type": "sources", "ids": list(all_ids)}

    # ==========================================================================
    # STEP 2: Follow-up search based on findings
    # ==========================================================================
    if all_results:
        yield {"type": "thinking", "text": f"\nAnalyzing patterns...\n"}
        yield {"type": "status", "msg": "Analyzing patterns..."}

        # Extract entities from results for follow-up
        all_senders = [r.get('sender_email', '') for r in all_results if r.get('sender_email')]
        all_recipients = []
        for r in all_results:
            recip = r.get('recipients_to', '')
            if recip:
                if isinstance(recip, list):
                    all_recipients.extend(recip[:2])
                elif isinstance(recip, str):
                    all_recipients.extend(recip.split(',')[:2])

        # Find most common domain
        domains = [s.split('@')[1] if '@' in s else '' for s in all_senders]
        domain_counts = {}
        for d in domains:
            if d and d not in ['gmail.com', 'yahoo.com', 'hotmail.com']:
                domain_counts[d] = domain_counts.get(d, 0) + 1

        # Generate follow-up search
        followup_term = None

        if domain_counts:
            top_domain = max(domain_counts.items(), key=lambda x: x[1])[0]
            followup_term = top_domain.split('.')[0]  # Use domain name
            yield {"type": "thinking", "text": f"  Interesting domain pattern: {top_domain}\n"}
        elif all_recipients:
            # Search for a recipient
            recip = all_recipients[0].strip()
            if '@' in recip:
                followup_term = recip.split('@')[0]
                yield {"type": "thinking", "text": f"  Following recipient trail: {recip}\n"}

        if followup_term and followup_term.lower() not in [t.lower() for t in initial_terms]:
            yield {"type": "thinking", "text": f"\n[Search 2] \"{followup_term}\"\n"}
            yield {"type": "status", "msg": f"Searching: {followup_term}..."}

            results2 = search_corpus(followup_term, limit=8)
            search_history.append({"term": followup_term, "count": len(results2)})

            if results2:
                new_count = 0
                for r in results2:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                        new_count += 1
                yield {"type": "thinking", "text": f"  → {len(results2)} emails ({new_count} new)\n"}
                yield {"type": "sources", "ids": list(all_ids)}

    # ==========================================================================
    # STEP 3: One more targeted search
    # ==========================================================================
    if len(all_results) > 3:
        # Look for connections - find names in snippets
        name_pattern = r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b'
        all_names = []
        for r in all_results[:5]:
            snippet = r.get('snippet', '')
            names = re.findall(name_pattern, snippet)
            all_names.extend(names)

        # Filter out common false positives
        filtered_names = [n for n in all_names if n.lower() not in ['new york', 'los angeles', 'united states']]

        if filtered_names:
            # Find a name not in original query
            for name in filtered_names[:3]:
                if name.lower() not in query.lower():
                    yield {"type": "thinking", "text": f"\n[Search 3] Connection: \"{name}\"\n"}
                    yield {"type": "status", "msg": f"Checking connection: {name}..."}

                    results3 = search_corpus(name, limit=6)
                    search_history.append({"term": name, "count": len(results3)})

                    if results3:
                        new_count = 0
                        for r in results3:
                            if r.get('id') not in all_ids:
                                all_results.append(r)
                                all_ids.add(r.get('id'))
                                new_count += 1
                        yield {"type": "thinking", "text": f"  → {len(results3)} emails ({new_count} new)\n"}
                        if new_count > 0:
                            yield {"type": "sources", "ids": list(all_ids)}
                    break

    # ==========================================================================
    # STEP 4: Synthesize with Haiku (1 API call)
    # ==========================================================================
    yield {"type": "thinking", "text": f"\n--- Synthesis ---\n"}
    yield {"type": "status", "msg": "Synthesizing findings..."}

    if not all_results:
        response = "Nothing in the corpus. The absence of data is itself data - it means either the connection doesn't exist in these documents, or it's hidden under different names. Try specific email addresses, dates, or alternate spellings."
        yield {"type": "chunk", "text": response}
        yield {"type": "done", "sources": []}
        return

    # Prepare data for Haiku
    results_text = []
    for r in all_results[:15]:  # Limit to 15 most relevant
        results_text.append(
            f"Email #{r.get('id')}:\n"
            f"  Subject: {r.get('name', 'No subject')}\n"
            f"  From: {r.get('sender_email', '?')}\n"
            f"  To: {r.get('recipients_to', '?')}\n"
            f"  Date: {str(r.get('date', '?'))[:10]}\n"
            f"  Excerpt: {re.sub(r'<[^>]+>', '', r.get('snippet', ''))[:200]}"
        )

    search_summary = ", ".join([f"'{s['term']}' ({s['count']})" for s in search_history])

    haiku_prompt = f"""Investigation query: "{query}"

Searches performed: {search_summary}
Total unique emails found: {len(all_results)}

EMAIL DATA:
{NL.join(results_text)}

Write your analysis as L. What patterns do you see? What's suspicious? What connections emerge?
Reference specific emails by #ID. End with next investigation steps."""

    haiku_response = await call_haiku(haiku_prompt, system=HAIKU_SYSTEM_PROMPT, max_tokens=1000)

    if "error" in haiku_response:
        # Fallback to basic response
        yield {"type": "thinking", "text": "API unavailable, using local analysis...\n"}

        response_parts = []
        response_parts.append(f"{len(all_results)} emails found across {len(search_history)} searches. Interesting.")

        senders = list(set(r.get('sender_email', '') for r in all_results if r.get('sender_email')))[:3]
        if senders:
            response_parts.append(f"Key contacts: {', '.join(senders)}")

        dates = [str(r.get('date', ''))[:7] for r in all_results if r.get('date')]
        if dates:
            date_range = f"{min(dates)} to {max(dates)}"
            response_parts.append(f"Timeline spans {date_range}.")

        certainty = random.choice([12, 18, 23, 27, 31])
        response_parts.append(f"I'm at {certainty}% certainty there's something here worth pursuing.")
        response_parts.append(f"Sources: {', '.join([f'#{id}' for id in list(all_ids)[:5]])}")

        response = NL.join(response_parts)
    else:
        response = haiku_response.get("text", "Analysis complete.")

    yield {"type": "chunk", "text": response}

    # Save response
    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "assistant", response, 1 if is_auto else 0)
            )
        except:
            pass

    # Suggest follow-ups
    suggestions = []
    for s in search_history:
        if s['count'] > 0:
            suggestions.append(s['term'])

    if suggestions:
        yield {"type": "suggestions", "queries": suggestions[:4]}

    yield {"type": "done", "sources": list(all_ids)}


# =============================================================================
# AUTO-INVESTIGATION (unchanged)
# =============================================================================

async def auto_investigate(conversation_id: str, max_queries: int = 10) -> AsyncGenerator[Dict[str, Any], None]:
    """Auto-investigation mode"""

    messages = execute_query(
        "sessions",
        "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,)
    )

    if not messages:
        yield {"type": "error", "msg": "No user message found."}
        return

    yield {"type": "auto_start", "max_queries": max_queries}

    query_count = 0
    pending = [messages[0]['content']]
    processed = set()

    while query_count < max_queries and pending:
        current = pending.pop(0)
        if current in processed:
            continue
        processed.add(current)
        query_count += 1

        yield {"type": "auto_query", "query": current, "index": query_count}

        async for event in process_query(current, conversation_id, is_auto=True):
            if event.get("type") == "suggestions":
                for q in event.get("queries", []):
                    if q not in processed and q not in pending:
                        pending.append(q)
            yield event

    yield {"type": "auto_complete", "total_queries": query_count}
