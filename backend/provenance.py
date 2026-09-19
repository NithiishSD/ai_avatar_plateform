"""
Voice reference provenance and consent records.

Two problems share one solution.

The benchmark reads ``inputs/`` and measures cloning similarity against
whatever it finds first. Nothing recorded *what* that clip was, so a reference
concatenated from our own Kokoro output would have been measured, scored
against the >85% threshold and written into ``docs/benchmarks/`` as acceptance
evidence. Synthetic speech is a flattering cloning target -- no room reverb,
no mic coloration, no breath noise -- so the number would have looked good and
meant nothing.

Roadmap Phase 5 separately asks Developer 1 for a "biometric voice consent
verification protocol", which needs a durable record of who a reference voice
belongs to and on what basis it may be cloned.

A sidecar ``<audio>.provenance.json`` answers both. ``SYNTHETIC`` references
stay usable for wiring up the pipeline; only a ``HUMAN`` clip with a recorded
consent basis is admissible as evidence for the threshold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROVENANCE_SUFFIX = ".provenance.json"

# Where the audio came from.
HUMAN = "human"
SYNTHETIC = "synthetic"

# Consent bases we accept for a human reference. A public corpus carries its
# consent in its licence, which is why it needs no separate recording.
CONSENT_BASES = {
    "speaker-recorded",  # the speaker recorded it themselves for this project
    "written-consent",  # a third party consented in writing
    "open-licence",  # public corpus (LJSpeech, LibriSpeech, VCTK, ...)
}


@dataclass
class VoiceProvenance:
    """What a reference clip is, and whether it may be cloned."""

    source: str
    speaker: str = "unknown"
    licence: str = ""
    consent_basis: str = ""
    notes: str = ""
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def is_synthetic(self) -> bool:
        return self.source == SYNTHETIC

    def admissibility(self) -> tuple[bool, str]:
        """
        Whether this clip may back the assignment's cloning-similarity claim.

        Returns ``(admissible, reason)``. The reason is written into the
        benchmark report so a future reader can see why a number was or was
        not counted.
        """
        if self.source == SYNTHETIC:
            return False, (
                "reference is synthetic (TTS output), which is an artificially "
                "easy cloning target; usable for pipeline testing only"
            )
        if self.source != HUMAN:
            return False, f"unknown provenance source {self.source!r}"
        if self.consent_basis not in CONSENT_BASES:
            return False, (
                f"consent basis {self.consent_basis!r} is not one of "
                f"{sorted(CONSENT_BASES)}"
            )
        return True, f"human speech, consent basis: {self.consent_basis}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "speaker": self.speaker,
            "licence": self.licence,
            "consentBasis": self.consent_basis,
            "notes": self.notes,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "VoiceProvenance":
        return cls(
            source=str(raw.get("source", "")),
            speaker=str(raw.get("speaker", "unknown")),
            licence=str(raw.get("licence", "")),
            consent_basis=str(raw.get("consentBasis", "")),
            notes=str(raw.get("notes", "")),
            created=str(raw.get("created", "")),
        )


def sidecar_path(audio_path: Path | str) -> Path:
    """The provenance file that belongs beside ``audio_path``."""
    audio = Path(audio_path)
    return audio.with_name(audio.name + PROVENANCE_SUFFIX)


def load(audio_path: Path | str) -> Optional[VoiceProvenance]:
    """Read the sidecar, or ``None`` when the clip has no provenance record."""
    path = sidecar_path(audio_path)
    if not path.is_file():
        return None
    try:
        return VoiceProvenance.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def write(
    audio_path: Path | str,
    source: str,
    speaker: str = "unknown",
    licence: str = "",
    consent_basis: str = "",
    notes: str = "",
) -> Path:
    """Write a provenance sidecar beside ``audio_path`` and return its path."""
    if source not in (HUMAN, SYNTHETIC):
        raise ValueError(f"source must be {HUMAN!r} or {SYNTHETIC!r}, got {source!r}")
    record = VoiceProvenance(
        source=source,
        speaker=speaker,
        licence=licence,
        consent_basis=consent_basis,
        notes=notes,
    )
    path = sidecar_path(audio_path)
    path.write_text(json.dumps(record.to_dict(), indent=2) + "\n")
    return path


def describe(audio_path: Path | str) -> Dict[str, object]:
    """
    Provenance projected for a report, including the admissibility decision.

    A clip with no record is not admissible: silence is not consent, and an
    unlabelled reference is exactly the ambiguity this module removes.
    """
    record = load(audio_path)
    if record is None:
        return {
            "hasRecord": False,
            "admissible": False,
            "reason": (
                f"no provenance record. Create "
                f"{sidecar_path(audio_path).name} describing the speaker and "
                f"consent basis before this clip backs any published metric."
            ),
        }
    admissible, reason = record.admissibility()
    return {
        "hasRecord": True,
        "admissible": admissible,
        "reason": reason,
        **record.to_dict(),
    }


def warnings_for(audio_path: Path | str) -> List[str]:
    """Human-readable warnings to surface next to a measurement."""
    info = describe(audio_path)
    if info["admissible"]:
        return []
    return [f"NOT acceptance evidence: {info['reason']}"]
