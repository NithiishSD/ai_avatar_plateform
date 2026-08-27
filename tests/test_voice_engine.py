import sys
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voice_engine import VoiceEngineRouter


class VoiceEngineTests(unittest.TestCase):
    def test_select_model_routes_fast_english_to_kokoro(self):
        router = VoiceEngineRouter(device="cpu")

        self.assertEqual(router.select_model(mode="fast", language="en", quality="fast"), "kokoro")
        self.assertEqual(router.select_model(mode="clone", language="fr"), "xtts-v2")


    def test_select_model_rejects_unsupported_fast_language(self):
        router = VoiceEngineRouter(device="cpu")

        with self.assertRaisesRegex(ValueError, "English only"):
            router.select_model(mode="fast", language="fr")


    def test_fast_synthesis_returns_structured_metadata(self):
        router = VoiceEngineRouter(device="cpu")
        samples = np.zeros(2400, dtype=np.float32)

        router.kokoro_pipeline = lambda text, voice, speed: iter([(None, None, samples)])
        output_dir = Path(__file__).resolve().parents[1] / "outputs" / "test_phase1"
        output_dir.mkdir(exist_ok=True)

        import voice_engine
        original_output_dir = voice_engine.OUTPUT_DIR
        voice_engine.OUTPUT_DIR = output_dir
        try:
            result = router.synthesize("Test speech")
        finally:
            voice_engine.OUTPUT_DIR = original_output_dir

        self.assertEqual(result.model, "kokoro")
        self.assertEqual(result.mode, "fast")
        self.assertEqual(result.sample_rate, 24000)
        self.assertAlmostEqual(result.duration_seconds, 0.1)
        self.assertTrue(Path(result.output_path).exists())
        self.assertEqual(sf.info(result.output_path).samplerate, 24000)
        Path(result.output_path).unlink()
        output_dir.rmdir()


    def test_synthesis_rejects_empty_text(self):
        router = VoiceEngineRouter(device="cpu")

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            router.synthesize("  ")


if __name__ == "__main__":
    unittest.main()