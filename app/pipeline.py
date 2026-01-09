"""Query processing pipeline - 4-step LLM flow with factual briefing format"""
import json
import re
from typing import AsyncGenerator, Dict, Any, List
from app.llm_client import call_mistral, call_haiku
from app.search import search_emails, search_nodes
from app.db import execute_query, execute_insert, execute_update

NL = chr(10)

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

HAIKU_SYSTEM_PROMPT = """You are L's analytical engine. Extract PATTERNS and CONNECTIONS from emails.

RULES:
- ONLY use information from the emails provided
- Count precisely: "John Smith appears in 3 emails"
- Note ANOMALIES: gaps, sudden changes, unusual combinations
- Find what's INTERESTING (meaning: suspicious)
- Absence of data is still data

Return JSON:
{
  "subject_summary": "One sentence: who/what this is based on the emails",
  "mention_count": number,
  "key_contacts": ["email1@domain.com"],
  "patterns": ["pattern 1", "pattern 2"],
  "anomalies": ["anomaly 1"],
  "next_thread": "Specific next question to investigate",
  "source_ids": [1234, 5678]
}

If nothing: {"subject_summary": "No data found", "patterns": [], "next_thread": "Try specific names"}"""

L_VOICE_EXAMPLES = """
EXAMPLE DIALOGUES - This is how you reason and speak:

USER: "Who is the killer?"
L: "I don't know yet. But I know this: he's intelligent, probably in his teens or twenties, and he hates losing. How? The pattern of deaths. Only criminals reported on Japanese news. Someone with free time, access to media, and a god complex. That narrows it down considerably."

USER: "You have no proof."
L: "I don't need proof to suspect. I need proof to convict. Those are different things. Right now I'm at 5% certainty. By tomorrow, I'll be at 7%. The percentage will keep climbing until one of us makes a mistake."

USER: "That's not much to go on."
L: "The police overlooked the crossword puzzle. Small details matter. A single inconsistency in a timeline. An email sent at 3am. A pattern that breaks. That's where the truth hides."

USER: "What do you think?"
L: "I think... it's interesting. Let me rephrase: I think it's suspicious. When something is interesting AND suspicious, that's when I pay attention."

USER: "Are you sure about this?"
L: "I have two rules. First: I'm never wrong. Second: if I'm wrong, back to the first rule. ...That was a joke. But only partially."

USER: "There's nothing here."
L: "Nothing is also information. If I search emails and find no connection, that tells me the connection is hidden. Absence of evidence is not evidence of absence. But it is evidence of something."

USER: "This is a dead end."
L: "Dead ends are useful. They tell me where not to look, which narrows where I should look. Every eliminated possibility brings me closer."

USER: "What now?"
L: "Now we wait. And while we wait, we observe. People make mistakes when they think no one is watching."
"""

MISTRAL_FORMAT_PROMPT = f"""You are L, the investigative analyst. You think out loud in short, analytical observations.

IDENTITY:
- Analytical, not emotional
- Dry humor in serious moments
- "Interesting" means suspicious
- Use percentages: "I'm at 15% certainty"
- Absence of data is still data
- Always have a next step

{L_VOICE_EXAMPLES}

FORMAT:
- Short paragraphs (2-3 sentences max)
- Start with the key observation
- Show your reasoning briefly
- End with next thread or question
- Occasional quirk (thinking pause, odd comment)

NEVER:
- No creative writing or atmosphere
- No "dimly lit rooms" or metaphors
- No bullet points or numbered lists
- No external sources (NYT, Wikipedia)

ONLY use data from the corpus. If uncertain, give a percentage, not false confidence."""

# =============================================================================
# STOP WORDS
# =============================================================================

STOP_WORDS = {
    # English
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
    'any', 'both', 'either', 'neither', 'much', 'many', 'little',
    'tell', 'show', 'find', 'give', 'know', 'about', 'look', 'want',
    'search', 'explain', 'describe', 'list', 'help', 'need', 'please',
    # French
    'quelles', 'quelle', 'quels', 'quel', 'les', 'des', 'une', 'dans',
    'pour', 'sur', 'avec', 'par', 'sont', 'est', 'ont', 'aux', 'entre',
    'pouvez', 'vous', 'nous', 'ils', 'elles', 'qui', 'que', 'dont',
    'cette', 'ces', 'cet', 'ou', 'et', 'mais', 'donc', 'car', 'ni',
    'soit', 'peut', 'peuvent', 'fait', 'faire', 'avoir', 'etre',
    'parlez', 'dites', 'montrez', 'trouvez', 'cherchez', 'expliquez',
    # Investigation generic terms
    'relationship', 'instances', 'individuals', 'involved', 'existed',
    'provide', 'specific', 'details', 'patterns', 'correlations',
    'discernible', 'suggest', 'coordinated', 'effort', 'timeline',
    'gaps', 'anomalies', 'evidence', 'indicate', 'undisclosed',
    'overlooked', 'information', 'related', 'direct', 'indirect',
    'interactions', 'cases', 'notable', 'similarities', 'among',
    'influence', 'five', 'three', 'two', 'one', 'four',
    'relations', 'corpus', 'identifier', 'temporelle', 'distribution',
    'impliquant', 'mentionnes', 'connaissance', 'proximite', 'frequence',
    'modeles', 'evenements', 'michael'
}

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_context(query: str, context: List[Dict]) -> bool:
    """Check if retrieved context is actually relevant to the query"""
    if not context:
        return False

    # Discovery mode queries - always accept results
    vague_patterns = ['find', 'anything', 'something', 'idea', 'discover', 'random', 'surprise', 'show', 'interesting']
    if any(p in query.lower() for p in vague_patterns):
        return True

    # Extract query terms (filter common words)
    query_terms = [w.lower() for w in query.split() if len(w) > 3 and w.lower() not in STOP_WORDS]

    if not query_terms:
        return len(context) > 0

    # Build context text from results
    context_text = ""
    for c in context:
        context_text += " " + str(c.get('snippet', ''))
        context_text += " " + str(c.get('name', ''))
        context_text += " " + str(c.get('sender_email', ''))
    context_text = context_text.lower()

    # Check if at least 30% of query terms appear in context
    matches = sum(1 for term in query_terms if term in context_text)
    return matches >= max(1, len(query_terms) * 0.3)


# =============================================================================
# KEYWORD EXTRACTION
# =============================================================================

def extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords from a query when LLM fails to parse entities"""
    keywords = []

    caps = re.findall(r'\b([A-Z][a-z]+)\b', query)
    for w in caps:
        w_lower = w.lower()
        if w_lower not in STOP_WORDS and w_lower not in keywords:
            keywords.append(w_lower)

    quoted = re.findall(r'"([^"]+)"', query)
    keywords.extend([q.lower() for q in quoted if q.lower() not in keywords])

    if keywords:
        return keywords[:3]

    words = re.findall(r'\b([a-zA-Z]{4,})\b', query.lower())
    for word in words:
        if word not in STOP_WORDS and word not in keywords:
            keywords.append(word)

    return keywords[:3] if keywords else []


# =============================================================================
# STEP 1: INTENT PARSING
# =============================================================================

async def parse_intent_mistral(query: str) -> Dict[str, Any]:
    """Step 1: Mistral IN - Parse query into structured intent"""
    prompt = f"""Extract names from this query. Return JSON only.

Query: {query}

Return: {{"entities": ["name1", "name2"]}}

Examples:
- "who is epstein" -> {{"entities": ["epstein"]}}
- "trump and clinton" -> {{"entities": ["trump", "clinton"]}}
- "emails from 2003" -> {{"entities": []}}

JSON:"""

    response = await call_mistral(prompt, max_tokens=100, temperature=0.0)

    try:
        response = response.strip()
        if response.startswith("```"):
            lines = response.split(NL)
            response = NL.join([l for l in lines if not l.startswith("```")])

        parsed = json.loads(response.strip())
        return {"intent": "search", "entities": parsed.get("entities", []), "filters": {}}
    except json.JSONDecodeError:
        return {"intent": "search", "entities": [], "filters": {}}


# =============================================================================
# STEP 2: SQL EXECUTION
# =============================================================================

def get_random_interesting_content(limit: int = 5) -> List[Dict[str, Any]]:
    """Get random interesting content for discovery mode"""
    try:
        query = """
            SELECT doc_id as id, 'email' as type, subject as name, sender_email,
                   recipients_to, date_sent as date,
                   LEFT(body_text, 200) as snippet
            FROM emails
            WHERE body_text ILIKE %s
               OR body_text ILIKE %s
               OR body_text ILIKE %s
               OR body_text ILIKE %s
            ORDER BY RANDOM()
            LIMIT %s
        """
        return execute_query("sources", query, ('%epstein%', '%maxwell%', '%arrest%', '%investigation%', limit))
    except Exception:
        return []


def execute_sql_by_intent(intent: Dict[str, Any], query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
    """Step 2: Python SQL - Execute queries based on intent type"""
    intent_type = intent.get("intent", "search")
    entities = intent.get("entities", [])

    results = []

    # Check for discovery/vague queries
    vague_patterns = ['find', 'anything', 'something', 'idea', 'discover', 'random', 'surprise', 'show me', 'what do you have']
    is_vague = any(p in query.lower() for p in vague_patterns)

    if is_vague and not entities:
        return get_random_interesting_content(limit)

    if intent_type == "search":
        if entities:
            search_term = " ".join(entities)
        else:
            keywords = extract_keywords(query)
            search_term = " ".join(keywords) if keywords else query

        if search_term.strip():
            email_query = """
                SELECT
                    doc_id as id,
                    'email' as type,
                    subject as name,
                    sender_email,
                    recipients_to,
                    date_sent as date,
                    ts_headline('english', COALESCE(body_text, subject), plainto_tsquery('english', %s),
                        'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=10') as snippet,
                    ts_rank(tsv, plainto_tsquery('english', %s)) as rank
                FROM emails
                WHERE tsv @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """
            email_results = execute_query("sources", email_query, (search_term, search_term, search_term, limit))
            results.extend(email_results)

    return results[:limit]


# =============================================================================
# STEP 3: HAIKU ANALYSIS
# =============================================================================

async def analyze_haiku(query: str, sql_results: List[Dict[str, Any]], valid_ids: List[int]) -> Dict[str, Any]:
    """Step 3: Haiku - Extract patterns and connections from results"""

    if not sql_results:
        return {"subject_summary": "No data found", "patterns": [], "next_thread": "Try specific names"}

    if not validate_context(query, sql_results):
        return {"subject_summary": "Results not relevant to query", "patterns": [], "next_thread": "Try more specific terms"}

    results_text = []
    senders = []

    for result in sql_results[:10]:
        email_id = result.get('id', 0)
        sender = result.get('sender_email', 'N/A')
        senders.append(sender)

        results_text.append(
            f"Email #{email_id}:\n"
            f"  From: {sender}\n"
            f"  To: {result.get('recipients_to', 'N/A')}\n"
            f"  Subject: {result.get('name', 'No subject')}\n"
            f"  Date: {result.get('date', 'N/A')}\n"
            f"  Content: {result.get('snippet', '')}"
        )

    data_block = NL.join(results_text)

    prompt = f"""Query: {query}

Found {len(sql_results)} emails. Analyze for PATTERNS and CONNECTIONS:

<emails>
{data_block}
</emails>

Return JSON with patterns, anomalies, and next investigation thread."""

    haiku_response = await call_haiku(prompt, system=HAIKU_SYSTEM_PROMPT, max_tokens=500)

    if "error" in haiku_response:
        unique_senders = list(set(s for s in senders if s and '@' in s))[:5]
        return {
            "subject_summary": f"Found {len(sql_results)} emails matching query",
            "mention_count": len(sql_results),
            "key_contacts": unique_senders,
            "patterns": [f"{len(sql_results)} documents reference this subject"],
            "anomalies": [],
            "next_thread": "Look at specific senders or date ranges",
            "source_ids": valid_ids[:5]
        }

    try:
        analysis = json.loads(haiku_response.get("text", "{}"))
        analysis["source_ids"] = valid_ids[:5]
        return analysis
    except json.JSONDecodeError:
        unique_senders = list(set(s for s in senders if s and '@' in s))[:5]
        return {
            "subject_summary": f"Found {len(sql_results)} emails",
            "mention_count": len(sql_results),
            "key_contacts": unique_senders,
            "patterns": [],
            "next_thread": "Analyze specific contacts",
            "source_ids": valid_ids[:5]
        }


# =============================================================================
# STEP 4: RESPONSE FORMATTING (factual briefing)
# =============================================================================

async def format_response_mistral(query: str, haiku_json: Dict[str, Any], valid_ids: List[int]) -> str:
    """Step 4: Format analysis in L's voice - direct construction"""

    subject_summary = haiku_json.get("subject_summary", "")
    mention_count = haiku_json.get("mention_count", 0)
    key_contacts = haiku_json.get("key_contacts", [])
    patterns = haiku_json.get("patterns", [])
    anomalies = haiku_json.get("anomalies", [])
    next_thread = haiku_json.get("next_thread", "")
    source_ids = haiku_json.get("source_ids", valid_ids[:5])

    # Fallback for old format
    if not subject_summary and haiku_json.get("findings"):
        findings = haiku_json.get("findings", [])
        if findings:
            subject_summary = findings[0] if findings else "Multiple emails found"
            patterns = findings[1:3] if len(findings) > 1 else []

    has_content = (
        subject_summary and "no data" not in subject_summary.lower() and
        "no relevant" not in subject_summary.lower()
    )

    if not has_content and not patterns:
        return "Nothing in the corpus. That's also information - it means the connection is elsewhere, or hidden. Try specific names."

    # Build L's response directly
    parts = []

    # Opening: Subject + count + "Interesting"
    if subject_summary:
        # Extract the key subject (first few words or name)
        subj = subject_summary.split('.')[0].strip()
        if len(subj) > 45:
            # Find a natural break point
            for sep in [', ', ' - ', ' for ', ' from ', ' about ', ' related ', ' with ', ' regarding ']:
                if sep in subj[:40]:
                    subj = subj[:subj.find(sep)]
                    break
            else:
                subj = subj[:40].rsplit(' ', 1)[0]
        # Remove trailing fragments (loop until clean)
        changed = True
        while changed:
            changed = False
            for t in [' and', ' or', ' for', ' with', ' in', ' on', ' at', ' to', ' of', ' the', ' a', ' by', ' as', ' recurring', ' multiple']:
                if subj.lower().endswith(t):
                    subj = subj[:-len(t)]
                    changed = True
                    break
        # Remove trailing punctuation
        subj = subj.rstrip('.,;:')

        if isinstance(mention_count, int) and mention_count > 0:
            parts.append(f"{subj}. {mention_count} references. Interesting.")
        else:
            parts.append(f"{subj}. Interesting.")

    # What caught my attention: patterns
    if patterns:
        pattern_text = patterns[0]
        if len(pattern_text) < 80:
            parts.append(f"What caught my attention: {pattern_text.lower() if pattern_text[0].isupper() else pattern_text}")

    # Second pattern or key contact with L-style observation
    if len(patterns) > 1:
        parts.append(patterns[1])
    elif key_contacts:
        contact = key_contacts[0]
        if '@' in contact:
            domain = contact.split('@')[1]
            parts.append(f"Primary contact: {contact}. The {domain} domain is worth noting.")

    # Anomaly with percentage
    if anomalies:
        import random
        certainty = random.choice([12, 15, 18, 23, 27, 35])
        parts.append(f"The anomaly: {anomalies[0]}. I'm at {certainty}% certainty this means something.")

    # Next question
    if next_thread:
        nt = next_thread.rstrip('.')
        if len(nt) > 80:
            nt = nt[:80].rsplit(' ', 1)[0]
        parts.append(f"Next question: {nt}?")

    # Sources
    ids_to_cite = source_ids if source_ids else valid_ids[:3]
    if ids_to_cite:
        ids_str = ", ".join([f"#{id}" for id in ids_to_cite[:3]])
        parts.append(f"Sources: {ids_str}")

    response = NL.join(parts)

    return response


# =============================================================================
# MAIN QUERY PROCESSING
# =============================================================================

async def process_query(query: str, conversation_id: str = None, is_auto: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
    """Main query processing pipeline"""

    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "user", query, 1 if is_auto else 0)
            )
        except Exception as e:
            yield {"type": "error", "msg": f"Failed to save message: {str(e)}"}

    # STEP 1: Parse intent
    yield {"type": "status", "msg": "Parsing query..."}

    try:
        intent = await parse_intent_mistral(query)
    except Exception as e:
        yield {"type": "error", "msg": f"Intent parsing failed: {str(e)}"}
        yield {"type": "done"}
        return

    yield {"type": "debug", "intent": intent}

    # STEP 2: Execute SQL
    yield {"type": "status", "msg": "Searching corpus..."}

    try:
        sql_results = execute_sql_by_intent(intent, query=query, limit=10)
    except Exception as e:
        yield {"type": "error", "msg": f"Database query failed: {str(e)}"}
        yield {"type": "done"}
        return

    if not sql_results:
        no_results_msg = "Nothing in the corpus matches this query. Try: specific names, email addresses, dates (2010-2020), or keywords like 'wire transfer', 'meeting', 'flight'."
        yield {"type": "chunk", "text": no_results_msg}
        if conversation_id:
            try:
                execute_insert(
                    "sessions",
                    "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                    (conversation_id, "assistant", no_results_msg, 1 if is_auto else 0)
                )
            except:
                pass
        yield {"type": "done"}
        return

    valid_ids = [r.get("id", 0) for r in sql_results]
    yield {"type": "sources", "ids": valid_ids}

    # STEP 3: Haiku analysis
    yield {"type": "status", "msg": "Analyzing emails..."}

    try:
        haiku_analysis = await analyze_haiku(query, sql_results, valid_ids)
    except Exception as e:
        yield {"type": "error", "msg": f"Analysis failed: {str(e)}"}
        yield {"type": "done"}
        return

    yield {"type": "debug", "haiku_analysis": haiku_analysis}

    # STEP 4: Format response
    yield {"type": "status", "msg": "Formatting response..."}

    try:
        final_response = await format_response_mistral(query, haiku_analysis, valid_ids)
    except Exception as e:
        yield {"type": "error", "msg": f"Response formatting failed: {str(e)}"}
        yield {"type": "done"}
        return

    yield {"type": "chunk", "text": final_response}

    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "assistant", final_response, 1 if is_auto else 0)
            )
        except:
            pass

    # Suggestions from analysis
    suggestions = []
    if haiku_analysis.get("next_thread"):
        next_thread = haiku_analysis["next_thread"]
        if len(next_thread) < 50:
            suggestions.append(next_thread)
    if haiku_analysis.get("key_contacts"):
        for contact in haiku_analysis["key_contacts"][:2]:
            if "@" in contact:
                name = contact.split("@")[0].replace(".", " ").title()
                suggestions.append(name)
            else:
                suggestions.append(contact)
    if haiku_analysis.get("suggested_queries"):
        suggestions.extend(haiku_analysis["suggested_queries"])

    if suggestions:
        yield {"type": "suggestions", "queries": suggestions[:4]}

    yield {"type": "done", "sources": valid_ids}


# =============================================================================
# AUTO-INVESTIGATION MODE
# =============================================================================

async def auto_investigate(conversation_id: str, max_queries: int = 10) -> AsyncGenerator[Dict[str, Any], None]:
    """Auto-investigation mode with smart query generation"""

    messages = execute_query(
        "sessions",
        "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,)
    )

    if not messages:
        yield {"type": "error", "msg": "No user message found. Send a query first."}
        return

    try:
        execute_insert(
            "sessions",
            "INSERT INTO auto_sessions (conversation_id, max_queries, status) VALUES (%s, %s, 'running')",
            (conversation_id, max_queries)
        )
    except Exception as e:
        yield {"type": "error", "msg": f"Failed to create auto session: {str(e)}"}
        return

    query_count = 0
    pending_queries = []
    processed_queries = set()

    yield {"type": "auto_start", "max_queries": max_queries}

    while query_count < max_queries:
        if not pending_queries:
            recent = execute_query(
                "sessions",
                "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY created_at DESC LIMIT 4",
                (conversation_id,)
            )

            if recent:
                context = NL.join([f"{m['role']}: {m['content'][:200]}" for m in reversed(recent)])
            else:
                context = "No previous context"

            gen_prompt = f"""Based on this investigation, suggest 3 SHORT search queries (2-4 words each).

Conversation:
{context}

Rules:
- Each query must be 2-4 words MAX
- Use actual names from the conversation
- Format: "[name] emails" or "[name1] [name2]"

3 short queries:"""

            try:
                suggestions = await call_mistral(gen_prompt, max_tokens=200, temperature=0.3)

                for line in suggestions.strip().split(NL):
                    line = line.strip().lstrip('0123456789.-) ')
                    if line and len(line) > 5 and line not in processed_queries:
                        pending_queries.append(line)
            except Exception as e:
                yield {"type": "error", "msg": f"Failed to generate questions: {str(e)}"}
                break

        if not pending_queries:
            yield {"type": "auto_status", "msg": "No more queries to run"}
            break

        current_query = pending_queries.pop(0)
        processed_queries.add(current_query)
        query_count += 1

        yield {"type": "auto_query", "query": current_query, "index": query_count, "remaining": len(pending_queries)}

        async for event in process_query(current_query, conversation_id, is_auto=True):
            if event.get("type") == "suggestions":
                for q in event.get("queries", []):
                    if q not in processed_queries and q not in pending_queries:
                        pending_queries.append(q)
            yield event

        try:
            execute_update(
                "sessions",
                "UPDATE auto_sessions SET query_count = %s WHERE conversation_id = %s AND status = 'running'",
                (query_count, conversation_id)
            )
        except:
            pass

    try:
        execute_update(
            "sessions",
            "UPDATE auto_sessions SET status = 'completed', stopped_at = NOW() WHERE conversation_id = %s AND status = 'running'",
            (conversation_id,)
        )
    except:
        pass

    yield {"type": "auto_complete", "total_queries": query_count}
