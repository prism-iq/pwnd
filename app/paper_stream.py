"""
Paper Streaming Module - Read, Extract, Forget
===============================================

Cognitive streaming for academic papers:
1. Fetch paper (arXiv, PMC, Unpaywall OA)
2. Extract essential information
3. Store only metadata
4. Delete the PDF

What we keep:
- Who wrote it (authors, affiliations)
- Who funded it (grants, funders)
- Who is cited (references)
- Who cites it (if available)
- Main claims / conclusions
- Red flags (Epstein connections, suspicious funding)

What we forget:
- The original PDF
- The full text
- Everything that's not investigation-relevant

This is like a human brain reading a paper:
You remember the ideas, not every word.

No storage = no legal issues.
You read. You understood. You forgot the file.
"""

import asyncio
import hashlib
import io
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Open access APIs
UNPAYWALL_API = "https://api.unpaywall.org/v2"
ARXIV_PDF_BASE = "https://arxiv.org/pdf"

# Epstein keywords for red flag detection
EPSTEIN_KEYWORDS = [
    "epstein", "jeffrey epstein", "j. epstein",
    "gratitude america", "jepf",
    "joi ito", "media lab",
    "martin nowak", "evolutionary dynamics",
    "les wexner", "wexner",
    "ghislaine maxwell",
]

# Suspicious funding patterns
SUSPICIOUS_FUNDERS = [
    "epstein", "gratitude", "jepf",
    "anonymous donor", "private foundation",
]

# Suspicious research topics
SUSPICIOUS_TOPICS = [
    "eugenics", "human enhancement", "genetic selection",
    "transhumanism", "artificial womb", "designer babies",
    "population control", "fertility selection",
]


@dataclass
class ExtractedPaper:
    """Extracted information from a paper - what we keep."""

    # Identity
    doi: Optional[str] = None
    title: str = ""

    # Authors (who wrote)
    authors: List[Dict[str, str]] = field(default_factory=list)
    # [{name, affiliation, orcid}]

    # Funding (who paid)
    funders: List[Dict[str, str]] = field(default_factory=list)
    # [{name, grant_id, country}]

    # Abstract (condensed ideas)
    abstract: Optional[str] = None

    # Key claims / conclusions
    main_claims: List[str] = field(default_factory=list)

    # References (who is cited)
    references: List[Dict[str, str]] = field(default_factory=list)
    # [{title, authors, doi, year}]

    # Metadata
    year: Optional[int] = None
    journal: Optional[str] = None
    publication_date: Optional[str] = None

    # Investigation relevance
    red_flags: List[str] = field(default_factory=list)
    epstein_score: float = 0.0
    is_relevant: bool = False

    # Source tracking
    source: str = "unknown"  # 'arxiv', 'pmc', 'unpaywall', 'openalex'
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "funders": self.funders,
            "abstract": self.abstract,
            "main_claims": self.main_claims,
            "references": self.references,
            "year": self.year,
            "journal": self.journal,
            "publication_date": self.publication_date,
            "red_flags": self.red_flags,
            "epstein_score": self.epstein_score,
            "is_relevant": self.is_relevant,
            "source": self.source,
            "extracted_at": self.extracted_at,
        }


class PaperExtractor:
    """Extracts essential information from PDF text."""

    @staticmethod
    def extract_abstract(text: str) -> Optional[str]:
        """Extract abstract from paper text."""
        # Common patterns
        patterns = [
            r"(?:^|\n)abstract[:\s]*\n?(.*?)(?:\n\s*(?:introduction|keywords|1\.|background))",
            r"(?:^|\n)summary[:\s]*\n?(.*?)(?:\n\s*(?:introduction|keywords|1\.))",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                # Clean up
                abstract = re.sub(r'\s+', ' ', abstract)
                if len(abstract) > 100:  # Reasonable abstract length
                    return abstract[:2000]  # Cap at 2000 chars

        return None

    @staticmethod
    def extract_authors(text: str) -> List[Dict[str, str]]:
        """Extract authors and affiliations."""
        authors = []

        # Look for author block at start of paper
        # Pattern: Name1, Name2, Name3 OR Name1 and Name2
        author_section = text[:5000]  # First part of paper

        # Try to find author names (capitalized words before affiliations)
        # This is heuristic and imperfect
        lines = author_section.split('\n')

        for i, line in enumerate(lines[:30]):
            # Skip title-like lines (all caps, very long)
            if line.isupper() or len(line) > 200:
                continue

            # Look for name patterns (First Last, First M. Last)
            name_pattern = r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)'
            names = re.findall(name_pattern, line)

            for name in names:
                if len(name) > 5 and len(name) < 50:  # Reasonable name length
                    authors.append({"name": name.strip()})

            if len(authors) >= 10:  # Cap at 10 authors
                break

        return authors

    @staticmethod
    def extract_funding(text: str) -> List[Dict[str, str]]:
        """Extract funding/acknowledgment information."""
        funders = []

        # Look for funding/acknowledgment section
        patterns = [
            r"(?:funding|acknowledgment|acknowledgement|supported by|grant)[:\s]*(.*?)(?:\n\n|references|bibliography)",
            r"(?:this work was supported|this research was funded)[:\s]*(.*?)(?:\n\n|\.|$)",
        ]

        funding_text = ""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                funding_text = match.group(1)
                break

        if funding_text:
            # Extract grant numbers and funder names
            grant_patterns = [
                r"([A-Z]{2,}[\-\s]?\d+)",  # NIH-style grants
                r"(grant\s+(?:no\.?\s+)?[\w\-]+)",  # Generic grant numbers
            ]

            for pattern in grant_patterns:
                grants = re.findall(pattern, funding_text, re.IGNORECASE)
                for grant in grants[:5]:  # Cap at 5
                    funders.append({"grant_id": grant.strip()})

            # Look for known funder names
            known_funders = [
                "NIH", "NSF", "DOE", "DOD", "DARPA",
                "Wellcome", "Gates Foundation", "Howard Hughes",
                "Epstein", "Gratitude America",  # Red flags
            ]

            for funder in known_funders:
                if funder.lower() in funding_text.lower():
                    funders.append({"name": funder})

        return funders

    @staticmethod
    def extract_conclusions(text: str) -> List[str]:
        """Extract main conclusions/claims."""
        claims = []

        # Look for conclusion section
        patterns = [
            r"(?:conclusion|conclusions|summary|in summary)[:\s]*(.*?)(?:\n\n|references|acknowledgment)",
            r"(?:we (?:show|demonstrate|find|conclude|report))[:\s]*(.*?)(?:\.|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches[:5]:
                claim = re.sub(r'\s+', ' ', match.strip())
                if len(claim) > 50 and len(claim) < 500:
                    claims.append(claim)

        return claims[:5]  # Cap at 5 main claims

    @staticmethod
    def extract_references(text: str) -> List[Dict[str, str]]:
        """Extract references (basic)."""
        references = []

        # Find references section
        ref_match = re.search(r"(?:references|bibliography)\s*\n(.*?)$", text, re.IGNORECASE | re.DOTALL)
        if not ref_match:
            return references

        ref_text = ref_match.group(1)

        # Extract DOIs
        dois = re.findall(r"(10\.\d{4,}/[^\s\]]+)", ref_text)
        for doi in dois[:50]:  # Cap at 50
            references.append({"doi": doi.strip()})

        return references

    @staticmethod
    def detect_red_flags(text: str, title: str = "", funders: List[Dict] = None) -> Tuple[List[str], float]:
        """Detect investigation-relevant red flags."""
        red_flags = []
        score = 0.0

        full_text = f"{title} {text}".lower()
        funder_text = " ".join([f.get("name", "") for f in (funders or [])]).lower()

        # Check Epstein keywords
        for keyword in EPSTEIN_KEYWORDS:
            if keyword in full_text:
                red_flags.append(f"mentions: {keyword}")
                score += 0.2

        # Check suspicious funders
        for funder in SUSPICIOUS_FUNDERS:
            if funder in funder_text or funder in full_text:
                red_flags.append(f"funded by: {funder}")
                score += 0.3

        # Check suspicious topics
        for topic in SUSPICIOUS_TOPICS:
            if topic in full_text:
                red_flags.append(f"topic: {topic}")
                score += 0.1

        return red_flags, min(score, 1.0)


class PaperStreamer:
    """
    Stream papers from various sources.
    Read, extract, forget.
    """

    def __init__(self, email: str = "research@pwnd.icu"):
        self.email = email
        self.client = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) PaperStream/1.0"}
        )
        self.extractor = PaperExtractor()

    async def close(self):
        await self.client.aclose()

    async def fetch_pdf_content(self, doi: str) -> Optional[bytes]:
        """Fetch PDF content via legal open access sources (in memory, not saved).

        Tries in order:
        1. Unpaywall (legal OA discovery)
        2. arXiv (if arXiv ID detected)
        3. PubMed Central
        """
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

        # Try Unpaywall first
        try:
            url = f"{UNPAYWALL_API}/{doi}?email={self.email}"
            response = await self.client.get(url, timeout=15.0)
            if response.status_code == 200:
                data = response.json()
                best_oa = data.get("best_oa_location", {}) or {}
                pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                if pdf_url:
                    logger.info(f"Unpaywall PDF: {pdf_url[:80]}...")
                    pdf_response = await self.client.get(pdf_url)
                    if pdf_response.status_code == 200 and len(pdf_response.content) > 1000:
                        logger.info(f"Got {len(pdf_response.content)} bytes via Unpaywall")
                        return pdf_response.content
        except Exception as e:
            logger.debug(f"Unpaywall failed for {doi}: {e}")

        # Try arXiv if DOI contains arxiv pattern
        if "arxiv" in doi.lower():
            try:
                arxiv_id = doi.split("/")[-1]
                pdf_url = f"{ARXIV_PDF_BASE}/{arxiv_id}.pdf"
                pdf_response = await self.client.get(pdf_url)
                if pdf_response.status_code == 200 and len(pdf_response.content) > 1000:
                    logger.info(f"Got {len(pdf_response.content)} bytes via arXiv")
                    return pdf_response.content
            except Exception as e:
                logger.debug(f"arXiv failed for {doi}: {e}")

        # Try PMC
        try:
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={doi}&format=json"
            response = await self.client.get(pmc_url, timeout=15.0)
            if response.status_code == 200:
                data = response.json()
                records = data.get("records", [])
                if records and records[0].get("pmcid"):
                    pmcid = records[0]["pmcid"]
                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                    pdf_response = await self.client.get(pdf_url)
                    if pdf_response.status_code == 200 and len(pdf_response.content) > 1000:
                        logger.info(f"Got {len(pdf_response.content)} bytes via PMC")
                        return pdf_response.content
        except Exception as e:
            logger.debug(f"PMC failed for {doi}: {e}")

        logger.warning(f"No open access PDF found for {doi}")
        return None

    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF content using pdftotext."""
        import subprocess

        try:
            # Use pdftotext via subprocess (in memory via stdin)
            process = subprocess.run(
                ["pdftotext", "-layout", "-", "-"],
                input=pdf_content,
                capture_output=True,
                timeout=30,
            )

            if process.returncode == 0:
                return process.stdout.decode("utf-8", errors="ignore")

        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")

        return ""

    async def stream_paper(self, doi: str) -> Optional[ExtractedPaper]:
        """
        Stream a paper: fetch, extract, forget.

        The PDF is never saved to disk.
        Only extracted information is returned.
        """
        logger.info(f"Streaming paper: {doi}")

        # Step 1: Fetch PDF (in memory)
        pdf_content = await self.fetch_pdf_content(doi)
        if not pdf_content:
            logger.warning(f"Could not fetch: {doi}")
            return None

        logger.info(f"Fetched {len(pdf_content)} bytes for {doi}")

        # Step 2: Extract text (in memory)
        text = self.extract_text_from_pdf(pdf_content)
        if not text or len(text) < 500:
            logger.warning(f"Could not extract text from: {doi}")
            return None

        logger.info(f"Extracted {len(text)} characters from {doi}")

        # Step 3: Extract essential information
        extracted = ExtractedPaper(
            doi=doi,
            source="open_access",
        )

        # Extract title (usually first significant line)
        lines = text.split('\n')
        for line in lines[:20]:
            line = line.strip()
            if len(line) > 20 and len(line) < 300 and not line.isupper():
                extracted.title = line
                break

        # Extract abstract
        extracted.abstract = self.extractor.extract_abstract(text)

        # Extract authors
        extracted.authors = self.extractor.extract_authors(text)

        # Extract funding
        extracted.funders = self.extractor.extract_funding(text)

        # Extract conclusions
        extracted.main_claims = self.extractor.extract_conclusions(text)

        # Extract references
        extracted.references = self.extractor.extract_references(text)

        # Detect red flags
        extracted.red_flags, extracted.epstein_score = self.extractor.detect_red_flags(
            text, extracted.title, extracted.funders
        )
        extracted.is_relevant = extracted.epstein_score > 0.1 or len(extracted.red_flags) > 0

        # Step 4: FORGET the PDF
        # pdf_content is automatically garbage collected when this function returns
        # text is also not stored anywhere permanent

        logger.info(f"Extracted paper: {extracted.title[:50]}... (score: {extracted.epstein_score:.2f})")

        if extracted.red_flags:
            logger.warning(f"RED FLAGS: {extracted.red_flags}")

        return extracted

    async def stream_batch(self, dois: List[str], delay: float = 2.0) -> List[ExtractedPaper]:
        """Stream multiple papers with rate limiting."""
        results = []

        for i, doi in enumerate(dois):
            try:
                extracted = await self.stream_paper(doi)
                if extracted:
                    results.append(extracted)

                # Rate limiting
                if i < len(dois) - 1:
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Failed to stream {doi}: {e}")

        return results


# CLI for testing
async def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python paper_stream.py <DOI>")
        print("Example: python paper_stream.py 10.1038/nature12373")
        return

    doi = sys.argv[1]

    streamer = PaperStreamer()
    try:
        result = await streamer.stream_paper(doi)
        if result:
            print("\n" + "=" * 60)
            print("EXTRACTED PAPER")
            print("=" * 60)
            print(f"Title: {result.title}")
            print(f"DOI: {result.doi}")
            print(f"Authors: {len(result.authors)}")
            for a in result.authors[:5]:
                print(f"  - {a.get('name', 'Unknown')}")
            print(f"Abstract: {result.abstract[:200] if result.abstract else 'N/A'}...")
            print(f"Funders: {result.funders}")
            print(f"Main claims: {len(result.main_claims)}")
            print(f"References: {len(result.references)}")
            print(f"Epstein score: {result.epstein_score:.2f}")
            print(f"Red flags: {result.red_flags}")
            print("=" * 60)
        else:
            print("Failed to extract paper")
    finally:
        await streamer.close()


if __name__ == "__main__":
    asyncio.run(main())
