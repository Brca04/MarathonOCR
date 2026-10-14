#!/usr/bin/env python3
"""MarathonOCR review: a desktop app, no browser, no server.

Uses the files raceday.py writes next to the photos, so scan / check / recheck /
publish / pack / merge all keep working:
    .marathon_ocr_suggestions.json   what the scan + Haiku found (read only)
    .marathon_ocr_review.json        what you confirmed (written on every change)

Run:
    python review_desktop.py "C:\\Users\\bruno\\Desktop\\marathonZG\\Krume Ivanovski"
    (no folder: a folder picker opens)

Needs one package:  pip install PySide6-Essentials

Keys (when you are not typing a number):
    E / Enter   confirm & next          Q   back
    S           save                    A   tick all
    N           next unsure photo       F5  look for new photos
    0-9         start typing a missed number (Enter adds it, Esc leaves the box)
    double-click the photo: open it full size
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, QSize, Qt, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QImage, QImageReader, QKeySequence,
                           QPainter, QPen, QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SUGGESTIONS = ".marathon_ocr_suggestions.json"
HAIKU_FILE = ".marathon_ocr_haiku.json"
REVIEW = ".marathon_ocr_review.json"
SHOW_MAX = 2200  # photos are decoded at most this big: fast, still sharp on a 4K screen

VERDICT_COLOUR = {
    "confident": "#3ddc4a", "agree": "#3ddc4a",
    "haiku_only": "#ff9f1a", "model_only": "#ff9f1a", "error": "#ff9f1a",
    "disagree": "#ff3b30", "empty": "#9a9a9a",
}


# --------------------------------------------------------------------------- files

def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_suggestions(folder: Path) -> dict:
    p = folder / HAIKU_FILE
    return read_json(p if p.exists() else folder / SUGGESTIONS)


def natural(name: str):
    """_2 before _10: the order the photographer shot them in."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def images_in(folder: Path) -> list[Path]:
    try:
        return sorted((e for e in (Path(x.path) for x in os.scandir(folder))
                       if e.suffix.lower() in IMAGE_EXTS), key=lambda p: natural(p.name))
    except OSError:
        return []


def find_parts(root: Path) -> list[Path]:
    """The root and every folder under it that holds photos (hidden/_ folders skipped)."""
    out: list[Path] = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        if any(e.is_file() and Path(e.name).suffix.lower() in IMAGE_EXTS for e in entries):
            out.append(d)
        stack.extend(Path(e.path) for e in entries
                     if e.is_dir() and not e.name.startswith((".", "_")))
    return sorted(out, key=lambda p: (p != root, str(p).lower()))


class FolderLock:
    """Several reviewers on one folder: each save re-reads the file and changes only its photo."""

    def __init__(self, folder: Path):
        self.path = folder / ".marathon_ocr_review.lock"

    def __enter__(self):
        for _ in range(200):
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 10:
                        self.path.unlink(missing_ok=True)
                except OSError:
                    pass
                time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def save_entry(folder: Path, name: str, entry: dict) -> dict:
    with FolderLock(folder):
        disk = read_json(folder / REVIEW)
        disk[name] = entry
        tmp = (folder / REVIEW).with_suffix(".tmp")
        tmp.write_text(json.dumps(disk, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(folder / REVIEW)
    return disk


def priority(entry: dict | None) -> tuple[int, int]:
    if not entry:
        return (0, 0)
    disagree = sum(1 for p in entry.get("persons", []) if p.get("verdict") == "disagree")
    return (-disagree, -int(entry.get("needs_human", 0)))


def decode(path: Path) -> QImage:
    """Decode straight to screen size (JPEG scales while decoding, so this is fast)."""
    r = QImageReader(str(path))
    r.setAutoTransform(True)
    s = r.size()
    if s.isValid() and max(s.width(), s.height()) > SHOW_MAX:
        f = SHOW_MAX / max(s.width(), s.height())
        r.setScaledSize(QSize(round(s.width() * f), round(s.height() * f)))
    img = r.read()
    if not img.isNull():
        img.setText("orig_long", str(max(s.width(), s.height()) if s.isValid() else 0))
    return img


def clean(values) -> list[str]:
    nums: list[str] = []
    for v in values:
        for t in str(v).replace(",", " ").split():
            if t not in nums:
                nums.append(t)
    return nums


# --------------------------------------------------------------------------- photo

class PhotoView(QWidget):
    def __init__(self):
        super().__init__()
        self.img = QImage()
        self.entry: dict = {}
        self.path: Path | None = None
        self._pix = None
        self.setMinimumSize(400, 300)

    def show_photo(self, path: Path, img: QImage, entry: dict | None):
        self.path, self.img, self.entry = path, img, entry or {}
        self._pix = None
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1b1d21"))
        if self.img.isNull():
            p.setPen(QColor("#aaa"))
            p.drawText(self.rect(), Qt.AlignCenter, "Could not open this photo" if self.path else "")
            return
        iw, ih = self.img.width(), self.img.height()
        k = min(self.width() / iw, self.height() / ih)
        w, h = iw * k, ih * k
        x0, y0 = (self.width() - w) / 2, (self.height() - h) / 2
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(x0, y0, w, h), self.img)
        # Boxes were stored in the frame the checks ran on (entry w/h, else 2000 px long side).
        if self.entry.get("w"):
            frame_long = max(self.entry["w"], self.entry.get("h") or 0)
        else:
            orig = int(self.img.text("orig_long") or max(iw, ih))
            frame_long = min(orig, 2000)
        s = max(w, h) / frame_long
        f = QFont(self.font())
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setRenderHint(QPainter.Antialiasing)
        for person in self.entry.get("persons", []):
            if person.get("verdict") == "whole_only" or "box" not in person:
                continue
            col = QColor(VERDICT_COLOUR.get(person.get("verdict"), "#ff9f1a"))
            bx0, by0, bx1, by1 = person["box"]
            rect = QRectF(x0 + bx0 * s, y0 + by0 * s, (bx1 - bx0) * s, (by1 - by0) * s)
            p.setPen(QPen(col, 3))
            p.setBrush(Qt.NoBrush)
            p.drawRect(rect)
            haiku = (person.get("haiku") or {}).get("numbers") or []
            best = [t for t, _ in sorted(person.get("ocr", []), key=lambda c: -c[1])][:1]
            label = ", ".join(haiku or best) or "-"
            tw = p.fontMetrics().horizontalAdvance(label) + 10
            th = p.fontMetrics().height() + 2
            tag = QRectF(rect.left(), max(y0, rect.top() - th), tw, th)
            p.fillRect(tag, col)
            p.setPen(QColor("#000"))
            p.drawText(tag, Qt.AlignCenter, label)


# --------------------------------------------------------------------------- window

class Review(QMainWindow):
    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.settings = QSettings("MarathonOCR", "Review")
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.cache: dict[Path, object] = {}  # path -> Future[QImage]
        self.folder: Path = root
        self.sug: dict = {}
        self.progress: dict = {}
        self.images: list[Path] = []
        self.idx = 0
        self.bibs: list[str] = []
        self.checked: set[str] = set()
        self.dirty = False

        self.setWindowTitle(f"MarathonOCR Review  -  {root.name}")
        self.resize(1500, 950)
        self._build()
        self.parts = find_parts(root)
        self._fill_parts()
        last = self.settings.value(f"part/{root}", "")
        i = next((n for n, p in enumerate(self.parts) if str(p) == last), 0)
        self.part_box.setCurrentIndex(i)
        self.load_part(i)

    # ---- layout
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(10, 8, 10, 8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Name:"))
        self.name = QLineEdit(self.settings.value("name", ""))
        self.name.setPlaceholderText("your name")
        self.name.setMaximumWidth(140)
        self.name.editingFinished.connect(lambda: self.settings.setValue("name", self.name.text().strip()))
        top.addWidget(self.name)
        top.addSpacing(12)
        top.addWidget(QLabel("Part:"))
        self.part_box = QComboBox()
        self.part_box.setMinimumWidth(280)
        self.part_box.activated.connect(self.on_part)
        top.addWidget(self.part_box)
        self.only_need = QCheckBox("Only photos that need me")
        self.only_need.setChecked(self.settings.value("only_need", "false") == "true")
        self.only_need.toggled.connect(self.on_filter)
        top.addWidget(self.only_need)
        self.order = QComboBox()
        self.order.addItems(["Photo order (1, 2, 3 ...)", "Unsure photos first"])
        self.order.setCurrentIndex(int(self.settings.value("order", 0)))
        self.order.setToolTip("Photo order keeps shots of the same runners next to each other.")
        self.order.activated.connect(self.on_filter)
        top.addWidget(self.order)
        self.share = QComboBox()
        self.share.addItems(["All photos", "Reviewer 1 (first half)", "Reviewer 2 (second half)"])
        self.share.activated.connect(self.on_filter)
        top.addWidget(self.share)
        refresh = QPushButton("New photos? (F5)")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        top.addStretch(1)
        self.counters = QLabel()
        self.counters.setStyleSheet("font-size:15px")
        top.addWidget(self.counters)
        outer.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        outer.addWidget(self.bar)

        split = QSplitter()
        outer.addWidget(split, 1)
        self.view = PhotoView()
        split.addWidget(self.view)

        panel = QWidget()
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(520)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 0, 0, 0)
        self.photo_name = QLabel()
        self.photo_name.setStyleSheet("font-family:Consolas,monospace; color:#666")
        self.photo_name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pl.addWidget(self.photo_name)
        self.status = QLabel()
        self.status.setWordWrap(True)
        pl.addWidget(self.status)

        head = QHBoxLayout()
        self.list_title = QLabel()
        self.list_title.setStyleSheet("font-weight:bold; font-size:15px")
        head.addWidget(self.list_title, 1)
        tick_all = QPushButton("Tick all (A)")
        tick_all.clicked.connect(self.tick_all)
        head.addWidget(tick_all)
        pl.addLayout(head)

        self.rows_box = QFrame()
        self.rows_box.setFrameShape(QFrame.StyledPanel)
        self.rows = QGridLayout(self.rows_box)
        self.rows.setColumnStretch(2, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.rows_box)
        scroll.setMinimumHeight(180)
        pl.addWidget(scroll, 2)

        add = QHBoxLayout()
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("missed number, Enter adds (several: 1057 2210)")
        self.add_input.returnPressed.connect(self.add_typed)
        add.addWidget(self.add_input, 1)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_typed)
        add.addWidget(add_btn)
        pl.addLayout(add)

        self.others_title = QLabel("<b>Other reads</b> (not in the list)")
        pl.addWidget(self.others_title)
        self.others_box = QWidget()
        self.others = QGridLayout(self.others_box)
        self.others.setContentsMargins(0, 0, 0, 0)
        self.others.setColumnStretch(1, 1)
        pl.addWidget(self.others_box, 1)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("◀  Back (Q)")
        self.back_btn.clicked.connect(self.back)
        save = QPushButton("Save (S)")
        save.clicked.connect(lambda: self.save(force=True))
        self.next_btn = QPushButton("Confirm && next  ▶  (E)")
        self.next_btn.setStyleSheet("QPushButton{background:#1f6feb;color:white;font-weight:bold;padding:9px}")
        self.next_btn.clicked.connect(self.confirm_next)
        nav.addWidget(self.back_btn, 1)
        nav.addWidget(save, 1)
        nav.addWidget(self.next_btn, 2)
        pl.addLayout(nav)

        jump = QHBoxLayout()
        jump.addWidget(QLabel("Photo"))
        self.goto = QSpinBox()
        self.goto.setMinimum(1)
        self.goto.setKeyboardTracking(False)
        self.goto.valueChanged.connect(lambda v: self.go(v - 1))
        jump.addWidget(self.goto)
        self.of_label = QLabel()
        jump.addWidget(self.of_label)
        unsure = QPushButton("Next unsure (N)")
        unsure.clicked.connect(self.next_unsure)
        jump.addWidget(unsure)
        pl.addLayout(jump)

        files = QHBoxLayout()
        exp = QPushButton("Save file to send back")
        exp.setToolTip("One .json with everything reviewed here; raceday.py merge reads it.")
        exp.clicked.connect(self.export_json)
        files.addWidget(exp)
        csv_btn = QPushButton("Export CSV")
        csv_btn.clicked.connect(self.export_csv)
        files.addWidget(csv_btn)
        pl.addLayout(files)
        hint = QLabel("Keys: E next · Q back · S save · A tick all · N next unsure · "
                      "type digits to add · Esc leaves the box · double-click photo = full size")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#777; font-size:11px")
        pl.addWidget(hint)
        split.addWidget(panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        for key, fn in (("F5", self.refresh), ("Ctrl+S", lambda: self.save(force=True))):
            QShortcut(QKeySequence(key), self, activated=fn)
        QApplication.instance().installEventFilter(self)

    # ---- keys: letters act only when you are not typing in a box
    def eventFilter(self, obj, ev):
        if ev.type() != ev.Type.KeyPress or not self.isActiveWindow():
            return False
        focus = QApplication.focusWidget()
        # Qt passes one key press to the window, the focused widget and then its parents:
        # act once, at the focused widget, and never on a held-down key.
        if obj is not (focus or self) or ev.isAutoRepeat():
            return False
        typing = isinstance(focus, (QLineEdit, QSpinBox)) or (focus and isinstance(focus.parent(), QSpinBox))
        key, text = ev.key(), ev.text().lower()
        if typing:
            if key == Qt.Key_Escape:
                self.view.setFocus()
                return True
            return False
        if isinstance(focus, QComboBox) and key in (Qt.Key_Up, Qt.Key_Down):
            return False
        acts = {"e": self.confirm_next, "q": self.back, "s": lambda: self.save(force=True),
                "a": self.tick_all, "n": self.next_unsure}
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.confirm_next()
            return True
        if text in acts and not ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            acts[text]()
            return True
        if text.isdigit():
            self.add_input.setFocus()
            self.add_input.insert(text)
            return True
        return False

    # ---- parts and filters
    def _part_label(self, d: Path) -> str:
        name = "(photos in this folder)" if d == self.root else str(d.relative_to(self.root))
        sug = load_suggestions(d)
        if not sug:
            return f"{name}  ·  not scanned yet"
        rev = read_json(d / REVIEW)
        left = sum(1 for k, v in sug.items() if v.get("needs_human") and k not in rev)
        return f"{name}  ·  {left} need you"

    def _fill_parts(self):
        self.part_box.clear()
        for d in self.parts:
            self.part_box.addItem(self._part_label(d))

    def on_part(self, i: int):
        self.save()
        self.load_part(i)

    def load_part(self, i: int):
        if not self.parts:
            self.images = []
            self.show_current()
            return
        self.folder = self.parts[i]
        self.settings.setValue(f"part/{self.root}", str(self.folder))
        self.sug = load_suggestions(self.folder)
        self.progress = read_json(self.folder / REVIEW)
        self.cache.clear()
        self.apply_filter(keep_name=None)

    def on_filter(self, *_):
        self.settings.setValue("only_need", "true" if self.only_need.isChecked() else "false")
        self.settings.setValue("order", self.order.currentIndex())
        self.save()
        cur = self.images[self.idx].name if self.images else None
        self.apply_filter(keep_name=cur)

    def apply_filter(self, keep_name: str | None):
        allp = images_in(self.folder)
        if self.sug and self.order.currentIndex() == 1:
            imgs = sorted(allp, key=lambda p: (priority(self.sug.get(p.name)), natural(p.name)))
        else:
            imgs = list(allp)
        if self.sug and self.only_need.isChecked():
            imgs = [p for p in imgs if self.sug.get(p.name, {}).get("needs_human")]
        if self.share.currentIndex():
            # Two people on one photographer: first half / second half in photo order,
            # so each keeps the shots of the same runners together.
            order = {p.name: n for n, p in enumerate(allp)}
            half = (len(allp) + 1) // 2
            first = self.share.currentIndex() == 1
            imgs = [p for p in imgs if (order[p.name] < half) == first]
        self.images = imgs
        names = [p.name for p in imgs]
        if keep_name in names:
            self.idx = names.index(keep_name)
        else:  # start at the first photo nobody has done yet
            self.idx = next((n for n, p in enumerate(imgs) if p.name not in self.progress), 0)
        self.show_current()

    def refresh(self):
        """Pick up photos added (or removed) since the app opened, and new scan results."""
        self.save()
        cur_part = self.folder
        cur = self.images[self.idx].name if self.images else None
        self.parts = find_parts(self.root)
        self._fill_parts()
        if cur_part in self.parts:
            i = self.parts.index(cur_part)
            self.part_box.setCurrentIndex(i)
            self.folder = cur_part
            self.sug = load_suggestions(cur_part)
            self.progress = read_json(cur_part / REVIEW)
            self.apply_filter(keep_name=cur)
        else:
            self.load_part(0)
        self.flash(f"{len(self.images)} photo(s) in this view")

    # ---- photo state
    def _model_reads(self, entry: dict) -> tuple[list[str], dict[str, float], set[str]]:
        model, conf, haiku = [], {}, set()
        for p in entry.get("persons", []):
            for t, c in p.get("ocr", []):
                if t not in model:
                    model.append(t)
                conf[t] = max(conf.get(t, 0.0), float(c))
            haiku.update((p.get("haiku") or {}).get("numbers") or [])
        return model, conf, haiku

    def _image(self, path: Path):
        if path not in self.cache:
            self.cache[path] = self.pool.submit(decode, path)
        return self.cache[path]

    def show_current(self):
        n = len(self.images)
        done = sum(1 for p in self.images if p.name in self.progress)
        need = sum(1 for p in self.images if self.sug.get(p.name, {}).get("needs_human")
                   and p.name not in self.progress)
        self.counters.setText(f"<b>{done:,}</b> / {n:,} reviewed &nbsp;&nbsp; "
                              f"<b style='color:#e8900c'>{need:,}</b> still need you")
        self.bar.setMaximum(max(n, 1))
        self.bar.setValue(done)
        self.goto.blockSignals(True)
        self.goto.setMaximum(max(n, 1))
        self.goto.setValue(self.idx + 1)
        self.goto.blockSignals(False)
        self.of_label.setText(f"of {n:,}")
        if not n:
            self.view.show_photo(None, QImage(), None)
            self.photo_name.setText("")
            self.status.setText("Nothing left that needs you here. Untick \"Only photos that need me\", "
                                "pick another part, or press F5 if new photos arrived."
                                if images_in(self.folder) else "No photos in this folder.")
            self.bibs, self.checked = [], set()
            self.render_rows()
            return
        path = self.images[self.idx]
        entry = self.sug.get(path.name) or {}
        saved = self.progress.get(path.name)
        model, self.conf, self.haiku = self._model_reads(entry)
        self.model_numbers = model
        self.bibs = list(saved["numbers"]) if saved else list(entry.get("numbers", []))
        self.checked = set((saved or {}).get("checked", [])) & set(self.bibs)
        self.dirty = False
        img = self._image(path).result()
        self.view.show_photo(path, img, entry)
        for nxt in self.images[self.idx + 1:self.idx + 4]:  # decode ahead while you look
            self._image(nxt)
        for old in [p for p in self.cache if p not in self.images[max(0, self.idx - 2):self.idx + 4]]:
            self.cache.pop(old, None)
        tag = "reviewed" if saved else "not reviewed"
        if saved and saved.get("by"):
            tag += f" by {saved['by']}"
        self.photo_name.setText(f"{path.name}   [{tag}]")
        flag = entry.get("needs_human", 0)
        if not self.sug:
            self.status.setText("<span style='color:#c33'>This part is not scanned yet "
                                "(run raceday.py scan). Type the numbers you see.</span>")
        elif flag and not saved:
            self.status.setText(f"<span style='color:#d08000'><b>{flag} runner(s)</b> the model was unsure "
                                "about: check the orange / red boxes.</span>")
        else:
            self.status.setText("")
        self.back_btn.setEnabled(self.idx > 0)
        self.render_rows()

    def source(self, num: str) -> str:
        parts = []
        if num in self.conf:
            parts.append(f"model {self.conf[num]:.0%}")
        if num in self.haiku:
            parts.append("Haiku")
        return " · ".join(parts) or "added by you"

    def render_rows(self):
        for grid in (self.rows, self.others):
            while grid.count():
                w = grid.takeAt(0).widget()
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        big = QFont(self.font())
        big.setPointSize(18)
        big.setBold(True)
        for r, num in enumerate(self.bibs):
            cb = QCheckBox()
            cb.setChecked(num in self.checked)
            cb.setFocusPolicy(Qt.NoFocus)
            cb.toggled.connect(lambda on, n=num: self.toggle(n, on))
            lab = QLabel(num)
            lab.setFont(big)
            src = QLabel(self.source(num))
            src.setStyleSheet("color:#777")
            rm = QPushButton("Remove")
            rm.setFocusPolicy(Qt.NoFocus)
            rm.clicked.connect(lambda _=False, n=num: self.set_bibs([b for b in self.bibs if b != n]))
            for c, w in enumerate((cb, lab, src, rm)):
                self.rows.addWidget(w, r, c)
        if not self.bibs:
            self.rows.addWidget(QLabel("None yet. Type the numbers you see."), 0, 0, 1, 4)
        self.rows.setRowStretch(len(self.bibs) + 1, 1)
        done = sum(1 for n in self.bibs if n in self.checked)
        self.list_title.setText(f"Bibs in this photo   ✓ {done}/{len(self.bibs)}")

        cand = list(dict.fromkeys(sorted(self.conf, key=lambda t: -self.conf[t]) + sorted(self.haiku)))
        others = [n for n in cand if n not in self.bibs and (self.conf.get(n, 0) >= 0.1 or n in self.haiku)][:12]
        self.others_title.setVisible(bool(others))
        for r, num in enumerate(others):
            lab = QLabel(f"<b>{num}</b>")
            src = QLabel(self.source(num))
            src.setStyleSheet("color:#777")
            ad = QPushButton("Add")
            ad.setFocusPolicy(Qt.NoFocus)
            ad.clicked.connect(lambda _=False, n=num: self.set_bibs(self.bibs + [n]))
            self.others.addWidget(lab, r, 0)
            self.others.addWidget(src, r, 1)
            self.others.addWidget(ad, r, 2)
        self.others.setRowStretch(len(others) + 1, 1)

    # ---- edits
    def toggle(self, num: str, on: bool):
        (self.checked.add if on else self.checked.discard)(num)
        self.dirty = True
        done = sum(1 for n in self.bibs if n in self.checked)
        self.list_title.setText(f"Bibs in this photo   ✓ {done}/{len(self.bibs)}")

    def tick_all(self):
        self.checked = set(self.bibs)
        self.dirty = True
        self.render_rows()

    def set_bibs(self, new: list[str]):
        self.bibs = clean(new)
        self.checked &= set(self.bibs)
        self.save(force=True)
        self.render_rows()

    def add_typed(self):
        t = self.add_input.text().strip()
        self.add_input.clear()
        if t:
            self.set_bibs(self.bibs + t.replace(",", " ").split())
        self.view.setFocus()

    def save(self, force: bool = False):
        if not self.images or not (force or self.dirty):
            return
        name = self.images[self.idx].name
        entry = {"numbers": clean(self.bibs), "model_numbers": self.model_numbers,
                 "checked": sorted(n for n in self.checked if n in self.bibs),
                 "by": self.name.text().strip(), "at": round(time.time())}
        try:
            self.progress = save_entry(self.folder, name, entry)
        except OSError as exc:
            QMessageBox.warning(self, "Not saved", f"Could not save {name}:\n{exc}")
            return
        self.dirty = False
        if force:
            self.flash(f"Saved {name}")

    def flash(self, msg: str):
        self.statusBar().showMessage(msg, 2500)

    # ---- navigation
    def go(self, i: int):
        if not self.images:
            return
        i = max(0, min(i, len(self.images) - 1))
        if i == self.idx and self.goto.value() == i + 1:
            return
        self.save()
        self.progress = read_json(self.folder / REVIEW)  # someone else may have saved meanwhile
        self.idx = i
        self.show_current()

    def confirm_next(self):
        if not self.images:
            return
        if self.add_input.text().strip():
            self.add_typed()
        self.save(force=True)
        if self.idx == len(self.images) - 1:
            self.flash("That was the last photo in this view.")
            self.show_current()
            return
        self.go(self.idx + 1)

    def back(self):
        self.go(self.idx - 1)

    def next_unsure(self):
        n = len(self.images)
        for k in list(range(self.idx + 1, n)) + list(range(0, self.idx + 1)):
            nm = self.images[k].name
            if nm not in self.progress and self.sug.get(nm, {}).get("needs_human"):
                self.go(k)
                return
        self.flash("No unsure photos left here.")

    # ---- files out
    def export_json(self):
        self.save()
        if len(self.parts) > 1:
            data = {"parts": {(d.relative_to(self.root).as_posix() if d != self.root else "."):
                              read_json(d / REVIEW) for d in self.parts}}
        else:
            data = read_json(self.folder / REVIEW)
        out = self.root.parent / f"review_{self.root.name.replace(' ', '_')}.json"
        try:
            out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            out = Path.home() / out.name
            out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        QMessageBox.information(self, "Saved", f"Send this file back:\n\n{out}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.parent)))

    def export_csv(self):
        self.save()
        out = self.folder / "bib_export.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["image_name", "bib_numbers"])
            for p in images_in(self.folder):
                e = self.progress.get(p.name)
                w.writerow([p.name, ", ".join(e["numbers"] if e else [])])
        self.flash(f"Saved {out}")

    def closeEvent(self, e):
        self.save()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(e)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MarathonOCR Review")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        root = Path(args[0]).expanduser().resolve()
    else:
        picked = QFileDialog.getExistingDirectory(None, "Folder of photos (a photographer or one part)")
        if not picked:
            return 0
        root = Path(picked).resolve()
    if not root.is_dir():
        QMessageBox.critical(None, "MarathonOCR Review", f"Not a folder:\n{root}")
        return 1
    w = Review(root)
    w.show()
    w.view.setFocus()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
