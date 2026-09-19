# Phase 3 Benchmark Report

Generated: 2026-09-17T10:22:22+00:00
Device: cuda  |  Queue: celery

## Acceptance matrix

| Requirement | Measured | Verdict | Method |
|---|---|---|---|
| TTS quality MOS > 3.5 | 4.326 | **PASS** | torchaudio-squim |
| Voice cloning similarity > 85% | — | **NOT MEASURED** | No reference recording in inputs/. Add 30-60s of consented speech to measure cloning similarity. |
| API initiation response < 500 ms | 13.01 | **PASS** | queue=celery |
| API capacity 100+ requests/minute | 120 | **PASS** | min(rate-limit policy 120 rpm, raw app throughput 25781.2 rpm over 150 sequential in-process requests); not a deployed-server load test |
| Warm synthesis latency < 2 s | 73.72 | **PASS** | median of repeated Kokoro runs, model resident |

## Synthesis latency

- Kokoro cold start: 6336.0 ms
- Kokoro warm median: 73.72 ms (p95 92.42 ms, n=15)
- Real-time factor: 0.0176 (65.92 s of audio generated)

| Language | Model | Cold ms | Warm ms | Duration s |
|---|---|---|---|---|
| hin (Hindi) | mms-tts | 1716.71 | 145.61 | 3.84 |
| tam (Tamil) | mms-tts | 1749.49 | 57.35 | 4.1 |
| swh (Swahili) | mms-tts | 1989.58 | 54.58 | 3.46 |
| spa (Spanish) | mms-tts | 1408.93 | 56.48 | 4.14 |

## Emotion prosody

| Emotion | Duration ratio | Expected | Loudness ratio | Expected |
|---|---|---|---|---|
| joy | 0.909 | 0.909 | 1.15 | 1.15 |
| anger | 0.877 | 0.877 | 1.349 | 1.35 |
| sorrow | 1.163 | 1.163 | 0.82 | 0.82 |
| authority | 1.075 | 1.075 | 1.12 | 1.12 |
| calm | 1.087 | 1.087 | 0.92 | 0.92 |
| excitement | 0.847 | 0.847 | 1.28 | 1.28 |

## Speech quality (torchaudio SQUIM)

- Mean MOS: **4.326** (min 4.009) over 5 sentences
- Mean PESQ: 3.921
- Method: torchaudio-squim

## Voice cloning similarity

- SKIPPED: No reference recording in inputs/. Add 30-60s of consented speech to measure cloning similarity.
