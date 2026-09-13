"""Two-tier recognition: a fast local engine, with a strong fallback for the
crops it is unsure about.

This exists because of a measured property of the eval set rather than a
general principle. EasyOCR's confidence on bib crops is unusually well
calibrated:

    confidence  share of crops   exact   fuzzy@1
    0.8 - 1.0        67%         90.8%    100.0%
    0.6 - 0.8        16%         73.9%     95.7%
    0.4 - 0.6         8%         72.7%     90.9%
    0.2 - 0.4         5%         12.5%     37.5%
    0.0 - 0.2         4%          0.0%      0.0%

Every read above 0.8 was correct within edit distance 1, and essentially all
the errors sit in the bottom ~9%. So the useful question is not "which single
recognizer is best" but "how little work can the expensive one do".

At ``threshold=0.4`` the primary keeps 90% of crops at 98.5% fuzzy@1 and defers
14 of 146. Scaled to a 20k-photo event (~60k crops) that is ~6k fallback calls:
a few dollars per race against ~$60 to run a VLM over everything.

Re-measure ``threshold`` whenever you change the primary engine or the
preprocessing — calibration is a property of the specific pipeline, not a
constant, and a stale threshold silently spends money or loses accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from .base import Reading, Recognizer

__all__ = ["CascadeRecognizer", "CascadeStats"]


@dataclass
class CascadeStats:
    """How much work each tier actually did. Log this per batch — a drifting
    deferral rate is the earliest signal that input quality has changed."""

    total: int = 0
    deferred: int = 0
    fallback_failed: int = 0
    fallback_improved: int = 0
    _deferred_confidences: list[float] = field(default_factory=list)

    @property
    def deferral_rate(self) -> float:
        return self.deferred / self.total if self.total else 0.0

    def summary(self) -> dict:
        return {
            "total": self.total,
            "deferred": self.deferred,
            "deferral_rate": round(self.deferral_rate, 4),
            "fallback_failed": self.fallback_failed,
            "fallback_changed_answer": self.fallback_improved,
        }


class CascadeRecognizer(Recognizer):
    """Run ``primary``; escalate to ``fallback`` only on low confidence.

    Both readings are kept in the returned candidate list. That matters
    downstream: if the primary said ``1308`` at 0.35 and the fallback says
    ``1300``, fuzzy search should be able to match either, and discarding the
    loser throws away a real hypothesis.
    """

    name = "cascade"

    def __init__(
        self,
        primary: Recognizer,
        fallback: Recognizer | None = None,
        threshold: float = 0.4,
    ):
        self.primary = primary
        self.fallback = fallback
        self.threshold = threshold
        self.stats = CascadeStats()

    @property
    def full_name(self) -> str:
        tail = self.fallback.name if self.fallback else "none"
        return f"cascade({self.primary.name}@{self.threshold}->{tail})"

    def warmup(self) -> None:
        self.primary.warmup()
        # The fallback is loaded lazily on first deferral: for a clean batch it
        # may never be needed, and if it is a remote API there is nothing to
        # warm up anyway.

    def read(self, crop: Image.Image) -> Reading:
        self.stats.total += 1
        reading = self.primary.read(crop)

        if reading.confidence >= self.threshold or self.fallback is None:
            return reading

        self.stats.deferred += 1
        self.stats._deferred_confidences.append(reading.confidence)

        try:
            second = self.fallback.read(crop)
        except Exception:  # noqa: BLE001
            # A failing fallback must degrade to the primary's guess, never
            # take down a batch of 60k crops.
            self.stats.fallback_failed += 1
            return reading

        if not second.candidates:
            return reading

        if second.best != reading.best:
            self.stats.fallback_improved += 1

        # Fallback ranks first; the primary's guess survives as a candidate.
        merged = list(second.candidates)
        seen = {t for t, _ in merged}
        for text, conf in reading.candidates:
            if text not in seen:
                merged.append((text, conf))
        return Reading(merged)
