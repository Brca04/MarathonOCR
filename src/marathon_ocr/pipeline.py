"""Full-frame processing: photo in, bib numbers out.

This is the production path. The benchmark in ``scripts/eval_recognizers.py``
measures recognition on perfect human-drawn crops; this measures what actually
happens when the detector has to find the bibs itself, which is always worse and
is the only number that predicts the product.

Design note: the pipeline emits **every candidate reading it saw**, each with a
confidence, rather than one answer per photo. A runner searching for 1308 needs
that number to be *somewhere* in the photo's candidate set; pruning to a single
best guess per crop is how photos silently go missing from search results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from .crops import prepare_for_ocr
from .detectors.base import Detection, Detector
from .recognizers.base import Reading, Recognizer

__all__ = ["BibHit", "PhotoResult", "BibPipeline"]


@dataclass
class BibHit:
    """One candidate bib found in a photo."""

    text: str
    confidence: float
    box: Detection
    source_height: float

    def as_row(self, photo_id: str) -> dict:
        """Shaped for the ``detections`` table."""
        return {
            "photo_id": photo_id,
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": [
                round(self.box.x0, 1),
                round(self.box.y0, 1),
                round(self.box.x1, 1),
                round(self.box.y1, 1),
            ],
        }


@dataclass
class PhotoResult:
    hits: list[BibHit] = field(default_factory=list)
    regions_examined: int = 0

    @property
    def numbers(self) -> set[str]:
        return {h.text for h in self.hits}

    def best_per_number(self) -> list[BibHit]:
        """Collapse duplicate readings of the same number, keeping the most
        confident. Two photographers' angles on one runner legitimately produce
        the same number twice; the database wants one row per (photo, number)."""
        best: dict[str, BibHit] = {}
        for hit in self.hits:
            if hit.text not in best or hit.confidence > best[hit.text].confidence:
                best[hit.text] = hit
        return sorted(best.values(), key=lambda h: -h.confidence)


class BibPipeline:
    """detect -> crop -> upscale -> recognize, over a whole photo."""

    def __init__(
        self,
        detector: Detector,
        recognizer: Recognizer,
        min_height: int = 64,
        expand: float = 0.05,
        min_confidence: float = 0.0,
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.min_height = min_height
        self.expand = expand
        # Kept at 0 by default: a low-confidence reading is still worth storing,
        # because fuzzy search ranks by confidence rather than filtering on it.
        # Raise it only if false positives become a real problem in the UI.
        self.min_confidence = min_confidence

    def warmup(self) -> None:
        self.detector.warmup()
        self.recognizer.warmup()

    def process(self, image: Image.Image) -> PhotoResult:
        if image.mode != "RGB":
            image = image.convert("RGB")

        result = PhotoResult()
        regions = self.detector.detect(image)
        result.regions_examined = len(regions)

        for region in regions:
            if region.width < 4 or region.height < 4:
                continue
            padded = region.expand(self.expand, (image.width, image.height))
            crop = prepare_for_ocr(padded.crop(image), self.min_height)

            reading = self.recognizer.read(crop)
            for text, confidence in self._candidates(reading):
                if confidence < self.min_confidence:
                    continue
                result.hits.append(
                    BibHit(
                        text=text,
                        confidence=confidence,
                        box=padded,
                        source_height=region.height,
                    )
                )
        return result

    @staticmethod
    def _candidates(reading: Reading) -> list[tuple[str, float]]:
        return reading.candidates
