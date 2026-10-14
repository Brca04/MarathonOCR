"""Offline tests: the whole pipeline against a fake Sonnet (no API key, no cost).

    python sonnet/test_sonnet_bibs.py [photo_folder_with_raceday_reads]

The fake answers like a model would: the survey reports boxes (taken from the old
pipeline's detections if a folder is given), the zoom reads some bibs differently,
the judge settles them. It checks the plumbing, not the accuracy.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import types
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sonnet_bibs as sb  # noqa: E402


# --------------------------------------------------------------------------- unit checks

def test_units():
    assert sb.fit_size(2000, 1333, 1.0) == (2000, 1333)
    W, H = sb.fit_size(4000, 3000, 1.0)
    assert sb.img_tokens(W, H) <= sb.MAX_IMG_TOKENS and max(W, H) <= sb.MAX_EDGE
    W, H = sb.fit_size(1160, 773, 2.5)
    assert sb.img_tokens(W, H) <= sb.MAX_IMG_TOKENS and W > 2000
    assert sb.clean_number("No. 0042") == "42" and sb.clean_number("2?15") == "2?15"
    assert sb.pattern_match("23?5", "2315") and not sb.pattern_match("23?5", "235")
    r = sb.Read("zoom", "2315", "clear", "none")
    assert r.full == "2315" and r.clear
    assert sb.Read("zoom", "2315", "partial", "left").full is None
    assert sb.Read("zoom", "23?5", "partial", "none").full is None
    assert sb.same_bib([0, 0, 100, 50], [5, 3, 104, 55]) and not sb.same_bib([0, 0, 100, 50], [300, 0, 400, 50])
    c = sb.Cand([0, 0, 100, 50], [sb.Read("survey", "2315", "clear", "none")])
    assert sb.decide(c, sb.Read("zoom", "2315", "clear", "none"), None)["status"] == "accept"
    assert sb.decide(c, sb.Read("zoom", "2316", "clear", "none"), None)["status"] == "judge"
    assert sb.decide(c, sb.Read("zoom", "2316", "clear", "none"), sb.Read("judge", "2316", "clear", "none"))["number"] == "2316"
    assert sb.decide(c, sb.Read("zoom", "", "unreadable", "unknown", is_bib=False), None)["status"] == "drop"
    c2 = sb.Cand([0, 0, 100, 50], [sb.Read("survey", "23?5", "partial", "none")])
    d = sb.decide(c2, sb.Read("zoom", "23?5", "partial", "none"), None)
    assert d["status"] == "review" and d["pattern"] == "23?5"
    # bursts: 23?5 next to frames that clearly show 2315 -> accepted; far away -> not
    st = sb.Settings(burst_window=2)
    order = ["a1", "a2", "a3", "a4", "a5", "a6"]
    acc = lambda n: dict(status="accept", number=n)  # noqa: E731
    entries = {n: dict(bibs=[]) for n in order}
    entries["a2"]["bibs"] = [acc("2315")]
    entries["a3"]["bibs"] = [dict(status="review", candidates=[], pattern="23?5")]
    entries["a6"]["bibs"] = [dict(status="review", candidates=[], pattern="23?5")]
    entries["a4"]["bibs"] = [dict(status="judge", candidates=["881", "861"])]
    entries["a5"]["bibs"] = [acc("861")]
    sb.resolve_folder(entries, order, st)
    assert entries["a3"]["numbers"] == ["2315"], entries["a3"]
    assert entries["a6"]["numbers"] == [] and entries["a6"]["needs_human"] == 1
    assert entries["a4"]["numbers"] == ["861"]
    # start list: an accepted number that does not exist goes to a person
    st = sb.Settings(start={"2315", "861"})
    e = {"x": dict(bibs=[acc("2316")])}
    sb.resolve_folder(e, ["x"], st)
    assert e["x"]["needs_human"] == 1 and "2315" in e["x"]["bibs"][0]["candidates"]
    assert sb.parse_json('blah ```json\n{"a": 1}\n``` blah') == {"a": 1}
    print("units ok")


# --------------------------------------------------------------------------- fake Sonnet

class FakeUsage:
    def __init__(self, i, o):
        self.input_tokens, self.output_tokens = i, o
        self.cache_creation_input_tokens = self.cache_read_input_tokens = 0


class FakeMsg:
    def __init__(self, data, i=4000, o=300):
        self.content = [types.SimpleNamespace(type="thinking", thinking="..."),
                        types.SimpleNamespace(type="text", text=json.dumps(data))]
        self.usage = FakeUsage(i, o)


class FakeModel:
    """Knows each test photo's 'true' bibs (box -> number)."""

    def __init__(self, truth: dict[str, list[tuple[list[float], str]]]):
        self.truth, self.calls = truth, []
        self.lock = threading.Lock()

    def answer(self, p: dict) -> FakeMsg:
        assert p["model"] and p["max_tokens"] and p["messages"]
        assert "budget_tokens" not in json.dumps(p.get("thinking", {})), "budget_tokens is rejected by Sonnet 5.5"
        content = p["messages"][0]["content"]
        text = content[-1]["text"]
        imgs = [c for c in content if c["type"] == "image"]
        photo = p.pop("_photo")
        with self.lock:
            self.calls.append((text[:20], photo))
        bibs = self.truth[photo]
        if text.startswith("This is a full race photo"):
            # Survey: misses the last bib, misreads the second one.
            out = []
            for i, (box, n) in enumerate(bibs[:-1] if len(bibs) > 1 else bibs):
                out.append(dict(box=[round(v) for v in box], number=(n[:-1] + "9") if i == 1 else n,
                                legibility="clear", cut="none"))
            return FakeMsg({"bibs": out})
        if text.startswith("This is an enlarged part"):
            # Tile 0: finds the missed bib (coordinates in the enlarged tile).
            rect, scale = p.pop("_rect"), p.pop("_scale")
            out = []
            box, n = bibs[-1]
            if rect[0] <= box[0] and box[2] <= rect[2] and rect[1] <= box[1] and box[3] <= rect[3]:
                b = [(box[0] - rect[0]) * scale, (box[1] - rect[1]) * scale,
                     (box[2] - rect[0]) * scale, (box[3] - rect[1]) * scale]
                out.append(dict(box=[round(v) for v in b], number=n, legibility="clear", cut="none"))
            return FakeMsg({"bibs": out}, 4700, 200)
        if text.startswith("Below are"):
            boxes = p.pop("_boxes")
            out = []
            for i, b in enumerate(boxes, 1):
                n = min(bibs, key=lambda t: abs(t[0][0] - b[0]) + abs(t[0][1] - b[1]))[1]
                out.append(dict(id=i, is_bib=True, number=n, legibility="clear" if i % 3 else "partial",
                                cut="none", alternatives=[]))
            assert len(imgs) == 2 * len(boxes)
            return FakeMsg({"bibs": out}, 3000, 250)
        if text.startswith("Two independent"):
            b = p.pop("_box")
            n = min(bibs, key=lambda t: abs(t[0][0] - b[0]) + abs(t[0][1] - b[1]))[1]
            assert len(imgs) == 3
            return FakeMsg(dict(is_bib=True, number=n, legibility="clear", cut="none", reason="digits plain"), 3500, 900)
        raise AssertionError(text[:60])


def install_fake(fake: FakeModel, batch_mode: bool):
    """Swap the API client for the fake and tag each request with its photo."""
    orig_run = sb.Runner.run

    def run(self, step, jobs, on_result):
        for j in jobs:
            b = j.build

            def tagged(b=b, j=j, step=step):
                p = b()
                p["_photo"] = j.meta["photo"].name
                if step == "tiles":
                    p["_rect"], p["_scale"] = j.meta["rect"], j.meta["scale"]
                if step == "zoom":
                    p["_boxes"] = [[float(v) for v in k.split(",")] for k in j.meta["cands"]]
                if step == "judge":
                    p["_box"] = [float(v) for v in j.meta["cand"].split(",")]
                return p
            j.build = tagged
        return orig_run(self, step, jobs, on_result)

    batches_store = {}

    class Batches:
        def create(self, requests):
            bid = f"msgbatch_{len(batches_store)}"
            batches_store[bid] = [(r["custom_id"], fake.answer(r["params"])) for r in requests]
            return types.SimpleNamespace(id=bid)

        def retrieve(self, bid):
            return types.SimpleNamespace(processing_status="ended")

        def results(self, bid):
            for cid, msg in batches_store[bid]:
                yield types.SimpleNamespace(custom_id=cid, result=types.SimpleNamespace(type="succeeded", message=msg))

    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **p: fake.answer(p), batches=Batches()))
    sb.Runner.run = run
    sb.Runner.client = property(lambda self: client)
    return lambda: setattr(sb.Runner, "run", orig_run)


def make_root(src: Path | None, tmp: Path, n: int = 6) -> tuple[Path, dict]:
    root = tmp / "event"
    folder = root / "Test Photographer"
    folder.mkdir(parents=True)
    truth, review = {}, {}
    if src and (src / ".raceday_reads.jsonl").exists():
        reads = {}
        for line in (src / ".raceday_reads.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if len(r.get("hits", [])) >= 2:
                reads[r["file"]] = r
        names = [nm for nm in sorted(reads, key=sb.natural) if (src / nm).exists()][:n]
        for i, nm in enumerate(names, 1):
            dst = f"Test_{i}.jpg"
            shutil.copy(src / nm, folder / dst)
            boxes = []
            for h in reads[nm]["hits"]:  # the old detector sometimes boxes one bib twice
                if not any(sb.same_bib(h["bbox"], b) for b in boxes):
                    boxes.append(h["bbox"])
            truth[dst] = [(b, str(1000 + 7 * i + k)) for k, b in enumerate(boxes[:5])]
    else:
        for i in range(1, n + 1):
            Image.new("RGB", (2000, 1333), (90 + i * 10, 120, 140)).save(folder / f"Test_{i}.jpg")
            truth[f"Test_{i}.jpg"] = [([100 + 300 * k, 600, 220 + 300 * k, 680], str(2000 + 10 * i + k))
                                      for k in range(3)] + [([1700, 200, 1760, 240], str(3000 + i))]
    for nm, bibs in truth.items():
        review[nm] = {"numbers": [n for _, n in bibs], "by": "test", "at": 1}
    sb.write_json(folder / sb.REVIEW, review)
    return root, truth


def args_for(root: Path, **kw):
    ns = types.SimpleNamespace(root=str(root), folder=None, reviewed=False, limit=None, start_list=None,
                               model=sb.MODEL, judge_model=None, tiles="always", think="medium",
                               judge_think="high", no_schema=False, burst_window=6, batch=False, workers=4,
                               max_usd=None, undo=False, bibs_per_photo=3.0, tile_share=0.55, judge_share=0.15)
    ns.__dict__.update(kw)
    return ns


def test_pipeline(src: Path | None, batch: bool):
    tmp = Path(tempfile.mkdtemp())
    try:
        root, truth = make_root(src, tmp)
        fake = FakeModel(truth)
        undo = install_fake(fake, batch)
        try:
            assert sb.cmd_run(args_for(root, batch=batch, reviewed=True, limit=4)) == 0
            n1 = len(fake.calls)
            # re-run: nothing new for the same photos
            assert sb.cmd_run(args_for(root, batch=batch, reviewed=True, limit=4)) == 0
            assert len(fake.calls) == n1, "re-run sent requests again"
            assert sb.cmd_run(args_for(root, batch=batch)) == 0  # the rest
        finally:
            undo()
        folder = root / "Test Photographer"
        res = sb.read_json(folder / sb.STATE / "results.json")
        assert len(res) == len(truth)
        for nm, bibs in truth.items():
            want = {n for _, n in bibs}
            got = set(res[nm]["numbers"])
            assert got == want, (nm, got, want, res[nm]["bibs"])
        steps = sorted({c[0][:8] for c in fake.calls})
        print(f"  {'batch' if batch else 'live '}: {len(fake.calls)} calls {steps} -> every photo exactly right")
        sb.cmd_eval(args_for(root))
        sb.cmd_review(args_for(root))
        sug = sb.read_json(folder / sb.SUGGESTIONS)
        assert set(sug) == set(truth) and all("persons" in v for v in sug.values())
        sb.cmd_review(args_for(root, undo=True))
        sb.cmd_export(args_for(root))
        rows = (root / "_publish_sonnet" / "bib_export.csv").read_text(encoding="utf-8").splitlines()
        assert rows[0] == "image_name,bib_numbers" and len(rows) == len(truth) + 1
        sb.cmd_status(args_for(root))
        sb.cmd_estimate(args_for(root))
        if batch:
            reg = sb.read_json(root / sb.STATE / "batches.json")
            assert reg and all(b["done"] for v in reg.values() for b in v)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_units()
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    test_pipeline(src, batch=False)
    test_pipeline(src, batch=True)
    print("all tests passed")
