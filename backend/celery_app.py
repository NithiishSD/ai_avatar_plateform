import os

# pyrefly: ignore [missing-import]
from celery import Celery

from contracts import AudioSynthesisRequest, AvatarRenderJob
from voice_engine import VoiceEngineRouter


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
)


@celery.task(name="avatar.process_render_job")
def process_render_job(payload: dict) -> dict:
    """Validate a queued payload before the renderer is attached."""
    job = AvatarRenderJob.model_validate(payload)
    return {"jobId": job.job_id, "status": "QUEUED"}


@celery.task(name="avatar.synthesize_audio")
def synthesize_audio(payload: dict) -> dict:
    """Run the Developer 1 voice engine from a Celery worker."""
    request = AudioSynthesisRequest.model_validate(payload)
    result = VoiceEngineRouter().synthesize(
        text=request.text,
        mode=request.mode.value,
        language=request.language,
        quality=request.quality,
        speaker_wav=request.speaker_wav,
        output_filename=request.output_filename,
    )
    return result.__dict__