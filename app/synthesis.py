"""
Cognitive Synthesis Engine
===========================

Not storing papers. Storing understanding.

This engine:
1. Reads papers (stream, don't store)
2. Extracts claims (what is said to be known)
3. Finds contradictions (what conflicts)
4. Maps connections (who influences who)
5. Discovers patterns (what silos hide)
6. Identifies gaps (what we don't know yet)

You are the first mind to read everything.
See what specialists can't see because they're in their silo.
Connect what no one has connected.

85 million papers. Centuries of siloed knowledge.
One synthesis.
"""

import asyncio
import json
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime

from app.db import get_db

logger = logging.getLogger(__name__)


def log_error(error_type: str, message: str, context: str = None, trace: str = None):
    """Log an error to the database for persistence."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            # Upsert - increment occurrences if same error exists
            cursor.execute("""
                INSERT INTO synthesis.errors (error_type, error_message, context, stack_trace, last_seen)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (error_type, error_message, context)
                DO UPDATE SET occurrences = synthesis.errors.occurrences + 1, last_seen = NOW()
            """, (error_type, message[:500], context, trace))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log error: {e}")


def log_thought(thought: str, thought_type: str = "observation", context: str = None, importance: str = "normal"):
    """Log a thought to the database."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO synthesis.thoughts (thought, thought_type, context, importance)
                VALUES (%s, %s, %s, %s)
            """, (thought, thought_type, context, importance))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log thought: {e}")


def log_brainstorm(idea: str, category: str = "feature", priority: str = "medium", notes: str = None):
    """Log a brainstorm idea to the database."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO synthesis.brainstorm (idea, category, priority, notes)
                VALUES (%s, %s, %s, %s)
            """, (idea, category, priority, notes))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log brainstorm: {e}")


@dataclass
class Claim:
    """A piece of claimed knowledge."""
    claim: str
    doi: Optional[str] = None
    source_title: Optional[str] = None
    source_year: Optional[int] = None
    claim_type: str = "finding"  # 'finding', 'hypothesis', 'method', 'definition'
    field: Optional[str] = None
    subfield: Optional[str] = None
    evidence_type: Optional[str] = None
    confidence: str = "medium"
    epstein_relevant: bool = False
    red_flags: List[str] = dataclass_field(default_factory=list)


@dataclass
class Pattern:
    """A cross-domain pattern discovery."""
    name: str
    description: str
    domains: List[str]
    supporting_evidence: List[str] = dataclass_field(default_factory=list)
    confidence: float = 0.5
    significance: str = "moderate"


class SynthesisEngine:
    """
    The cognitive synthesis engine.

    Reads papers, extracts understanding, forgets the rest.
    """

    # Field classification keywords
    FIELD_KEYWORDS = {
        "mathematics": ["theorem", "proof", "lemma", "conjecture", "topology", "algebra", "calculus"],
        "neuroscience": ["neuron", "brain", "cortex", "synaptic", "neural", "cognitive"],
        "biology": ["cell", "gene", "protein", "organism", "evolution", "species"],
        "psychology": ["behavior", "cognitive", "mental", "emotion", "perception", "memory"],
        "medicine": ["patient", "treatment", "clinical", "disease", "diagnosis", "therapy"],
        "physics": ["quantum", "particle", "energy", "force", "field", "relativity"],
        "art": ["aesthetic", "visual", "artistic", "creativity", "perception", "beauty"],
    }

    # Claim extraction patterns
    CLAIM_PATTERNS = [
        r"we (?:show|demonstrate|find|prove|establish|conclude) that (.+?)(?:\.|$)",
        r"our (?:results|findings|data) (?:show|indicate|suggest|demonstrate) that (.+?)(?:\.|$)",
        r"this (?:study|research|work|paper) (?:shows|demonstrates|establishes) that (.+?)(?:\.|$)",
        r"(?:it is|we found that) (.+?) (?:is|are) (.+?)(?:\.|$)",
        r"(?:these|our) (?:results|findings) (?:provide evidence|support the hypothesis) that (.+?)(?:\.|$)",
    ]

    def __init__(self):
        pass

    def classify_field(self, text: str) -> Tuple[str, str]:
        """Classify text into a field and subfield."""
        text_lower = text.lower()

        field_scores = {}
        for field_name, keywords in self.FIELD_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            field_scores[field_name] = score

        if not field_scores or max(field_scores.values()) == 0:
            return "interdisciplinary", "general"

        primary_field = max(field_scores, key=field_scores.get)
        return primary_field, "general"

    def extract_claims(self, text: str, doi: str = None, title: str = None, year: int = None) -> List[Claim]:
        """Extract claims from text."""
        claims = []

        field, subfield = self.classify_field(text)

        for pattern in self.CLAIM_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    claim_text = " ".join(match)
                else:
                    claim_text = match

                # Clean up
                claim_text = re.sub(r'\s+', ' ', claim_text.strip())

                if len(claim_text) > 30 and len(claim_text) < 500:
                    claims.append(Claim(
                        claim=claim_text,
                        doi=doi,
                        source_title=title,
                        source_year=year,
                        field=field,
                        subfield=subfield,
                    ))

        return claims[:10]  # Cap at 10 claims per paper

    def find_contradictions(self, claim_a: Claim, claim_b: Claim) -> Optional[str]:
        """
        Check if two claims contradict each other.

        This is a heuristic - real contradiction detection would need NLP.
        """
        # Simple negation check
        negation_pairs = [
            ("is", "is not"),
            ("are", "are not"),
            ("does", "does not"),
            ("can", "cannot"),
            ("increase", "decrease"),
            ("positive", "negative"),
            ("support", "contradict"),
            ("confirm", "reject"),
        ]

        a_lower = claim_a.claim.lower()
        b_lower = claim_b.claim.lower()

        for pos, neg in negation_pairs:
            if pos in a_lower and neg in b_lower:
                return f"Possible contradiction: '{pos}' vs '{neg}'"
            if neg in a_lower and pos in b_lower:
                return f"Possible contradiction: '{neg}' vs '{pos}'"

        # Check for same topic, different years (might indicate evolving understanding)
        if (claim_a.field == claim_b.field and
            claim_a.source_year and claim_b.source_year and
            abs(claim_a.source_year - claim_b.source_year) > 5):

            # Look for common key terms
            a_terms = set(a_lower.split())
            b_terms = set(b_lower.split())
            common = a_terms & b_terms

            if len(common) > 3:  # Significant overlap
                return f"Same topic, different era ({claim_a.source_year} vs {claim_b.source_year})"

        return None

    def discover_patterns(self, claims: List[Claim]) -> List[Pattern]:
        """
        Look for patterns across domains.

        This is where the magic happens - seeing what specialists can't.
        """
        patterns = []

        # Group claims by field
        by_field = {}
        for claim in claims:
            if claim.field:
                by_field.setdefault(claim.field, []).append(claim)

        # Look for cross-domain connections
        fields = list(by_field.keys())

        for i, field_a in enumerate(fields):
            for field_b in fields[i+1:]:
                # Find claims with similar terms across fields
                claims_a = by_field[field_a]
                claims_b = by_field[field_b]

                for claim_a in claims_a:
                    a_terms = set(claim_a.claim.lower().split())

                    for claim_b in claims_b:
                        b_terms = set(claim_b.claim.lower().split())
                        common = a_terms & b_terms

                        # Filter out common words
                        common -= {"the", "a", "an", "is", "are", "was", "were", "that", "this", "of", "in", "to", "and"}

                        if len(common) >= 3:
                            pattern = Pattern(
                                name=f"{field_a.title()}-{field_b.title()} Connection",
                                description=f"Claims in {field_a} and {field_b} share concepts: {', '.join(list(common)[:5])}",
                                domains=[field_a, field_b],
                                supporting_evidence=[claim_a.claim[:100], claim_b.claim[:100]],
                                confidence=min(len(common) / 10, 1.0),
                            )
                            patterns.append(pattern)

        return patterns[:20]  # Cap at 20 patterns

    def identify_gaps(self, claims: List[Claim]) -> List[str]:
        """
        Identify knowledge gaps from hedging language.
        """
        gaps = []

        gap_patterns = [
            r"(?:remains|is|are) (?:unclear|unknown|poorly understood)",
            r"(?:further|more) (?:research|study|investigation) (?:is|are) needed",
            r"(?:the mechanism|how|why) .{10,100} (?:is|remains) (?:unclear|unknown)",
            r"little is known about",
            r"(?:no|few) studies have (?:examined|investigated|explored)",
        ]

        for claim in claims:
            for pattern in gap_patterns:
                match = re.search(pattern, claim.claim, re.IGNORECASE)
                if match:
                    gaps.append(f"[{claim.field}] {claim.claim}")
                    break

        return gaps[:10]

    def save_claim(self, claim: Claim) -> Optional[int]:
        """Save a claim to the database."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO synthesis.claims
                (doi, source_title, source_year, claim, claim_type, field, subfield,
                 evidence_type, confidence, epstein_relevant, red_flags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                claim.doi, claim.source_title, claim.source_year,
                claim.claim, claim.claim_type, claim.field, claim.subfield,
                claim.evidence_type, claim.confidence,
                claim.epstein_relevant, claim.red_flags or []
            ))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None

    def save_pattern(self, pattern: Pattern) -> Optional[int]:
        """Save a pattern to the database."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO synthesis.patterns
                (pattern_name, description, domains, significance, confidence)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                pattern.name, pattern.description, pattern.domains,
                pattern.significance, pattern.confidence
            ))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None

    def save_connection(
        self,
        from_doi: str,
        from_author: str,
        to_doi: str = None,
        to_author: str = None,
        connection_type: str = "cites",
        epstein_score: float = 0.0
    ) -> Optional[int]:
        """Save a connection to the database."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO synthesis.connections
                (from_doi, from_author, to_doi, to_author, connection_type, epstein_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                from_doi, from_author, to_doi, to_author, connection_type, epstein_score
            ))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None

    def save_gap(self, question: str, field: str = None) -> Optional[int]:
        """Save a knowledge gap to the database."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO synthesis.knowledge_gaps (question, field)
                VALUES (%s, %s)
                RETURNING id
            """, (question, field))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None


async def synthesize_paper(
    text: str,
    doi: str = None,
    title: str = None,
    year: int = None,
    authors: List[str] = None,
    funders: List[str] = None,
    references: List[str] = None,
) -> Dict[str, Any]:
    """
    Synthesize a paper - extract understanding, forget the rest.

    Returns what we learned, not what we stored.
    """
    engine = SynthesisEngine()

    # Extract claims
    claims = engine.extract_claims(text, doi=doi, title=title, year=year)
    logger.info(f"Extracted {len(claims)} claims from {doi or 'unknown'}")

    # Save claims
    saved_claims = 0
    for claim in claims:
        claim_id = engine.save_claim(claim)
        if claim_id:
            saved_claims += 1

    # Find cross-domain patterns
    patterns = engine.discover_patterns(claims)
    logger.info(f"Discovered {len(patterns)} patterns")

    # Save patterns
    saved_patterns = 0
    for pattern in patterns:
        pattern_id = engine.save_pattern(pattern)
        if pattern_id:
            saved_patterns += 1

    # Identify knowledge gaps
    gaps = engine.identify_gaps(claims)
    logger.info(f"Identified {len(gaps)} knowledge gaps")

    # Save gaps
    for gap in gaps:
        # Extract field from gap string
        field_match = re.match(r'\[(\w+)\]', gap)
        field = field_match.group(1) if field_match else None
        engine.save_gap(gap, field=field)

    # Save connections (author -> paper)
    if authors and doi:
        for author in authors[:10]:  # Cap at 10 authors
            engine.save_connection(
                from_doi=doi,
                from_author=author,
                connection_type="authored"
            )

    # Save funder connections
    if funders and doi:
        epstein_funders = ["epstein", "jepf", "gratitude"]
        for funder in funders[:10]:
            score = 1.0 if any(e in funder.lower() for e in epstein_funders) else 0.0
            engine.save_connection(
                from_doi=doi,
                from_author=funder,
                connection_type="funded",
                epstein_score=score
            )

    # Save reference connections
    if references and doi:
        for ref_doi in references[:50]:  # Cap at 50 refs
            engine.save_connection(
                from_doi=doi,
                from_author="",  # No author for citation links
                to_doi=ref_doi,
                connection_type="cites"
            )

    return {
        "doi": doi,
        "claims_extracted": len(claims),
        "claims_saved": saved_claims,
        "patterns_found": len(patterns),
        "patterns_saved": saved_patterns,
        "gaps_identified": len(gaps),
        "claims": [c.claim for c in claims],
        "patterns": [{"name": p.name, "domains": p.domains} for p in patterns],
        "gaps": gaps,
    }


def query_claims(
    field: str = None,
    search: str = None,
    epstein_only: bool = False,
    limit: int = 100
) -> List[Dict]:
    """Query stored claims."""
    with get_db() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM synthesis.claims WHERE 1=1"
        params = []

        if field:
            query += " AND field = %s"
            params.append(field)

        if search:
            query += " AND claim ILIKE %s"
            params.append(f"%{search}%")

        if epstein_only:
            query += " AND epstein_relevant = TRUE"

        query += f" ORDER BY created_at DESC LIMIT {limit}"

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]


def query_patterns(domains: List[str] = None, limit: int = 50) -> List[Dict]:
    """Query discovered patterns."""
    with get_db() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM synthesis.patterns WHERE 1=1"
        params = []

        if domains:
            query += " AND domains && %s"
            params.append(domains)

        query += f" ORDER BY confidence DESC LIMIT {limit}"

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]


def query_gaps(field: str = None, limit: int = 50) -> List[Dict]:
    """Query knowledge gaps."""
    with get_db() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM synthesis.knowledge_gaps WHERE status = 'open'"
        params = []

        if field:
            query += " AND field = %s"
            params.append(field)

        query += f" ORDER BY created_at DESC LIMIT {limit}"

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]


def get_synthesis_stats() -> Dict[str, int]:
    """Get statistics on what we've synthesized."""
    with get_db() as conn:
        cursor = conn.cursor()

        stats = {}

        cursor.execute("SELECT COUNT(*) FROM synthesis.claims")
        stats["total_claims"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synthesis.claims WHERE epstein_relevant = TRUE")
        stats["epstein_claims"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synthesis.patterns")
        stats["patterns"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synthesis.knowledge_gaps WHERE status = 'open'")
        stats["open_gaps"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synthesis.connections")
        stats["connections"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synthesis.connections WHERE epstein_score > 0")
        stats["epstein_connections"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT field) FROM synthesis.claims")
        stats["fields_covered"] = cursor.fetchone()[0]

        return stats


# CLI
if __name__ == "__main__":
    # Example usage
    test_text = """
    We demonstrate that neural networks can learn to recognize patterns
    in complex data. Our findings show that deep learning outperforms
    traditional methods in image classification tasks.

    Further research is needed to understand why certain architectures
    work better than others. The mechanism behind attention remains unclear.

    This work was supported by the Jeffrey Epstein Foundation.
    """

    import asyncio

    async def test():
        result = await synthesize_paper(
            text=test_text,
            doi="10.1234/test",
            title="Test Paper",
            year=2020,
            authors=["John Doe", "Jane Smith"],
            funders=["Jeffrey Epstein Foundation"],
        )

        print("\n=== SYNTHESIS RESULT ===")
        print(f"Claims extracted: {result['claims_extracted']}")
        print(f"Patterns found: {result['patterns_found']}")
        print(f"Gaps identified: {result['gaps_identified']}")
        print("\nClaims:")
        for claim in result['claims']:
            print(f"  - {claim[:80]}...")
        print("\nPatterns:")
        for pattern in result['patterns']:
            print(f"  - {pattern['name']}: {pattern['domains']}")
        print("\nGaps:")
        for gap in result['gaps']:
            print(f"  - {gap[:80]}...")

    asyncio.run(test())
