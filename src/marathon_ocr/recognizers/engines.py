"""Concrete recognizers.

Each backend is imported lazily inside ``warmup``/``read`` so the harness runs
with whatever subset you have installed. Missing a dependency skips that engine
rather than breaking the run.
"""

from __future__ import annotations

import base64
import io
import os

import numpy as np
from PIL import Image

from .base import Reading, Recognizer

__all__ = ["PaddleRecognizer", "EasyOCRRecognizer", "TrOCRRecognizer", "VLMRecognizer"]


class PaddleRecognizer(Recognizer):
    """PaddleOCR. The strongest classical baseline for short numeric strings.

    ``use_angle_cls`` stays off: we deskew during cropping, so the angle
    classifier only adds latency and a chance to rotate a good crop into a bad
    one.
    """

    name = "paddleocr"

    def __init__(self, use_gpu: bool = True, lang: str = "en"):
        self.use_gpu = use_gpu
        self.lang = lang
        self._ocr = None

    def warmup(self) -> None:
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(
            use_angle_cls=False,
            lang=self.lang,
            use_gpu=self.use_gpu,
            show_log=False,
        )

    def read(self, crop: Image.Image) -> Reading:
        self.warmup()
        result = self._ocr.ocr(np.array(crop), cls=False)
        if not result or not result[0]:
            return Reading()
        raw = [(line[1][0], float(line[1][1])) for line in result[0]]
        return Reading.from_raw(raw)


class EasyOCRRecognizer(Recognizer):
    """EasyOCR with a digit allowlist.

    The allowlist is doing real work here — constraining the decoder to ``0-9``
    removes the entire class of letter/digit confusions before they happen,
    which matters more than the base model quality on 2-5 character strings.
    """

    name = "easyocr"

    def __init__(self, gpu: bool = True):
        self.gpu = gpu
        self._reader = None

    def warmup(self) -> None:
        if self._reader is not None:
            return
        import easyocr

        self._reader = easyocr.Reader(["en"], gpu=self.gpu, verbose=False)

    def read(self, crop: Image.Image) -> Reading:
        self.warmup()
        result = self._reader.readtext(
            np.array(crop),
            allowlist="0123456789",
            detail=1,
            paragraph=False,
        )
        raw = [(text, float(conf)) for _, text, conf in result]
        return Reading.from_raw(raw)


class TrOCRRecognizer(Recognizer):
    """TrOCR, optionally a checkpoint you fine-tuned on synthetic bibs.

    Bib typography is a tiny, generatable domain — a few condensed sans faces on
    coloured card. Fine-tuning ``trocr-small-printed`` on synthetic bibs is an
    evening's work on a 5070 and is the most likely route past whatever ceiling
    the off-the-shelf engines hit.
    """

    name = "trocr"

    def __init__(
        self,
        checkpoint: str = "microsoft/trocr-small-printed",
        device: str | None = None,
    ):
        self.checkpoint = checkpoint
        self.device = device
        self._model = None
        self._processor = None

    def warmup(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        self.device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._processor = TrOCRProcessor.from_pretrained(self.checkpoint)
        self._model = (
            VisionEncoderDecoderModel.from_pretrained(self.checkpoint)
            .to(self.device)
            .eval()
        )

    def read(self, crop: Image.Image) -> Reading:
        return self.read_batch([crop])[0]

    def read_batch(self, crops: list[Image.Image]) -> list[Reading]:
        self.warmup()
        import torch

        pixel_values = self._processor(
            images=[c.convert("RGB") for c in crops], return_tensors="pt"
        ).pixel_values.to(self.device)

        with torch.no_grad():
            generated = self._model.generate(
                pixel_values, max_new_tokens=8, num_beams=3
            )
        texts = self._processor.batch_decode(generated, skip_special_tokens=True)
        # TrOCR gives no calibrated per-sequence score without extra work; a
        # flat confidence is honest rather than inventing one.
        return [Reading.single(t, 0.5) for t in texts]


class VLMRecognizer(Recognizer):
    """A vision language model, via the Anthropic API.

    Included because on tilted, folded and motion-blurred bibs it tends to beat
    classical OCR by a wide margin, and it needs no training data at all. Treat
    it as the accuracy ceiling to measure the free engines against — and as a
    genuinely viable production option: at a few thousand crops per event the
    cost is small.

    Swap ``_call`` for a local Qwen2.5-VL if you want the loop fully offline.
    """

    name = "vlm"

    PROMPT = (
        "This is a cropped race bib from a marathon photo. "
        "Reply with ONLY the bib number as digits. "
        "If no number is legible, reply exactly: NONE"
    )

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def warmup(self) -> None:
        if self._client is not None:
            return
        import anthropic

        self._client = anthropic.Anthropic(api_key=self.api_key)

    def read(self, crop: Image.Image) -> Reading:
        self.warmup()
        buf = io.BytesIO()
        crop.convert("RGB").save(buf, format="PNG")
        b64 = base64.standard_b64encode(buf.getvalue()).decode()

        message = self._client.messages.create(
            model=self.model,
            max_tokens=16,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": self.PROMPT},
                    ],
                }
            ],
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        if text.upper().startswith("NONE"):
            return Reading()
        return Reading.single(text, 0.9)


REGISTRY = {
    "paddleocr": PaddleRecognizer,
    "easyocr": EasyOCRRecognizer,
    "trocr": TrOCRRecognizer,
    "vlm": VLMRecognizer,
}
