import os

from celery_app import celery, synthesize_audio
from contracts import AudioSynthesisRequest, AvatarRenderJob, RenderJobResponse, SynthesisJobResponse
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from job_queue import CeleryJobQueue, InMemoryJobQueue


app = FastAPI(
    title="AI Avatar Platform API",
    version="1.0.0",
    description="Developer 1 audio and avatar render-job service.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
job_queue = CeleryJobQueue() if os.getenv("QUEUE_BACKEND") == "celery" else InMemoryJobQueue()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "queueBackend": os.getenv("QUEUE_BACKEND", "in_memory")}


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


@app.post(
    "/api/v1/audio/synthesize",
    response_model=SynthesisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_synthesis_job(request: AudioSynthesisRequest) -> SynthesisJobResponse:
    task = synthesize_audio.delay(request.model_dump(by_alias=True, mode="json"))
    return SynthesisJobResponse(taskId=task.id, status="QUEUED")


@app.get("/api/v1/audio/synthesize/{task_id}", response_model=SynthesisJobResponse)
def get_synthesis_job(task_id: str) -> SynthesisJobResponse:
    task = celery.AsyncResult(task_id)
    task_status = "QUEUED" if task.state == "PENDING" else task.state
    return SynthesisJobResponse(taskId=task_id, status=task_status)