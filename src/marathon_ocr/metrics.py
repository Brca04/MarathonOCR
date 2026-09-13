"""Scoring.

The metric you choose quietly decides which model you ship, so it is worth
being explicit about what we optimise for.

For a photo gallery the user-facing question is *"did the runner find their
photo?"*, and that is **recall under fuzzy search**, not exact-match accuracy.
A bib read as ``l308`` still finds ``1308`` once trigram search is in front of
it. So we report three numbers side by side:

``exact``
    Strict string equality. The number people quote in papers. Pessimistic
    relative to the product.
``cer``
    Character error rate. Diagnostic: tells you *how* wrong the wrong ones are.
    A CER of 0.1 means fuzzy search will rescue most of them; 0.6 means the
    recognizer is hallucinating and no search layer will help.
``fuzzy@1``
    Correct within edit distance 1 — a direct proxy for what the production
    query will recover. This is the number to optimise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["levenshtein", "Prediction", "ScoreBoard"]


def levenshtein(a: str, b: str) -> int:
    """Standard edit distance, iterative with a single row of state."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        previous = current
    return previous[-1]


@dataclass
class Prediction:
    """What a recognizer said about one crop, against what was true."""

    key: str
    truth: str
    predicted: str
    confidence: float = 0.0
    original_height: float = 0.0

    @property
    def exact(self) -> bool:
        return self.predicted == self.truth

    @property
    def distance(self) -> int:
        return levenshtein(self.predicted, self.truth)

    @property
    def cer(self) -> float:
        return self.distance / max(len(self.truth), 1)

    @property
    def fuzzy1(self) -> bool:
        return self.distance <= 1

    @property
    def empty(self) -> bool:
        """The recognizer declined to read anything. Worth tracking separately:
        a blank is recoverable by a second pass, a confident wrong answer is
        not."""
        return not self.predicted


@dataclass
class ScoreBoard:
    """Aggregates predictions and slices them by crop height.

    The height slices are the interesting part. A single accuracy number hides
    the fact that performance falls off a cliff below ~20px, which is precisely
    the decision you need when choosing between "train a better recognizer" and
    "require higher-resolution source photos".
    """

    name: str
    predictions: list[Prediction] = field(default_factory=list)
    elapsed_s: float = 0.0

    def add(self, prediction: Prediction) -> None:
        self.predictions.append(prediction)

    def _stats(self, subset: list[Prediction]) -> dict:
        n = len(subset)
        if n == 0:
            return {"n": 0, "exact": 0.0, "fuzzy1": 0.0, "cer": 0.0, "empty": 0.0}
        return {
            "n": n,
            "exact": sum(p.exact for p in subset) / n,
            "fuzzy1": sum(p.fuzzy1 for p in subset) / n,
            "cer": sum(p.cer for p in subset) / n,
            "empty": sum(p.empty for p in subset) / n,
        }

    def report(self) -> dict:
        buckets = {
            "all": self.predictions,
            "tiny (<20px)": [p for p in self.predictions if p.original_height < 20],
            "small (20-40px)": [
                p for p in self.predictions if 20 <= p.original_height < 40
            ],
            "large (>=40px)": [p for p in self.predictions if p.original_height >= 40],
        }
        return {
            "name": self.name,
            "elapsed_s": round(self.elapsed_s, 1),
            "per_crop_ms": round(
                1000 * self.elapsed_s / max(len(self.predictions), 1), 1
            ),
            "buckets": {k: self._stats(v) for k, v in buckets.items()},
        }

    def worst(self, limit: int = 15) -> list[Prediction]:
        """The most-wrong predictions, for eyeballing failure modes."""
        return sorted(self.predictions, key=lambda p: -p.cer)[:limit]

    def format_table(self) -> str:
        r = self.report()
        lines = [
            f"{r['name']}  ({r['per_crop_ms']} ms/crop, {r['elapsed_s']}s total)",
            f"  {'bucket':<18}{'n':>5}{'exact':>9}{'fuzzy@1':>9}{'CER':>8}{'blank':>8}",
        ]
        for bucket, s in r["buckets"].items():
            if s["n"] == 0:
                continue
            lines.append(
                f"  {bucket:<18}{s['n']:>5}{s['exact']:>8.1%}{s['fuzzy1']:>9.1%}"
                f"{s['cer']:>8.3f}{s['empty']:>8.1%}"
            )
        return "\n".join(lines)
