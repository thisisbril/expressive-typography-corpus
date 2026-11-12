import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = ROOT / "entries"
IMAGES = ROOT / "images"
OUTPUT = ROOT / "exports" / "corpus.json"

# Edit this list if your final primitive set differs
PRIMITIVES = {"Substitution", "Mutation", "Suppression", "Extension", "Inflection"}

SECTION_KEYS = {
    "Operation Description": "operation_description",
    "Concept Encoded": "concept_encoded",
    "Semantic Mechanism": "semantic_mechanism",
    "Curatorial Note": "curatorial_note",
    "Generative Principle": "generative_principle",
}


def parse_entry(path):
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").strip()
    text = re.sub(r"^```[a-z]*\n", "", text)
    text = re.sub(r"\n```$", "", text)

    # Layout A: YAML between two '---' lines, optional prose below.
    # Layout B: everything is YAML, with no closing '---'.
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n(.*))?$", text, re.DOTALL)
    if match:
        yaml_text, body = match.group(1), match.group(2) or ""
    else:
        yaml_text, body = re.sub(r"^---\s*\n", "", text, count=1), ""

    meta = yaml.safe_load(yaml_text) or {}

    # Pick up any "## Heading" prose sections without overwriting YAML fields
    parts = re.split(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        key = SECTION_KEYS.get(parts[i].strip())
        if key and key not in meta:
            meta[key] = parts[i + 1].strip()

    # Clean up the prose fields and turn "N/A" into null
    for key in SECTION_KEYS.values():
        value = meta.get(key)
        if isinstance(value, str):
            value = value.strip()
            meta[key] = None if value.upper() == "N/A" else value

    entry_id = meta.get("entry_id", "")
    matches = sorted(IMAGES.glob(f"{entry_id}-*"))
    meta["image"] = f"images/{matches[0].name}" if matches else None
    return meta


def validate(entry, filename):
    problems = []
    if entry.get("primary_primitive") not in PRIMITIVES:
        problems.append(f"unknown primary primitive: {entry.get('primary_primitive')}")
    for p in entry.get("secondary_primitives") or []:
        if p not in PRIMITIVES:
            problems.append(f"unknown secondary primitive: {p}")
    score = entry.get("surprise_legibility_ratio")
    if score not in (1, 2, 3, 4, 5):
        problems.append(f"score out of range: {score}")
    if len(entry.get("secondary_primitives") or []) > 2:
        problems.append("more than two secondary primitives")
    return [f"{filename}: {p}" for p in problems]


def main():
    entries, problems = [], []
    for path in sorted(ENTRIES.glob("ET-*.md")):
        entry = parse_entry(path)
        problems += validate(entry, path.name)
        entries.append(entry)

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(entries)} entries to {OUTPUT}")

    if problems:
        print("\nCheck these:")
        for p in problems:
            print(" -", p)


if __name__ == "__main__":
    main()