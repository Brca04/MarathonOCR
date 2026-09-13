"""Detection: finding bibs in a full photo.

Two stages, and the split is deliberate.

``PersonDetector`` uses stock YOLO weights trained on COCO — no labelled data
needed, works today. Cropping to torsos turns "find a 19px object in a 6000px
frame" into "find a 19px object in a 400px frame", which is the difference
between a detector that works and one that does not.

``BibDetector`` is the part you fine-tune. Until you have training data, the
``TorsoHeuristicDetector`` below gives the pipeline something to run end to end
so the rest of the system can be built and measured in parallel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

__all__ = [
    "Detection",
    "Detector",
    "PersonDetector",
    "TorsoHeuristicDetector",
    "WholeImageDetector",
]


@dataclass(frozen=True)
class Detection:
    """An upright box in source-image coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0
    label: str = "bib"

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def expand(self, ratio: float, bounds: tuple[int, int]) -> "Detection":
        """Grow the box by ``ratio`` on each side, clipped to the image."""
        dx, dy = self.width * ratio, self.height * ratio
        w, h = bounds
        return Detection(
            max(0, self.x0 - dx),
            max(0, self.y0 - dy),
            min(w, self.x1 + dx),
            min(h, self.y1 + dy),
            self.confidence,
            self.label,
        )

    def crop(self, image: Image.Image) -> Image.Image:
        return image.crop(
            (round(self.x0), round(self.y0), round(self.x1), round(self.y1))
        )


class Detector(ABC):
    name: str = "detector"

    @abstractmethod
    def detect(self, image: Image.Image) -> list[Detection]:
        ...

    def warmup(self) -> None:
        ...


class PersonDetector(Detector):
    """Stock YOLO, COCO class 0. No training required."""

    name = "yolo-person"

    def __init__(self, weights: str = "yolo11n.pt", conf: float = 0.25):
        self.weights = weights
        self.conf = conf
        self._model = None

    def warmup(self) -> None:
        if self._model is not None:
            return
        from ultralytics import YOLO

        self._model = YOLO(self.weights)

    def detect(self, image: Image.Image) -> list[Detection]:
        self.warmup()
        results = self._model.predict(
            image, classes=[0], conf=self.conf, verbose=False
        )
        out = []
        for r in results:
            for b in r.boxes:
                x0, y0, x1, y1 = (float(v) for v in b.xyxy[0])
                out.append(Detection(x0, y0, x1, y1, float(b.conf[0]), "person"))
        return out


class TorsoHeuristicDetector(Detector):
    """Placeholder bib detector: the torso band of each detected person.

    A bib sits roughly between 30% and 65% of standing height, centred. This is
    crude and will produce false positives, but it makes the end-to-end pipeline
    runnable *now*, and gives the recognizer realistic (imperfect) crops to be
    measured on. Replace with a fine-tuned single-class YOLO as soon as you have
    training data; the interface does not change.
    """

    name = "torso-heuristic"

    def __init__(self, person_detector: PersonDetector | None = None):
        self.person = person_detector or PersonDetector()

    def warmup(self) -> None:
        self.person.warmup()

    def detect(self, image: Image.Image) -> list[Detection]:
        out = []
        for p in self.person.detect(image):
            out.append(
                Detection(
                    x0=p.x0 + 0.15 * p.width,
                    y0=p.y0 + 0.30 * p.height,
                    x1=p.x1 - 0.15 * p.width,
                    y1=p.y0 + 0.65 * p.height,
                    confidence=p.confidence,
                    label="bib?",
                )
            )
        return out


class YOLOBibDetector(Detector):
    """Your fine-tuned single-class bib detector. Point ``weights`` at the
    ``best.pt`` from training and this drops straight into the pipeline."""

    name = "yolo-bib"

    def __init__(self, weights: str, conf: float = 0.25, imgsz: int = 1280):
        self.weights = weights
        self.conf = conf
        self.imgsz = imgsz
        self._model = None

    def warmup(self) -> None:
        if self._model is not None:
            return
        from ultralytics import YOLO

        self._model = YOLO(self.weights)

    def detect(self, image: Image.Image) -> list[Detection]:
        self.warmup()
        results = self._model.predict(
            image, conf=self.conf, imgsz=self.imgsz, verbose=False
        )
        out = []
        for r in results:
            for b in r.boxes:
                x0, y0, x1, y1 = (float(v) for v in b.xyxy[0])
                out.append(Detection(x0, y0, x1, y1, float(b.conf[0]), "bib"))
        return out


class WholeImageDetector(Detector):
    """A control, not a strategy: hands the entire frame to the recognizer.

    Included so the end-to-end benchmark can quantify what person-cropping
    actually buys. With a median bib height of 19px in a full frame, this is
    expected to fail badly — and having that number measured rather than
    assumed is what justifies the two-stage design.
    """

    name = "whole-image"

    def detect(self, image: Image.Image) -> list[Detection]:
        return [Detection(0, 0, image.width, image.height, 1.0, "frame")]
