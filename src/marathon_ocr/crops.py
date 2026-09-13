"""Turning annotated boxes into recognizer-ready crops.

Two separate concerns live here and it is worth keeping them straight:

*   :func:`extract_crop` produces a **ground-truth** crop from an annotation.
    Feeding these to a recognizer measures recognition in isolation, with
    detection error removed. That upper bound is the first number you want:
    if PaddleOCR only reads 60% of perfect crops, no detector improvement will
    save the pipeline.
*   :func:`prepare_for_ocr` is the preprocessing applied to *any* crop, ground
    truth or detector output, before it reaches a recognizer. It must be
    identical in both paths or your benchmark stops predicting production.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .dataset import Box, Dataset, Sample

__all__ = ["CropSpec", "extract_crop", "prepare_for_ocr", "export_benchmark_crops"]

# Bibs sit inside a printed border and OCR engines want quiet space around the
# glyphs. 15% of the box on each side empirically keeps the digits whole even
# when the annotator drew tight.
DEFAULT_PADDING = 0.15

# Below roughly 48px of glyph height, every OCR engine we care about degrades
# sharply. Upscaling is not free information, but it does let the engine's own
# convolutions see the strokes at the scale they were trained for.
DEFAULT_MIN_HEIGHT = 64


@dataclass(frozen=True)
class CropSpec:
    """A crop paired with its ground truth, ready to score."""

    image: Image.Image
    text: str | None
    source: str
    index: int
    original_height: float

    @property
    def key(self) -> str:
        stem = Path(self.source).stem
        return f"{stem}_{self.index:02d}"


def extract_crop(
    image: Image.Image,
    box: Box,
    padding: float = DEFAULT_PADDING,
) -> Image.Image:
    """Crop ``box`` out of ``image``, undoing the box's rotation.

    The box is deskewed by rotating the whole image about the box centre and
    then taking an upright crop. Rotating the full image is wasteful for a
    6000px original, but it is exact, and this runs offline on a batch — clarity
    beats cleverness until it shows up in a profile.
    """
    cx, cy = box.center

    if abs(box.rotation) > 0.5:
        # ``Box.corners`` rotates clockwise in screen space, so a positive
        # rotation tilts the bib clockwise; PIL's positive angle is
        # counter-clockwise, which is exactly the inverse we want.
        image = image.rotate(
            box.rotation,
            resample=Image.BICUBIC,
            center=(cx, cy),
        )

    pad_x = box.width * padding
    pad_y = box.height * padding
    left = cx - box.width / 2 - pad_x
    top = cy - box.height / 2 - pad_y
    right = cx + box.width / 2 + pad_x
    bottom = cy + box.height / 2 + pad_y

    # ``Image.crop`` happily returns black beyond the edges, which is the right
    # behaviour for a bib clipped by the frame.
    return image.crop((round(left), round(top), round(right), round(bottom)))


def prepare_for_ocr(
    crop: Image.Image,
    min_height: int = DEFAULT_MIN_HEIGHT,
) -> Image.Image:
    """Upscale a crop to a height OCR engines can work with.

    Plain Lanczos is the baseline. A learned super-resolution model
    (Real-ESRGAN) belongs here too and is the first thing to A/B once the
    harness reports a baseline — swap the body, rerun, compare the table.
    """
    if crop.mode != "RGB":
        crop = crop.convert("RGB")
    if crop.height >= min_height:
        return crop
    scale = min_height / max(crop.height, 1)
    target = (max(1, round(crop.width * scale)), min_height)
    return crop.resize(target, resample=Image.LANCZOS)


def iter_crops(
    dataset: Dataset,
    legible_only: bool = True,
    padding: float = DEFAULT_PADDING,
):
    """Yield a :class:`CropSpec` for every annotated box in the dataset."""
    for sample in dataset:
        with Image.open(sample.path) as img:
            img = img.convert("RGB")
            for i, box in enumerate(sample.boxes):
                if legible_only and not box.is_legible:
                    continue
                yield CropSpec(
                    image=extract_crop(img, box, padding=padding),
                    text=box.text,
                    source=sample.name,
                    index=i,
                    original_height=box.height,
                )


def export_benchmark_crops(
    dataset: Dataset,
    out_dir: str | Path,
    legible_only: bool = True,
) -> Path:
    """Write every ground-truth crop to disk alongside a labels file.

    Having the crops on disk matters more than it looks: it lets you eyeball
    what the recognizer is actually being asked to read, and it lets other
    tools (a fine-tuning run, a labelling pass) consume the same set.
    """
    import csv

    out_dir = Path(out_dir)
    (out_dir / "crops").mkdir(parents=True, exist_ok=True)

    rows = []
    for spec in iter_crops(dataset, legible_only=legible_only):
        filename = f"{spec.key}.png"
        spec.image.save(out_dir / "crops" / filename)
        rows.append(
            {
                "file": filename,
                "text": spec.text or "",
                "source": spec.source,
                "original_height": round(spec.original_height, 1),
            }
        )

    labels = out_dir / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["file", "text", "source", "original_height"]
        )
        writer.writeheader()
        writer.writerows(rows)

    return labels
