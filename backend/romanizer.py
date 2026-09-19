"""
Shared lazy uroman romanizer.

Two subsystems need the same romanizer for different reasons:

* ``mms_engine`` — MMS-TTS checkpoints whose tokenizer sets ``is_uroman``
  expect romanized input, so synthesizing non-Latin script depends on it.
* ``alignment_engine`` — torchaudio MMS_FA is a character-level CTC aligner
  over an a-z dictionary. Without romanization a Hindi or Tamil transcript
  reduces to zero alignable words, and the aligner degrades to energy-based
  guessing that yields visemes unrelated to the speech.

Constructing ``uroman.Uroman`` loads its transliteration tables, so the
instance is built once per process and shared. ``uroman`` is an optional
dependency: every caller must handle ``None``.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_romanizer = None
_checked = False


def get_romanizer():
    """Return the process-wide ``uroman.Uroman``, or ``None`` if not installed."""
    global _romanizer, _checked
    if _checked:
        return _romanizer
    _checked = True
    try:
        import uroman as ur

        _romanizer = ur.Uroman()
        logger.info("uroman romanizer available")
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "uroman not available (%s); non-Latin script support is limited", exc
        )
        _romanizer = None
    return _romanizer


def is_ascii(text: str) -> bool:
    """True when romanization would be a no-op because the text is already ASCII."""
    return all(ord(ch) < 128 for ch in text)


def romanize(text: str, lcode: Optional[str] = None) -> Optional[str]:
    """
    Romanize ``text``, or return ``None`` when no romanizer is installed.

    ``lcode`` is an ISO-639-3 hint. uroman works without it, but transliterates
    several scripts more accurately when it is supplied.
    """
    romanizer = get_romanizer()
    if romanizer is None:
        return None
    if lcode:
        try:
            return romanizer.romanize_string(text, lcode=lcode)
        except TypeError:
            # Older uroman builds take no lcode keyword.
            pass
    return romanizer.romanize_string(text)


def reset_cache() -> None:
    """Drop the cached instance. For tests that patch the import."""
    global _romanizer, _checked
    _romanizer = None
    _checked = False
