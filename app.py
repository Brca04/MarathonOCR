#!/usr/bin/env python3
"""Test UI: upload a real marathon photo, see the bib numbers the pipeline finds.

Same detect -> crop -> upscale -> recognize path as scripts/run.py, just with
a browser front end so you can drag in your own photos instead of using the
CLI. Nothing new is implemented in the pipeline itself.

Run with:
    .venv\\Scripts\\streamlit.exe run app.py
or, if the venv is activated:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.detectors import (  # noqa: E402
    PersonDetector,
    TorsoHeuristicDetector,
    WholeImageDetector,
    YOLOBibDetector,
)
from marathon_ocr.pipeline import BibPipeline  # noqa: E402
from marathon_ocr.recognizers import build  # noqa: E402

DEFAULT_BIB_WEIGHTS = ROOT / "models" / "bib_detector" / "best.pt"

st.set_page_config(page_title="MarathonOCR — bib test", layout="wide")


@st.cache_resource(show_spinner=False)
def load_pipeline(detector_kind: str, weights_path: str, det_conf: float,
                   min_conf: float, min_height: int, use_gpu: bool) -> BibPipeline:
    """Build and warm up a pipeline once per unique settings combo."""
    if detector_kind == "yolo-bib":
        detector = YOLOBibDetector(weights_path, conf=det_conf)
    elif detector_kind == "person":
        detector = PersonDetector(conf=det_conf)
    elif detector_kind == "torso":
        detector = TorsoHeuristicDetector(PersonDetector(conf=det_conf))
    else:
        detector = WholeImageDetector()

    recognizer = build("easyocr", gpu=use_gpu)
    pipeline = BibPipeline(
        detector, recognizer, min_height=min_height, min_confidence=min_conf
    )
    pipeline.warmup()
    return pipeline


def draw_boxes(image: Image.Image, hits) -> Image.Image:
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for hit in hits:
        b = hit.box
        draw.rectangle([b.x0, b.y0, b.x1, b.y1], outline="lime", width=4)
        label = f"{hit.text} ({hit.confidence:.2f})"
        draw.text((b.x0, max(0, b.y0 - 20)), label, fill="lime")
    return out


st.title("MarathonOCR — bib detection test")
st.caption(
    "Upload a real race photo. detect \u2192 crop \u2192 upscale \u2192 recognize, "
    "using the trained bib detector + EasyOCR."
)

with st.sidebar:
    st.header("Settings")
    detector_choices = ["yolo-bib", "whole", "person", "torso"]
    default_idx = 0 if DEFAULT_BIB_WEIGHTS.exists() else 1
    detector_kind = st.selectbox("Detector", detector_choices, index=default_idx)

    weights_path = str(DEFAULT_BIB_WEIGHTS)
    if detector_kind == "yolo-bib":
        weights_path = st.text_input("Bib detector weights", value=str(DEFAULT_BIB_WEIGHTS))
        if not Path(weights_path).exists():
            st.error(f"weights not found: {weights_path}")

    det_conf = st.slider("Detector confidence", 0.05, 0.9, 0.25, 0.05)
    min_conf = st.slider(
        "Recognizer min confidence", 0.0, 0.9, 0.3, 0.05,
        help="0.3 was the measured sweet spot on the eval set",
    )
    min_height = st.slider("Min crop height (upscale target, px)", 32, 128, 64, 8)
    use_gpu = st.checkbox("Use GPU", value=True)

uploaded = st.file_uploader(
    "Marathon photo", type=["jpg", "jpeg", "png", "bmp", "webp"]
)

if uploaded is not None:
    image = Image.open(uploaded).convert("RGB")

    try:
        pipeline = load_pipeline(
            detector_kind, weights_path, det_conf, min_conf, min_height, use_gpu
        )
    except Exception as exc:  # surfaces missing weights, CUDA errors, etc.
        st.error(f"failed to load pipeline: {exc}")
        st.stop()

    t0 = time.perf_counter()
    result = pipeline.process(image)
    elapsed = time.perf_counter() - t0

    hits = result.best_per_number()
    annotated = draw_boxes(image, hits)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Original")
        st.image(image, use_container_width=True)
    with col2:
        st.subheader("Detections")
        st.image(annotated, use_container_width=True)

    st.write(
        f"**{elapsed:.2f}s** \u00b7 {result.regions_examined} region(s) examined \u00b7 "
        f"{len(hits)} bib number(s) found"
    )

    if hits:
        st.table(
            [
                {
                    "bib number": h.text,
                    "confidence": round(h.confidence, 3),
                    "crop height (px)": round(h.source_height, 1),
                }
                for h in hits
            ]
        )
    else:
        st.info("No bib numbers found. Try lowering detector/recognizer confidence.")
else:
    st.info("Upload a photo to run the pipeline.")
