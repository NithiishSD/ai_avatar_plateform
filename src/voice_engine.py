import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
import soundfile as sf
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
INPUT_DIR = PROJECT_ROOT / "inputs"
OUTPUT_DIR.mkdir(exist_ok=True)
INPUT_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class SynthesisResult:
    output_path: str
    sample_rate: int
    duration_seconds: float
    latency_ms: float
    model: str
    mode: str


class VoiceEngineRouter:
    """
    Multi-Model TTS Orchestration Router (PDF Specification Section 5)
    Routes synthesis requests dynamically based on latency and quality needs.
    """
    def __init__(self, device="cuda"):
        self.device = device if torch.cuda.is_available() else "cpu"
        print(f"[Router Initialized] Processing Device: {self.device.upper()}")
        self.kokoro_pipeline = None
        self.xtts_model = None

    def select_model(
        self,
        mode: str = "fast",
        language: str = "en",
        quality: str = "balanced",
    ) -> str:
        """Select the first available model for the requested workload."""
        normalized_language = language.lower().replace("_", "-")
        if mode == "clone":
            return "xtts-v2"
        if mode != "fast":
            raise ValueError("Invalid mode! Choose 'fast' or 'clone'.")
        if quality not in {"fast", "balanced", "high"}:
            raise ValueError("Invalid quality! Choose 'fast', 'balanced', or 'high'.")
        if normalized_language not in {"en", "en-us", "en-gb"}:
            raise ValueError(
                "Kokoro currently supports English only; use mode='clone' for multilingual synthesis."
            )
        return "kokoro"

    def load_kokoro_realtime(self):
        """Loads Kokoro-82M for real-time sub-100ms streaming generation."""
        if self.kokoro_pipeline is None:
            print("\n[Loading Model] Initializing Kokoro v1.0 (82M params) for Real-Time Mode...")
            from kokoro import KPipeline
            self.kokoro_pipeline = KPipeline(lang_code='a')  # 'a' = American English
            print(" -> Kokoro v1.0 loaded successfully.")

    def load_xtts_cloning(self):
        """Loads XTTS-v2 for Zero-Shot Voice Cloning from 30-60s audio samples."""
        if self.xtts_model is None:
            print("\n[Loading Model] Initializing XTTS-v2 for Zero-Shot Voice Cloning...")
            from TTS.api import TTS
            self.xtts_model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
            print(" -> XTTS-v2 loaded successfully.")

    def synthesize(
        self,
        text: str,
        mode: str = "fast",
        speaker_wav: Optional[str] = None,
        output_filename: str = "speech.wav",
        language: str = "en",
        quality: str = "balanced",
    ) -> SynthesisResult:
        """
        Executes synthesis based on target mode:
        - mode='fast': Real-time streaming via Kokoro-82M (<100ms target)
        - mode='clone': Zero-shot voice cloning via XTTS-v2 (>90% similarity target)
        """
        if not text.strip():
            raise ValueError("text must not be empty")
        model_name = self.select_model(mode=mode, language=language, quality=quality)
        start_time = time.time()
        output_path = OUTPUT_DIR / output_filename

        if mode == "fast":
            self.load_kokoro_realtime()
            print(f"\n[Synthesizing - Real-time Mode] Generating audio for: '{text}'")
            generator = self.kokoro_pipeline(text, voice='af_heart', speed=1.0)
            
            audio_chunks = [audio for _, _, audio in generator]
            if not audio_chunks:
                raise RuntimeError("Kokoro returned no audio chunks")
            combined_audio = np.concatenate(audio_chunks)
            sf.write(output_path, combined_audio, 24000)
            sample_rate = 24000
            duration_seconds = len(combined_audio) / sample_rate

        elif mode == "clone":
            if not speaker_wav or not os.path.exists(speaker_wav):
                raise FileNotFoundError(
                    f"❌ Voice cloning requires a reference audio file at '{speaker_wav}'. "
                    "Please place a 30-60s .wav clip in inputs/voice_sample.wav!"
                )
            
            self.load_xtts_cloning()
            print(f"\n[Synthesizing - Voice Clone Mode] Cloning speaker from '{speaker_wav}'...")
            print(f" -> Input Text: '{text}'")
            
            # XTTS Zero-Shot Voice Generation
            self.xtts_model.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language="en",
                file_path=output_path
            )
            sample_rate = 24000
            duration_seconds = float(sf.info(output_path).duration)

        latency = (time.time() - start_time) * 1000
        print("----------------------------------------------------------")
        print(f"✅ SUCCESS: Audio saved to -> {os.path.abspath(output_path)}")
        print(f"⏱️  Synthesis Latency: {latency:.2f} ms")
        print("==========================================================")
        return SynthesisResult(
            output_path=str(output_path),
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
            latency_ms=latency,
            model=model_name,
            mode=mode,
        )


# ==========================================================
# EXECUTION & BENCHMARK TEST
# ==========================================================
if __name__ == "__main__":
    router = VoiceEngineRouter()

    # TEST 1: Real-Time Fast Synthesis (Kokoro-82M)
    print("\n--- RUNNING TEST 1: REAL-TIME STREAMING TTS ---")
    script_1 = "Hello! I am your AI avatar running real-time speech synthesis on your local GPU."
    router.synthesize(text=script_1, mode="fast", output_filename="fast_speech.wav")

    # TEST 2: Zero-Shot Voice Cloning (XTTS-v2)
    print("\n--- RUNNING TEST 2: ZERO-SHOT VOICE CLONING ---")
    reference_audio = "inputs/voice_sample.wav"
    script_2 = "This audio was generated by cloning the target voice using zero-shot deep learning."
    
    if os.path.exists(reference_audio):
        router.synthesize(
            text=script_2, 
            mode="clone", 
            speaker_wav=reference_audio, 
            output_filename="cloned_speech.wav"
        )
    else:
        print(f"⚠️ SKIPPING TEST 2: '{reference_audio}' not found.")
        print(" -> To run voice cloning, add a 30-60s .wav recording into the inputs/ directory!")