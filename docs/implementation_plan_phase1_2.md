# Phase 1 Completion: Multi-Model TTS Router

## Current Status Audit

### ✅ Already Done
- **Kokoro v1.0 (82M)** — Fully integrated via `KPipeline`. Works end-to-end in `fast` mode.
- **XTTS-v2** — Integrated for `clone` mode (zero-shot voice cloning from reference audio).
- **Basic routing** — `select_model()` routes `fast` → Kokoro, `clone` → XTTS-v2.

### ❌ Not Done / Incomplete
| Requirement | Status |
|---|---|
| Higgs Audio V2 (5.77B) integration | NOT DONE |
| Dia 1.6B (Nari Labs) integration | NOT DONE |
| Quality-aware model selection (`quality=high` → Dia/Higgs) | NOT DONE |
| Language-aware routing (multilingual → Higgs) | NOT DONE |
| Speed/style routing (`style` param for dialogue) | NOT DONE |
| Frontend controls for new models/styles | NOT DONE |

## Hardware Constraint Assessment

- GPU: RTX 4050 Laptop, **6.05 GB VRAM**, ~5.09 GB currently free
- **Higgs TTS 2 (3B variant)** — ~3 GB VRAM, fits on GPU
- **Higgs TTS 2 (full 5.77B)** — ~5.6 GB VRAM — TIGHT fit (needs careful loading)
- **Dia 1.6B** — ~1.6 GB VRAM — Comfortably fits
- Both installed via `transformers` / pip without conflict

> [!IMPORTANT]
> We will integrate **Higgs TTS 2 (3B, `bosonai/higgs-tts-2-3b-base`)** — same model family as Higgs Audio V2 but sized to fit the 6 GB VRAM. The 5.77B variant will be noted as optional with a `device_map="auto"` CPU-offload fallback.

> [!IMPORTANT]
> Dia requires `numpy>=2.2.4` but the project pins `numpy<2.0.0` for XTTS-v2 / Numba stability. We will use **lazy-import isolation**: Dia loads inside a subprocess or with a compatibility shim. Because `nari-tts` has strict numpy>=2.2.4, we will install it in the same env and see if there is a conflict; if so, we will use the `transformers`-native Dia approach via `nari-labs/Dia-1.6B` without the `nari-tts` package.

## Proposed Changes

---

### Core Backend: Voice Engine Router

#### [MODIFY] [voice_engine.py](file:///home/nithiish/Documents/ai_avatar_plateform/backend/voice_engine.py)

Complete rewrite of `VoiceEngineRouter` with:
- `SynthesisMode` extended to: `fast`, `clone`, `high_quality`, `dialogue`
- `select_model()` — full decision matrix:
  - `mode=fast` + English → **Kokoro**
  - `mode=clone` → **XTTS-v2**
  - `mode=high_quality` OR `quality=high` OR non-English → **Higgs TTS 2**
  - `mode=dialogue` (multi-speaker with `[S1]/[S2]` tags) → **Dia 1.6B**
  - Fallback chain: Higgs unavailable → XTTS-v2; Dia unavailable → Kokoro
- `load_higgs()` — lazy-load `bosonai/higgs-tts-2-3b-base` via transformers pipeline
- `load_dia()` — lazy-load `nari-labs/Dia-1.6B` via transformers
- `synthesize()` — branches to all four model paths

#### [MODIFY] [contracts.py](file:///home/nithiish/Documents/ai_avatar_plateform/backend/contracts.py)

- Extend `SynthesisMode` enum with `HIGH_QUALITY = "high_quality"` and `DIALOGUE = "dialogue"`
- Add `style: Optional[str]` field (e.g. `"dialogue"`, `"expressive"`) to `AudioSynthesisRequest`
- Add `model_used: Optional[str]` to `SynthesisJobResponse` for frontend display

#### [MODIFY] [celery_app.py](file:///home/nithiish/Documents/ai_avatar_plateform/backend/celery_app.py)

- Update `synthesize_audio` task to pass `style` field from request

---

### Frontend: New Controls

#### [MODIFY] [App.jsx](file:///home/nithiish/Documents/ai_avatar_plateform/frontend/src/App.jsx)

- Add `style` dropdown: `standard`, `expressive`, `dialogue`
- Add mode option: `high_quality` (maps to Higgs)
- Show which model was used in the result panel

---

### Dependencies

#### [MODIFY] [requirements.txt](file:///home/nithiish/Documents/ai_avatar_plateform/backend/requirements.txt)

- Add `git+https://github.com/nari-labs/dia.git` (or note it separately since it conflicts with numpy pin)
- Add note for Higgs (loaded via existing `transformers>=4.38.0`)

> [!WARNING]
> `nari-tts` (the Dia package) requires `numpy>=2.2.4` while the project pins `numpy<2.0.0` for TTS/Numba stability. **Resolution plan**: Dia will be loaded via `transformers` `AutoModel` API using `nari-labs/Dia-1.6B` without the `nari-tts` package, so no numpy conflict occurs. We verify this path works first.

---

## Routing Decision Matrix

| Input Conditions | Model Selected | Rationale |
|---|---|---|
| `mode=fast`, English | Kokoro 82M | Sub-second, real-time, English-only |
| `mode=clone` | XTTS-v2 | Zero-shot cloning requires speaker reference |
| `mode=high_quality` OR `quality=high` | Higgs TTS 2 (3B) | MOS >4.0 target, multilingual |
| Non-English language | Higgs TTS 2 (3B) | Kokoro is English-only |
| `mode=dialogue` / `style=dialogue` | Dia 1.6B | Multi-speaker `[S1]/[S2]` dialogue |
| Higgs unavailable (OOM) | XTTS-v2 fallback | Graceful degradation |
| Dia unavailable | Kokoro fallback | Graceful degradation |

## Open Questions

> [!NOTE]
> Dia 1.6B uses `[S1]` / `[S2]` speaker tags embedded in text. The `AudioSynthesisRequest` will pass these verbatim in `text` when `mode=dialogue`.

> [!NOTE]
> Higgs TTS 2 requires a reference audio for voice cloning. For `high_quality` without cloning, it uses a default system voice. The API will accept optional `speaker_wav` for cloning on the Higgs path too.

## Verification Plan

### Automated Tests
- `python -m unittest discover -s tests -p 'test_*.py'` — all 20 must still pass
- Add 3 new model routing tests (mock model loading)

### Live Validation
- `POST /api/v1/audio/synthesize` with `mode=high_quality` → Higgs audio output
- `POST /api/v1/audio/synthesize` with `mode=dialogue` text `[S1] Hi [S2] Hello` → Dia output
- `POST /api/v1/audio/synthesize` with `language=es` → auto-routes to Higgs
