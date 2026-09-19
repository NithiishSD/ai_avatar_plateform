"""
Model weight presence audit.

``VoiceEngineRouter`` loads every backend lazily and caches load failures so a
missing model degrades to a fallback instead of failing the request. That is
the right behaviour in production and the wrong behaviour during development:
three of the five routed models sat in the tree for several phases with only
their ``config.json`` cached, every test passed, and the benchmark silently
measured Kokoro in their place.

This module answers one narrow question without downloading anything or
importing torch: *are this model's weights actually on disk?* A HuggingFace
snapshot that holds no weight file is metadata only -- ``from_pretrained``
would reach the network, and offline it raises.

The audit runs at API startup (loudly) and is served from ``/health`` so the
frontend and the benchmark script can refuse to report a model as working when
its weights were never fetched.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Extensions that hold actual trained parameters, as opposed to configs,
# tokenizer vocabularies or READMEs.
WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pth", ".pt", ".ckpt", ".onnx")

# A tokenizer vocabulary can be a .bin of a few hundred KB, so require at least
# one weight file big enough to be a real checkpoint shard.
MIN_CHECKPOINT_BYTES = 1_000_000


@dataclass(frozen=True)
class ModelWeightStatus:
    """Whether one routed model's weights are on disk."""

    key: str
    name: str
    source: str
    present: bool
    size_bytes: int
    detail: str

    @property
    def size_label(self) -> str:
        if self.size_bytes >= 1_000_000_000:
            return f"{self.size_bytes / 1_000_000_000:.1f} GB"
        if self.size_bytes >= 1_000_000:
            return f"{self.size_bytes / 1_000_000:.0f} MB"
        if self.size_bytes > 0:
            return f"{self.size_bytes / 1_000:.0f} KB"
        return "0 B"

    def to_dict(self) -> Dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "source": self.source,
            "present": self.present,
            "sizeBytes": self.size_bytes,
            "sizeLabel": self.size_label,
            "detail": self.detail,
        }


def _weight_bytes(root: Path) -> int:
    """Total bytes of checkpoint-sized weight files under ``root``."""
    total = 0
    if not root.is_dir():
        return 0
    for path in root.rglob("*"):
        if path.suffix.lower() not in WEIGHT_SUFFIXES:
            continue
        try:
            # Snapshots are symlinks into blobs/, so resolve before measuring.
            size = path.resolve().stat().st_size
        except OSError:
            continue
        if size >= MIN_CHECKPOINT_BYTES:
            total += size
    return total


def _hf_cache_root() -> Path:
    try:
        from huggingface_hub import constants

        return Path(constants.HF_HUB_CACHE)
    except Exception:  # noqa: BLE001
        return Path(
            os.getenv("HF_HUB_CACHE")
            or os.getenv("HUGGINGFACE_HUB_CACHE")
            or Path.home() / ".cache" / "huggingface" / "hub"
        )


def _hf_repo_dir(repo_id: str) -> Path:
    return _hf_cache_root() / f"models--{repo_id.replace('/', '--')}"


def check_hf_repo(key: str, name: str, repo_id: str) -> ModelWeightStatus:
    """Audit one HuggingFace repo in the local hub cache."""
    repo_dir = _hf_repo_dir(repo_id)
    if not repo_dir.is_dir():
        return ModelWeightStatus(
            key=key,
            name=name,
            source=repo_id,
            present=False,
            size_bytes=0,
            detail="not in the HuggingFace cache; never downloaded",
        )
    size = _weight_bytes(repo_dir / "snapshots")
    if size == 0:
        return ModelWeightStatus(
            key=key,
            name=name,
            source=repo_id,
            present=False,
            size_bytes=0,
            detail=(
                "cached metadata only (no weight file) - from_pretrained would "
                "download on first use and fail when offline"
            ),
        )
    return ModelWeightStatus(
        key=key,
        name=name,
        source=repo_id,
        present=True,
        size_bytes=size,
        detail="weights present",
    )


def _coqui_roots() -> List[Path]:
    """
    Candidate Coqui TTS download directories.

    Coqui derives this from ``XDG_DATA_HOME``, which the VS Code snap rewrites
    to a sandboxed path. A backend started from a normal shell therefore looks
    somewhere different than one started from the IDE terminal, so check both.
    """
    roots: List[Path] = []
    try:
        from TTS.utils.manage import ModelManager

        roots.append(Path(ModelManager().output_prefix))
    except Exception:  # noqa: BLE001
        pass
    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        roots.append(Path(xdg) / "tts")
    roots.append(Path.home() / ".local" / "share" / "tts")
    unique: List[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def check_coqui_model(key: str, name: str, model_name: str) -> ModelWeightStatus:
    """Audit a Coqui TTS model such as XTTS-v2 in its download directory."""
    folder = model_name.replace("/", "--")
    searched: List[str] = []
    for root in _coqui_roots():
        candidate = root / folder
        searched.append(str(candidate))
        size = _weight_bytes(candidate)
        if size:
            return ModelWeightStatus(
                key=key,
                name=name,
                source=str(candidate),
                present=True,
                size_bytes=size,
                detail="weights present",
            )
    return ModelWeightStatus(
        key=key,
        name=name,
        source=model_name,
        present=False,
        size_bytes=0,
        detail=(
            "no Coqui download found, so voice cloning cannot run. Searched: "
            + ", ".join(searched)
        ),
    )


def check_mms(key: str = "mms-tts", name: str = "MMS-TTS") -> ModelWeightStatus:
    """
    Audit MMS-TTS, which is one ~145 MB VITS checkpoint per language.

    There is no single repo to check, so report how many are cached. Any one of
    them proves the path works; the router downloads the rest on demand.
    """
    root = _hf_cache_root()
    prefix = "models--facebook--mms-tts-"
    cached: List[str] = []
    total = 0
    if root.is_dir():
        for repo_dir in sorted(root.glob(f"{prefix}*")):
            size = _weight_bytes(repo_dir / "snapshots")
            if size:
                cached.append(repo_dir.name[len(prefix) :])
                total += size
    if not cached:
        return ModelWeightStatus(
            key=key,
            name=name,
            source="facebook/mms-tts-<iso3>",
            present=False,
            size_bytes=0,
            detail="no per-language checkpoint cached yet; each is fetched on demand",
        )
    return ModelWeightStatus(
        key=key,
        name=name,
        source="facebook/mms-tts-<iso3>",
        present=True,
        size_bytes=total,
        detail=f"{len(cached)} language(s) cached: {', '.join(cached)}",
    )


def audit_model_weights() -> List[ModelWeightStatus]:
    """Audit every model ``VoiceEngineRouter.select_model`` can return."""
    return [
        check_hf_repo("kokoro", "Kokoro v1.0 (82M)", "hexgrad/Kokoro-82M"),
        check_coqui_model(
            "xtts-v2",
            "XTTS-v2 (voice cloning)",
            "tts_models/multilingual/multi-dataset/xtts_v2",
        ),
        check_hf_repo(
            "higgs-tts-2", "Higgs TTS 2 (3B)", "bosonai/higgs-tts-2-3b-base"
        ),
        check_hf_repo("dia-1.6b", "Dia-1.6B (dialogue)", "nari-labs/Dia-1.6B"),
        check_mms(),
    ]


def log_weight_audit(statuses: Optional[List[ModelWeightStatus]] = None) -> List[ModelWeightStatus]:
    """
    Log the audit at startup, warning per missing model.

    A missing model is a warning rather than a fatal error because the router
    degrades gracefully by design and Kokoro alone is enough to serve English.
    The point is that the degradation is never again silent.
    """
    statuses = statuses if statuses is not None else audit_model_weights()
    present = [s for s in statuses if s.present]
    missing = [s for s in statuses if not s.present]

    logger.info(
        "Model weight audit: %d/%d available (%s)",
        len(present),
        len(statuses),
        ", ".join(f"{s.key} {s.size_label}" for s in present) or "none",
    )
    for status in missing:
        logger.warning(
            "MODEL WEIGHTS MISSING - %s [%s]: %s. Requests routed here will "
            "fall back to another model.",
            status.name,
            status.key,
            status.detail,
        )
    return statuses


def audit_summary() -> Dict[str, object]:
    """The audit projected for ``/health``."""
    statuses = audit_model_weights()
    return {
        "available": sum(1 for s in statuses if s.present),
        "total": len(statuses),
        "missing": [s.key for s in statuses if not s.present],
        "models": [s.to_dict() for s in statuses],
    }
