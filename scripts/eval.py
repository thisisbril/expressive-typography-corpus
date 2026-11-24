"""Benchmark evaluation for the Expressive Typography Corpus.

Three tasks, scored against exports/corpus.json:

  loc   Localization. The model sees the image and the word, and returns a
        bounding box for where the typographic operation acts. Scored by IoU
        against `target_union` (hit at IoU >= 0.5, or >= 0.3 when the target
        is an absent letter).
  cls   Primitive classification. The model picks one of the five primitives.
        Scored against `primary_primitive`.
  fail  Failure detection. The model says whether the design successfully
        expresses the word's meaning. Scored against `surprise_legibility_ratio`
        <= 2 (a failure). Reported as precision, recall and F1 on the failure
        class, because failures are rare.

The model never sees labels, scores, or the `source` field.

Usage (from the repo root):
    python scripts/eval.py --model random
    python scripts/eval.py --model trivial
    python scripts/eval.py --model anthropic --model-name <model id>

The anthropic model needs `pip install anthropic` and ANTHROPIC_API_KEY set.
To test another model, add a class with localize / classify / judge methods
(see RandomModel) and register it in MODELS.

Per-entry predictions are saved to results/<model>.json.
"""
import argparse
import base64
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIMITIVES = ["Substitution", "Mutation", "Suppression", "Extension", "Inflection"]
FAILURE_MAX_SCORE = 2
IOU_THRESHOLD = 0.5
IOU_THRESHOLD_ABSENT = 0.3

PRIMITIVE_DEFINITIONS = """\
Substitution: acts on identity. The letterform is replaced by, or revealed to contain, something else.
Mutation: acts on structure. The letterform's geometry is deformed.
Suppression: acts on presence. The letterform, or part of it, is absent.
Extension: acts on boundary. The letterform's geometry is extended beyond where it normally ends.
Inflection: acts on state. Position, orientation, scale, fill, opacity, colour, or attached effects such as motion trails change, while the geometry stays the same."""

LOC_PROMPT = """This image is expressive typography for the word "{word}". One or more letterforms have been altered, removed or replaced so that they carry meaning.
Return the bounding box of the region where this operation acts, as normalized coordinates between 0 and 1 with the origin at the top-left of the image.
Reply with JSON only: {{"box": [x1, y1, x2, y2]}}"""

CLS_PROMPT = """This image is expressive typography for the word "{word}". One operation on the letterforms carries its meaning. The five possible operations are:

{definitions}

Which one is the main operation? Reply with JSON only: {{"primitive": "<one of: Substitution, Mutation, Suppression, Extension, Inflection>"}}"""

JUDGE_PROMPT = """This image is expressive typography for the word "{word}". Does the typography successfully express the meaning of the word while staying legible, or does its execution fail (for example by contradicting the word's meaning)?
Reply with JSON only: {{"success": true}} or {{"success": false}}"""


# ---------------------------------------------------------------- helpers

def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def valid_box(box):
    try:
        x1, y1, x2, y2 = [float(v) for v in box]
    except (TypeError, ValueError):
        return False
    return 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1


def wilson(k, n, z=1.96):
    """95% Wilson confidence interval for k successes out of n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def parse_json(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def normalize_primitive(value):
    if not isinstance(value, str):
        return None
    for p in PRIMITIVES:
        if value.strip().lower() == p.lower():
            return p
    return None


# ----------------------------------------------------------------- models
# Each model gets only the word and the image path. Never labels.

class RandomModel:
    """Chance baseline: random box, random primitive, random verdict."""
    name = "random"
    needs_images = False

    def __init__(self, seed=0, **_):
        self.rng = random.Random(seed)

    def localize(self, word, image_path):
        w, h = self.rng.uniform(0.1, 0.6), self.rng.uniform(0.1, 0.6)
        x1, y1 = self.rng.uniform(0, 1 - w), self.rng.uniform(0, 1 - h)
        return [x1, y1, x1 + w, y1 + h]

    def classify(self, word, image_path):
        return self.rng.choice(PRIMITIVES)

    def judge(self, word, image_path):
        return self.rng.random() < 0.5


class TrivialModel:
    """Floor baseline: whole-image box, most common primitive, always 'success'."""
    name = "trivial"
    needs_images = False

    def __init__(self, priors=None, **_):
        self.majority = (priors or Counter({"Substitution": 1})).most_common(1)[0][0]

    def localize(self, word, image_path):
        return [0.0, 0.0, 1.0, 1.0]

    def classify(self, word, image_path):
        return self.majority

    def judge(self, word, image_path):
        return True


class AnthropicModel:
    """Vision model through the Anthropic API."""
    name = "anthropic"
    needs_images = True

    def __init__(self, model_name=None, **_):
        if not model_name:
            sys.exit("--model-name is required for --model anthropic")
        try:
            import anthropic
        except ImportError:
            sys.exit("Run: pip install anthropic")
        self.client = anthropic.Anthropic()
        self.model_name = model_name
        self.name = f"anthropic-{model_name}"
        self.errors = 0

    def _ask(self, prompt, image_path):
        suffix = Path(image_path).suffix.lower()
        media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "gif": "image/gif"}.get(suffix.lstrip("."))
        data = base64.standard_b64encode(Path(image_path).read_bytes()).decode()
        try:
            reply = self.client.messages.create(
                model=self.model_name,
                max_tokens=200,
                temperature=0,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}},
                    {"type": "text", "text": prompt},
                ]}],
            )
            return parse_json(reply.content[0].text)
        except Exception as exc:  # network, rate limit, refusal: count and move on
            self.errors += 1
            print(f"  API error: {exc}")
            return None

    def localize(self, word, image_path):
        out = self._ask(LOC_PROMPT.format(word=word), image_path)
        return out.get("box") if out else None

    def classify(self, word, image_path):
        out = self._ask(CLS_PROMPT.format(word=word, definitions=PRIMITIVE_DEFINITIONS), image_path)
        return out.get("primitive") if out else None

    def judge(self, word, image_path):
        out = self._ask(JUDGE_PROMPT.format(word=word), image_path)
        value = out.get("success") if out else None
        return value if isinstance(value, bool) else None


MODELS = {"random": RandomModel, "trivial": TrivialModel, "anthropic": AnthropicModel}


# ------------------------------------------------------------- evaluation

def run(model, entries, tasks):
    rows = []
    for e in entries:
        row = {
            "entry_id": e["entry_id"],
            "word": e["word"],
            "primary_primitive": e["primary_primitive"],
            "absent": bool(e.get("target_absent")),
            "failure": e["surprise_legibility_ratio"] <= FAILURE_MAX_SCORE,
        }
        image = ROOT / e["image"] if e.get("image") else None
        if model.needs_images and not (image and image.exists()):
            print(f"  skipping {e['entry_id']}: image not found")
            continue
        print(f"  {e['entry_id']} {e['word']}")

        if "loc" in tasks and e.get("target_union"):
            pred = model.localize(e["word"], image)
            ok = valid_box(pred)
            threshold = IOU_THRESHOLD_ABSENT if row["absent"] else IOU_THRESHOLD
            score = iou([float(v) for v in pred], e["target_union"]) if ok else 0.0
            row.update(loc_pred=pred, loc_valid=ok, iou=score, loc_hit=score >= threshold)

        if "cls" in tasks:
            pred = normalize_primitive(model.classify(e["word"], image))
            row.update(cls_pred=pred, cls_correct=pred == e["primary_primitive"])

        if "fail" in tasks:
            verdict = model.judge(e["word"], image)
            row.update(judge_success=verdict,
                       pred_failure=(not verdict) if isinstance(verdict, bool) else None)
        rows.append(row)
    return rows


def report(model_name, rows, tasks):
    print(f"\n=== {model_name}  ({len(rows)} entries) ===")

    if "loc" in tasks:
        loc = [r for r in rows if "iou" in r]
        hits = sum(r["loc_hit"] for r in loc)
        lo, hi = wilson(hits, len(loc))
        mean_iou = sum(r["iou"] for r in loc) / len(loc) if loc else 0
        invalid = sum(not r["loc_valid"] for r in loc)
        print(f"Localization      mean IoU {mean_iou:.2f}   hits {hits}/{len(loc)} ({pct(hits / len(loc) if loc else None)}, 95% CI {pct(lo)}-{pct(hi)})   invalid boxes: {invalid}")
        print(f"                  (hit = IoU >= {IOU_THRESHOLD}, or >= {IOU_THRESHOLD_ABSENT} for absent letters)")

    if "cls" in tasks:
        correct = sum(r["cls_correct"] for r in rows)
        lo, hi = wilson(correct, len(rows))
        invalid = sum(r["cls_pred"] is None for r in rows)
        print(f"Classification    {correct}/{len(rows)} ({pct(correct / len(rows) if rows else None)}, 95% CI {pct(lo)}-{pct(hi)})   unparseable: {invalid}")

    if "fail" in tasks:
        judged = [r for r in rows if r["pred_failure"] is not None]
        tp = sum(r["failure"] and r["pred_failure"] for r in judged)
        fp = sum((not r["failure"]) and r["pred_failure"] for r in judged)
        fn = sum(r["failure"] and not r["pred_failure"] for r in judged)
        tn = sum((not r["failure"]) and not r["pred_failure"] for r in judged)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        specificity = tn / (tn + fp) if tn + fp else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
        parts = [x for x in (recall, specificity) if x is not None]
        balanced = sum(parts) / len(parts) if parts else None
        print(f"Failure detection precision {pct(precision)}   recall {pct(recall)}   F1 {pct(f1)}   balanced acc {pct(balanced)}   "
              f"(failures in set: {tp + fn}, unparseable: {len(rows) - len(judged)})")

    print("\nBy primary primitive:")
    groups = defaultdict(list)
    for r in rows:
        groups[r["primary_primitive"]].append(r)
    print(f"  {'primitive':<14}{'n':>3}{'mean IoU':>10}{'cls acc':>9}")
    for p in PRIMITIVES:
        g = groups.get(p, [])
        if not g:
            continue
        ious = [r["iou"] for r in g if "iou" in r]
        mean_iou = f"{sum(ious) / len(ious):.2f}" if ious else "n/a"
        cls = f"{pct(sum(r['cls_correct'] for r in g) / len(g))}" if "cls" in tasks else "n/a"
        print(f"  {p:<14}{len(g):>3}{mean_iou:>10}{cls:>9}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=MODELS, default="random")
    ap.add_argument("--model-name", help="model id, for --model anthropic")
    ap.add_argument("--tasks", default="loc,cls,fail", help="comma list from: loc, cls, fail")
    ap.add_argument("--corpus", default=str(ROOT / "exports" / "corpus.json"))
    ap.add_argument("--limit", type=int, help="only the first N entries (for a cheap test run)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    tasks = {t.strip() for t in args.tasks.split(",")}
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    entries = corpus[: args.limit] if args.limit else corpus

    priors = Counter(e["primary_primitive"] for e in corpus)
    model = MODELS[args.model](seed=args.seed, model_name=args.model_name, priors=priors)

    print(f"Running {model.name} on {len(entries)} entries, tasks: {', '.join(sorted(tasks))}")
    rows = run(model, entries, tasks)
    report(model.name, rows, tasks)

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{model.name}.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nPer-entry predictions saved to {out}")


if __name__ == "__main__":
    main()