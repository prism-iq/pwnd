"""
Job Queue System for Background Tasks
Handles file uploads, processing, entity extraction
"""
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import json

class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    DONE = "done"
    ERROR = "error"

@dataclass
class Job:
    """Background job"""
    id: str
    type: str  # upload, extract, process
    status: JobStatus
    filename: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: int = 0
    total: int = 100
    error: Optional[str] = None
    result: Optional[Dict] = None
    metadata: Dict = field(default_factory=dict)

class JobQueue:
    """
    Global job queue with SSE support
    Singleton pattern for shared state
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs: Dict[str, Job] = {}
            cls._instance._subscribers: Dict[str, List[asyncio.Queue]] = {}
        return cls._instance

    def create_job(self, job_type: str, filename: str, metadata: Dict = None) -> str:
        """Create new job and return ID"""
        job_id = str(uuid.uuid4())

        job = Job(
            id=job_id,
            type=job_type,
            status=JobStatus.QUEUED,
            filename=filename,
            created_at=datetime.now(),
            metadata=metadata or {}
        )

        self._jobs[job_id] = job
        self._subscribers[job_id] = []

        # Notify subscribers
        asyncio.create_task(self._broadcast(job_id, {
            "event": "created",
            "job": self._job_to_dict(job)
        }))

        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        result: Optional[Dict] = None
    ):
        """Update job state and notify subscribers"""
        job = self._jobs.get(job_id)
        if not job:
            return

        if status:
            job.status = status
            if status == JobStatus.PROCESSING and not job.started_at:
                job.started_at = datetime.now()
            elif status in [JobStatus.DONE, JobStatus.ERROR]:
                job.completed_at = datetime.now()

        if progress is not None:
            job.progress = progress

        if error:
            job.error = error

        if result:
            job.result = result

        # Broadcast update
        asyncio.create_task(self._broadcast(job_id, {
            "event": "updated",
            "job": self._job_to_dict(job)
        }))

    async def subscribe(self, job_id: str) -> AsyncGenerator[Dict, None]:
        """
        Subscribe to job updates via SSE
        Yields events as they happen
        """
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []

        queue = asyncio.Queue()
        self._subscribers[job_id].append(queue)

        # Send current state immediately
        job = self._jobs.get(job_id)
        if job:
            yield {
                "event": "current",
                "job": self._job_to_dict(job)
            }

        try:
            while True:
                event = await queue.get()
                yield event

                # Stop if job is done or error
                if event.get("job", {}).get("status") in ["done", "error"]:
                    break
        finally:
            # Cleanup
            if queue in self._subscribers.get(job_id, []):
                self._subscribers[job_id].remove(queue)

    async def _broadcast(self, job_id: str, event: Dict):
        """Broadcast event to all subscribers of this job"""
        subscribers = self._subscribers.get(job_id, [])
        for queue in subscribers:
            await queue.put(event)

    def _job_to_dict(self, job: Job) -> Dict:
        """Convert job to dict for JSON serialization"""
        return {
            "id": job.id,
            "type": job.type,
            "status": job.status.value,
            "filename": job.filename,
            "progress": job.progress,
            "total": job.total,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error,
            "result": job.result,
            "metadata": job.metadata
        }

    def list_jobs(self, limit: int = 50) -> List[Dict]:
        """List all jobs (recent first)"""
        jobs = sorted(
            self._jobs.values(),
            key=lambda j: j.created_at,
            reverse=True
        )[:limit]

        return [self._job_to_dict(job) for job in jobs]

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove jobs older than max_age_hours"""
        now = datetime.now()
        to_remove = []

        for job_id, job in self._jobs.items():
            age = (now - job.created_at).total_seconds() / 3600
            if age > max_age_hours and job.status in [JobStatus.DONE, JobStatus.ERROR]:
                to_remove.append(job_id)

        for job_id in to_remove:
            del self._jobs[job_id]
            if job_id in self._subscribers:
                del self._subscribers[job_id]

# Global instance
job_queue = JobQueue()
