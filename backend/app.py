import os
from contextlib import asynccontextmanager
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
    EmotionPresetEntry,
    EmotionPresetsResponse,
    LanguageEntry,
    LanguagesResponse,
    QualityAuditRequest,
    QualityAuditResponse,
    VoiceSimilarityRequest,
    VoiceSimilarityResponse,
)
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import language_registry
from audio_utils import list_voice_samples, SUPPORTED_EXTENSIONS
from alignment_engine import ForcedAligner, PhonemeToVisemeMapper
from emotion_engine import preset_catalogue
from job_queue import CeleryJobQueue, InMemoryJobQueue
from model_registry import audit_summary, log_weight_audit
from quality_auditor import SpeechQualityAuditor
from security import API_KEY_HEADER, SecurityGate



@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Audit model weights before serving a single request.

    Printed as well as logged: the router's fallbacks are silent by design, so
    a missing checkpoint has to be impossible to miss in the server output.
    """
    statuses = log_weight_audit()
    missing = [s for s in statuses if not s.present]
    print("=" * 60)
    print(f"[Model Weights] {len(statuses) - len(missing)}/{len(statuses)} available")
    for status in statuses:
        mark = "OK  " if status.present else "MISS"
        print(f"  {mark}  {status.key:<13} {status.size_label:>8}  {status.detail}")
    if missing:
        print(
            f"[Model Weights] {len(missing)} model(s) will fall back: "
            f"{', '.join(s.key for s in missing)}"
        )
        print("[Model Weights] Fetch them with: python scripts/fetch_models.py")
    print("=" * 60)
    yield


app = FastAPI(
    title="AI Avatar Platform API",
    version="1.0.0",
    description="Developer 1 audio and avatar render-job service.",
    lifespan=lifespan,
)
# Vite picks the next free port when 5173 is taken, so pinning a single port
# breaks the dev server silently. Any loopback port is allowed in development;
# set CORS_ORIGINS to an explicit comma-separated list for deployment.
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or [],
    allow_origin_regex=None if _cors_origins else r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-key auth + per-identity rate limiting. Both are configured from .env and
# auth is off by default so local development needs no key.
security_gate = SecurityGate()


@app.middleware("http")
async def enforce_security(request: Request, call_next):
    # CORS preflight carries no headers to authenticate; let the CORS
    # middleware answer it.
    if request.method == "OPTIONS":
        return await call_next(request)

    allowed, status_code, detail = security_gate.inspect(
        path=request.url.path,
        api_key=request.headers.get(API_KEY_HEADER),
        client_host=request.client.host if request.client else None,
    )
    if not allowed:
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail.get("detail", "request rejected")},
            headers=detail.get("headers", {}),
        )
    return await call_next(request)

inputs_dir = project_root / "inputs"
inputs_dir.mkdir(parents=True, exist_ok=True)

outputs_dir = project_root / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

queue_backend = os.getenv("QUEUE_BACKEND", "in_memory").lower()
job_queue = CeleryJobQueue() if queue_backend == "celery" else InMemoryJobQueue()

# One auditor for the process: SQUIM weights load once, on first audit.
quality_auditor = SpeechQualityAuditor()


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
    return {
        "status": "ok",
        "queueBackend": os.getenv("QUEUE_BACKEND", "in_memory"),
        "security": security_gate.describe(),
        "capabilities": {
            # Keys the router can select. Routable is not the same as usable:
            # modelWeights below says which ones have weights on disk.
            "models": ["kokoro", "xtts-v2", "higgs-tts-2", "dia-1.6b", "mms-tts"],
            "languages": language_registry.supported_count(),
            "emotions": [preset["name"] for preset in preset_catalogue()],
            "visemes": PhonemeToVisemeMapper.get_supported_visemes(),
        },
        "modelWeights": audit_summary(),
    }


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def resolve_audio_path(raw: str) -> Path:
    """
    Resolve a caller-supplied audio path to a file inside the project.

    Absolute paths are honoured; relative ones are tried against the project
    root, ``outputs/`` and ``inputs/``. Anything that resolves outside those
    three roots is rejected, so a path like ``../../etc/passwd`` cannot be used
    to read arbitrary files through the audit endpoints.
    """
    candidate = Path(raw)
    roots = (project_root, outputs_dir, inputs_dir)
    if not candidate.is_absolute():
        for root in roots:
            option = (root / raw)
            if option.exists():
                candidate = option
                break
        else:
            candidate = project_root / raw

    resolved = candidate.resolve()
    if not any(
        resolved == root.resolve() or root.resolve() in resolved.parents
        for root in roots
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio path must be inside the project inputs/ or outputs/ folder",
        )
    if not resolved.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"audio file not found: {raw}",
        )
    return resolved


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
        audio_path = resolve_audio_path(request.audio_path)
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
    except HTTPException:
        raise
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Alignment failed: {str(err)}",
        ) from err


def _job_response(task_id: str, task_status: str, result: dict) -> SynthesisJobResponse:
    """Project a completed VoiceEngineRouter result onto the API response."""
    return SynthesisJobResponse(
        taskId=task_id,
        status=task_status,
        modelUsed=result.get("model"),
        outputPath=result.get("output_path"),
        durationSeconds=result.get("duration_seconds"),
        phonemeTimestamps=result.get("phoneme_timestamps"),
        emotion=result.get("emotion"),
        qualityReport=result.get("quality_report"),
        language=result.get("language"),
        latencyMs=result.get("latency_ms"),
    )


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
        result = task.result if hasattr(task, "result") else None
        if task_status == "SUCCESS" and isinstance(result, dict):
            return _job_response(task.id, task_status, result)
        return SynthesisJobResponse(taskId=task.id, status=task_status)
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
        if task.state == "SUCCESS" and isinstance(task.result, dict):
            return _job_response(task_id, task_status, task.result)
        return SynthesisJobResponse(taskId=task_id, status=task_status)
    except Exception as error:
        return SynthesisJobResponse(taskId=task_id, status="UNKNOWN")

# ---------------------------------------------------------------------------
# Phase 3 — multilingual catalogue, emotion presets, quality auditing
# ---------------------------------------------------------------------------
@app.get("/api/v1/audio/languages", response_model=LanguagesResponse)
def list_languages(q: str = "", limit: int = 100) -> LanguagesResponse:
    """
    Search the MMS-TTS language catalogue.

    ``q`` matches ISO-639-3 codes and language names; ``limit=0`` returns the
    whole catalogue.
    """
    limit = max(0, min(limit, language_registry.supported_count()))
    matches = language_registry.search(q, limit=limit)
    return LanguagesResponse(
        total=language_registry.supported_count(),
        returned=len(matches),
        query=q,
        source=language_registry.catalogue_source(),
        languages=[LanguageEntry.model_validate(info.to_dict()) for info in matches],
    )


@app.get("/api/v1/audio/languages/{code}", response_model=LanguageEntry)
def describe_language(code: str) -> LanguageEntry:
    """Resolve one code and report which backends can speak it."""
    return LanguageEntry.model_validate(language_registry.resolve(code).to_dict())


@app.get("/api/v1/audio/emotions", response_model=EmotionPresetsResponse)
def list_emotions() -> EmotionPresetsResponse:
    """The emotion prosody presets and the prosody each one applies."""
    return EmotionPresetsResponse(
        presets=[EmotionPresetEntry.model_validate(p) for p in preset_catalogue()],
    )


@app.post(
    "/api/v1/audio/quality-audit",
    response_model=QualityAuditResponse,
    status_code=status.HTTP_200_OK,
)
def audit_quality(request: QualityAuditRequest) -> QualityAuditResponse:
    """Predict MOS, PESQ, STOI and SI-SDR for a generated clip (SQUIM)."""
    audio_path = resolve_audio_path(request.audio_path)
    reference = (
        resolve_audio_path(request.reference_path) if request.reference_path else None
    )
    try:
        report = quality_auditor.audit(audio_path, reference_path=reference)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quality audit failed: {err}",
        ) from err
    return QualityAuditResponse(audioPath=str(audio_path), report=report.to_dict())


@app.post(
    "/api/v1/audio/voice-similarity",
    response_model=VoiceSimilarityResponse,
    status_code=status.HTTP_200_OK,
)
def voice_similarity(request: VoiceSimilarityRequest) -> VoiceSimilarityResponse:
    """
    Speaker-similarity score between a cloning reference and its output.

    The response names the scoring method: only an ``ecapa-tdnn`` result counts
    as evidence for the assignment's >85% cloning-similarity threshold.
    """
    reference = resolve_audio_path(request.reference_path)
    generated = resolve_audio_path(request.generated_path)
    try:
        report = quality_auditor.speaker_similarity(reference, generated)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Similarity scoring failed: {err}",
        ) from err
    return VoiceSimilarityResponse(report=report.to_dict())
