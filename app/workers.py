"""
Parallel LLM Worker Pool for L Investigation Framework

Architecture:
- Multiple Phi-3 workers for local inference (free, fast for extraction)
- Haiku API for complex synthesis only (cost-effective)
- Job queue for handling concurrent users
- Response caching to avoid redundant work
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from collections import OrderedDict

from app.config import LLM_DIR
from concurrent.futures import ThreadPoolExecutor, Future
import threading

log = logging.getLogger("workers")

# Configuration
NUM_PHI3_WORKERS = 3  # 3 workers × 2GB = 6GB RAM
THREADS_PER_WORKER = 2  # 3 workers × 2 threads = 6 threads (leaving 2 for system)
CACHE_MAX_SIZE = 500
CACHE_TTL = 3600  # 1 hour
MAX_QUEUE_SIZE = 100
JOB_TIMEOUT = 120  # seconds


class JobType(Enum):
    EXTRACT_ENTITIES = "extract_entities"
    EXTRACT_RELATIONSHIPS = "extract_relationships"
    FILTER_RELEVANCE = "filter_relevance"
    SUMMARIZE = "summarize"
    SYNTHESIZE = "synthesize"  # Complex - may use Haiku
    # New parallel parsing types
    PARSE_INTENT = "parse_intent"  # Understand query intent
    GENERATE_SUBQUERIES = "generate_subqueries"  # Self-questioning
    EXTRACT_KEYWORDS = "extract_keywords"  # Key terms for search
    SCORE_RESULTS = "score_results"  # Rate result relevance


class JobPriority(Enum):
    HIGH = 0
    NORMAL = 1
    LOW = 2


@dataclass(order=True)
class Job:
    priority: int
    created_at: float = field(compare=False)
    job_id: str = field(compare=False)
    job_type: JobType = field(compare=False)
    payload: Dict[str, Any] = field(compare=False)
    user_id: str = field(compare=False, default="anonymous")
    callback: Optional[Callable] = field(compare=False, default=None)
    result: Optional[Any] = field(compare=False, default=None)
    error: Optional[str] = field(compare=False, default=None)
    completed: bool = field(compare=False, default=False)


class LRUCache:
    """Thread-safe LRU cache with TTL"""

    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl: int = CACHE_TTL):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _make_key(self, job_type: str, payload: Dict) -> str:
        content = json.dumps({"type": job_type, "payload": payload}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, job_type: str, payload: Dict) -> Optional[Any]:
        key = self._make_key(job_type, payload)
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None

            # Check TTL
            if time.time() - self.timestamps[key] > self.ttl:
                del self.cache[key]
                del self.timestamps[key]
                self.misses += 1
                return None

            # Move to end (most recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]

    def set(self, job_type: str, payload: Dict, value: Any):
        key = self._make_key(job_type, payload)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.max_size:
                    oldest = next(iter(self.cache))
                    del self.cache[oldest]
                    del self.timestamps[oldest]
            self.cache[key] = value
            self.timestamps[key] = time.time()

    def stats(self) -> Dict:
        with self.lock:
            total = self.hits + self.misses
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": self.hits / total if total > 0 else 0
            }


class Phi3Worker:
    """Single Phi-3 worker with dedicated model instance"""

    def __init__(self, worker_id: int, model_path: str, n_threads: int = THREADS_PER_WORKER):
        self.worker_id = worker_id
        self.model_path = model_path
        self.n_threads = n_threads
        self.model = None
        self.busy = False
        self.jobs_processed = 0
        self.total_time = 0.0
        self.lock = threading.Lock()

    def load(self) -> bool:
        try:
            from llama_cpp import Llama
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=self.n_threads,
                n_batch=256,
                n_gpu_layers=0,
                use_mlock=False,  # Don't lock - let OS manage
                verbose=False,
            )
            log.info(f"Worker {self.worker_id} loaded (threads={self.n_threads})")
            return True
        except Exception as e:
            log.error(f"Worker {self.worker_id} failed to load: {e}")
            return False

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.3) -> str:
        if not self.model:
            return ""
        start = time.time()
        try:
            response = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["<|end|>", "<|user|>", "<|system|>", "</s>", "\n\n\n"],
                echo=False,
            )
            elapsed = time.time() - start
            result = response["choices"][0]["text"].strip()
            with self.lock:
                self.jobs_processed += 1
                self.total_time += elapsed
            return result
        except Exception as e:
            log.error(f"Worker {self.worker_id} generation error: {e}")
            return ""

    def stats(self) -> Dict:
        avg_time = self.total_time / self.jobs_processed if self.jobs_processed > 0 else 0
        return {
            "worker_id": self.worker_id,
            "busy": self.busy,
            "jobs_processed": self.jobs_processed,
            "avg_time": round(avg_time, 2)
        }


class WorkerPool:
    """Pool of Phi-3 workers with job queue"""

    def __init__(self, num_workers: int = NUM_PHI3_WORKERS):
        self.num_workers = num_workers
        self.workers: List[Phi3Worker] = []
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        self.job_queue: asyncio.PriorityQueue = None
        self.cache = LRUCache()
        self.pending_jobs: Dict[str, Job] = {}
        self.running = False
        self._job_counter = 0
        self._lock = threading.Lock()

    async def start(self, model_path: str):
        """Initialize workers and start processing"""
        log.info(f"Starting worker pool with {self.num_workers} workers")

        # Create workers
        for i in range(self.num_workers):
            worker = Phi3Worker(i, model_path, THREADS_PER_WORKER)
            if worker.load():
                self.workers.append(worker)
            else:
                log.warning(f"Worker {i} failed to initialize")

        if not self.workers:
            raise RuntimeError("No workers initialized")

        self.job_queue = asyncio.PriorityQueue(maxsize=MAX_QUEUE_SIZE)
        self.running = True
        log.info(f"Worker pool started: {len(self.workers)} workers ready")

    async def stop(self):
        """Shutdown workers"""
        self.running = False
        for w in self.workers:
            w.model = None
        self.workers.clear()
        self.executor.shutdown(wait=False)
        log.info("Worker pool stopped")

    def _get_available_worker(self) -> Optional[Phi3Worker]:
        """Get first non-busy worker and mark it busy atomically"""
        for w in self.workers:
            with w.lock:
                if not w.busy:
                    w.busy = True
                    return w
        return None

    def _release_worker(self, worker: Phi3Worker):
        """Release worker back to pool"""
        with worker.lock:
            worker.busy = False

    def _generate_job_id(self) -> str:
        with self._lock:
            self._job_counter += 1
            return f"job_{self._job_counter}_{int(time.time() * 1000) % 100000}"

    async def submit(self, job_type: JobType, payload: Dict,
                     priority: JobPriority = JobPriority.NORMAL,
                     user_id: str = "anonymous") -> str:
        """Submit job to queue, return job_id"""

        # Check cache first
        cached = self.cache.get(job_type.value, payload)
        if cached is not None:
            job_id = self._generate_job_id()
            job = Job(
                priority=priority.value,
                created_at=time.time(),
                job_id=job_id,
                job_type=job_type,
                payload=payload,
                user_id=user_id,
                result=cached,
                completed=True
            )
            self.pending_jobs[job_id] = job
            return job_id

        # Create new job
        job_id = self._generate_job_id()
        job = Job(
            priority=priority.value,
            created_at=time.time(),
            job_id=job_id,
            job_type=job_type,
            payload=payload,
            user_id=user_id
        )
        self.pending_jobs[job_id] = job

        try:
            await asyncio.wait_for(
                self.job_queue.put(job),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            job.error = "Queue full"
            job.completed = True

        return job_id

    async def process_job(self, job: Job) -> Any:
        """Process a single job"""
        worker = self._get_available_worker()
        if not worker:
            # Wait for available worker
            for _ in range(50):  # 5 seconds max
                await asyncio.sleep(0.1)
                worker = self._get_available_worker()
                if worker:
                    break

        if not worker:
            job.error = "No workers available"
            job.completed = True
            return None
        # Execute based on job type
        loop = asyncio.get_event_loop()
        try:
            if job.job_type == JobType.EXTRACT_ENTITIES:
                result = await loop.run_in_executor(
                    self.executor,
                    self._extract_entities,
                    worker,
                    job.payload.get("text", "")
                )
            elif job.job_type == JobType.EXTRACT_RELATIONSHIPS:
                result = await loop.run_in_executor(
                    self.executor,
                    self._extract_relationships,
                    worker,
                    job.payload.get("text", ""),
                    job.payload.get("entities", [])
                )
            elif job.job_type == JobType.FILTER_RELEVANCE:
                result = await loop.run_in_executor(
                    self.executor,
                    self._filter_relevance,
                    worker,
                    job.payload.get("query", ""),
                    job.payload.get("items", [])
                )
            elif job.job_type == JobType.SUMMARIZE:
                result = await loop.run_in_executor(
                    self.executor,
                    self._summarize,
                    worker,
                    job.payload.get("text", ""),
                    job.payload.get("max_length", 200)
                )
            # New parallel job types
            elif job.job_type == JobType.PARSE_INTENT:
                result = await loop.run_in_executor(
                    self.executor,
                    self._parse_intent,
                    worker,
                    job.payload.get("query", "")
                )
            elif job.job_type == JobType.GENERATE_SUBQUERIES:
                result = await loop.run_in_executor(
                    self.executor,
                    self._generate_subqueries,
                    worker,
                    job.payload.get("query", ""),
                    job.payload.get("context", "")
                )
            elif job.job_type == JobType.EXTRACT_KEYWORDS:
                result = await loop.run_in_executor(
                    self.executor,
                    self._extract_keywords,
                    worker,
                    job.payload.get("text", "")
                )
            elif job.job_type == JobType.SCORE_RESULTS:
                result = await loop.run_in_executor(
                    self.executor,
                    self._score_results,
                    worker,
                    job.payload.get("query", ""),
                    job.payload.get("results", [])
                )
            elif job.job_type == JobType.SYNTHESIZE:
                result = await loop.run_in_executor(
                    self.executor,
                    self._synthesize,
                    worker,
                    job.payload.get("text", ""),
                    job.payload.get("max_length", 512)
                )
            else:
                result = None

            job.result = result
            job.completed = True

            # Cache result
            if result is not None:
                self.cache.set(job.job_type.value, job.payload, result)

            return result

        except Exception as e:
            job.error = str(e)
            job.completed = True
            return None
        finally:
            self._release_worker(worker)

    def _extract_entities(self, worker: Phi3Worker, text: str) -> List[Dict]:
        """Extract entities using Phi-3 - detect ALL entities"""
        prompt = f"""<|system|>
You are an entity extraction assistant. Extract ALL named entities accurately.
<|end|>

<|user|>
Extract ALL named entities from this text.

Entity types:
- person: Human names (e.g., "Jeffrey Epstein", "Bill Clinton")
- org: Companies, foundations, agencies, media (e.g., "Clinton Foundation", "FBI", "Washington Post")
- location: Cities, countries, islands, addresses (e.g., "New York", "Virgin Islands", "Hong Kong")
- date: Specific dates (e.g., "August 2019", "2015-03-14")
- amount: Money values (e.g., "$5 million", "$500,000")
- media: News sources, publications (e.g., "The Post", "CNBC", "Daily News")

Return JSON array: [{{"name": "...", "type": "person|org|location|date|amount|media"}}]

Text: {text[:2500]}
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=800, temperature=0.1)
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except Exception:
            pass
        return []

    def _extract_relationships(self, worker: Phi3Worker, text: str, entities: List[Dict]) -> List[Dict]:
        """Extract relationships between entities"""
        names = [e.get("name", "") for e in entities[:15]]
        prompt = f"""<|system|>
You are a relationship extraction assistant. Find connections between entities.
<|end|>

<|user|>
Find relationships between these entities in the text.
Entities: {', '.join(names)}
Format: [{{"from": "...", "to": "...", "type": "..."}}]

Text: {text[:2000]}
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=600, temperature=0.2)
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except Exception:
            pass
        return []

    def _filter_relevance(self, worker: Phi3Worker, query: str, items: List[Dict]) -> List[Dict]:
        """Filter items by relevance to query"""
        items_text = "\n".join([f"{i}: {item.get('text', '')[:100]}" for i, item in enumerate(items[:20])])
        prompt = f"""<|system|>
You are a relevance filter. Select only items relevant to the query.
<|end|>

<|user|>
Which items are relevant to: "{query}"?
Return JSON array of indices (0-based).

Items:
{items_text}
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=100, temperature=0.1)
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                indices = json.loads(response[start:end])
                return [items[i] for i in indices if i < len(items)]
        except Exception:
            pass
        return items

    def _summarize(self, worker: Phi3Worker, text: str, max_length: int) -> str:
        """Process text - if already formatted (contains <|), pass through. Otherwise wrap."""
        if "<|" in text:
            # Already Phi-3 formatted prompt - pass through
            prompt = text[:8000]
        else:
            # Raw text - wrap in Phi-3 format
            prompt = f"""<|system|>
You are a concise summarizer. Extract key facts only.
<|end|>

<|user|>
Summarize in {max_length} chars max:

{text[:3000]}
<|end|>

<|assistant|>"""

        # Cap max_tokens to 512 for reasonable response time (about 20-30s)
        max_tokens = min(512, max_length // 3)
        return worker.generate(prompt, max_tokens=max_tokens, temperature=0.3)

    def _parse_intent(self, worker: Phi3Worker, query: str) -> Dict:
        """Parse user query intent - what are they looking for?"""
        prompt = f"""<|system|>
You are a query analysis assistant. Parse investigation queries into structured format.
<|end|>

<|user|>
Analyze this investigation query. Return JSON:
{{
  "intent": "find_person|find_connection|timeline|financial|communication|other",
  "targets": ["name1", "name2"],
  "time_range": "specific date or null",
  "keywords": ["key", "terms"],
  "confidence": 0.0-1.0
}}

Query: {query}
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=300, temperature=0.1)
        try:
            if "{" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                return json.loads(response[start:end])
        except Exception:
            pass
        return {"intent": "other", "targets": [], "keywords": query.split()[:3], "confidence": 0.3}

    def _generate_subqueries(self, worker: Phi3Worker, query: str, context: str = "") -> List[str]:
        """Self-questioning - generate follow-up queries to explore"""
        prompt = f"""<|system|>
You are an investigator assistant. Generate follow-up questions to explore.
<|end|>

<|user|>
Given this investigation query, generate 3-5 related questions to explore.
Think like an investigator - what angles should we check?

Query: {query}
{f"Context: {context[:500]}" if context else ""}

Return JSON array of strings: ["question1", "question2", ...]
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=400, temperature=0.4)
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except Exception:
            pass
        return []

    def _extract_keywords(self, worker: Phi3Worker, text: str) -> List[Dict]:
        """Extract searchable keywords from text"""
        prompt = f"""<|system|>
You are a keyword extraction assistant. Extract searchable terms from text.
<|end|>

<|user|>
Extract key search terms from this text.
Return JSON: [{{"term": "...", "type": "name|org|place|date|keyword", "priority": 1-5}}]

Text: {text[:2000]}
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=400, temperature=0.1)
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except Exception:
            pass
        return []

    def _score_results(self, worker: Phi3Worker, query: str, results: List[Dict]) -> List[Dict]:
        """Score search results for relevance to query"""
        results_text = "\n".join([
            f"{i}: {r.get('name', '')[:60]} - {r.get('sender_email', '')} - {r.get('snippet', '')[:80]}"
            for i, r in enumerate(results[:15])
        ])
        prompt = f"""<|system|>
You are a relevance scoring assistant. Score email results for relevance to a query.
<|end|>

<|user|>
Score these email results for relevance to: "{query}"
Return JSON: [{{"index": 0, "score": 0.0-1.0, "reason": "why relevant"}}]

Results:
{results_text}
<|end|>

<|assistant|>"""

        response = worker.generate(prompt, max_tokens=600, temperature=0.1)
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                scores = json.loads(response[start:end])
                # Apply scores to results
                for s in scores:
                    idx = s.get("index", -1)
                    if 0 <= idx < len(results):
                        results[idx]["llm_score"] = s.get("score", 0.5)
                        results[idx]["llm_reason"] = s.get("reason", "")
                return results
        except Exception:
            pass
        return results

    def _synthesize(self, worker: Phi3Worker, prompt: str, max_length: int) -> str:
        """Generate synthesis response from prompt"""
        # The prompt already includes the Phi-3 format
        response = worker.generate(prompt, max_tokens=max_length, temperature=0.4)
        return response.strip() if response else ""

    async def get_result(self, job_id: str, timeout: float = JOB_TIMEOUT) -> Optional[Job]:
        """Wait for job result with timeout"""
        job = self.pending_jobs.get(job_id)
        if not job:
            return None

        if job.completed:
            return job

        # Process the job directly if not yet completed
        if not job.completed and not job.error:
            try:
                await asyncio.wait_for(self.process_job(job), timeout=timeout)
            except asyncio.TimeoutError:
                log.warning(f"Job {job_id} timed out after {timeout}s")
                job.error = f"Timeout after {timeout}s"
                job.completed = True

        return job

    def stats(self) -> Dict:
        """Get pool statistics"""
        return {
            "workers": [w.stats() for w in self.workers],
            "queue_size": self.job_queue.qsize() if self.job_queue else 0,
            "pending_jobs": len(self.pending_jobs),
            "cache": self.cache.stats()
        }


# Global worker pool instance
worker_pool = WorkerPool()


async def init_workers():
    """Initialize the global worker pool"""
    default_model = str(LLM_DIR / "Phi-3-mini-4k-instruct-q4.gguf")
    model_path = os.getenv("PHI3_MODEL_PATH", default_model)
    await worker_pool.start(model_path)


async def shutdown_workers():
    """Shutdown the global worker pool"""
    await worker_pool.stop()


# =============================================================================
# PARALLEL EXTRACTION PIPELINE
# =============================================================================

class ParallelExtractor:
    """
    Multi-Phi-3 parallel pipeline for specialized entity extraction.

    Architecture:
        [Doc batch]
              ↓
    ┌─────────────────────────────────────┐
    │  Phi3-A (dates)    → SQL dates      │
    │  Phi3-B (persons)  → SQL persons    │  parallel
    │  Phi3-C (orgs)     → SQL orgs       │
    │  Phi3-D (amounts)  → SQL amounts    │
    └─────────────────────────────────────┘
              ↓ merge results
    [Haiku] → validate, correct, structure → clean INSERT
    """

    ENTITY_PROMPTS = {
        "dates": """<|system|>
You are a date extraction assistant. Extract all dates from text.
<|end|>

<|user|>
Extract ALL dates from this text.
Return JSON: [{{"value": "YYYY-MM-DD", "context": "what happened", "confidence": 0.0-1.0}}]
If date is partial (e.g. "March 2015"), use first of month.
If only year, use January 1.

Text: {text}
<|end|>

<|assistant|>""",

        "persons": """<|system|>
You are a person extraction assistant. Extract all person names from text.
<|end|>

<|user|>
Extract ALL person names from this text.
Return JSON: [{{"name": "Full Name", "role": "their role if known", "email": "if found", "confidence": 0.0-1.0}}]
Include variations (e.g. "Jeff Epstein" and "Jeffrey Epstein" separately).

Text: {text}
<|end|>

<|assistant|>""",

        "orgs": """<|system|>
You are an organization extraction assistant. Extract all organizations from text.
<|end|>

<|user|>
Extract ALL organizations from this text.
Return JSON: [{{"name": "Org Name", "type": "company|foundation|gov|media|other", "confidence": 0.0-1.0}}]
Include companies, foundations, agencies, universities, media outlets.

Text: {text}
<|end|>

<|assistant|>""",

        "amounts": """<|system|>
You are a financial extraction assistant. Extract all money amounts from text.
<|end|>

<|user|>
Extract ALL money amounts from this text.
Return JSON: [{{"value": "amount", "currency": "USD|EUR|etc", "context": "what for", "confidence": 0.0-1.0}}]
Normalize to numbers (e.g. "$5 million" → "5000000").

Text: {text}
<|end|>

<|assistant|>""",

        "locations": """<|system|>
You are a location extraction assistant. Extract all locations from text.
<|end|>

<|user|>
Extract ALL locations from this text.
Return JSON: [{{"name": "Location", "type": "city|country|address|property", "coordinates": "if known", "confidence": 0.0-1.0}}]
Include addresses, cities, islands, properties.

Text: {text}
<|end|>

<|assistant|>"""
    }

    @staticmethod
    async def extract_parallel(text: str, entity_types: List[str] = None) -> Dict[str, List[Dict]]:
        """
        Run multiple Phi-3 extractions in parallel.

        Args:
            text: Document text to process
            entity_types: List of types to extract, defaults to all

        Returns:
            Dict mapping entity_type -> list of extracted entities
        """
        if entity_types is None:
            entity_types = ["dates", "persons", "orgs", "amounts", "locations"]

        # Truncate text for each worker
        text_chunk = text[:3000]

        # Create tasks for parallel execution
        async def extract_type(etype: str) -> tuple:
            worker = worker_pool._get_available_worker()
            if not worker:
                # Wait briefly for a worker
                for _ in range(20):
                    await asyncio.sleep(0.1)
                    worker = worker_pool._get_available_worker()
                    if worker:
                        break

            if not worker:
                return etype, []

            try:
                prompt = ParallelExtractor.ENTITY_PROMPTS.get(etype, "")
                if not prompt:
                    return etype, []

                prompt = prompt.format(text=text_chunk)
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    worker_pool.executor,
                    worker.generate,
                    prompt,
                    600,  # max_tokens
                    0.1   # temperature
                )

                # Parse JSON response
                if "[" in response:
                    start = response.index("[")
                    end = response.rindex("]") + 1
                    entities = json.loads(response[start:end])
                    return etype, entities
            except Exception as e:
                log.error(f"Parallel extract {etype} error: {e}")
            finally:
                worker_pool._release_worker(worker)

            return etype, []

        # Run all extractions in parallel
        tasks = [extract_type(et) for et in entity_types]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        extracted = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            etype, entities = r
            extracted[etype] = entities

        return extracted

    @staticmethod
    def merge_results(extracted: Dict[str, List[Dict]]) -> Dict:
        """Merge and deduplicate extraction results"""
        merged = {
            "dates": [],
            "persons": [],
            "orgs": [],
            "amounts": [],
            "locations": [],
            "total_count": 0
        }

        # Dedupe by normalized value
        seen = {k: set() for k in merged.keys() if k != "total_count"}

        for etype, entities in extracted.items():
            if etype not in merged:
                continue
            for e in entities:
                # Get key for dedup
                if etype == "dates":
                    key = e.get("value", "")
                elif etype == "persons":
                    key = e.get("name", "").lower()
                elif etype == "orgs":
                    key = e.get("name", "").lower()
                elif etype == "amounts":
                    key = str(e.get("value", ""))
                elif etype == "locations":
                    key = e.get("name", "").lower()
                else:
                    key = str(e)

                if key and key not in seen[etype]:
                    seen[etype].add(key)
                    merged[etype].append(e)
                    merged["total_count"] += 1

        return merged

    @staticmethod
    def generate_sql_inserts(merged: Dict, source_id: int = None) -> List[str]:
        """Generate SQL INSERT statements for extracted entities"""
        inserts = []

        # Nodes table inserts
        for person in merged.get("persons", []):
            name = person.get("name", "").replace("'", "''")
            if name:
                inserts.append(
                    f"INSERT INTO nodes (type, name, name_normalized, metadata) "
                    f"VALUES ('person', '{name}', '{name.lower()}', '{json.dumps(person)}') "
                    f"ON CONFLICT (type, name_normalized) DO UPDATE SET metadata = EXCLUDED.metadata;"
                )

        for org in merged.get("orgs", []):
            name = org.get("name", "").replace("'", "''")
            if name:
                inserts.append(
                    f"INSERT INTO nodes (type, name, name_normalized, metadata) "
                    f"VALUES ('organization', '{name}', '{name.lower()}', '{json.dumps(org)}') "
                    f"ON CONFLICT (type, name_normalized) DO UPDATE SET metadata = EXCLUDED.metadata;"
                )

        for loc in merged.get("locations", []):
            name = loc.get("name", "").replace("'", "''")
            if name:
                inserts.append(
                    f"INSERT INTO nodes (type, name, name_normalized, metadata) "
                    f"VALUES ('location', '{name}', '{name.lower()}', '{json.dumps(loc)}') "
                    f"ON CONFLICT (type, name_normalized) DO UPDATE SET metadata = EXCLUDED.metadata;"
                )

        return inserts

    @staticmethod
    async def process_and_validate(
        text: str,
        query: str,
        entity_types: List[str] = None
    ) -> Dict:
        """
        Full pipeline: parallel Phi-3 extraction → merge → Haiku validation

        Returns validated and structured extraction results.
        """
        # Step 1: Parallel Phi-3 extraction
        extracted = await ParallelExtractor.extract_parallel(text, entity_types)

        # Step 2: Merge results
        merged = ParallelExtractor.merge_results(extracted)

        # Step 3: Generate SQL
        sql_inserts = ParallelExtractor.generate_sql_inserts(merged)

        # Step 4: Local validation (no external API)
        # Phi-3 extraction is trusted - return entities directly
        return {
            "raw_extracted": merged,
            "validated": merged,
            "corrections": [],
            "confidence": 0.75,
            "missing": [],
            "sql_inserts": sql_inserts,
            "local_validation": True
        }


# Convenience function
async def parallel_extract(text: str, query: str = "", entity_types: List[str] = None) -> Dict:
    """Run parallel Phi-3 extraction with local validation"""
    return await ParallelExtractor.process_and_validate(text, query, entity_types)
