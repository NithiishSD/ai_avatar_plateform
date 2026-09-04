import os
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
dotenv_path = project_root / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
else:
    load_dotenv()

from celery_app import celery, synthesize_audio
from contracts import AudioSynthesisRequest, AvatarRenderJob, RenderJobResponse, SynthesisJobResponse
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

outputs_dir = project_root / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

queue_backend = os.getenv("QUEUE_BACKEND", "in_memory").lower()
job_queue = CeleryJobQueue() if queue_backend == "celery" else InMemoryJobQueue()


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
    try:
        task = synthesize_audio.delay(request.model_dump(by_alias=True, mode="json"))
        task_status = getattr(task, "status", "QUEUED")
        if task_status == "PENDING":
            task_status = "QUEUED"
        # For eager (in-memory) mode, task result is available immediately
        model_used = None
        if task_status == "SUCCESS" and hasattr(task, "result") and isinstance(task.result, dict):
            model_used = task.result.get("model")
        return SynthesisJobResponse(taskId=task.id, status=task_status, modelUsed=model_used)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Synthesis service unavailable: {str(error)}",
        ) from error


@app.get("/api/v1/audio/synthesize/{task_id}", response_model=SynthesisJobResponse)
def get_synthesis_job(task_id: str) -> SynthesisJobResponse:
    try:
        task = celery.AsyncResult(task_id)
        state_mapping = {
            "PENDING": "QUEUED",
            "STARTED": "PROCESSING",
            "SUCCESS": "SUCCESS",
            "FAILURE": "FAILED",
            "RETRY": "RETRYING",
            "REVOKED": "CANCELLED",
        }
        task_status = state_mapping.get(task.state, task.state)
        model_used = None
        if task.state == "SUCCESS" and isinstance(task.result, dict):
            model_used = task.result.get("model")
        return SynthesisJobResponse(taskId=task_id, status=task_status, modelUsed=model_used)
    except Exception as error:
        return SynthesisJobResponse(taskId=task_id, status="UNKNOWN")