"""The recognizer contract.

Every candidate engine — PaddleOCR, EasyOCR, a fine-tuned TrOCR, a local VLM —
hides behind this one interface so the harness can score them interchangeably
and the production pipeline can swap them with a config change.

The important design decision is :class:`Reading`: a recognizer returns a
*ranked list of candidates*, never a single string. Storing every candidate is
what makes fuzzy search work later; a recognizer that collapses to one answer
throws away the information the search layer needs.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from PIL import Image

__all__ = ["Reading", "Recognizer", "normalise_digits"]

# Bib numbers in the dataset are 2-5 digits. Anything outside that is noise
# (sponsor text, timing-chip codes, the letter suffixes some races print).
MIN_DIGITS = 2
MAX_DIGITS = 6

# Characters OCR engines habitually confuse with digits. Mapping them back
# costs nothing and recovers a surprising number of reads.
_CONFUSIONS = str.maketrans(
    {
        "O": "0", "o": "0", "Q": "0", "D": "0",
        "I": "1", "l": "1", "|": "1", "i": "1", "!": "1",
        "Z": "2", "z": "2",
        "E": "3",
        "A": "4",
        "S": "5", "s": "5",
        "G": "6", "b": "6",
        "T": "7", "?": "7",
        "B": "8",
        "g": "9", "q": "9",
    }
)


def normalise_digits(raw: str) -> str:
    """Coerce a raw OCR string into a plausible bib number, or ``""``.

    Applied identically in the benchmark and in production. Keep it that way:
    normalisation that exists only in the harness is how a benchmark starts
    lying to you.
    """
    if not raw:
        return ""
    cleaned = raw.strip().translate(_CONFUSIONS)
    digits = re.sub(r"\D", "", cleaned)
    if not (MIN_DIGITS <= len(digits) <= MAX_DIGITS):
        return ""
    return digits


@dataclass
class Reading:
    """A ranked set of hypotheses for one crop."""

    candidates: list[tuple[str, float]] = field(default_factory=list)

    @property
    def best(self) -> str:
        return self.candidates[0][0] if self.candidates else ""

    @property
    def confidence(self) -> float:
        return self.candidates[0][1] if self.candidates else 0.0

    @classmethod
    def single(cls, text: str, confidence: float = 1.0) -> "Reading":
        text = normalise_digits(text)
        return cls([(text, confidence)] if text else [])

    @classmethod
    def from_raw(cls, raw: list[tuple[str, float]]) -> "Reading":
        """Normalise, drop rejects, merge duplicates, sort by confidence."""
        merged: dict[str, float] = {}
        for text, conf in raw:
            digits = normalise_digits(text)
            if digits:
                merged[digits] = max(merged.get(digits, 0.0), float(conf))
        ranked = sorted(merged.items(), key=lambda kv: -kv[1])
        return cls(ranked)


class Recognizer(ABC):
    """Reads digits from a pre-cropped, deskewed, upscaled bib image."""

    name: str = "recognizer"

    @abstractmethod
    def read(self, crop: Image.Image) -> Reading:
        """Read one crop."""

    def read_batch(self, crops: list[Image.Image]) -> list[Reading]:
        """Read many. Override where the backend supports real batching —
        on a 5070 that is typically a 5-10x throughput difference."""
        return [self.read(c) for c in crops]

    def warmup(self) -> None:
        """Optional: load weights so the first timed call is not the slow one."""
