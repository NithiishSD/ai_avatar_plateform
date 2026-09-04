import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

from contracts import AvatarRenderJob, JobStatus
from redis import Redis


@dataclass(frozen=True)
class QueuedJob:
    job: AvatarRenderJob
    status: JobStatus = JobStatus.QUEUED


class InMemoryJobQueue:
    """Small queue adapter used until the Redis/Celery worker is wired in."""

    def __init__(self):
        self._jobs: Dict[str, QueuedJob] = {}

    def enqueue(self, job: AvatarRenderJob) -> QueuedJob:
        if job.job_id in self._jobs:
            raise ValueError(f"jobId already exists: {job.job_id}")
        queued_job = QueuedJob(job=job)
        self._jobs[job.job_id] = queued_job
        return queued_job

    def get(self, job_id: str) -> Optional[QueuedJob]:
        return self._jobs.get(job_id)


class CeleryJobQueue:
    """Publishes validated jobs to the configured Celery broker."""

    def __init__(self, redis_client: Optional[Redis] = None):
        self._redis = redis_client or Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )

    @staticmethod
    def _key(job_id: str) -> str:
        return f"avatar:render-job:{job_id}"

    def enqueue(self, job: AvatarRenderJob) -> QueuedJob:
        if self._redis.exists(self._key(job.job_id)):
            raise ValueError(f"jobId already exists: {job.job_id}")
        from celery_app import process_render_job

        queued_job = QueuedJob(job=job)
        self._redis.set(
            self._key(job.job_id),
            json.dumps({"job": job.model_dump(by_alias=True, mode="json"), "status": queued_job.status.value}),
        )
        process_render_job.delay(job.model_dump(by_alias=True, mode="json"))
        return queued_job

    def get(self, job_id: str) -> Optional[QueuedJob]:
        stored_job = self._redis.get(self._key(job_id))
        if stored_job is None:
            return None
        assert isinstance(stored_job, (str, bytes))
        payload = json.loads(stored_job)
        return QueuedJob(
            job=AvatarRenderJob.model_validate(payload["job"]),
            status=JobStatus(payload["status"]),
        )