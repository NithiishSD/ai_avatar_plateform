from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RenderQuality(str, Enum):
    PREVIEW = "PREVIEW"
    HD_1080P = "1080P_HQ"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SynthesisMode(str, Enum):
    FAST = "fast"
    CLONE = "clone"
    HIGH_QUALITY = "high_quality"
    DIALOGUE = "dialogue"


class PhonemeTimestamp(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    phoneme: str = Field(min_length=1)
    viseme: str = Field(min_length=1)
    start_ms: int = Field(alias="startMs", ge=0)
    end_ms: int = Field(alias="endMs", gt=0)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("endMs must be greater than startMs")
        return self


class EmotionVector(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    happy: float = Field(ge=0, le=1)
    neutral: float = Field(ge=0, le=1)
    eyeblink_rate: float = Field(alias="eyeblinkRate", ge=0, le=10)


class AvatarRenderJob(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    job_id: str = Field(alias="jobId", min_length=1)
    avatar_id: str = Field(alias="avatarId", min_length=1)
    audio_url: str = Field(alias="audioUrl", min_length=1)
    sample_rate: int = Field(alias="sampleRate", ge=8000, le=192000)
    duration_seconds: float = Field(alias="durationSeconds", gt=0, le=3600)
    phoneme_timestamps: List[PhonemeTimestamp] = Field(alias="phonemeTimestamps", min_length=1)
    emotion_vector: EmotionVector = Field(alias="emotionVector")
    render_quality: RenderQuality = Field(alias="renderQuality")
    target_fps: int = Field(alias="targetFps", ge=1, le=120)

    @field_validator("audio_url")
    @classmethod
    def validate_audio_url(cls, value: str) -> str:
        if "://" not in value:
            raise ValueError("audioUrl must be an absolute storage or HTTP URL")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self):
        previous_start = -1
        duration_ms = self.duration_seconds * 1000
        for timestamp in self.phoneme_timestamps:
            if timestamp.start_ms < previous_start:
                raise ValueError("phonemeTimestamps must be ordered by startMs")
            if timestamp.end_ms > duration_ms:
                raise ValueError("phoneme timestamp exceeds durationSeconds")
            previous_start = timestamp.start_ms
        return self


class RenderJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    status: JobStatus


class AudioSynthesisRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str = Field(min_length=1)
    mode: SynthesisMode = SynthesisMode.FAST
    language: str = Field(default="en", min_length=2, max_length=16)
    quality: str = Field(default="balanced", pattern="^(fast|balanced|high)$")
    style: Optional[str] = Field(
        default=None,
        description="Optional style hint: 'dialogue', 'expressive', 'narration'",
    )
    speaker_wav: Optional[str] = Field(default=None, alias="speakerWav")
    output_filename: str = Field(default="speech.wav", alias="outputFilename", min_length=1)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty")
        return value


class AudioSynthesisResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    output_path: str = Field(alias="outputPath")
    sample_rate: int = Field(alias="sampleRate")
    duration_seconds: float = Field(alias="durationSeconds")
    latency_ms: float = Field(alias="latencyMs")
    model: str
    mode: SynthesisMode


class SynthesisJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    status: str
    model_used: Optional[str] = Field(default=None, alias="modelUsed")