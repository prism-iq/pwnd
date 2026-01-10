"""
Academic Papers Ingestion Module
================================

Harvests papers from multiple sources:
- OpenAlex (metadata, 240M+ works)
- Semantic Scholar (metadata + S2ORC bulk)
- arXiv (preprints, math/physics/CS)
- PubMed Central (biomedical open access)
- Unpaywall (legal OA PDF discovery)
- Sci-Hub (fallback for paywalled content)

Priority domains: Mathematics, Neuroscience, Biology, Psychology, Medicine, Art
"""

import httpx
import asyncio
import json
import logging
import hashlib
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from dataclasses import dataclass, field, asdict

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

# Configuration
ACADEMIC_DATA_DIR = BASE_DIR / "external_data" / "academic"
PAPERS_DIR = ACADEMIC_DATA_DIR / "papers"
PROCESSED_DIR = ACADEMIC_DATA_DIR / "processed"

# API endpoints
OPENALEX_API = "https://api.openalex.org"
SEMANTIC_API = "https://api.semanticscholar.org/graph/v1"
ARXIV_API = "http://export.arxiv.org/api/query"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
SCIHUB_DOMAINS = ["sci-hub.se", "sci-hub.st", "sci-hub.ru"]

# Priority fields for investigation
PRIORITY_FIELDS = {
    "Mathematics": ["pure mathematics", "applied mathematics", "statistics"],
    "Neuroscience": ["neuroscience", "cognitive science", "brain"],
    "Biology": ["biology", "genetics", "molecular biology", "evolutionary biology"],
    "Psychology": ["psychology", "behavioral science", "psychiatry"],
    "Medicine": ["medicine", "clinical medicine", "public health"],
    "Art": ["art", "visual arts", "art history", "aesthetics"],
}

# Epstein-related keywords for relevance scoring
EPSTEIN_KEYWORDS = [
    "epstein", "joi ito", "media lab", "mit media lab",
    "martin nowak", "evolutionary dynamics", "santa fe institute",
    "transhumanism", "eugenics", "human enhancement",
    "child", "minor", "trafficking", "exploitation",
    "wexner", "les wexner", "gratitude america",
]

# Institutions with known Epstein connections
EPSTEIN_INSTITUTIONS = [
    "mit media lab", "massachusetts institute of technology",
    "harvard", "program for evolutionary dynamics",
    "santa fe institute", "rockefeller university",
    "new york university", "columbia university",
]


@dataclass
class Paper:
    """Represents an academic paper."""
    doi: Optional[str] = None
    title: str = ""
    abstract: Optional[str] = None
    authors: List[Dict] = field(default_factory=list)
    year: Optional[int] = None
    publication_date: Optional[date] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    source_type: str = "journal"

    # Identifiers
    openalex_id: Optional[str] = None
    semantic_id: Optional[str] = None
    arxiv_id: Optional[str] = None
    pmid: Optional[str] = None
    pmcid: Optional[str] = None

    # Institutions and funding
    institutions: List[Dict] = field(default_factory=list)
    funders: List[Dict] = field(default_factory=list)
    topics: List[Dict] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)

    # Metrics
    citation_count: int = 0
    reference_count: int = 0

    # Open access
    is_open_access: bool = False
    oa_status: Optional[str] = None
    oa_url: Optional[str] = None

    # Content
    has_full_text: bool = False
    full_text: Optional[str] = None
    pdf_path: Optional[str] = None

    # Source tracking
    source: str = "unknown"

    # Investigation relevance (NOT automatically good)
    epstein_relevant: bool = False
    relevance_score: float = 0.0
    investigation_notes: Optional[str] = None

    def calculate_relevance(self) -> float:
        """
        Calculate relevance to Epstein investigation.
        NOT automatic - based on actual content matching.
        Returns 0.0 to 1.0.
        """
        score = 0.0
        text_to_check = f"{self.title} {self.abstract or ''} {json.dumps(self.funders)} {json.dumps(self.institutions)}"
        text_lower = text_to_check.lower()

        # Check for Epstein keywords
        matches = []
        for keyword in EPSTEIN_KEYWORDS:
            if keyword in text_lower:
                matches.append(keyword)
                score += 0.15

        # Check for Epstein-connected institutions
        for inst in self.institutions:
            inst_name = inst.get("name", "").lower()
            for epstein_inst in EPSTEIN_INSTITUTIONS:
                if epstein_inst in inst_name:
                    matches.append(f"institution:{inst_name}")
                    score += 0.2

        # Check funders
        for funder in self.funders:
            funder_name = funder.get("name", "").lower()
            if any(k in funder_name for k in ["epstein", "jepf", "gratitude"]):
                matches.append(f"funder:{funder_name}")
                score += 0.5  # Strong signal

        # Cap at 1.0
        self.relevance_score = min(score, 1.0)
        self.epstein_relevant = self.relevance_score > 0.1

        if matches:
            self.investigation_notes = f"Matches: {', '.join(matches)}"

        return self.relevance_score


class OpenAlexClient:
    """Client for OpenAlex API - 240M+ works, free, no auth required."""

    def __init__(self, email: str = "research@pwnd.icu"):
        self.base_url = OPENALEX_API
        self.email = email
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def search_works(
        self,
        query: Optional[str] = None,
        filter_str: Optional[str] = None,
        per_page: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for works in OpenAlex.

        Examples:
            - query="epstein funding"
            - filter_str="institutions.id:I136199984"  (MIT)
            - filter_str="authorships.institutions.display_name:MIT Media Lab"
        """
        params = {
            "mailto": self.email,
            "per-page": min(per_page, 200),
        }

        if query:
            params["search"] = query
        if filter_str:
            params["filter"] = filter_str
        if cursor:
            params["cursor"] = cursor

        url = f"{self.base_url}/works"
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def get_work(self, openalex_id: str) -> Dict[str, Any]:
        """Get a single work by OpenAlex ID."""
        url = f"{self.base_url}/works/{openalex_id}"
        params = {"mailto": self.email}
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def search_by_institution(
        self,
        institution_name: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> List[Dict]:
        """Search works by institution name."""
        filters = [f"authorships.institutions.display_name.search:{institution_name}"]

        if year_from:
            filters.append(f"publication_year:>{year_from-1}")
        if year_to:
            filters.append(f"publication_year:<{year_to+1}")

        filter_str = ",".join(filters)
        result = await self.search_works(filter_str=filter_str, per_page=200)
        return result.get("results", [])

    async def search_by_funder(self, funder_name: str) -> List[Dict]:
        """Search works by funder name."""
        filter_str = f"grants.funder_display_name.search:{funder_name}"
        result = await self.search_works(filter_str=filter_str, per_page=200)
        return result.get("results", [])

    async def get_institution(self, name: str) -> Optional[Dict]:
        """Get institution details by name."""
        url = f"{self.base_url}/institutions"
        params = {
            "mailto": self.email,
            "search": name,
            "per-page": 1,
        }
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        return results[0] if results else None

    def parse_work(self, work: Dict) -> Paper:
        """Parse OpenAlex work into Paper object."""
        # Extract authors with affiliations
        authors = []
        institutions = set()
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            author_data = {
                "name": author.get("display_name", ""),
                "openalex_id": author.get("id", ""),
                "orcid": author.get("orcid"),
                "position": authorship.get("author_position", ""),
            }

            # Get institutions
            for inst in authorship.get("institutions", []):
                author_data["affiliation"] = inst.get("display_name", "")
                author_data["affiliation_id"] = inst.get("id", "")
                institutions.add(json.dumps({
                    "id": inst.get("id"),
                    "name": inst.get("display_name"),
                    "country": inst.get("country_code"),
                    "type": inst.get("type"),
                }))

            authors.append(author_data)

        # Extract funders
        funders = []
        for grant in work.get("grants", []):
            funders.append({
                "id": grant.get("funder"),
                "name": grant.get("funder_display_name", ""),
                "award_id": grant.get("award_id"),
            })

        # Extract topics
        topics = []
        fields = set()
        for topic in work.get("topics", []):
            topics.append({
                "id": topic.get("id"),
                "name": topic.get("display_name"),
                "field": topic.get("field", {}).get("display_name"),
                "subfield": topic.get("subfield", {}).get("display_name"),
            })
            if topic.get("field", {}).get("display_name"):
                fields.add(topic["field"]["display_name"])

        # Parse publication date
        pub_date = None
        date_str = work.get("publication_date")
        if date_str:
            try:
                pub_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        # Open access info
        oa_info = work.get("open_access", {})
        best_oa = work.get("best_oa_location", {}) or {}

        paper = Paper(
            doi=work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None,
            openalex_id=work.get("id"),
            title=work.get("title", ""),
            abstract=work.get("abstract"),
            authors=authors,
            institutions=[json.loads(i) for i in institutions],
            funders=funders,
            topics=topics,
            fields=list(fields),
            year=work.get("publication_year"),
            publication_date=pub_date,
            journal=work.get("primary_location", {}).get("source", {}).get("display_name") if work.get("primary_location") else None,
            publisher=work.get("primary_location", {}).get("source", {}).get("host_organization_name") if work.get("primary_location") else None,
            source_type=work.get("type", "journal-article"),
            citation_count=work.get("cited_by_count", 0),
            reference_count=len(work.get("referenced_works", [])),
            is_open_access=oa_info.get("is_oa", False),
            oa_status=oa_info.get("oa_status"),
            oa_url=best_oa.get("pdf_url") or best_oa.get("landing_page_url"),
            source="openalex",
        )

        # Calculate relevance (not automatic - based on content)
        paper.calculate_relevance()

        return paper


class UnpaywallClient:
    """Client for Unpaywall API - finds legal open access PDFs."""

    def __init__(self, email: str = "research@pwnd.icu"):
        self.base_url = UNPAYWALL_API
        self.email = email
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def get_oa_location(self, doi: str) -> Optional[Dict]:
        """Get open access location for a DOI."""
        if not doi:
            return None

        # Clean DOI
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

        url = f"{self.base_url}/{doi}"
        params = {"email": self.email}

        try:
            response = await self.client.get(url, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Unpaywall error for {doi}: {e}")
            return None

    async def get_pdf_url(self, doi: str) -> Optional[str]:
        """Get direct PDF URL if available."""
        data = await self.get_oa_location(doi)
        if not data:
            return None

        best_oa = data.get("best_oa_location", {})
        if best_oa:
            return best_oa.get("url_for_pdf") or best_oa.get("url")

        return None


class ArxivClient:
    """Client for arXiv API - preprints in math, physics, CS, etc."""

    def __init__(self):
        self.base_url = ARXIV_API
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.client.aclose()

    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        max_results: int = 100,
        start: int = 0,
    ) -> List[Dict]:
        """
        Search arXiv.

        Categories: math, physics, cs, q-bio, q-fin, stat, eess, econ
        """
        search_query = query
        if category:
            search_query = f"cat:{category} AND ({query})"

        params = {
            "search_query": f"all:{search_query}",
            "start": start,
            "max_results": min(max_results, 1000),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        response = await self.client.get(self.base_url, params=params)
        response.raise_for_status()

        # Parse Atom XML response
        return self._parse_atom(response.text)

    def _parse_atom(self, xml_text: str) -> List[Dict]:
        """Parse arXiv Atom XML response."""
        import xml.etree.ElementTree as ET

        papers = []
        root = ET.fromstring(xml_text)

        # Namespace
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        for entry in root.findall("atom:entry", ns):
            arxiv_id = entry.find("atom:id", ns)
            if arxiv_id is not None:
                arxiv_id = arxiv_id.text.split("/abs/")[-1]

            title = entry.find("atom:title", ns)
            title = title.text.strip().replace("\n", " ") if title is not None else ""

            abstract = entry.find("atom:summary", ns)
            abstract = abstract.text.strip() if abstract is not None else ""

            published = entry.find("atom:published", ns)
            pub_date = None
            if published is not None:
                try:
                    pub_date = datetime.fromisoformat(published.text.replace("Z", "+00:00")).date()
                except:
                    pass

            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns)
                if name is not None:
                    authors.append({"name": name.text})

            # Categories
            categories = []
            for cat in entry.findall("atom:category", ns):
                term = cat.get("term")
                if term:
                    categories.append(term)

            # PDF link
            pdf_url = None
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href")
                    break

            papers.append({
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "publication_date": pub_date,
                "categories": categories,
                "pdf_url": pdf_url,
                "is_open_access": True,
                "oa_status": "green",
            })

        return papers

    def parse_paper(self, data: Dict) -> Paper:
        """Parse arXiv result into Paper object."""
        paper = Paper(
            arxiv_id=data.get("arxiv_id"),
            title=data.get("title", ""),
            abstract=data.get("abstract"),
            authors=data.get("authors", []),
            publication_date=data.get("publication_date"),
            year=data.get("publication_date").year if data.get("publication_date") else None,
            is_open_access=True,
            oa_status="green",
            oa_url=data.get("pdf_url"),
            source="arxiv",
            fields=self._categories_to_fields(data.get("categories", [])),
        )

        paper.calculate_relevance()
        return paper

    def _categories_to_fields(self, categories: List[str]) -> List[str]:
        """Map arXiv categories to our field names."""
        field_map = {
            "math": "Mathematics",
            "physics": "Physics",
            "cs": "Computer Science",
            "q-bio": "Biology",
            "q-fin": "Finance",
            "stat": "Statistics",
            "econ": "Economics",
        }

        fields = set()
        for cat in categories:
            prefix = cat.split(".")[0]
            if prefix in field_map:
                fields.add(field_map[prefix])

        return list(fields)


class SciHubClient:
    """
    Client for Sci-Hub - fallback for paywalled papers.

    Uses scidownl package or direct HTTP.
    This is for research purposes in OSINT investigation.
    """

    def __init__(self):
        self.domains = SCIHUB_DOMAINS
        self.client = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        self.working_domain = None

    async def close(self):
        await self.client.aclose()

    async def find_working_domain(self) -> Optional[str]:
        """Find a working Sci-Hub domain."""
        for domain in self.domains:
            try:
                response = await self.client.get(f"https://{domain}", timeout=10.0)
                if response.status_code == 200:
                    self.working_domain = domain
                    logger.info(f"Sci-Hub working domain: {domain}")
                    return domain
            except Exception as e:
                logger.debug(f"Sci-Hub domain {domain} failed: {e}")
                continue

        logger.warning("No working Sci-Hub domain found")
        return None

    async def get_pdf_url(self, doi: str) -> Optional[str]:
        """Get PDF URL from Sci-Hub for a DOI."""
        if not self.working_domain:
            await self.find_working_domain()

        if not self.working_domain:
            return None

        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        url = f"https://{self.working_domain}/{doi}"

        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None

            # Parse response to find PDF iframe/embed
            html = response.text

            # Look for PDF URL patterns
            patterns = [
                r'iframe[^>]+src=["\']([^"\']+\.pdf[^"\']*)["\']',
                r'embed[^>]+src=["\']([^"\']+\.pdf[^"\']*)["\']',
                r'(https?://[^\s"\']+\.pdf)',
            ]

            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    pdf_url = match.group(1)
                    if pdf_url.startswith("//"):
                        pdf_url = "https:" + pdf_url
                    return pdf_url

            return None

        except Exception as e:
            logger.warning(f"Sci-Hub error for {doi}: {e}")
            return None

    async def download_pdf(self, doi: str, output_path: Path) -> bool:
        """Download PDF for a DOI."""
        pdf_url = await self.get_pdf_url(doi)
        if not pdf_url:
            return False

        try:
            response = await self.client.get(pdf_url)
            if response.status_code == 200 and len(response.content) > 1000:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)
                logger.info(f"Downloaded: {doi} -> {output_path}")
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to download {doi}: {e}")
            return False


class SemanticScholarClient:
    """Client for Semantic Scholar API."""

    def __init__(self, api_key: Optional[str] = None):
        self.base_url = SEMANTIC_API
        self.api_key = api_key
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        self.client = httpx.AsyncClient(timeout=30.0, headers=headers)

    async def close(self):
        await self.client.aclose()

    async def search(
        self,
        query: str,
        fields: str = "paperId,title,abstract,authors,year,citationCount,openAccessPdf",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search for papers."""
        url = f"{self.base_url}/paper/search"
        params = {
            "query": query,
            "fields": fields,
            "limit": min(limit, 100),
            "offset": offset,
        }

        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def get_paper(self, paper_id: str) -> Dict[str, Any]:
        """Get paper by Semantic Scholar ID or DOI."""
        fields = "paperId,title,abstract,authors,year,venue,citationCount,referenceCount,openAccessPdf,fieldsOfStudy"
        url = f"{self.base_url}/paper/{paper_id}"
        params = {"fields": fields}

        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def parse_paper(self, data: Dict) -> Paper:
        """Parse Semantic Scholar result into Paper object."""
        authors = []
        for author in data.get("authors", []):
            authors.append({
                "name": author.get("name", ""),
                "semantic_id": author.get("authorId"),
            })

        oa_pdf = data.get("openAccessPdf", {}) or {}

        paper = Paper(
            semantic_id=data.get("paperId"),
            title=data.get("title", ""),
            abstract=data.get("abstract"),
            authors=authors,
            year=data.get("year"),
            journal=data.get("venue"),
            citation_count=data.get("citationCount", 0),
            reference_count=data.get("referenceCount", 0),
            is_open_access=bool(oa_pdf.get("url")),
            oa_url=oa_pdf.get("url"),
            source="semantic_scholar",
            fields=data.get("fieldsOfStudy", []),
        )

        paper.calculate_relevance()
        return paper


# Utility functions

def doi_to_filename(doi: str) -> str:
    """Convert DOI to safe filename."""
    return hashlib.sha256(doi.encode()).hexdigest()[:16] + ".pdf"


async def download_paper_pdf(
    paper: Paper,
    unpaywall: UnpaywallClient,
    scihub: Optional[SciHubClient] = None,
) -> Optional[Path]:
    """
    Try to download PDF for a paper.

    Priority:
    1. Direct OA URL from paper
    2. Unpaywall (legal OA)
    3. Sci-Hub (fallback)
    """
    if not paper.doi:
        return None

    output_path = PAPERS_DIR / doi_to_filename(paper.doi)

    if output_path.exists():
        paper.pdf_path = str(output_path)
        return output_path

    # Try direct OA URL
    if paper.oa_url and ".pdf" in paper.oa_url.lower():
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(paper.oa_url)
                if response.status_code == 200 and len(response.content) > 1000:
                    output_path.write_bytes(response.content)
                    paper.pdf_path = str(output_path)
                    return output_path
        except Exception as e:
            logger.debug(f"Direct download failed for {paper.doi}: {e}")

    # Try Unpaywall
    pdf_url = await unpaywall.get_pdf_url(paper.doi)
    if pdf_url:
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(pdf_url)
                if response.status_code == 200 and len(response.content) > 1000:
                    output_path.write_bytes(response.content)
                    paper.pdf_path = str(output_path)
                    return output_path
        except Exception as e:
            logger.debug(f"Unpaywall download failed for {paper.doi}: {e}")

    # Try Sci-Hub as last resort
    if scihub:
        success = await scihub.download_pdf(paper.doi, output_path)
        if success:
            paper.pdf_path = str(output_path)
            return output_path

    return None


# Main testing
if __name__ == "__main__":
    async def test():
        print("Testing OpenAlex client...")
        client = OpenAlexClient()

        # Search MIT Media Lab papers
        print("\n--- MIT Media Lab papers ---")
        works = await client.search_by_institution("MIT Media Lab", year_from=2010, year_to=2019)
        print(f"Found {len(works)} papers")

        for work in works[:3]:
            paper = client.parse_work(work)
            print(f"\nTitle: {paper.title[:80]}...")
            print(f"Year: {paper.year}")
            print(f"Relevance: {paper.relevance_score:.2f}")
            if paper.investigation_notes:
                print(f"Notes: {paper.investigation_notes}")

        # Search for Epstein funding
        print("\n--- Epstein funding search ---")
        works = await client.search_by_funder("Epstein")
        print(f"Found {len(works)} papers")

        await client.close()

    asyncio.run(test())
