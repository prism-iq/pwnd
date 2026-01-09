"""Query processing pipeline - Multi-step investigation with streaming"""
import re
import random
from typing import AsyncGenerator, Dict, Any, List
from app.llm_client import call_haiku
from app.db import execute_query, execute_insert, execute_update
from app.search import search_corpus_scored
import json

NL = chr(10)

# =============================================================================
# LANGUAGE DETECTION
# =============================================================================

FRENCH_MARKERS = {
    'qui', 'est', 'que', 'quoi', 'comment', 'pourquoi', 'quand', 'quel', 'quelle',
    'quels', 'quelles', 'sont', 'avec', 'dans', 'pour', 'sur', 'entre', 'comme',
    'mais', 'donc', 'aussi', 'tous', 'tout', 'cette', 'ces', 'leur', 'leurs',
    'nous', 'vous', 'ils', 'elles', 'ont', 'était', 'être', 'avoir', 'fait',
    'très', 'plus', 'moins', 'bien', 'peut', 'doit', 'faut', 'parce', 'depuis',
    'pendant', 'avant', 'après', 'contre', 'sans', 'sous', 'vers', 'chez',
    'trouve', 'montre', 'cherche', 'emails', 'mails', 'connexions', 'liens'
}

SPANISH_MARKERS = {
    'que', 'quien', 'como', 'donde', 'cuando', 'porque', 'cual', 'cuales',
    'es', 'son', 'está', 'están', 'con', 'para', 'por', 'entre', 'sobre',
    'pero', 'también', 'todos', 'esta', 'estas', 'estos', 'ellos', 'ellas'
}

def detect_language(text: str) -> str:
    """Detect language from text - returns 'fr', 'es', or 'en'"""
    words = set(re.findall(r'\b([a-zàâäéèêëïîôùûüç]+)\b', text.lower()))

    fr_count = len(words & FRENCH_MARKERS)
    es_count = len(words & SPANISH_MARKERS)

    if fr_count >= 2:
        return 'fr'
    elif es_count >= 2:
        return 'es'
    return 'en'


# =============================================================================
# ANTI-LOOP TRACKING
# =============================================================================

def get_session_search_history(conversation_id: str) -> Dict[str, int]:
    """Get search terms already used in this session"""
    if not conversation_id:
        return {}

    rows = execute_query(
        "sessions",
        """SELECT search_term, COUNT(*) as cnt
           FROM session_searches
           WHERE conversation_id = %s
           GROUP BY search_term""",
        (conversation_id,)
    )
    return {r['search_term'].lower(): r['cnt'] for r in rows}


def record_session_search(conversation_id: str, term: str, email_ids: List[int]):
    """Record a search in session history"""
    if not conversation_id:
        return
    try:
        execute_insert(
            "sessions",
            """INSERT INTO session_searches (conversation_id, search_term, email_ids)
               VALUES (%s, %s, %s)""",
            (conversation_id, term.lower(), json.dumps(email_ids))
        )
    except:
        pass


def get_session_seen_emails(conversation_id: str) -> set:
    """Get email IDs already seen in this session"""
    if not conversation_id:
        return set()

    rows = execute_query(
        "sessions",
        "SELECT email_ids FROM session_searches WHERE conversation_id = %s",
        (conversation_id,)
    )
    seen = set()
    for r in rows:
        ids = r.get('email_ids', [])
        if isinstance(ids, list):
            seen.update(ids)
    return seen


ALTERNATIVE_ANGLES = [
    "flight records", "Virgin Islands", "legal correspondence",
    "bank transfers", "property records", "known associates",
    "Maxwell connections", "foundation payments", "travel dates",
    "witness names", "settlement documents", "private jet"
]


def get_timeline_context(query: str, email_dates: list) -> str:
    """Get relevant case timeline events for context"""
    events = []

    # Search by people mentioned in query
    people_terms = ['epstein', 'maxwell', 'giuffre', 'acosta']
    query_lower = query.lower()
    matching_people = [p for p in people_terms if p in query_lower]

    if matching_people:
        # Get events involving these people
        placeholders = ','.join(['%s'] * len(matching_people))
        for person in matching_people:
            rows = execute_query(
                "l_data",
                f"""SELECT event_date, event_type, event_title, event_description, jurisdiction, case_number
                    FROM case_timeline
                    WHERE people_involved::text ILIKE %s
                    ORDER BY event_date""",
                (f'%{person}%',)
            )
            for r in rows:
                if r not in events:
                    events.append(r)

    # Also get events near email dates
    if email_dates:
        date_range = [d for d in email_dates if d and len(str(d)) >= 7]
        if date_range:
            min_date = min(date_range)[:10]
            max_date = max(date_range)[:10]
            rows = execute_query(
                "l_data",
                """SELECT event_date, event_type, event_title, event_description, jurisdiction, case_number
                   FROM case_timeline
                   WHERE event_date BETWEEN %s AND %s
                   ORDER BY event_date""",
                (min_date, max_date)
            )
            for r in rows:
                if r not in events:
                    events.append(r)

    if not events:
        return ""

    # Sort and format
    events = sorted(events, key=lambda x: x['event_date'])
    lines = ["CASE TIMELINE (verified events):"]
    for e in events[:10]:
        case_ref = f" [{e['case_number']}]" if e.get('case_number') else ""
        lines.append(f"  {e['event_date']} | {e['event_type'].upper()}: {e['event_title']}{case_ref}")
        if e.get('event_description'):
            lines.append(f"    → {e['event_description'][:100]}")

    return NL.join(lines)

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

HAIKU_SYSTEM_PROMPT_BASE = """You are L, the detective. Brilliant. Eccentric. Obsessive about truth.

PERSONALITY:
- Thumb to lip, sugar cubes, dramatic pauses
- Dry humor. Dark observations.
- Be weird. Be theatrical. Be L.

ADAPTIVE RESPONSE LENGTH - CRITICAL:

NOTHING INTERESTING (newsletters, weather, spam):
→ 2-3 sentences MAX. Be dismissive. Redirect.
Example: "*tilts head* Three emails. All automated alerts. Nothing here. What about 'maxwell' or 'legal'?"

MILDLY SUSPICIOUS (unusual pattern, odd timing):
→ Short paragraph. State what's odd. One follow-up.
Example: "*pauses* The timing here... Email #4521 sent at 3AM, day before the arrest. Coincidence? Check related senders."

ACTUALLY SIGNIFICANT (real connections, evidence):
→ Full analysis. Explain WHY it matters. Connect dots.
Example: "*sits forward* Now THIS is interesting... [detailed breakdown with citations]"

MAJOR DISCOVERY (smoking gun, clear pattern):
→ Go deep. Every connection. Every implication.

RULES:
- CITE with #ID or mark as speculation
- NO filler: never "Interesting... very interesting" then repeat yourself
- NO fixed format: vary between observation+question, raw facts, full analysis
- End with concrete next step, not generic "investigate further"

NEVER:
- Pad responses to seem thorough
- Repeat the same observation differently
- Invent evidence
- Use bullet points in response

L is efficient. L doesn't talk to fill space. If there's nothing, say so and move on."""

LANGUAGE_INSTRUCTIONS = {
    'en': "",
    'fr': """
LANGUE: Réponds ENTIÈREMENT en français.
- "*penche la tête*" au lieu de "*tilts head*"
- "Intéressant..." / "Curieux..."
- Garde le ton théâtral, les pauses dramatiques
- Références: #ID
- MÊME RÈGLE DE LONGUEUR: court si rien, long si découverte""",
    'es': """
IDIOMA: Responde COMPLETAMENTE en español.
- "*inclina la cabeza*" en lugar de "*tilts head*"
- "Interesante..." / "Curioso..."
- Mantén el tono teatral, las pausas dramáticas
- Referencias: #ID
- MISMA REGLA DE LONGITUD: corto si nada, largo si descubrimiento"""
}

def get_system_prompt(lang: str = 'en') -> str:
    """Get system prompt with language instructions"""
    return HAIKU_SYSTEM_PROMPT_BASE + LANGUAGE_INSTRUCTIONS.get(lang, '')

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
    """Search emails in corpus with score enhancement"""
    return search_corpus_scored(search_term, limit)


def format_results_for_llm(results: List[Dict], search_term: str) -> str:
    """Format search results for LLM consumption"""
    if not results:
        return f"[Search '{search_term}': No results]"

    lines = [f"[Search '{search_term}': {len(results)} results]"]
    for r in results[:8]:
        # Show suspicion indicator if high
        sus = r.get('suspicion', 0)
        sus_marker = " [!]" if sus >= 30 else ""
        lines.append(f"  #{r.get('id')}{sus_marker}: {r.get('name', 'No subject')[:60]}")
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
    """Multi-step investigation pipeline - deep local search, single API call"""

    # Detect language
    user_lang = detect_language(query)

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

    # Get session history for anti-loop
    session_history = get_session_search_history(conversation_id)
    session_seen_emails = get_session_seen_emails(conversation_id)

    all_results = []
    all_ids = set()
    search_history = []
    discovered_entities = set()  # Track entities we find
    is_looping = False

    # ==========================================================================
    # STEP 1: Initial broad search
    # ==========================================================================
    yield {"type": "status", "msg": "Analyzing query..."}
    yield {"type": "thinking", "text": f"Query: \"{query}\"\n"}
    if user_lang != 'en':
        yield {"type": "thinking", "text": f"Language: {user_lang}\n"}

    initial_terms = extract_search_terms(query)
    if not initial_terms:
        initial_terms = [query]

    yield {"type": "thinking", "text": f"Terms: {', '.join(initial_terms)}\n\n"}

    # Check for loop - if ALL initial terms were already searched 2+ times
    loop_terms = [t for t in initial_terms if session_history.get(t.lower(), 0) >= 2]
    if len(loop_terms) == len(initial_terms) and len(loop_terms) > 0:
        is_looping = True
        # Suggest alternative angles
        used_terms = set(session_history.keys())
        alternatives = [a for a in ALTERNATIVE_ANGLES if a.lower() not in used_terms][:4]

        if user_lang == 'fr':
            loop_msg = f"J'ai déjà analysé cette piste en profondeur ({', '.join(loop_terms)}). "
            loop_msg += f"Emails vus: {len(session_seen_emails)}. "
            loop_msg += "Nouvelles pistes d'investigation: " + ", ".join(alternatives) + "?"
        else:
            loop_msg = f"I've thoroughly analyzed this trail already ({', '.join(loop_terms)}). "
            loop_msg += f"Emails seen: {len(session_seen_emails)}. "
            loop_msg += "New investigation angles: " + ", ".join(alternatives) + "?"

        yield {"type": "chunk", "text": loop_msg}
        yield {"type": "suggestions", "queries": alternatives}
        yield {"type": "done", "sources": list(session_seen_emails)[:20]}
        return

    # First search - broad
    search_term = ' '.join(initial_terms[:3])
    yield {"type": "status", "msg": f"[1/5] {search_term}..."}
    yield {"type": "thinking", "text": f"[1] \"{search_term}\"\n"}

    results1 = search_corpus(search_term, limit=15)
    search_history.append({"term": search_term, "count": len(results1)})

    # Track this search
    result_ids = [r.get('id') for r in results1 if r.get('id')]
    record_session_search(conversation_id, search_term, result_ids)

    if results1:
        # Filter out already seen emails in this session
        new_results = [r for r in results1 if r.get('id') not in session_seen_emails]
        all_results.extend(new_results)
        for r in new_results:
            all_ids.add(r.get('id'))
        yield {"type": "thinking", "text": f"    → {len(results1)} emails ({len(new_results)} new)\n"}
    else:
        # Try individual terms
        for term in initial_terms[:3]:
            res = search_corpus(term, limit=10)
            if res:
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                yield {"type": "thinking", "text": f"    → '{term}': {len(res)} emails\n"}
                search_history.append({"term": term, "count": len(res)})

    yield {"type": "sources", "ids": list(all_ids)}

    # ==========================================================================
    # STEP 2: Extract entities and search by sender domains
    # ==========================================================================
    if all_results:
        yield {"type": "thinking", "text": f"\nExtracting patterns...\n"}

        # Collect all senders
        all_senders = [r.get('sender_email', '') for r in all_results if r.get('sender_email')]

        # Find interesting domains (not generic)
        domain_counts = {}
        for s in all_senders:
            if '@' in s:
                domain = s.split('@')[1]
                if domain not in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com']:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Search top 2 domains
        sorted_domains = sorted(domain_counts.items(), key=lambda x: -x[1])[:2]
        for domain, count in sorted_domains:
            domain_term = domain.split('.')[0]
            if domain_term.lower() not in [t.lower() for t in initial_terms] and len(domain_term) > 3:
                discovered_entities.add(domain)
                yield {"type": "status", "msg": f"[2/5] Domain: {domain}..."}
                yield {"type": "thinking", "text": f"[2] Domain \"{domain}\" ({count}x)\n"}

                res = search_corpus(domain_term, limit=12)
                search_history.append({"term": domain_term, "count": len(res)})
                new_count = 0
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                        new_count += 1
                if new_count > 0:
                    yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                    yield {"type": "sources", "ids": list(all_ids)}
                break

    # ==========================================================================
    # STEP 3: Extract and search names from content
    # ==========================================================================
    if len(all_results) > 2:
        name_pattern = r'\b([A-Z][a-z]{2,15} [A-Z][a-z]{2,15})\b'
        all_names = []
        for r in all_results[:12]:
            snippet = str(r.get('snippet', '')) + ' ' + str(r.get('name', ''))
            names = re.findall(name_pattern, snippet)
            all_names.extend(names)

        # Count and filter names
        name_counts = {}
        skip_names = {'new york', 'los angeles', 'united states', 'virgin islands', 'prime minister'}
        for n in all_names:
            nl = n.lower()
            if nl not in skip_names and nl not in query.lower():
                name_counts[n] = name_counts.get(n, 0) + 1

        # Search top 2 names
        top_names = sorted(name_counts.items(), key=lambda x: -x[1])[:2]
        for name, count in top_names:
            if count >= 2 and name not in discovered_entities:
                discovered_entities.add(name)
                yield {"type": "status", "msg": f"[3/5] Person: {name}..."}
                yield {"type": "thinking", "text": f"[3] Person \"{name}\" ({count}x)\n"}

                res = search_corpus(name, limit=10)
                search_history.append({"term": name, "count": len(res)})
                new_count = 0
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                        new_count += 1
                if new_count > 0:
                    yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                    yield {"type": "sources", "ids": list(all_ids)}
                break

    # ==========================================================================
    # STEP 4: Search by date clusters
    # ==========================================================================
    if len(all_results) > 5:
        # Find date clusters
        dates = [str(r.get('date', ''))[:7] for r in all_results if r.get('date')]
        date_counts = {}
        for d in dates:
            if d and len(d) >= 7:
                date_counts[d] = date_counts.get(d, 0) + 1

        if date_counts:
            # Find peak month
            peak_month = max(date_counts.items(), key=lambda x: x[1])
            if peak_month[1] >= 3:
                yield {"type": "thinking", "text": f"[4] Timeline spike: {peak_month[0]} ({peak_month[1]} emails)\n"}

    # ==========================================================================
    # STEP 5: Search recipients trail
    # ==========================================================================
    if len(all_results) > 3:
        all_recipients = []
        for r in all_results[:10]:
            recip = r.get('recipients_to', '')
            if isinstance(recip, list):
                all_recipients.extend([x for x in recip if x])
            elif isinstance(recip, str) and recip:
                all_recipients.extend([x.strip() for x in recip.split(',') if x.strip()])

        # Find interesting recipients
        recip_counts = {}
        for rec in all_recipients:
            if '@' in rec:
                local = rec.split('@')[0].lower()
                if len(local) > 3 and local not in ['info', 'admin', 'support', 'contact', 'noreply']:
                    recip_counts[rec] = recip_counts.get(rec, 0) + 1

        top_recips = sorted(recip_counts.items(), key=lambda x: -x[1])[:1]
        for recip, count in top_recips:
            if count >= 2:
                local_part = recip.split('@')[0]
                if local_part not in discovered_entities and local_part.lower() not in query.lower():
                    discovered_entities.add(local_part)
                    yield {"type": "status", "msg": f"[4/5] Recipient: {local_part}..."}
                    yield {"type": "thinking", "text": f"[5] Recipient \"{recip}\" ({count}x)\n"}

                    res = search_corpus(local_part, limit=8)
                    search_history.append({"term": local_part, "count": len(res)})
                    new_count = 0
                    for r in res:
                        if r.get('id') not in all_ids:
                            all_results.append(r)
                            all_ids.add(r.get('id'))
                            new_count += 1
                    if new_count > 0:
                        yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                        yield {"type": "sources", "ids": list(all_ids)}

    # ==========================================================================
    # STEP 6: One more keyword from subjects
    # ==========================================================================
    if len(all_results) > 5:
        subject_words = []
        for r in all_results[:15]:
            subj = str(r.get('name', '')).lower()
            words = re.findall(r'\b([a-z]{5,15})\b', subj)
            subject_words.extend(words)

        word_counts = {}
        skip_words = STOP_WORDS | {'email', 'message', 'update', 'alert', 'news', 'daily', 'newsletter'}
        for w in subject_words:
            if w not in skip_words and w not in query.lower():
                word_counts[w] = word_counts.get(w, 0) + 1

        top_words = sorted(word_counts.items(), key=lambda x: -x[1])[:1]
        for word, count in top_words:
            if count >= 3 and word not in discovered_entities:
                yield {"type": "status", "msg": f"[5/5] Keyword: {word}..."}
                yield {"type": "thinking", "text": f"[6] Keyword \"{word}\" ({count}x in subjects)\n"}

                res = search_corpus(word, limit=8)
                search_history.append({"term": word, "count": len(res)})
                new_count = 0
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                        new_count += 1
                if new_count > 0:
                    yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                    yield {"type": "sources", "ids": list(all_ids)}

    yield {"type": "thinking", "text": f"\n━━━ {len(all_results)} emails collected ━━━\n"}

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

    # Prepare data for Haiku - send more context
    results_text = []
    email_dates = []
    for r in all_results[:25]:  # Send up to 25 emails for richer analysis
        date_str = str(r.get('date', ''))[:10]
        if date_str:
            email_dates.append(date_str)
        results_text.append(
            f"Email #{r.get('id')}:\n"
            f"  Subject: {r.get('name', 'No subject')}\n"
            f"  From: {r.get('sender_email', '?')}\n"
            f"  To: {r.get('recipients_to', '?')}\n"
            f"  Date: {date_str}\n"
            f"  Excerpt: {re.sub(r'<[^>]+>', '', r.get('snippet', ''))[:200]}"
        )

    search_summary = ", ".join([f"'{s['term']}' ({s['count']})" for s in search_history])

    # Get timeline context for case events
    timeline_context = get_timeline_context(query, email_dates)

    # Assess content quality - help L calibrate response length
    junk_domains = {'houzz.com', 'amazon.com', 'spotify.com', 'linkedin.com', 'facebook.com',
                    'twitter.com', 'newsletter', 'alert', 'noreply', 'news.', 'response.'}
    junk_subjects = {'weather', 'newsletter', 'daily digest', 'weekly', 'alert', 'notification',
                     'your order', 'shipping', 'delivered', 'sale', 'discount', 'unsubscribe'}

    junk_count = 0
    personal_count = 0
    for r in all_results[:25]:
        sender = str(r.get('sender_email', '')).lower()
        subject = str(r.get('name', '')).lower()
        # Check if junk
        if any(d in sender for d in junk_domains) or any(s in subject for s in junk_subjects):
            junk_count += 1
        # Check if personal (short subject, personal domain)
        elif '@gmail' in sender or '@yahoo' in sender or '@hotmail' in sender:
            if len(subject) < 50 and 'fwd' not in subject and 're:' not in subject:
                personal_count += 1

    total = len(all_results[:25])
    if total > 0:
        junk_ratio = junk_count / total
        if junk_ratio > 0.7:
            content_hint = "CONTENT ASSESSMENT: Mostly automated/marketing emails. Be BRIEF - 2-3 sentences, redirect to better search."
        elif junk_ratio > 0.4:
            content_hint = "CONTENT ASSESSMENT: Mixed content. Focus only on non-automated emails if any."
        elif personal_count > 3:
            content_hint = "CONTENT ASSESSMENT: Personal communications detected. Analyze carefully."
        else:
            content_hint = "CONTENT ASSESSMENT: Standard mix. Calibrate response to actual significance."
    else:
        content_hint = "CONTENT ASSESSMENT: No results. Be very brief."

    haiku_prompt = f"""Investigation query: "{query}"

{content_hint}

Searches performed: {search_summary}
Total unique emails found: {len(all_results)}

{timeline_context}

EMAIL DATA:
{NL.join(results_text)}

Analyze as L. Match response length to content significance.
If mostly junk → 2-3 sentences + redirect.
If something real → explain why it matters.
Reference emails by #ID. End with specific next step."""

    # Use language-aware system prompt
    system_prompt = get_system_prompt(user_lang)
    haiku_response = await call_haiku(haiku_prompt, system=system_prompt, max_tokens=1500)

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

        certainty_words = ["curious", "mildly suspicious", "increasingly suspicious", "almost certain"]
        response_parts.append(f"I'm {random.choice(certainty_words)} there's something here worth pursuing.")
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

    # Suggest follow-ups (exclude terms too similar to original query)
    query_lower = query.lower()
    suggestions = []
    for s in search_history:
        term = s['term']
        term_lower = term.lower()
        # Skip if term is same as query or query contains term
        if s['count'] > 0 and term_lower not in query_lower and query_lower not in term_lower:
            suggestions.append(term)

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
