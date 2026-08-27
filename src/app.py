from fastapi import FastAPI, HTTPException, status

from contracts import AvatarRenderJob, RenderJobResponse
import os

from job_queue import CeleryJobQueue, InMemoryJobQueue


app = FastAPI(
    title="AI Avatar Platform API",
    version="1.0.0",
    description="Developer 1 audio and avatar render-job service.",
)
job_queue = CeleryJobQueue() if os.getenv("QUEUE_BACKEND") == "celery" else InMemoryJobQueue()


@app.post(
    "/api/v1/avatar/render-job",
    response_model=RenderJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_render_job(job: AvatarRenderJob) -> RenderJobResponse:
    try:
        queued_job = job_queue.enqueue(job)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return RenderJobResponse(jobId=queued_job.job.job_id, status=queued_job.status)


@app.get("/api/v1/avatar/render-job/{job_id}", response_model=RenderJobResponse)
def get_render_job(job_id: str) -> RenderJobResponse:
    queued_job = job_queue.get(job_id)
    if queued_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="render job not found")
    return RenderJobResponse(jobId=job_id, status=queued_job.status)