"""Parsing of the CVAT 1.1 annotation format used by the archive/ dataset.

The dataset is our *evaluation* set: 30 images, 146 hand-labelled bib boxes.
It is far too small to train on, but it is exactly the right size to score a
pipeline against, which is what every decision in this project depends on.

Two details of the CVAT format matter and are easy to get wrong:

1.  ``rotation`` is in degrees, clockwise, about the *centre* of the box. The
    xtl/ytl/xbr/ybr values describe the box **before** rotation. 100 of our 146
    boxes are rotated, so ignoring this silently corrupts most of the crops.
2.  ``<attribute name="text">`` carries the ground-truth digits. It may be
    absent or empty for an unreadable bib; those samples are kept but flagged,
    since "the detector should find it but nobody can read it" is a real and
    distinct case from "there is no bib here".
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

__all__ = ["Box", "Sample", "Dataset"]


@dataclass(frozen=True)
class Box:
    """One annotated bib, in the coordinate space of its source image."""

    xtl: float
    ytl: float
    xbr: float
    ybr: float
    rotation: float = 0.0
    text: str | None = None

    @property
    def width(self) -> float:
        return self.xbr - self.xtl

    @property
    def height(self) -> float:
        return self.ybr - self.ytl

    @property
    def center(self) -> tuple[float, float]:
        return ((self.xtl + self.xbr) / 2.0, (self.ytl + self.ybr) / 2.0)

    @property
    def is_legible(self) -> bool:
        """True when a human transcribed digits for this box."""
        return bool(self.text and self.text.strip())

    def corners(self) -> list[tuple[float, float]]:
        """The four corners after applying ``rotation``, clockwise from top-left.

        CVAT rotates clockwise in screen space (y grows downward), which is why
        the sine terms are not the textbook counter-clockwise arrangement.
        """
        cx, cy = self.center
        theta = math.radians(self.rotation)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        raw = [
            (self.xtl, self.ytl),
            (self.xbr, self.ytl),
            (self.xbr, self.ybr),
            (self.xtl, self.ybr),
        ]
        out = []
        for x, y in raw:
            dx, dy = x - cx, y - cy
            out.append((cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t))
        return out

    def axis_aligned_bounds(self) -> tuple[float, float, float, float]:
        """Smallest upright box containing the rotated box. Used for IoU scoring."""
        xs, ys = zip(*self.corners())
        return (min(xs), min(ys), max(xs), max(ys))

    def iou(self, other: "Box") -> float:
        """Intersection-over-union of the two axis-aligned bounds.

        Deliberately axis-aligned: detectors in this project emit upright boxes,
        so scoring against rotated polygons would penalise them for something we
        never asked them to predict.
        """
        ax0, ay0, ax1, ay1 = self.axis_aligned_bounds()
        bx0, by0, bx1, by1 = other.axis_aligned_bounds()
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        inter = (ix1 - ix0) * (iy1 - iy0)
        union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
        return inter / union if union > 0 else 0.0


@dataclass
class Sample:
    """One annotated photo."""

    image_id: int
    name: str
    width: int
    height: int
    boxes: list[Box] = field(default_factory=list)
    root: Path | None = None

    @property
    def path(self) -> Path:
        if self.root is None:
            raise ValueError(f"Sample {self.name!r} has no dataset root attached")
        return self.root / self.name

    @property
    def legible_boxes(self) -> list[Box]:
        return [b for b in self.boxes if b.is_legible]


class Dataset:
    """The archive/ evaluation set."""

    def __init__(self, samples: list[Sample], root: Path):
        self.samples = samples
        self.root = root

    @classmethod
    def from_cvat(cls, annotations: str | Path) -> "Dataset":
        annotations = Path(annotations)
        root = annotations.parent
        tree = ET.parse(annotations)

        samples: list[Sample] = []
        for node in tree.getroot().findall("image"):
            boxes = []
            for b in node.findall("box"):
                text = None
                for attr in b.findall("attribute"):
                    if attr.get("name") == "text":
                        text = (attr.text or "").strip() or None
                # CVAT writes rotation as 0-360; normalise to (-180, 180] so that
                # a bib tilted 5 degrees left reads as -5, not 355.
                rotation = float(b.get("rotation") or 0.0) % 360.0
                if rotation > 180.0:
                    rotation -= 360.0
                boxes.append(
                    Box(
                        xtl=float(b.get("xtl")),
                        ytl=float(b.get("ytl")),
                        xbr=float(b.get("xbr")),
                        ybr=float(b.get("ybr")),
                        rotation=rotation,
                        text=text,
                    )
                )
            samples.append(
                Sample(
                    image_id=int(node.get("id")),
                    name=node.get("name"),
                    width=int(node.get("width")),
                    height=int(node.get("height")),
                    boxes=boxes,
                    root=root,
                )
            )

        samples.sort(key=lambda s: s.image_id)
        return cls(samples, root)

    def __iter__(self):
        return iter(self.samples)

    def __len__(self) -> int:
        return len(self.samples)

    @cached_property
    def all_boxes(self) -> list[Box]:
        return [b for s in self.samples for b in s.boxes]

    def summary(self) -> dict:
        """Headline statistics. The height percentiles are the number that
        decides whether a given pipeline design is viable at all."""
        import numpy as np

        heights = np.array([b.height for b in self.all_boxes])
        widths = np.array([b.width for b in self.all_boxes])
        rotated = sum(1 for b in self.all_boxes if abs(b.rotation) > 0.5)
        legible = sum(1 for b in self.all_boxes if b.is_legible)
        return {
            "images": len(self.samples),
            "boxes": len(self.all_boxes),
            "legible": legible,
            "illegible": len(self.all_boxes) - legible,
            "rotated": rotated,
            "height_p10": float(np.percentile(heights, 10)),
            "height_median": float(np.median(heights)),
            "height_p90": float(np.percentile(heights, 90)),
            "width_median": float(np.median(widths)),
            "under_20px": int((heights < 20).sum()),
            "under_32px": int((heights < 32).sum()),
        }
