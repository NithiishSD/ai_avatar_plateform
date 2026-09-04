import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
dotenv_path = project_root / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
else:
    load_dotenv()

from celery_app import celery, synthesize_audio
from contracts import (
    AudioSynthesisRequest,
    AvatarRenderJob,
    RenderJobResponse,
    SynthesisJobResponse,
    AlignmentRequest,
    AlignmentResponse,
)
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from audio_utils import list_voice_samples, SUPPORTED_EXTENSIONS
from alignment_engine import ForcedAligner
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

inputs_dir = project_root / "inputs"
inputs_dir.mkdir(parents=True, exist_ok=True)

outputs_dir = project_root / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

queue_backend = os.getenv("QUEUE_BACKEND", "in_memory").lower()
job_queue = CeleryJobQueue() if queue_backend == "celery" else InMemoryJobQueue()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class VoiceSampleInfo(BaseModel):
    filename: str
    path: str
    duration_seconds: float
    sample_rate: int
    channels: int
    format: str
    size_bytes: int
    ready_for_cloning: bool
    duration_label: str


class VoiceSamplesResponse(BaseModel):
    samples: List[VoiceSampleInfo]
    supported_formats: List[str]
    inputs_dir: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "queueBackend": os.getenv("QUEUE_BACKEND", "in_memory")}


# ---------------------------------------------------------------------------
# Voice samples — used by UI to list available clone reference files
# ---------------------------------------------------------------------------
@app.get("/api/v1/audio/samples", response_model=VoiceSamplesResponse)
def list_samples() -> VoiceSamplesResponse:
    """
    Return all audio files found in the inputs/ directory.
    Files are listed with format/duration metadata so the frontend
    can display them and let the user pick one for voice cloning.
    """
    samples = list_voice_samples(inputs_dir)
    return VoiceSamplesResponse(
        samples=[
            VoiceSampleInfo(
                filename=s.filename,
                path=s.path,
                duration_seconds=round(s.duration_seconds, 2),
                sample_rate=s.sample_rate,
                channels=s.channels,
                format=s.format,
                size_bytes=s.size_bytes,
                ready_for_cloning=s.ready_for_cloning,
                duration_label=s.duration_label,
            )
            for s in samples
        ],
        supported_formats=sorted(SUPPORTED_EXTENSIONS),
        inputs_dir=str(inputs_dir),
    )



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
    "/api/v1/audio/align",
    response_model=AlignmentResponse,
    status_code=status.HTTP_200_OK,
)
def align_audio(request: AlignmentRequest) -> AlignmentResponse:
    """Standalone forced alignment extracting millisecond phoneme/viseme timestamps."""
    try:
        # Check if audio_path is relative to outputs/ or inputs/
        audio_path = Path(request.audio_path)
        if not audio_path.is_absolute():
            candidate = project_root / request.audio_path
            if candidate.exists():
                audio_path = candidate
            elif (outputs_dir / request.audio_path).exists():
                audio_path = outputs_dir / request.audio_path
            elif (inputs_dir / request.audio_path).exists():
                audio_path = inputs_dir / request.audio_path

        aligner = ForcedAligner()
        timestamps = aligner.align(
            audio_path_or_tensor=str(audio_path),
            transcript=request.transcript,
            sample_rate=request.sample_rate,
            language=request.language,
        )
        duration_s = timestamps[-1].end_ms / 1000.0 if timestamps else 0.0
        return AlignmentResponse(
            phonemeTimestamps=timestamps,
            durationSeconds=duration_s,
            phonemeCount=len(timestamps),
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Alignment failed: {str(err)}",
        ) from err


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
        output_path = None
        duration_seconds = None
        phoneme_timestamps = None
        if task_status == "SUCCESS" and hasattr(task, "result") and isinstance(task.result, dict):
            model_used = task.result.get("model")
            output_path = task.result.get("output_path")
            duration_seconds = task.result.get("duration_seconds")
            phoneme_timestamps = task.result.get("phoneme_timestamps")
        return SynthesisJobResponse(
            taskId=task.id,
            status=task_status,
            modelUsed=model_used,
            outputPath=output_path,
            durationSeconds=duration_seconds,
            phonemeTimestamps=phoneme_timestamps,
        )
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
        output_path = None
        duration_seconds = None
        phoneme_timestamps = None
        if task.state == "SUCCESS" and isinstance(task.result, dict):
            model_used = task.result.get("model")
            output_path = task.result.get("output_path")
            duration_seconds = task.result.get("duration_seconds")
            phoneme_timestamps = task.result.get("phoneme_timestamps")
        return SynthesisJobResponse(
            taskId=task_id,
            status=task_status,
            modelUsed=model_used,
            outputPath=output_path,
            durationSeconds=duration_seconds,
            phonemeTimestamps=phoneme_timestamps,
        )
    except Exception as error:
        return SynthesisJobResponse(taskId=task_id, status="UNKNOWN")