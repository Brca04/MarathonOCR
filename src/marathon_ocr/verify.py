"""Second opinion from Claude Haiku on the bib reads the local model is unsure of.

The review chain is three steps:

    local OCR (every person)  ->  Haiku (only unsure reads)  ->  human (review app)

The local model's confidence is well calibrated (every read above 0.8 was
correct within one digit on the eval set), so confident reads are accepted as
they are and Haiku only sees the rest. Its job is not to replace the model but
to agree or disagree with it: agreement makes a read safe to publish, and
disagreement is exactly what a person should look at first.

Needs ANTHROPIC_API_KEY in the environment (or a .env file next to the repo).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field

from PIL import Image

from .recognizers.base import normalise_digits

__all__ = ["HaikuVerifier", "HaikuRead", "Verdict", "judge"]

DEFAULT_MODEL = os.environ.get("MARATHON_HAIKU_MODEL", "claude-haiku-4-5")

PROMPT = """This image is cropped around one runner in a race photo.

Read the race bib number(s) printed on bibs pinned to runners in this image.
Only count numbers on race bibs - ignore shirt text, logos, sponsor names,
timing clocks, dates and signs.

The local OCR model suggested: {hint}. It may be wrong; read the image yourself.

Reply with JSON only, no other text:
{{"bibs": [{{"number": "213", "clarity": "clear"}}], "note": ""}}

- "clarity" is "clear" if every digit is plainly readable, "partial" if some
  digits are hidden, blurred or cut off (give your best reading).
- If no bib is visible or no digits can be read, reply {{"bibs": [], "note": "why"}}."""


WHOLE_PROMPT = """This is a full photo from a running race.

List every race bib number you can read on bibs pinned to runners anywhere in
the photo, including runners in the background. Ignore shirt text, logos,
sponsor names, timing clocks, dates and signs.

Numbers already found by the per-runner check: {hint}. Include those too if
you can see them, and add any that were missed.

Reply with JSON only, no other text:
{{"bibs": [{{"number": "213", "clarity": "clear"}}], "note": ""}}

- "clarity" is "clear" if every digit is plainly readable, "partial" if some
  digits are hidden, blurred or cut off (give your best reading).
- If no bib can be read, reply {{"bibs": [], "note": "why"}}."""


@dataclass
class HaikuRead:
    numbers: list[str] = field(default_factory=list)
    clarity: dict[str, str] = field(default_factory=dict)
    note: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    @property
    def clear_numbers(self) -> list[str]:
        return [n for n in self.numbers if self.clarity.get(n) == "clear"]


class HaikuVerifier:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None,
                 max_side: int = 1024):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_side = max_side
        self._client = None

    def warmup(self) -> None:
        if self._client is not None:
            return
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Put it in a .env file in the repo "
                "root (ANTHROPIC_API_KEY=sk-ant-...) - never commit it."
            )
        import anthropic

        # The SDK already retries 429/5xx with backoff; a few more tries help
        # when a whole event is pushed through at once.
        self._client = anthropic.Anthropic(api_key=self.api_key, max_retries=5)

    def _encode(self, crop: Image.Image, max_side: int) -> str:
        img = crop.convert("RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return base64.standard_b64encode(buf.getvalue()).decode()

    def read_whole(self, photo: Image.Image, found: list[str] | None = None) -> HaikuRead:
        """One look at the entire photo, to catch runners the person detector
        missed or cropped badly (cut-off torso, bib on the edge of the box)."""
        return self.read(photo, found, prompt=WHOLE_PROMPT, max_side=1568)

    def read(self, crop: Image.Image, hint: list[str] | None = None,
             prompt: str = PROMPT, max_side: int | None = None) -> HaikuRead:
        self.warmup()
        hint_text = ", ".join(hint) if hint else "nothing"
        side = max_side or self.max_side
        try:
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64",
                                                     "media_type": "image/jpeg",
                                                     "data": self._encode(crop, side)}},
                        {"type": "text", "text": prompt.format(hint=hint_text)},
                    ],
                }],
            )
        except Exception as exc:  # noqa: BLE001 - one bad call must not stop a batch
            return HaikuRead(error=f"{type(exc).__name__}: {exc}"[:300])

        text = "".join(b.text for b in msg.content if b.type == "text")
        read = parse_reply(text)
        read.input_tokens = msg.usage.input_tokens
        read.output_tokens = msg.usage.output_tokens
        return read


def parse_reply(text: str) -> HaikuRead:
    """Tolerant JSON parse: Haiku occasionally wraps the object in prose/fences."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return HaikuRead(error=f"unparseable: {text[:120]!r}")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return HaikuRead(error=f"bad json: {text[:120]!r}")
    out = HaikuRead(note=str(data.get("note") or "")[:200])
    for b in data.get("bibs") or []:
        n = normalise_digits(str(b.get("number", "")))
        if n and n not in out.numbers:
            out.numbers.append(n)
            out.clarity[n] = "clear" if b.get("clarity") == "clear" else "partial"
    return out


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    kind: str            # confident | agree | disagree | haiku_only | model_only | empty | error | whole_only
    numbers: list[str]   # what we propose to publish for this person
    needs_human: bool


def judge(ocr: list[tuple[str, float]], haiku: HaikuRead | None,
          confident_at: float = 0.8) -> Verdict:
    """Combine the local model's candidates with Haiku's reading for one person."""
    best = max(ocr, key=lambda c: c[1]) if ocr else None

    if best and best[1] >= confident_at:
        return Verdict("confident", [best[0]], False)
    if haiku is None:
        # Not sent (e.g. --dry-run): keep the model's guess, but flag it.
        return Verdict("model_only", [best[0]] if best else [], bool(best))
    if haiku.error:
        return Verdict("error", [best[0]] if best else [], True)

    ocr_texts = {t for t, _ in ocr}
    agreed = [n for n in haiku.numbers if n in ocr_texts]
    if agreed:
        # Both read the same number: safe unless Haiku itself was unsure.
        clear = all(haiku.clarity.get(n) == "clear" for n in agreed)
        return Verdict("agree", agreed, not clear)
    if haiku.numbers:
        # Haiku sees a bib the model missed or misread. Publish Haiku's read
        # (it is usually right on blurred/tilted bibs) but put it in front of you.
        return Verdict("disagree" if ocr else "haiku_only", haiku.numbers, True)
    if best:
        # Model read something, Haiku says there is no legible bib.
        return Verdict("disagree", [], True)
    return Verdict("empty", [], False)
