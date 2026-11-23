# Annotation Schema v1.1

## Identity Fields

- **Entry ID** — unique identifier (e.g. ET-001)
- **Word/Phrase** — the actual text being rendered
- **Designer/Studio** — attribution where known
- **Year** — date of creation where known
- **Source** — where the example was found or obtained

## Classification Fields

- **Primary Primitive** — the dominant operation from the five primitives
- **Secondary Primitive(s)** — up to two additional primitives present, if any
- **Primitive Relationship** — whether each secondary primitive enables, amplifies, or contrasts the primary
- **Target Glyph(s)** — which specific letterforms are being operated on
- **Operation Description** — precise plain-language account of what has been done to which letterform and why it works

## Semantic Fields

- **Concept Encoded** — the idea, object, or action the typography is performing
- **Semantic Mechanism** — how the typographic operation connects to the concept; why this letter, why this operation
- **Legibility Integrity** — one of three states:
  - *Full* — word remains completely readable without context
  - *Partial* — word requires a moment of decoding
  - *Contextual* — word requires surrounding context to decode

## Quality Fields

- **Surprise-Legibility Ratio** — rated 1 to 5:
  - **1** — Predictable and/or illegible; tension has collapsed
  - **2** — Visible but unsurprising; technique recognized without discovery
  - **3** — Surprising or legible, but not simultaneously
  - **4** — Strong tension with minor resolution cost
  - **5** — Maximum sustained tension; surprise and legibility amplify each other
- **Curatorial Note** — qualitative annotation in the curator's voice
- **Generative Principle** — optional; only when annotation reveals a transferable design rule. 

## Compound Rules

- Maximum two secondary primitives per entry
- Tiebreaker: when two primitives feel equally load-bearing,the primitive operating on the most semantically loaded letterform is designated primary
- Primitive relationship must specify for each secondary primitive whether it enables, amplifies, or contrasts the primary

## Bounding Box Rules

Boxes mark where the meaning lives in the image, so a model's localization can be scored against them.

### Format

- Coordinates are normalized to the image: `[x1, y1, x2, y2]`, each 0 to 1, origin at the top-left.
- Boxes are tight. No padding.
- Boxes are drawn on the design as pictured, not on the word as it would be typeset normally.

### Fields

| Field | Required | Meaning |
|---|---|---|
| `target_union` | yes | The smallest box enclosing everything the operation acts on |
| `target_boxes` | no | One box per target glyph, in the order of `target_glyphs`. Give these when the targets are separate instances (e.g. both E's in CHEERS) |
| `target_absent` | no | `true` when the target is a missing letter (Suppression) |

### Rules by primitive

- **Substitution.** When glyphs fuse into one object, draw a single union box around the whole fused form, not one box per letter. Example: the spatula in *grill*.
- **Mutation.** Include detached or displaced parts of the mutated glyph. Example: the crossbars of CHEERS that drop below the baseline.
- **Suppression.** Box the gap where the missing letter would sit, inferred from its neighbors, and set `target_absent: true`. Boxes for absent targets are approximate, so score them with a looser Intersection over Union (IoU) threshold.
- **Extension.** Include the extended geometry, up to where it ends. The operation acts on the boundary, so the boundary must be inside the box.
- **Inflection.** Box each glyph at its displaced position and orientation. Include attached effects, such as a motion trail, because the taxonomy defines them as part of the operation.

### Compound entries

Box the primary primitive's target. Give secondary targets in `target_boxes` only if they differ from the primary's.

### Scoring note

Evaluation uses IoU against `target_union`. Use 0.5 as the default threshold and 0.3 for entries with `target_absent: true`.