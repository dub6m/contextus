# Qualitative Review: Block + Step 6 vs Level 4 + Step 6

## What Changed

The earlier saved comparison was not clean enough: the Level 4 outputs had Step 6 artifacts, but block was being judged from a previous saved run. This folder contains a fresh apples-to-apples run where both strategies went through Step 5 and Step 6 in the same script.

The comparison script also had a file naming bug: `Path.with_suffix()` treated `.block` and `.semantic_walk` as extensions, so later strategy files overwrote earlier strategy files. That has been fixed. The artifacts here now include separate `*.block.step5.*`, `*.block.step6.*`, `*.semantic_walk.step5.*`, and `*.semantic_walk.step6.*` files.

## Closest Pair

Block + Step 6 produced 15 chunks. Level 4 + Step 6 produced 25 chunks.

Block's final chunks are often broad. For example, the opening is a 10-element chunk spanning the setup and assumptions, and the divide-and-conquer explanation becomes an 11-element chunk. These are not nonsense, but they feel more like slide-section blobs than retrieval-ready chunks.

Level 4 + Step 6 is more granular. It keeps the problem setup, assumptions, recursive setup, merge step, claims, proofs, and recurrence in smaller units. It also removes the obvious singleton headings after Step 6. For this document, Level 4 + Step 6 reads better as chunks.

## Inheritance

Block + Step 6 produced 22 chunks. Level 4 + Step 6 produced 25 chunks.

Block sometimes over-merges slide transitions. The opening chunk combines the title, biocultural model, environmental conditions, a figure, culture adaptation, and the Mendel image. That is readable as a deck opening, but it is too wide if the user asks about only one of those concepts.

Level 4 + Step 6 separates those topic turns better: title/biocultural model, culture adaptation, Mendel, heredity terms, Punnett square sections, mitosis/meiosis, DNA, variability, mutation, and evolution mostly land as distinct units. It still has some support/heading risks around slide figures, but the units are more inspectable.

## Verdict

Level 4 should stay as a parallel Step 5 candidate. Raw Level 4 still needs Step 6, but Level 4 + Step 6 is not a toy fallback; it is producing coherent chunks with much lower Step 5 cost. On these two documents, it is at least competitive with block and arguably better for retrieval granularity.
