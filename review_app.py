#!/usr/bin/env python3
"""Review UI: scan a folder of marathon photos, correct the model's bib reads,
export a CSV of (image, bib numbers) once you're done.

Workflow:
    1. Pick a folder of photos (native folder dialog, or paste a path).
    2. Step through them one at a time (or jump via the photo list); the
       model's detections show up as removable entries.
    3. Add any numbers the model missed, remove any wrong ones.
    4. Progress is saved to disk automatically, so closing the browser or
       restarting the app does not lose work.
    5. Export a CSV: image_name, bib_numbers.

Run with:
    .venv\\Scripts\\streamlit.exe run review_app.py
"""

from __future__ import annotations

import csv
import json
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
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

st.set_page_config(page_title="MarathonOCR Review", layout="wide")


# --------------------------------------------------------------------------
# Native folder picker
# --------------------------------------------------------------------------

def open_folder_dialog() -> str | None:
    """Open the OS folder picker and return the chosen path, or None."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title="Select folder of photos")
    root.destroy()
    return path or None


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_pipeline(detector_kind: str, weights_path: str, det_conf: float,
                   min_conf: float, min_height: int, use_gpu: bool) -> BibPipeline:
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
        draw.rectangle([b.x0, b.y0, b.x1, b.y1], outline="red", width=3)
        label = f"{hit.text} ({hit.confidence:.2f})"
        draw.text((b.x0, max(0, b.y0 - 18)), label, fill="red")
    return out


def iter_images(folder: Path):
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


# --------------------------------------------------------------------------
# Progress persistence: one JSON file per folder, keyed by filename
# --------------------------------------------------------------------------

def progress_path(folder: Path) -> Path:
    return folder / ".marathon_ocr_review.json"


def load_progress(folder: Path) -> dict:
    p = progress_path(folder)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_progress(folder: Path, progress: dict) -> None:
    progress_path(folder).write_text(
        json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def save_current(folder: Path, progress: dict, image_name: str, numbers: list[str],
                  model_numbers: list[str]) -> None:
    progress[image_name] = {"numbers": numbers, "model_numbers": model_numbers}
    save_progress(folder, progress)


# --------------------------------------------------------------------------
# Sidebar — folder + settings
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("MarathonOCR Review")

    if st.button("Browse for folder...", use_container_width=True):
        chosen = open_folder_dialog()
        if chosen:
            st.session_state["folder_input"] = chosen

    folder_input = st.text_input(
        "Folder of photos",
        value=st.session_state.get("folder_input", st.session_state.get("folder", "")),
        placeholder=r"C:\path\to\photos",
        key="folder_input",
    )

    recent = st.session_state.get("recent_folders", [])
    if recent:
        pick = st.selectbox("Recent folders", ["(none)"] + recent, index=0)
        if pick != "(none)":
            folder_input = pick

    with st.expander("Detection settings", expanded=False):
        detector_choices = ["yolo-bib", "whole", "person", "torso"]
        default_idx = 0 if DEFAULT_BIB_WEIGHTS.exists() else 1
        detector_kind = st.selectbox("Detector", detector_choices, index=default_idx)

        weights_path = str(DEFAULT_BIB_WEIGHTS)
        if detector_kind == "yolo-bib":
            weights_path = st.text_input(
                "Bib detector weights", value=str(DEFAULT_BIB_WEIGHTS)
            )

        det_conf = st.slider("Detector confidence", 0.05, 0.9, 0.25, 0.05)
        min_conf = st.slider("Recognizer min confidence", 0.0, 0.9, 0.3, 0.05)
        min_height = st.slider("Min crop height (px)", 32, 128, 64, 8)
        use_gpu = st.checkbox("Use GPU", value=True)

if not folder_input:
    st.title("MarathonOCR Review")
    st.write("Select a folder of photos in the sidebar to begin.")
    st.stop()

folder = Path(folder_input)
if not folder.is_dir():
    st.title("MarathonOCR Review")
    st.error(f"Not a folder: {folder}")
    st.stop()

images = iter_images(folder)
if not images:
    st.title("MarathonOCR Review")
    st.error(f"No images found in {folder}")
    st.stop()

recent_list = st.session_state.get("recent_folders", [])
if str(folder) not in recent_list:
    st.session_state["recent_folders"] = [str(folder)] + recent_list[:4]

if st.session_state.get("folder") != str(folder):
    st.session_state["folder"] = str(folder)
    st.session_state["idx"] = 0
    st.session_state["progress"] = load_progress(folder)
    st.session_state["progress_folder"] = str(folder)

progress: dict = st.session_state["progress"]
idx = max(0, min(st.session_state.get("idx", 0), len(images) - 1))
st.session_state["idx"] = idx
current_path = images[idx]
scanned_count = sum(1 for p in images if p.name in progress)
all_done = scanned_count == len(images)

# --------------------------------------------------------------------------
# Header: progress + jump-to-photo list
# --------------------------------------------------------------------------

st.title("MarathonOCR Review")

top_l, top_r = st.columns([3, 1])
with top_l:
    st.progress(scanned_count / len(images))
    st.caption(f"{scanned_count} / {len(images)} reviewed \u2014 {folder}")
with top_r:
    if all_done:
        st.write("All photos reviewed.")

with st.expander(f"Photo list ({len(images)})", expanded=False):
    cols_per_row = 10
    for row_start in range(0, len(images), cols_per_row):
        row_imgs = images[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, img_path in zip(cols, row_imgs):
            i = images.index(img_path)
            done = img_path.name in progress
            label = f"{'[x]' if done else '[ ]'} {i + 1}"
            with col:
                if st.button(
                    label, key=f"jump_{i}",
                    type="primary" if i == idx else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["idx"] = i
                    st.rerun()

st.divider()

# --------------------------------------------------------------------------
# Pipeline + detection for the current photo
# --------------------------------------------------------------------------

try:
    pipeline = load_pipeline(
        detector_kind, weights_path, det_conf, min_conf, min_height, use_gpu
    )
except Exception as exc:
    st.error(f"Failed to load pipeline: {exc}")
    st.stop()

image = Image.open(current_path).convert("RGB")

cache_key = (str(current_path), detector_kind, weights_path, det_conf, min_conf, min_height)
if st.session_state.get("last_cache_key") != cache_key:
    t0 = time.perf_counter()
    result = pipeline.process(image)
    elapsed = time.perf_counter() - t0
    hits = result.best_per_number()
    st.session_state["last_hits"] = hits
    st.session_state["last_regions"] = result.regions_examined
    st.session_state["last_elapsed"] = elapsed
    st.session_state["last_cache_key"] = cache_key
else:
    hits = st.session_state["last_hits"]

model_numbers = [h.text for h in hits]

chip_key = f"chips_{current_path.name}"
if chip_key not in st.session_state:
    existing_entry = progress.get(current_path.name)
    st.session_state[chip_key] = list(existing_entry["numbers"]) if existing_entry else list(model_numbers)

current_numbers: list[str] = st.session_state[chip_key]

# --------------------------------------------------------------------------
# Main layout: annotated image (left) + review panel (right)
# --------------------------------------------------------------------------

img_col, panel_col = st.columns([3, 2])

with img_col:
    status_text = "reviewed" if current_path.name in progress else "not reviewed"
    st.subheader(f"{current_path.name} ({status_text})")
    annotated = draw_boxes(image, hits)
    st.image(annotated, use_container_width=True)
    st.caption(
        f"{st.session_state['last_elapsed']:.2f}s, "
        f"{st.session_state['last_regions']} region(s) examined"
    )
    with st.expander("Show original (no boxes)"):
        st.image(image, use_container_width=True)

with panel_col:
    st.subheader("Confirmed bib numbers")

    if current_numbers:
        chip_cols = st.columns(min(len(current_numbers), 4) or 1)
        to_remove = None
        for i, num in enumerate(current_numbers):
            with chip_cols[i % len(chip_cols)]:
                if st.button(f"remove {num}", key=f"rm_{current_path.name}_{i}_{num}",
                              use_container_width=True):
                    to_remove = i
        if to_remove is not None:
            current_numbers.pop(to_remove)
            st.rerun()
    else:
        st.caption("No numbers yet.")

    with st.form(key=f"add_form_{current_path.name}", clear_on_submit=True):
        add_col, btn_col = st.columns([3, 1])
        with add_col:
            new_number = st.text_input(
                "Add a missed number", placeholder="e.g. 1057", label_visibility="collapsed"
            )
        with btn_col:
            add_clicked = st.form_submit_button("Add", use_container_width=True)
        if add_clicked and new_number.strip():
            for token in new_number.replace(",", " ").split():
                if token not in current_numbers:
                    current_numbers.append(token)
            st.rerun()

    if model_numbers:
        st.caption("Model suggested: " + ", ".join(model_numbers))
    else:
        st.caption("Model suggested: nothing found")

    st.write("")
    nav_prev, nav_save, nav_next = st.columns(3)
    with nav_prev:
        if st.button("Previous", disabled=idx == 0, use_container_width=True):
            save_current(folder, progress, current_path.name, current_numbers, model_numbers)
            st.session_state["idx"] = idx - 1
            st.rerun()
    with nav_save:
        if st.button("Save", use_container_width=True, type="primary"):
            save_current(folder, progress, current_path.name, current_numbers, model_numbers)
            st.toast(f"Saved {current_path.name}")
    with nav_next:
        if st.button("Next", disabled=idx == len(images) - 1, use_container_width=True):
            save_current(folder, progress, current_path.name, current_numbers, model_numbers)
            st.session_state["idx"] = idx + 1
            st.rerun()

# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

st.divider()

exp_l, exp_r = st.columns([3, 1])
with exp_l:
    st.subheader("Export")
    st.caption(
        "Writes one row per photo: image name and confirmed bib numbers. "
        "Unsaved edits on the current photo are included automatically."
    )
with exp_r:
    export_clicked = st.button("Export CSV", use_container_width=True)

if export_clicked:
    save_current(folder, progress, current_path.name, current_numbers, model_numbers)
    export_path = folder / "bib_export.csv"
    with export_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["image_name", "bib_numbers"])
        for img_path in images:
            entry = progress.get(img_path.name)
            numbers = entry["numbers"] if entry else []
            writer.writerow([img_path.name, ", ".join(numbers)])
    st.success(f"Exported to {export_path}")
    st.download_button(
        "Download CSV",
        data=export_path.read_bytes(),
        file_name="bib_export.csv",
        mime="text/csv",
    )
