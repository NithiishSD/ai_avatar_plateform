import os
import threading
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
dotenv_path = project_root / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
else:
    load_dotenv()

from celery import Celery

from contracts import AudioSynthesisRequest, AvatarRenderJob
from voice_engine import VoiceEngineRouter

# One router per worker process. Building a new one per task threw away every
# lazily-loaded model and paid the cold-start cost on every request.
_router: Optional[VoiceEngineRouter] = None
_router_lock = threading.Lock()


def get_router() -> VoiceEngineRouter:
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = VoiceEngineRouter()
    return _router



is_in_memory = os.getenv("QUEUE_BACKEND", "in_memory").lower() != "celery"

if is_in_memory:
    celery = Celery(
        "avatar_platform",
        broker="memory://",
        backend="cache+memory://",
    )
else:
    celery = Celery(
        "avatar_platform",
        broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    )

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=is_in_memory,
    task_store_eager_result=is_in_memory,
)


@celery.task(name="avatar.process_render_job")
def process_render_job(payload: dict) -> dict:
    """Validate a queued payload before the renderer is attached."""
    job = AvatarRenderJob.model_validate(payload)
    return {"jobId": job.job_id, "status": "QUEUED"}


@celery.task(name="avatar.synthesize_audio")
def synthesize_audio(payload: dict) -> dict:
    """Run the Developer 1 voice engine from a Celery task."""
    request = AudioSynthesisRequest.model_validate(payload)
    result = get_router().synthesize(
        text=request.text,
        mode=request.mode.value,
        language=request.language,
        quality=request.quality,
        style=request.style,
        speed=request.speed,
        pitch=request.pitch,
        return_alignment=request.return_alignment,
        emotion=request.emotion,
        emotion_intensity=request.emotion_intensity,
        emotion_vector=request.emotion_vector,
        audit_quality=request.audit_quality,
        speaker_wav=request.speaker_wav,
        output_filename=request.output_filename,
    )
    return result.__dict__