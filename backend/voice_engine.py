"""
VoiceEngineRouter — Multi-Model TTS Orchestration (Phase 1)
============================================================
Routing matrix:
  fast        + English       → Kokoro-82M      (sub-second, real-time)
  clone                       → XTTS-v2         (zero-shot voice cloning)
  high_quality | quality=high → Higgs TTS 2     (MOS >4.0, multilingual)
  non-English language        → Higgs TTS 2     (Kokoro is English-only)
  dialogue    | style=dialogue → Dia-1.6B       (multi-speaker [S1]/[S2])
  Higgs unavailable (OOM)     → XTTS-v2 fallback
  Dia unavailable             → Kokoro fallback
"""

import os
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
import soundfile as sf
import numpy as np

from audio_utils import validate_and_convert_for_cloning, AudioValidationError

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
INPUT_DIR = PROJECT_ROOT / "inputs"
OUTPUT_DIR.mkdir(exist_ok=True)
INPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Supported English language codes for Kokoro routing
# ---------------------------------------------------------------------------
_KOKORO_ENGLISH_CODES = {"en", "en-us", "en-gb", "en-au", "en-ca"}

# ---------------------------------------------------------------------------
# Higgs TTS 2 default voice preset (no reference audio required)
# ---------------------------------------------------------------------------
_HIGGS_DEFAULT_VOICE = "default"

# ---------------------------------------------------------------------------
# Dia speaker tag pattern — if text contains [S1] or [S2] triggers Dia
# ---------------------------------------------------------------------------
_DIA_SPEAKER_TAGS = {"[S1]", "[S2]", "[s1]", "[s2]"}


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
    Intelligent Multi-Model TTS Orchestration Router.

    Lazily loads each model on first use to keep startup fast.
    All models are cached in instance attributes after first load.
    """

    def __init__(self, device: Optional[str] = None):
        if device is not None:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Router Initialized] Processing Device: {self.device.upper()}")

        # Lazy-loaded model handles
        self.kokoro_pipeline = None   # Kokoro-82M
        self.xtts_model = None        # XTTS-v2
        self._higgs_pipe = None       # Higgs TTS 2 (3B)
        self._dia_model = None        # Dia-1.6B
        self._dia_processor = None

        # Track load failures to avoid retrying broken models
        self._higgs_failed = False
        self._dia_failed = False

    # ------------------------------------------------------------------
    # Model Selection — Routing Decision Matrix
    # ------------------------------------------------------------------

    def select_model(
        self,
        mode: str = "fast",
        language: str = "en",
        quality: str = "balanced",
        style: Optional[str] = None,
        text: str = "",
    ) -> str:
        """
        Returns the canonical model key for the given request parameters.

        Priority order:
          1. Explicit dialogue mode / style or [S1]/[S2] tags → dia
          2. Explicit clone mode → xtts-v2
          3. Explicit high_quality mode OR quality=high → higgs-tts-2
          4. Non-English language → higgs-tts-2
          5. fast mode English → kokoro
          6. Unknown mode → raise ValueError
        """
        normalized_lang = language.lower().replace("_", "-")

        # 1. Dialogue detection
        is_dialogue_mode = mode == "dialogue"
        is_dialogue_style = (style or "").lower() in {"dialogue", "multi-speaker"}
        has_speaker_tags = any(tag in text for tag in _DIA_SPEAKER_TAGS)

        if is_dialogue_mode or is_dialogue_style or has_speaker_tags:
            if self._dia_failed:
                logger.warning("Dia unavailable — falling back to Kokoro for dialogue request")
                return "kokoro"
            return "dia-1.6b"

        # 2. Voice cloning
        if mode == "clone":
            return "xtts-v2"

        # 3. Explicit high quality mode
        if mode == "high_quality" or quality == "high":
            if self._higgs_failed:
                logger.warning("Higgs unavailable — falling back to XTTS-v2 for high_quality request")
                return "xtts-v2"
            return "higgs-tts-2"

        # 4. Non-English → Higgs (Kokoro is English-only)
        if normalized_lang not in _KOKORO_ENGLISH_CODES:
            if self._higgs_failed:
                raise ValueError(
                    f"Language '{language}' requires Higgs TTS 2, but it failed to load. "
                    "Use mode='clone' with XTTS-v2 for multilingual synthesis."
                )
            return "higgs-tts-2"

        # 5. Fast English
        if mode == "fast":
            return "kokoro"

        # 6. Unknown
        raise ValueError(
            f"Unsupported mode='{mode}'. "
            "Valid modes: 'fast', 'clone', 'high_quality', 'dialogue'."
        )

    # ------------------------------------------------------------------
    # Model Loaders (lazy, cached)
    # ------------------------------------------------------------------

    def load_kokoro_realtime(self) -> None:
        """Loads Kokoro-82M for real-time sub-100ms streaming generation."""
        if self.kokoro_pipeline is not None:
            return
        print(f"\n[Loading Model] Kokoro v1.0 (82M) on {self.device.upper()}...")
        from kokoro import KPipeline
        self.kokoro_pipeline = KPipeline(lang_code="a", device=self.device)
        print(" -> Kokoro v1.0 loaded.")

    def load_xtts_cloning(self) -> None:
        """Loads XTTS-v2 for zero-shot voice cloning."""
        if self.xtts_model is not None:
            return
        print(f"\n[Loading Model] XTTS-v2 on {self.device.upper()}...")
        from TTS.api import TTS
        self.xtts_model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
        if self.device == "cuda" and torch.cuda.is_available():
            self.xtts_model = self.xtts_model.to("cuda")
        else:
            self.xtts_model = self.xtts_model.to("cpu")
        print(" -> XTTS-v2 loaded.")

    def load_higgs(self) -> bool:
        """
        Loads Higgs TTS 2 (3B, bosonai/higgs-tts-2-3b-base) via transformers pipeline.
        Returns True on success, False on failure (OOM / missing).
        Caches failure in self._higgs_failed to skip future attempts.
        """
        if self._higgs_pipe is not None:
            return True
        if self._higgs_failed:
            return False

        print(f"\n[Loading Model] Higgs TTS 2 (3B) on {self.device.upper()}...")
        try:
            from transformers import pipeline as hf_pipeline

            device_arg = 0 if self.device == "cuda" else -1
            self._higgs_pipe = hf_pipeline(
                "text-to-speech",
                model="bosonai/higgs-tts-2-3b-base",
                device=device_arg,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            )
            print(" -> Higgs TTS 2 (3B) loaded.")
            return True
        except Exception as exc:
            logger.error("Higgs TTS 2 failed to load: %s", exc)
            self._higgs_failed = True
            print(f" -> [WARNING] Higgs TTS 2 load failed: {exc}")
            return False

    def load_dia(self) -> bool:
        """
        Loads Dia-1.6B (nari-labs/Dia-1.6B) via transformers AutoModel API.
        Returns True on success, False on failure.
        Caches failure in self._dia_failed.
        """
        if self._dia_model is not None:
            return True
        if self._dia_failed:
            return False

        print(f"\n[Loading Model] Dia-1.6B on {self.device.upper()}...")
        try:
            from transformers import AutoProcessor, AutoModel

            model_id = "nari-labs/Dia-1.6B"
            self._dia_processor = AutoProcessor.from_pretrained(model_id)
            self._dia_model = AutoModel.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map=self.device if self.device == "cuda" else None,
            )
            if self.device == "cpu":
                self._dia_model = self._dia_model.to("cpu")
            print(" -> Dia-1.6B loaded.")
            return True
        except Exception as exc:
            logger.error("Dia-1.6B failed to load: %s", exc)
            self._dia_failed = True
            print(f" -> [WARNING] Dia-1.6B load failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Synthesis Backends
    # ------------------------------------------------------------------

    def _synthesize_kokoro(self, text: str, output_path: Path) -> tuple[int, float]:
        """Run Kokoro-82M synthesis. Returns (sample_rate, duration_seconds)."""
        self.load_kokoro_realtime()
        assert self.kokoro_pipeline is not None
        print(f"\n[Kokoro] Synthesizing: '{text[:80]}...'")
        generator = self.kokoro_pipeline(text, voice="af_heart", speed=1.0)
        chunks = [audio for _, _, audio in generator]
        if not chunks:
            raise RuntimeError("Kokoro returned no audio chunks")
        audio = np.concatenate(chunks)
        sample_rate = 24000
        sf.write(output_path, audio, sample_rate)
        return sample_rate, len(audio) / sample_rate

    def _synthesize_xtts(
        self,
        text: str,
        output_path: Path,
        speaker_wav: Optional[str],
        language: str,
    ) -> tuple[int, float]:
        """Run XTTS-v2 voice cloning. Returns (sample_rate, duration_seconds)."""
        if not speaker_wav:
            raise FileNotFoundError(
                "Voice cloning requires a reference audio file.\n"
                "Place a WAV/MP3/FLAC recording (30–60 s) into the inputs/ folder, "
                "then select it in the UI."
            )

        speaker_path = Path(speaker_wav)
        if not speaker_path.exists():
            raise FileNotFoundError(
                f"Reference audio not found: '{speaker_wav}'\n"
                "Ensure the file is in the inputs/ folder and select it again."
            )

        # Validate + auto-convert to WAV 24 kHz mono (raises AudioValidationError on bad files)
        converted_dir = speaker_path.parent / ".converted"
        ready_path = validate_and_convert_for_cloning(speaker_path, converted_dir=converted_dir)

        self.load_xtts_cloning()
        assert self.xtts_model is not None
        print(f"\n[XTTS-v2] Cloning from '{ready_path.name}', text: '{text[:80]}...'")
        lang_code = language.split("-")[0].lower()  # "en-US" → "en"
        self.xtts_model.tts_to_file(
            text=text,
            speaker_wav=str(ready_path),
            language=lang_code,
            file_path=str(output_path),
        )
        sample_rate = 24000
        duration = float(sf.info(output_path).duration)
        return sample_rate, duration

    def _synthesize_higgs(
        self,
        text: str,
        output_path: Path,
        speaker_wav: Optional[str] = None,
    ) -> tuple[int, float]:
        """
        Run Higgs TTS 2 (3B) synthesis.
        Supports optional speaker_wav for voice cloning.
        Falls back to XTTS-v2 on load failure.
        Returns (sample_rate, duration_seconds).
        """
        if not self.load_higgs():
            print("[WARN] Higgs unavailable — falling back to XTTS-v2")
            # Higgs fallback: use XTTS-v2 if speaker_wav provided, else Kokoro
            if speaker_wav and os.path.exists(speaker_wav):
                return self._synthesize_xtts(text, output_path, speaker_wav, "en")
            return self._synthesize_kokoro(text, output_path)

        print(f"\n[Higgs TTS 2] Synthesizing: '{text[:80]}...'")
        result = self._higgs_pipe(text)  # type: ignore[call-arg]
        audio_array = result["audio"]
        sample_rate = result.get("sampling_rate", 24000)

        # Ensure 1D float32 numpy array
        if isinstance(audio_array, (list, tuple)):
            audio_array = np.array(audio_array, dtype=np.float32)
        if audio_array.ndim > 1:
            audio_array = audio_array.squeeze()

        sf.write(output_path, audio_array, sample_rate)
        duration = len(audio_array) / sample_rate
        return int(sample_rate), duration

    def _synthesize_dia(
        self,
        text: str,
        output_path: Path,
    ) -> tuple[int, float]:
        """
        Run Dia-1.6B multi-speaker dialogue synthesis.
        Text should use [S1] / [S2] speaker tags.
        Falls back to Kokoro on load failure.
        Returns (sample_rate, duration_seconds).
        """
        if not self.load_dia():
            print("[WARN] Dia unavailable — falling back to Kokoro")
            # Strip [S1]/[S2] tags before passing to Kokoro
            clean_text = text
            for tag in _DIA_SPEAKER_TAGS:
                clean_text = clean_text.replace(tag, "")
            clean_text = " ".join(clean_text.split())
            return self._synthesize_kokoro(clean_text, output_path)

        print(f"\n[Dia-1.6B] Dialogue synthesis: '{text[:80]}...'")
        assert self._dia_model is not None
        assert self._dia_processor is not None

        # Tokenize using the Dia processor
        inputs = self._dia_processor(text=text, return_tensors="pt")
        inputs = {k: v.to(self.device) if torch.is_tensor(v) else v for k, v in inputs.items()}

        with torch.no_grad():
            output = self._dia_model.generate(**inputs)

        audio_array = output.squeeze().cpu().numpy().astype(np.float32)
        sample_rate = 44100  # Dia native output rate
        sf.write(output_path, audio_array, sample_rate)
        duration = len(audio_array) / sample_rate
        return sample_rate, duration

    # ------------------------------------------------------------------
    # Main Public Interface
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        mode: str = "fast",
        speaker_wav: Optional[str] = None,
        output_filename: str = "speech.wav",
        language: str = "en",
        quality: str = "balanced",
        style: Optional[str] = None,
    ) -> SynthesisResult:
        """
        Synthesize speech using the automatically selected model.

        Parameters
        ----------
        text            : Text to synthesize. Use [S1]/[S2] tags for Dia dialogue.
        mode            : 'fast' | 'clone' | 'high_quality' | 'dialogue'
        speaker_wav     : Path to reference WAV (required for 'clone', optional for 'high_quality')
        output_filename : Output filename under outputs/
        language        : BCP-47 language code (e.g. 'en', 'es', 'fr', 'ja')
        quality         : 'fast' | 'balanced' | 'high'
        style           : Optional style hint ('dialogue', 'expressive', 'narration')
        """
        if not text.strip():
            raise ValueError("text must not be empty")

        model_key = self.select_model(
            mode=mode,
            language=language,
            quality=quality,
            style=style,
            text=text,
        )

        start_time = time.time()
        output_path = OUTPUT_DIR / output_filename

        print(
            f"\n{'='*60}\n"
            f"[VoiceEngine] mode={mode!r} lang={language!r} quality={quality!r} "
            f"style={style!r} → model={model_key!r}\n"
            f"{'='*60}"
        )

        if model_key == "kokoro":
            sample_rate, duration = self._synthesize_kokoro(text, output_path)

        elif model_key == "xtts-v2":
            sample_rate, duration = self._synthesize_xtts(
                text, output_path, speaker_wav, language
            )

        elif model_key == "higgs-tts-2":
            sample_rate, duration = self._synthesize_higgs(text, output_path, speaker_wav)

        elif model_key == "dia-1.6b":
            sample_rate, duration = self._synthesize_dia(text, output_path)

        else:
            raise ValueError(f"Internal error: unknown model key '{model_key}'")

        latency = (time.time() - start_time) * 1000
        print(f"\n✅ Audio saved → {os.path.abspath(output_path)}")
        print(f"⏱  Latency: {latency:.0f} ms  |  Duration: {duration:.2f}s  |  Model: {model_key}")
        print("=" * 60)

        return SynthesisResult(
            output_path=str(output_path),
            sample_rate=sample_rate,
            duration_seconds=duration,
            latency_ms=latency,
            model=model_key,
            mode=mode,
        )


# ------------------------------------------------------------------
# CLI Benchmark / Smoke Test
# ------------------------------------------------------------------
if __name__ == "__main__":
    router = VoiceEngineRouter()

    print("\n--- TEST 1: Kokoro fast (English) ---")
    router.synthesize(
        text="Hello! I am your AI avatar running real-time speech synthesis.",
        mode="fast",
        output_filename="test_kokoro.wav",
    )

    print("\n--- TEST 2: Higgs TTS 2 high_quality ---")
    router.synthesize(
        text="This is a high quality neural synthesis test using Higgs TTS 2.",
        mode="high_quality",
        output_filename="test_higgs.wav",
    )

    print("\n--- TEST 3: Dia-1.6B dialogue ---")
    router.synthesize(
        text="[S1] Good morning! How are you today? [S2] I am doing great, thank you!",
        mode="dialogue",
        output_filename="test_dia.wav",
    )

    print("\n--- TEST 4: Higgs multilingual (Spanish) ---")
    router.synthesize(
        text="Hola, soy tu avatar de inteligencia artificial.",
        mode="fast",
        language="es",
        output_filename="test_higgs_spanish.wav",
    )

    reference = str(INPUT_DIR / "voice_sample.wav")
    if os.path.exists(reference):
        print("\n--- TEST 5: XTTS-v2 voice clone ---")
        router.synthesize(
            text="This audio was generated by cloning the target voice using zero-shot deep learning.",
            mode="clone",
            speaker_wav=reference,
            output_filename="test_xtts_clone.wav",
        )
    else:
        print(f"\n--- TEST 5: SKIPPED (no reference audio at {reference}) ---")