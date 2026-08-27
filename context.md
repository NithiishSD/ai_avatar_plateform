# AI Avatar Platform Development Context

Last updated: 2026-08-27
Owner: Developer 1 - Audio AI, Voice Synthesis, and Backend
Roadmap source: `AI_Avatar_Platform_2_Developer_Roadmap.pdf`

## Project Snapshot

The repository currently contains an initial Developer 1 voice milestone:

- `src/voice_engine.py` provides a synchronous `VoiceEngineRouter`.
- `fast` mode lazily loads Kokoro and writes 24 kHz WAV output.
- `clone` mode lazily loads XTTS-v2 and requires a local reference WAV file.
- `tests/hardware_test.py` reports the selected Python, PyTorch, and CUDA state.
- `requirements.txt` includes Kokoro, Coqui TTS, PyTorch CUDA wheels, audio libraries, and supporting packages.
- No PostgreSQL layer or object storage adapter exists yet. The Phase 0 audio-visual render-job contract, FastAPI boundary, in-memory queue adapter, Celery tasks, Redis-persisted queue adapter, and asynchronous synthesis API are now present and broker-verified. The audio synthesis task is connected to `VoiceEngineRouter`.

## Baseline Verification

| Check | Result | Notes |
|---|---|---|
| Python compilation | PASS | `src/voice_engine.py` and `tests/hardware_test.py` compile successfully. |
| Environment smoke test | PASS with blocker | The project environment and PyTorch import work. |
| CUDA availability | PASS | Project environment reports CUDA available on an NVIDIA GeForce RTX 4050 Laptop GPU with 6.05 GB VRAM. |
| Fast Kokoro synthesis | EXISTING OUTPUT | `outputs/fast_speech.wav` is present, but this run is not a current GPU benchmark. |
| XTTS voice cloning | NOT RUN | `inputs/voice_sample.wav` is absent. |
| Automated regression tests | PASS | Eighteen standard-library `unittest` tests pass without loading large models. |
| Redis/Celery delivery | PASS | A real Redis 7 container delivered a validated render job to a Celery worker and returned the result. |

Baseline command:

```bash
/home/nithiish/Documents/ai_avatar_plateform/env/bin/python -m py_compile \
  /home/nithiish/Documents/ai_avatar_plateform/src/voice_engine.py \
  /home/nithiish/Documents/ai_avatar_plateform/tests/hardware_test.py
/home/nithiish/Documents/ai_avatar_plateform/env/bin/python \
  /home/nithiish/Documents/ai_avatar_plateform/tests/hardware_test.py
```

## Roadmap Status

### Phase 0 - Infrastructure Setup, GPU Environment, and Contract Freeze

- [x] Python environment and core audio dependencies installed.
- [x] Initial voice router scaffolded.
- [x] Verify NVIDIA driver/CUDA availability on the host (RTX 4050, driver 595.84).
- [x] Verify CUDA visibility from the project process outside the VS Code sandbox.
- [x] Add FastAPI service boundary.
- [x] Define and freeze the audio synthesis and avatar render-job contracts.
- [x] Add a phoneme/viseme payload model and validation tests.
- [x] Add mock queue/client behavior for integration testing.

### Phase 1 - Core TTS Engine

- [x] Kokoro integration is present in the router.
- [x] XTTS-v2 integration is present in the router.
- [x] Add model selection by language, latency, and quality requirements.
- [x] Add structured synthesis responses with duration, sample rate, and output URI.
- [x] Add repeatable tests without loading large models.

### Phase 2 - Voice Cloning and Alignment

- [ ] Validate reference-audio duration, format, sample rate, and consent metadata.
- [ ] Integrate OpenVoice V2 or confirm XTTS-v2 as the first cloning backend.
- [ ] Implement forced alignment and millisecond phoneme timestamps.
- [ ] Map phonemes to the shared viseme vocabulary.

### Phases 3-6

Not started. These depend on the contracts, job lifecycle, audio metadata, and alignment output above.

## Recommended Next Step

Complete the Phase 0 contract freeze before adding another model. The typed render-job model, FastAPI service boundary, Celery task, queue adapters, real Redis broker delivery, mocked audio synthesis task, and asynchronous synthesis API are verified; next run actual Kokoro inference on the RTX 4050 and persist completed output metadata.

1. TTS synthesis requests and results.
2. `POST /api/v1/avatar/render-job` payloads from the roadmap.
3. Phoneme timestamps and emotion vectors.
4. Job status and error states.

The validation-only and API tests use mock data and an in-memory queue. This lets Developer 2 consume a stable phoneme/viseme payload without depending on model downloads or a live Redis server. Next, introduce Celery/Redis as an asynchronous execution detail.

### Definition of Done for the Next Step

- Invalid timestamps are rejected, including negative values and `endMs < startMs`.
- Timestamps are ordered and do not exceed the declared audio duration.
- `sampleRate`, `targetFps`, and `durationSeconds` have explicit bounds.
- Render quality is an enum rather than an unchecked string.
- The sample payload from the roadmap validates unchanged.
- Contract tests run without importing or loading Kokoro/XTTS-v2.
- API and model decisions are recorded in this file.

## Corrections and Decisions Log

| Date | Area | Correction or decision | Reason |
|---|---|---|---|
| 2026-08-27 | Scope | Treat the current repository as an initial voice-engine milestone, not a complete Phase 0 implementation. | The only implementation files are the voice router and hardware check. |
| 2026-08-27 | Hardware | CUDA is currently unavailable in the project environment. | `torch.cuda.is_available()` returned `False`; GPU benchmarks are therefore pending. |
| 2026-08-27 | Architecture | Freeze typed contracts before queue and renderer integration. | It gives both developers a testable boundary and keeps model execution replaceable. |
| 2026-08-27 | Testing | Separate validation-only contract tests from model execution tests. | Large model downloads and GPU availability should not block API contract regressions. |

## Test and Milestone Log

Use this section for every development session. Keep the command, result, and any correction together.

### Entry Template

```text
Date:
Milestone / phase:
Change made:
Tests run:
Result:
Corrections or follow-up:
Evidence / artifact:
```

### Recorded Tests

#### 2026-08-27 - Phase 1 Core TTS Routing

- Change: Added explicit Kokoro/XTTS-v2 selection, `SynthesisResult` metadata, stable project-relative output paths, empty-text validation, and model-free regression tests.
- Tests: `env/bin/python -m unittest discover -s tests -p 'test_*.py'`.
- Result: PASS - 4 tests completed in 0.022 seconds without loading large models.
- Follow-up: Run real Kokoro and XTTS-v2 synthesis benchmarks now that project-level CUDA access is verified.

#### 2026-08-27 - Phase 0 Alignment Contract

- Change: Added Pydantic models for render jobs, phoneme timestamps, emotion vectors, and render quality; added bounds, ordering, interval, and URL validation.
- Tests: `python -m unittest discover -s tests -p 'test_*.py' -v`.
- Result: PASS - 8 tests completed in 0.011 seconds.
- Follow-up: Add FastAPI, then implement the endpoint and mock queue/client integration. Celery and Redis are not currently installed.

#### 2026-08-27 - Phase 0 Backend Dependencies

- Change: Installed FastAPI 0.141.1, Uvicorn 0.52.4, Celery 5.6.3, and Redis 8.1.0 into the project environment and pinned them in `requirements.txt`.
- Tests: Imported all four packages and ran `python -m unittest discover -s tests -p 'test_*.py' -q`.
- Result: PASS - all imports succeeded and 8 tests passed in 0.009 seconds.
- Follow-up: Implement the FastAPI render-job endpoint and mock queue/client behavior.

#### 2026-08-27 - Phase 0 FastAPI Boundary

- Change: Added `POST /api/v1/avatar/render-job`, job status lookup, `QUEUED` response state, duplicate protection, and an in-memory queue adapter.
- Tests: `python -m unittest discover -s tests -p 'test_*.py' -v`.
- Result: PASS - 13 tests completed in 0.027 seconds. A non-blocking Starlette deprecation warning recommends a future `httpx2` migration.
- Follow-up: Run a Redis service and switch `QUEUE_BACKEND=celery` for an end-to-end broker test.

#### 2026-08-27 - Celery and Redis Queue Adapter

- Change: Added Celery configuration, a validated `process_render_job` task, and a Redis-configured queue adapter selected with `QUEUE_BACKEND=celery`.
- Tests: `python -m unittest discover -s tests -p 'test_*.py' -v` with Celery eager mode for the queue test.
- Result: PASS - 14 tests completed in 0.080 seconds. No local `redis-server` executable or reachable broker was available for a real delivery test.
- Follow-up: Start Redis, run a worker, and verify broker delivery with a real process.

#### 2026-08-27 - Redis-Persisted Queue Status

- Change: Updated `CeleryJobQueue` to persist validated payloads and queued status in Redis, allowing status lookup across API-process boundaries; added an injectable fake-Redis regression test.
- Tests: `python -m unittest discover -s tests -p 'test_*.py' -v`.
- Result: PASS - 15 tests completed in 0.043 seconds. Existing eager Celery coverage was isolated from live Redis using the fake client.
- Follow-up: Update the Celery task to persist processing and failure states when the renderer is connected.

#### 2026-08-27 - Celery Audio Synthesis Task

- Change: Added typed audio synthesis requests/responses and connected the `avatar.synthesize_audio` Celery task to `VoiceEngineRouter`.
- Tests: `python -m unittest discover -s tests -p 'test_*.py' -v` with a mocked voice engine.
- Result: PASS - 16 tests completed in 0.042 seconds; the task parameter mapping and structured result were verified without loading a model.
- Follow-up: Add a synthesis API endpoint and durable processing/failure status updates, then run a real GPU inference benchmark.

#### 2026-08-27 - Asynchronous Synthesis API

- Change: Added `POST /api/v1/audio/synthesize` and `GET /api/v1/audio/synthesize/{task_id}` backed by the Celery result backend.
- Tests: `python -m unittest discover -s tests -p 'test_*.py' -v` with mocked Celery dispatch/state.
- Result: PASS - 18 tests completed in 0.048 seconds.
- Follow-up: Run the endpoint with a live worker and real Kokoro inference; persist output metadata and failure details.

#### 2026-08-27 - Real Redis and Celery Broker Delivery

- Test: Redis 7 container on port 6379, Celery worker with `--pool=solo`, and a real `process_render_job.delay(...)` producer.
- Result: PASS - task `36893ac7-5827-4179-9740-fcdecc1747ba` was delivered and returned `{'jobId': 'BROKER-TEST-1', 'status': 'QUEUED'}` through the Redis result backend.
- Follow-up: Connect the Celery task to the voice engine and add persistent job status storage before production use.

#### 2026-08-27 - Repository Baseline

- Milestone: Initial Developer 1 voice milestone review.
- Tests: Python compilation and `tests/hardware_test.py`.
- Result: Compilation passed; PyTorch imported; CUDA detection failed because no CUDA device was available.
- Follow-up: Do not claim sub-100 ms or GPU quality targets until hardware validation is available. Add contract tests next.

#### 2026-08-27 - CUDA Host Verification

- Evidence: Supplied host `nvidia-smi` output reports an NVIDIA GeForce RTX 4050, driver 595.84, CUDA 13.2, and 6141 MiB total VRAM.
- Test from the VS Code sandbox: `env/bin/python tests/hardware_test.py`.
- Result: Host driver is present, but the sandbox cannot communicate with it; PyTorch reports `torch 2.5.1+cu121`, compiled CUDA 12.1, and zero devices.
- Follow-up: Run the project environment directly in the host terminal, outside the VS Code sandbox, before real model benchmarking. CUDA 12.1 PyTorch should be compatible with the newer driver once device access is available.

#### 2026-08-27 - Project CUDA and Regression Verification

- Hardware test: `python tests/hardware_test.py`.
- Result: PASS - CUDA available; NVIDIA GeForce RTX 4050 Laptop GPU; 6.05 GB dedicated VRAM.
- Regression test: `python -m unittest discover -s tests -p 'test_*.py' -v`.
- Result: PASS - 4 tests completed in 0.124 seconds.
- Follow-up: Execute real Kokoro fast synthesis and XTTS-v2 cloning with approved reference audio, then record latency and output quality measurements.

## Useful Paths

- Source: `src/voice_engine.py`
- Existing smoke test: `tests/hardware_test.py`
- Dependencies: `requirements.txt`
- Input assets: `inputs/`
- Generated audio: `outputs/`
