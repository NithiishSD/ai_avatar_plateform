# Milestones and Task Tracker

The working plan. Every task has an ID, a status, and a way to verify it.
Update the status when you start or finish a task, and log the details in
`docs/context.md`. Rules and commands live in `CLAUDE.md`.

**Status words** — use exactly these:

| Status | Meaning |
|---|---|
| `Todo` | Not started |
| `In progress` | Someone is working on it |
| `Built` | Code exists, unit tests pass, not yet run on real weights/data |
| `Verified` | Run live on real weights/data, evidence recorded in `context.md` |
| `Blocked` | Waiting on something named in the Notes column |
| `Cut` | Deliberately dropped for now (reason given) |

**Next up:** `G1-01` — run the face engine tests, then `G1-02`.

---

## Gate status

| Gate | Criterion (roadmap) | Status |
|---|---|---|
| Gate 0 | Contracts frozen; mock payloads flow end to end | Passed |
| Gate 1 | Text produces speech **and** 468+ landmarks map onto a reference photo | Not passed |
| Gate 2 | Cloned voice + single photo → accurately lip-synced video clip | Not passed |
| Gate 3 | Custom avatar speaks a cloned multilingual voice with emotion | Not passed |
| Final demo | Measured, consented, rehearsed showcase | Not passed |

---

## Gate 1 — speech + face landmarks (target: end of week 1)

**Pass when:** one command/UI flow takes a consented photo and a sentence,
returns speech audio and the photo with 478 landmarks drawn, head pose and
blendshapes — all live, not mocked.

| ID | Task | Status | Verify by | Notes |
|---|---|---|---|---|
| G1-01 | Run `tests/test_face_engine.py`; fix any failure | Todo | Suite passes | Written, never run |
| G1-02 | Obtain a demo face with clear rights; add provenance sidecar | Blocked | `provenance.describe()` → admissible | Needs a team decision: own photo, licensed stock, or synthetic |
| G1-03 | Add face models to `model_registry` audit + write `scripts/fetch_vision_models.py` | Todo | Startup audit lists them | Bundles already on disk and checked by `doctor.py`; engine errors already name the fetch script |
| G1-04 | `POST /api/v1/avatar/face/analyze` (schema in `contracts.py`) | Todo | API test + live call on G1-02 photo | Return landmarks optional to keep payload small |
| G1-05 | Frontend: upload photo, draw landmarks + bbox on canvas | Todo | Manual check, screenshot in log | |
| G1-06 | Face quality gate: reject no face, multiple faces, \|yaw\| > 30° | Todo | Unit tests + live | Clear user-facing messages |
| G1-07 | Validate head-pose sign convention on a photo at a known angle | Todo | Left/right and up/down signs confirmed | Magnitudes correct; signs unverified |
| G1-08 | Fetch XTTS-v2 (human accepts Coqui CPML first) | Blocked | `fetch_models.py --dry-run` shows present | Licence acceptance needed |
| G1-09 | Register a consented human voice reference (e.g. LJSpeech clip) | Todo | `make_reference.py --human …` → admissible | Own voice not required |
| G1-10 | Live XTTS-v2 clone + ECAPA similarity via benchmark | Todo | Benchmark row shows MEASURED, > 85% | Depends on G1-08, G1-09 |

## Gate 2 — first talking avatar (target: end of week 2)

**Pass when:** `scripts/render_avatar.py --text … --voice … --face …`
produces an MP4 whose mouth visibly follows the speech, with a measured sync
score recorded.

| ID | Task | Status | Verify by | Notes |
|---|---|---|---|---|
| G2-01 | Viseme → ARKit blendshape table (15 visemes → mouth/jaw weights) | Todo | Unit tests; every viseme maps | Maps directly from `PHONEME_TO_VISEME` output |
| G2-02 | Fallback renderer: warp mouth region per frame from blendshape weights | Todo | MP4 plays, mouth moves in time | CPU only; guaranteed demo path |
| G2-03 | Frame timing: build frames at `targetFps` from `phonemeTimestamps` | Todo | Frame count = duration × fps | Interpolate between visemes to avoid jitter |
| G2-04 | Mux audio + frames to MP4 (ffmpeg) | Todo | `ffprobe` shows both streams, equal duration | |
| G2-05 | `scripts/render_avatar.py` end-to-end CLI | Todo | One command → MP4 in `outputs/` | Uses the render-job contract internally |
| G2-06 | Render worker consumes `POST /api/v1/avatar/render-job` | Todo | Job goes QUEUED → SUCCESS with video URL | Currently the endpoint only queues |
| G2-07 | Wav2Lip integration (GPU, unload TTS first) | Todo | MP4 + peak VRAM logged < 6 GB | Add weights to audit + fetcher |
| G2-08 | Lip-sync metric: SyncNet LSE-C / LSE-D | Todo | Numbers recorded with method | Needed before claiming any accuracy |
| G2-09 | MuseTalk trial at reduced resolution | Todo | Works or documented OOM | Optional quality upgrade |
| G2-10 | UI: render button, progress, video player | Todo | Manual check | |

## Gate 3 — custom multilingual avatar with emotion (week 3, if time)

| ID | Task | Status | Verify by | Notes |
|---|---|---|---|---|
| G3-01 | Hindi and Tamil talking avatar using romanized alignment | Todo | MP4 per language, sync score | Alignment fix already Verified for text |
| G3-02 | Emotion → face: `emotionVector` drives brow/cheek blendshapes and blink rate | Todo | Visible difference joy vs sorrow | Contract already carries `eyeblinkRate` |
| G3-03 | Background replacement in the render path | Todo | MP4 with swapped background | Segmenter already Built |
| G3-04 | Cross-lingual cloning: clone voice, speak another language | Todo | ECAPA similarity across languages | XTTS-v2 supports 17 languages |

## Final demo — ethics, measurement, rehearsal

| ID | Task | Status | Verify by | Notes |
|---|---|---|---|---|
| FD-01 | Audio watermark on every generated clip (e.g. AudioSeal) | Todo | Detector finds mark; MOS unchanged | |
| FD-02 | Refuse clone requests whose reference is not admissible | Todo | API test: 403 with reason | Provenance module exists |
| FD-03 | Visible "AI-generated" label burned into videos | Todo | Visible in output | |
| FD-04 | Re-run all benchmarks; date every number | Todo | New report in `docs/benchmarks/` | |
| FD-05 | Real load test against a running server (100+ req/min) | Todo | Report with method | Current figure is in-process only |
| FD-06 | Demo script rehearsal, recorded backup video | Todo | Backup MP4 exists | Protects against live failure |
| FD-07 | Obtain intact problem-statement PDF; re-check thresholds | Blocked | Thresholds table confirmed | Repo copy is corrupted |

---

## Already done (for reference)

| ID | Task | Status | Evidence |
|---|---|---|---|
| A-01 | FastAPI + Celery (eager) + contracts frozen | Verified | Gate 0 |
| A-02 | Kokoro fast English | Verified | 73.7 ms warm, MOS 4.33 |
| A-03 | Five-model router with fallbacks | Built | Only Kokoro + MMS have weights |
| A-04 | MMS-TTS 1,000+ languages | Verified | hin, tam, swh, spa benchmarked |
| A-05 | Forced alignment → 15 visemes | Verified | MMS_FA CTC spans |
| A-06 | Romanized alignment for non-Latin scripts | Verified | Hindi/Tamil produce alignable words |
| A-07 | Emotion vectors and prosody | Verified | 6 presets hit target ratios |
| A-08 | SQUIM quality auditor, ECAPA similarity | Verified | Benchmark 17 Sep 2026 |
| A-09 | API keys + rate limiting | Verified | Tests |
| A-10 | Model weight audit at startup + `/health` | Verified | Prints 2/5 available |
| A-11 | Provenance records + benchmark admissibility guard | Built | Tests; no human reference yet |
| A-12 | Face engine: landmarks, pose, blendshapes, crop, segmentation | Built | Checked on one photo (since deleted) |

---

## Improvements beyond the requirements

Worth doing once Gate 2 passes. Ordered by value for effort.

| ID | Improvement | Why |
|---|---|---|
| IM-01 | `scripts/doctor.py` one-command diagnostics | Done — see `CLAUDE.md` |
| IM-02 | Structured logs with `job_id` on every line | Trace one render through API, queue and models |
| IM-03 | SQLite job history (instead of Postgres) | Persistence with zero setup; Postgres later |
| IM-04 | Render cache keyed on (text, voice, face, settings) hash | Instant re-renders during demo prep |
| IM-05 | Chunked Kokoro streaming over WebSocket | First audio in < 200 ms; groundwork for live avatar |
| IM-06 | Idle motion: blinks and small head sway | Removes the "frozen photo" look |
| IM-07 | VRAM guard: check free memory before loading a model | Clear error instead of CUDA OOM mid-render |
| IM-08 | CI workflow running the unit suite on each push | Catches regressions early |
| IM-09 | OpenVoice V2 as a second cloner | Named in requirements; low demo value |
| IM-10 | Remove unused `frontend/src/App.new.jsx` | Less confusion |
