# Qualitative Review: Block vs Semantic Walk vs Proposition Walk

## Summary

The new `proposition_walk` pipeline ran successfully and produced comparable chunks, but it does not yet beat raw `semantic_walk` overall. It is faster and more granular than `block`, but slower and more expensive than `semantic_walk` because proposition generation adds Step 5 LLM calls.

## Closest Pair

- `block` produced 19 repaired chunks, but several chunks are broad slide-section blobs and it still leaves 3 singleton chunks. It also had the worst latency: 214.03s Step 5 plus 121.52s Step 6.
- `semantic_walk` produced 25 repaired chunks with no singletons. Its chunks read cleanly overall: setup, assumptions, recursive setup, merge logic, claims, proofs, and recurrence mostly stay inspectable.
- `proposition_walk` produced 26 repaired chunks with 1 singleton. It improved a few over-broad areas by splitting the divide-and-conquer setup and the Z-box proof into smaller units. However, it also split one proof transition into a singleton and separated some support from its local setup.

Verdict: `semantic_walk` is still the best closest-pair result. `proposition_walk` has useful signals but is too eager to split in proof transitions.

## Inheritance

- `block` produced 22 repaired chunks. It has fewer final chunks, but still over-merges some slide transitions and leaves one singleton.
- `semantic_walk` produced 25 repaired chunks with no singletons. It keeps the deck in readable topic-level units, though it still has heading/support risks around figures.
- `proposition_walk` also produced 25 repaired chunks with no singletons. It mostly matches `semantic_walk`, but it changes two spots: it merges Mendel/heredity labels with “Penetrance” and “Dominant vs. recessive,” then splits “Expression / Phenotype and Genotype”; later it merges the DNA title with storage and a DNA backbone figure, then separates ribosome/cell figures. The DNA split is a mixed result and was affected by a proposition-generation fallback on that block.

Verdict: `semantic_walk` and `proposition_walk` are close on inheritance, but `semantic_walk` is cleaner and cheaper.

## Metrics

- Closest Pair: `semantic_walk` used 9 calls and 94.52s total; `proposition_walk` used 23 calls and 151.31s total; `block` used 25 calls and 335.55s total.
- Inheritance: `semantic_walk` used 16 calls and 67.46s total; `proposition_walk` used 38 calls and 124.02s total; `block` used 36 calls and 205.01s total.
- `proposition_walk` cache misses were 98 for closest-pair and 68 for inheritance. Hits were 0 because this was a fresh one-pass run.

## Recommendation

Keep `proposition_walk` as an experimental parallel strategy, not the default. The next improvement should not be more LLM calls; it should constrain proposition-based splits with a local minimum chunk size or a proof/list continuation guard so proposition distance does not strand bridge sentences.
