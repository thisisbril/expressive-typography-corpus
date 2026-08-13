# Annotation Schema v1.1

## Identity Fields

- **Entry ID** — unique identifier (e.g. ET-001)
- **Word/Phrase** — the actual text being rendered
- **Designer/Studio** — attribution where known
- **Year** — date of creation where known
- **Source** — where the example was found or obtained

## Classification Fields

- **Primary Primitive** — the dominant operation from the six primitives
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
- **Generative Principle** — optional; only when annotation 

## Compound Rules

- Maximum two secondary primitives per entry
- Tiebreaker: when two primitives feel equally load-bearing,the primitive operating on the most semantically loaded letterform is designated primary
- Primitive Relationship must specify for each secondary primitive whether it enables, amplifies, or contrasts the primary