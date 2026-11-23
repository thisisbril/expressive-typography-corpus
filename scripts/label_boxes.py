"""Click-and-drag labeling tool for bounding boxes.

Run from the repo root:
    pip install opencv-python numpy pyyaml
    python scripts/label_boxes.py              # label every entry not yet boxed
    python scripts/label_boxes.py --redo ET-004  # redo one entry

Writes boxes.json (repo root), keyed by entry_id. Saves after every entry,
so you can quit any time and resume later. See SCHEMA.md, "Bounding Box Rules".

In the image window:
    drag with the mouse, then press ENTER or SPACE to confirm
    press C to cancel the box (skips the entry for now)
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_corpus import parse_entry  # reuse the same entry parser

BOXES_PATH = ROOT / "boxes.json"
MAX_W, MAX_H = 1200, 800  # display size cap


def load_image(path):
    # imdecode + fromfile handles Windows paths with spaces or non-ASCII characters
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def draw_box(img, title):
    """Show the image scaled to fit, let the user drag a box.
    Returns normalized [x1, y1, x2, y2] or None if cancelled."""
    h, w = img.shape[:2]
    scale = min(MAX_W / w, MAX_H / h, 1.0)
    shown = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img
    x, y, bw, bh = cv2.selectROI(title, shown, showCrosshair=False, fromCenter=False)
    cv2.destroyAllWindows()
    if bw == 0 or bh == 0:
        return None
    sw, sh = shown.shape[1], shown.shape[0]
    return [round(x / sw, 4), round(y / sh, 4), round((x + bw) / sw, 4), round((y + bh) / sh, 4)]


def ask_yes_no(prompt):
    return input(prompt + " [y/N] ").strip().lower() == "y"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", help="entry id to relabel, e.g. ET-004")
    args = ap.parse_args()

    boxes = json.loads(BOXES_PATH.read_text(encoding="utf-8")) if BOXES_PATH.exists() else {}

    for path in sorted((ROOT / "entries").glob("ET-*.md")):
        meta = parse_entry(path)
        eid = meta["entry_id"]
        if args.redo and eid != args.redo:
            continue
        if eid in boxes and not args.redo:
            continue

        images = sorted((ROOT / "images").glob(f"{eid}-*"))
        if not images:
            print(f"{eid}: no image found, skipping")
            continue
        img = load_image(images[0])
        glyphs = meta.get("target_glyphs") or []
        word = meta.get("word", "")
        primitive = meta.get("primary_primitive", "")

        print(f"\n{eid}  '{word}'  primary: {primitive}  targets: {glyphs}")
        print("Draw the UNION box, then ENTER. C cancels.")
        union = draw_box(img, f"{eid} {word} - union box")
        if union is None:
            print("  cancelled, skipped")
            continue

        entry = {"target_union": union}
        if primitive == "Suppression" or ask_yes_no("  Is the target an absent letter (box over the gap)?"):
            entry["target_absent"] = True

        if len(glyphs) > 1 and ask_yes_no("  Add per-glyph boxes?"):
            per = []
            for g in glyphs:
                print(f"  Draw the box for glyph '{g}', then ENTER.")
                b = draw_box(img, f"{eid} {word} - glyph {g}")
                if b is None:
                    print("  cancelled, per-glyph boxes dropped")
                    per = []
                    break
                per.append(b)
            if per:
                entry["target_boxes"] = per

        boxes[eid] = entry
        BOXES_PATH.write_text(json.dumps(boxes, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  saved {eid}  ({len(boxes)} boxed)")

    print(f"\nDone. {len(boxes)} entries in {BOXES_PATH.name}")


if __name__ == "__main__":
    main()