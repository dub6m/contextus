# Query-Time Evidence Package Thesis

Created: 2026-05-16

This artifact tracks the new prompt-conditioned evidence packaging line of work. It is intentionally written as a reasoning log, not as a polished design memo. The purpose is to preserve what we tried, what happened, what failed in concrete terms, and what those failures imply about the next implementation.

The working name for the current direction is:

```text
query-time evidence package assembly
```

The deeper idea is:

```text
prompt
-> find likely core evidence
-> expand around that evidence only when context helps
-> return a query-specific evidence package
```

This is different from the older chunking pipelines. The older pipelines try to build generally good chunks before the user asks anything. This new track assumes that "good chunk" may be question-dependent. A paragraph, figure, table, or sentence might be too small for one query, too broad for another query, and perfect for a third query. So the unit we ultimately want is not necessarily a permanent chunk. It is a package assembled for the prompt.

## Starting Thesis

The core thesis is:

```text
The document should not be permanently cut into the final answerable units.
Instead, source elements should remain available as evidence handles, and the
system should assemble a package around the most relevant handle at query time.
```

This is motivated by repeated failures from the existing chunking runs:

- Large prebuilt chunks often contain enough context but also contain unrelated material.
- Small atomic chunks are clean but often not answerable by themselves.
- Visual material frequently needs nearby caption, heading, or explanatory text.
- Reference-heavy text often looks retrievable but is semantically incomplete.
- Query language often does not match source language exactly.

So the desired shape is not:

```text
source document
-> one permanent chunking strategy
-> retrieve chunks
```

The desired shape is closer to:

```text
source document
-> evidence handles / propositions / structural units
-> prompt-conditioned core selection
-> prompt-conditioned context selection
-> query-specific package
```

The difference matters. A permanent chunk is a compromise made before the question is known. A query-specific package is an attempt to choose the minimum useful evidence after the question is known.

## Important Constraint

This new design should run in parallel to the existing pipelines unless a helper is clearly reusable. It should not mutate galloping, block, semantic_walk, or proposition_walk just to make this experiment fit. Those older pipelines remain baselines and sources of lessons, not the shape this system must conform to.

## What We Implemented First

The first implementation is deliberately cheap:

File:

```text
contextus/builder/query_assembly.py
```

Runner:

```text
evaluate_query_assembly.py
```

Tests:

```text
tests/test_builder_query_assembly.py
```

The first implementation does not use an LLM, a real reference resolver, a proposition graph, a discourse parser, or a verifier. It uses local embeddings and simple expansion rules.

The algorithm:

```text
1. Embed the prompt.
2. Embed all source elements.
3. Pick the top 5 most prompt-similar elements as candidate cores.
4. For each candidate core:
   a. Start with the core alone.
   b. Expand left first.
   c. Expand right second.
   d. On each addition, embed the whole package.
   e. Compare package-to-prompt similarity and package-to-core similarity.
   f. If an addition causes major drift away from both prompt and core, mark it.
   g. Give that direction up to 3 more elements to recover.
   h. If similarity recovers, keep the marked span.
   i. If it does not recover, roll back to before the mark and stop that direction.
   j. Stop on token budget, side limit, or repeated non-improving additions.
5. Return the assembled packages with decision traces.
```

Default knobs at initialization:

```text
top_k_cores = 5
lookahead_after_mark = 3
major_query_drop = 0.04
major_core_shift = 0.08
recovery_slack = 0.015
max_side_elements = 10
max_package_tokens = 280
stagnant_addition_limit = 2
```

The "mark and recovery" mechanism is the key experimental part. It encodes the intuition that sometimes a temporarily bad-looking neighbor is only bad because it is the first part of a larger local explanation. So the algorithm does not instantly reject the first drift. It gives the direction a small chance to recover.

This is still a crude approximation of the intended system. It measures embedding similarity, not actual understanding.

## Evaluation Setup

The current prompt suite has 12 fixed prompts across two documents:

```text
1. What is the closest pair problem?
2. How does the divide-and-conquer closest pair algorithm work?
3. How are Q and R used in the recursive closest pair algorithm?
4. What are the above three pairs in the closest pair algorithm?
5. Why does the proof say this contradicts the assumption?
6. Why can only nearby points in the strip be closest?
7. What does the Punnett square illustrate?
8. What does the figure show about meiosis producing haploid cells?
9. What does the DNA unwinding diagram show?
10. What does the malaria and sickle-cell map imply?
11. How are mitosis and meiosis different?
12. How do biological evolution and cultural evolution differ?
```

The suite covers:

- definitions
- procedures
- comparisons
- dangling references
- proof context
- visual support
- tables
- figure/heading dependencies

The latest run used:

```text
chunk_runs/query_assembly_20260516_093336/query_assembly.json
chunk_runs/query_assembly_20260516_093336/query_assembly.md
```

Summary:

```text
evidence_package:     hit@1 9/12,  hit@3 10/12, mean rank 6.17
query_assembled:      hit@1 9/12,  hit@3 10/12, mean rank 1.55
semantic_walk_step6:  hit@1 10/12, hit@3 11/12, mean rank 1.75
```

The semantic_walk comparison is no longer the main scoreboard, but it was useful as a reality check. The new implementation is not obviously worse than the best existing cheap baseline, but it is also not clearly better. The more important next evaluation is direct package judgment: did the package contain what the query actually needed?

## What The First Implementation Proved

It proved a narrow thing:

```text
A cheap embedding-only query-time assembler can often produce a relevant
package, and it is competitive enough to justify deeper work.
```

It did not prove:

```text
The chunking problem is solved.
```

It did not prove:

```text
Embeddings alone can choose the final package.
```

It did not prove:

```text
The core evidence can safely be chosen from raw document elements.
```

The useful result is that the mechanism has signal. When it gets the right core and the nearby evidence is locally ordered, the package is often good. When it fails, the failures are interpretable and point toward specific missing machinery.

## Core Selection Finding

Question:

```text
When the package chooses a bad core, was the right core absent from the top 5,
or was it present but the wrong candidate won?
```

Answer:

```text
Both happen.
```

There are three separate failure modes:

### 1. The right core is present, but a weaker core wins

Example: `inheritance-evolution-table`

Prompt:

```text
How do biological evolution and cultural evolution differ?
```

The top assembler package by internal score was a title:

```text
Genetics and Evolution
```

But the correct table package was also in the top 5:

```text
Table with columns BIOLOGICAL EVOLUTION, CULTURAL EVOLUTION...
```

This means the candidate generation step found the useful evidence, but the scoring layer preferred a vague title because the title embedding matched the broad query well.

Remedy:

```text
Do not let title-only packages win without attached answer-bearing body, table,
or figure evidence. Add answerability scoring and heading-only penalties.
```

### 2. The right core is nearby, but the selected core is only a reference fragment

Example: `closest-above-three-pairs`

Prompt:

```text
What are the above three pairs in the closest pair algorithm?
```

The package selected:

```text
find a closest pair of points in the left half
find a closest pair with one point in the left half and the other in the right half
return the pair that is the closest amongst the above three pairs
```

This is close, but it misses the right-half pair. The evidence lives in a list-like structure, and the system did not understand that "above three pairs" requires all sibling items in the list.

Remedy:

```text
Add list sibling closure. If a core references "above three pairs" or lands
inside a list, collect the whole sibling set before scoring final answerability.
```

### 3. The right core is not represented well as a raw element

Example: `closest-strip-nearby`

Prompt:

```text
Why can only nearby points in the strip be closest?
```

The answer depends on a proof spread across multiple elements:

```text
boxes
rows
Z
Sy
distance at least 3w/2
therefore at most 15 positions apart
```

The raw elements do not expose a clean single "core" that says "nearby points in the strip." The best evidence is a reasoning chain. Embedding the prompt against raw elements tends to find more literal "closest pair with Q and R" material instead of the rows/boxes proof.

Remedy:

```text
Represent proof claims as propositions or claim units, then map the selected
propositions back to source elements. The proposition may be the true core,
not the original element.
```

## Direct Package Analysis

### Good Package: closest-procedure

Prompt:

```text
How does the divide-and-conquer closest pair algorithm work?
```

The package centered on:

```text
The plan is to apply divide-and-conquer...
```

It added:

```text
find a closest pair in the left half
find a closest pair crossing the halves
return the closest among the above three pairs
recursive algorithm solves closest pair for a subset
```

This is a good query package. It contains the procedural skeleton. It could add the input/sorting setup, but it already answers the prompt at a useful level.

Lesson:

```text
When the source has a clean local procedure list, embedding expansion works
surprisingly well.
```

### Partial Package: closest-q-r

Prompt:

```text
How are Q and R used in the recursive closest pair algorithm?
```

The package included:

```text
Qy
Rx
Ry
recursive call on Q
recursive call on R
combine/compare cross-half pair
```

But it missed:

```text
Qx
the lead-in "the algorithm creates the following 4 lists"
```

This is not a retrieval failure in the broad sense. It is a structural closure failure. The system started in the middle of an enumerated list and did not recover the whole list.

Remedy:

```text
Add list-continuation detection and sibling completion.
```

### Partial Package: closest-above-three-pairs

Prompt:

```text
What are the above three pairs in the closest pair algorithm?
```

The package was close but incomplete:

Included:

```text
left half pair
cross-half pair
return closest among the above three pairs
```

Missed:

```text
right half pair
```

This shows why reference closure cannot be handled only by embedding stability. The package can remain semantically close while still missing one required sibling.

Remedy:

```text
Reference closure needs symbolic/structural signals, not only embedding score.
```

### Bad Package: closest-definition

Prompt:

```text
What is the closest pair problem?
```

The correct evidence is near the beginning:

```text
Given a set of n points in the plane, find a pair of points whose distance is
smallest possible.
```

The selected packages favored algorithm substeps:

```text
find a closest pair across halves
return the closest among the above three pairs
recursive algorithm...
```

This is a core selection failure. The prompt asks for a definition, but the embedding found repeated topical material about "closest pair" and "points." Repetition and topical overlap beat definitional role.

Remedy:

```text
Add query-intent features. A "what is X" prompt should favor definition-like
elements over procedural fragments.
```

Potential proposition remedy:

```text
Generate propositions such as "The closest pair problem asks for the pair of
points with minimum distance." That proposition would be a much better core
than a raw procedural element.
```

### Bad Package: closest-contradiction

Prompt:

```text
Why does the proof say this contradicts the assumption?
```

The package returned only:

```text
But this contradicts the assumption that d(s, t) < w.
```

This is the right sentence, but not a sufficient package. It needs the immediate proof setup:

```text
at least 3 rows of boxes separating s and t
distance at least 3w/2
therefore d(s,t) >= 3w/2 > w
assumption was d(s,t) < w
```

This is a dangling-reference failure. The selected sentence is answer-relevant but not answerable by itself.

Remedy:

```text
Add proof/discourse closure. Terms like "this contradicts", "therefore",
"assumption", and mathematical inequalities should trigger backward proof
context collection.
```

Potential proposition remedy:

```text
Generate propositions from proof steps, then connect them into a small proof
chain. The core may be "d(s,t) >= 3w/2 > w contradicts d(s,t) < w", not the
surface sentence alone.
```

### Bad Package: closest-strip-nearby

Prompt:

```text
Why can only nearby points in the strip be closest?
```

The selected package focused on Q/R merging, not the strip/box proof:

```text
one point in Q and one point in R
omega
is there a q in Q and r in R such that d(q,r) < omega?
```

The needed package should contain:

```text
strip or band S/Z
boxes
rows
at most one point per box
three rows imply distance at least 3w/2
therefore only nearby positions in Sy must be checked
```

This is partly query-language mismatch. The prompt says "nearby points in the strip." The source says "boxes", "rows", "Z", "Sy", and "at most 15 positions apart." Raw embedding did not reliably bridge that mismatch.

Remedy:

```text
Add generated proposition descriptions or contextual retrieval text that
normalizes the source's local terminology into query-like language.
```

### Good Package: inheritance-punnett

Prompt:

```text
What does the Punnett square illustrate?
```

The retrieved package included:

```text
Heredity Punnett Square
eye-color Punnett figure
2x2 Punnett square figure
```

It should also include:

```text
Genes = combinations of alleles
possibly father/mother gametes if present near the figure
```

This package is useful. It found visual support. But it still shows a weakness: the internal assembler score preferred title-only packages, while retrieval scoring surfaced the richer figure package.

Remedy:

```text
Answerability scoring should happen inside the assembler, not only accidentally
through the later retrieval scoring.
```

### Partial Package: inheritance-meiosis-figure

Prompt:

```text
What does the figure show about meiosis producing haploid cells?
```

The useful package included:

```text
meiosis figure
diploid cell
meiosis I / meiosis II
four haploid cells
Meiosis
Production of specialized cells from gametes
```

It also sometimes included noisy context:

```text
mitosis figure
chromosome/cell setup
```

This is an over-expansion problem. Nearby biology terms remain embedding-compatible, so they do not look like drift even when the prompt only needs the meiosis figure.

Remedy:

```text
Add figure-support rules and topic-boundary rules. A figure can pull its
caption/title/body, but crossing into adjacent figure topics should be penalized
unless the prompt asks for comparison.
```

### Partial Package: inheritance-dna-unwinding

Prompt:

```text
What does the DNA unwinding diagram show?
```

The core was excellent:

```text
DNA unwinding figure showing strands separate and nucleotide labels A, T, C, G
```

But it added:

```text
Sources of Variability
Mutation
Chemical change in DNA sequence
DNA replication figure
```

The additions are nearby and biology-related, but not needed for the prompt.

Remedy:

```text
For figure-description prompts, once the figure itself contains the answer,
prefer stopping unless a nearby caption/body explicitly explains that same
figure.
```

### Partial/Noisy Package: inheritance-sickle-map

Prompt:

```text
What does the malaria and sickle-cell map imply?
```

The core was useful:

```text
map of Africa showing malarial environments and sickle cell gene frequency
```

But the package added unrelated material:

```text
Mutation
DNA replication
biological/cultural evolution table
```

This is a visual-neighborhood drift problem. The relevant figure is near a slide transition into another section, and embeddings do not understand that the next table is a different topic.

Remedy:

```text
Use section/page/slide boundaries more strongly. Do not let a visual package
cross into the next conceptual slide unless the added element improves explicit
answerability.
```

### Bad Package: inheritance-mitosis-meiosis

Prompt:

```text
How are mitosis and meiosis different?
```

The top package was:

```text
Mitosis and Meiosis
Meiosis
```

This is not answerable. The needed package should include:

```text
Mitosis: replication of somatic cells
Meiosis: production of specialized cells from gametes
possibly the mitosis and meiosis figures
```

The right raw elements were nearby, but the algorithm let title-only cores dominate and did not attach the explanatory body text.

Remedy:

```text
Heading dependency and answerability scoring are required. A heading can be a
locator, but should not be treated as sufficient evidence.
```

Potential proposition remedy:

```text
Generate propositions such as "Mitosis replicates somatic cells" and "Meiosis
produces specialized cells/gametes." Then assemble both propositions for a
comparison prompt.
```

### Good Package: inheritance-evolution-table

Prompt:

```text
How do biological evolution and cultural evolution differ?
```

The right package contains:

```text
table comparing biological evolution and cultural evolution
Requirements For heading
```

The internal assembler ranked a title-only package higher, but the retrieval evaluator ranked the table package first. So this is a ranking/answerability issue, not a complete candidate-generation failure.

Remedy:

```text
Make table/figure/body answerability part of assembly scoring.
```

## Current Failure Thesis

The first implementation fails when similarity is asked to do jobs that are not similarity.

Embedding similarity can answer:

```text
Is this text broadly about the prompt?
```

It cannot reliably answer:

```text
Is this evidence sufficient?
Is this a heading with missing body?
Is this item 2 of a list whose item 1 is required?
Does "this" or "above" require earlier context?
Does this proof sentence need its prior inequalities?
Is this figure self-contained?
Did we cross into the next slide/topic?
```

So the remedy is not simply "tune thresholds." Threshold tuning can improve obvious over-expansion, but it cannot create missing structural understanding.

The next design should keep embedding similarity as one signal, but stop treating it as the full decision function.

## Remedy Thesis

The next implementation should move from:

```text
element embeddings choose core and context
```

to:

```text
propositions / evidence handles choose core intent
structural rules close required context
answerability scoring ranks packages
```

The likely next architecture:

```text
source elements
-> propositions or claim units
-> proposition embeddings
-> prompt selects candidate proposition cores
-> candidate propositions map back to source elements
-> context closure adds headings, siblings, proof steps, figures, tables
-> answerability scorer rejects title-only / dangling / unsupported packages
-> final query package
```

This would address several failures at once.

### Why Propositions May Help Core Selection

Raw elements are messy. A raw element can be:

- a title
- a bullet fragment
- a figure OCR blob
- a proof sentence
- a partial table row
- a list item
- a caption-like summary
- a whole paragraph

The prompt does not always match those raw units cleanly.

Propositions can normalize them into answer-shaped units:

```text
The closest pair problem asks for the pair of points with minimum distance.
Mitosis replicates somatic cells.
Meiosis produces specialized cells/gametes.
The proof derives d(s,t) >= 3w/2 > w, contradicting d(s,t) < w.
The Punnett square illustrates how allele combinations produce possible traits.
```

If retrieval happens over those propositions, the "core" is more likely to be answer-bearing rather than merely topically similar.

### Why Propositions Do Not Solve Everything Alone

Propositions help identify the answer-bearing claim, but they do not remove the need for source context.

A proposition must still map back to:

- source element IDs
- figures/tables
- captions
- page/slide
- bounding boxes
- neighboring proof/list context

Otherwise the system might retrieve a nice generated claim but lose citation safety.

The proposition should be a pointer and normalized retrieval surface, not a replacement for source evidence.

### Required Closure Layers

The next implementation should add at least these closure layers:

#### Heading/body closure

If the selected core is a heading or title, it should not stand alone. It should attach the body/figure/table under that heading, or be demoted.

#### List sibling closure

If the selected core is a list item, especially item 2/3/4 or text that references "above", "following", "these", or a count, collect the relevant siblings.

#### Proof/discourse closure

If the selected core contains:

```text
this contradicts
therefore
assumption
because
as a result
this means
```

then previous proof steps should be considered required context, not optional neighbors.

#### Visual support closure

If the selected core is a figure/table or the prompt asks about a figure/table/diagram/map, attach:

- the figure/table itself
- immediate caption-like text
- local heading
- explanatory body text if it points to the visual

But also stop before drifting into the next figure or section.

#### Answerability scoring

After assembling a candidate package, ask:

```text
Could this package answer the prompt without hidden context?
```

This can start cheap:

- title-only penalty
- lexical coverage of prompt terms
- expected support type present
- reference markers closed
- list sibling completeness
- figure/table present when requested
- no obvious section drift

Later it can become an LLM/verifier score.

## Implementation Log

### v1: Static evidence handles and context packages

Status:

```text
Implemented earlier.
```

Purpose:

```text
Build reusable evidence handles and static packages without disturbing existing
chunking pipelines.
```

Learned:

```text
Static packages improve over core-only retrieval, but this does not prove the
real query-time idea. They are useful machinery, not the final design.
```

Main flaw:

```text
Packages are built before the query, so they can only approximate usefulness.
```

### v2: Query-time embedding assembler

Status:

```text
Implemented.
```

Purpose:

```text
Test whether prompt-conditioned core selection and expansion has signal.
```

Performance:

```text
12 prompt suite:
hit@1 = 9/12
hit@3 = 10/12
mean best-hit rank = 1.55
```

Learned:

```text
The idea has signal, but raw-element embedding similarity is not enough.
```

Main flaws:

```text
bad core selection
heading/title-only cores
missing list siblings
missing proof setup
visual/topic over-expansion
weak answerability scoring
```

### Proposed v3: Proposition-conditioned evidence assembly

Status:

```text
Initial implementation completed.
```

Hypothesis:

```text
Generate propositions from source elements, retrieve/select proposition cores
with the prompt, then map propositions back to source elements and apply
closure rules.
```

Why:

```text
The current implementation often has the right source area but the wrong
answer-bearing unit. Propositions may expose the actual claim the prompt wants.
```

Risks:

```text
Proposition generation can hallucinate or distort source meaning.
Propositions can lose citation precision if mapping is weak.
Generated propositions can hide extraction errors.
Too many propositions can increase cost and indexing complexity.
```

Design guardrails:

```text
Every proposition must retain source element IDs.
Every proposition must be traceable to exact source text or asset.
The final package must cite source elements, not free-floating generated text.
The proposition layer should improve selection, not replace evidence.
```

Implementation:

```text
contextus/builder/query_assembly.py
evaluate_query_proposition_assembly.py
tests/test_builder_query_assembly.py
```

The implementation reuses the source-backed package expansion machinery. The difference is the core selection surface:

```text
raw source elements
-> source-mapped propositions
-> prompt/proposition embedding search
-> top 5 proposition cores
-> map each proposition to its source element
-> expand around that source element
-> return source-backed packages
```

The proposition generator uses the shared LLM wrapper and can run batches concurrently via `complete_many`. The OpenAI run used `gpt-5-nano`.

Run:

```text
chunk_runs/query_proposition_assembly_20260516_161630/query_proposition_assembly.json
chunk_runs/query_proposition_assembly_20260516_161630/query_proposition_assembly.md
```

Generated proposition counts:

```text
closest-pair: 134
09-Inheritance_fowler_anth1210_24: 170
```

Performance on the same 12 prompt suite:

```text
query_proposition_assembled:
hit@1 = 8/12
hit@3 = 11/12
mean best-hit rank = 1.45
misses = 1
```

Compared to the previous raw-element query assembler:

```text
raw-element query assembler:
hit@1 = 9/12
hit@3 = 10/12
mean best-hit rank = 1.55
misses = 2

proposition query assembler:
hit@1 = 8/12
hit@3 = 11/12
mean best-hit rank = 1.45
misses = 1
```

Interpretation:

```text
The proposition layer improved coverage/recall but did not improve top-rank
precision. It finds more of the right evidence somewhere in the top 3, but it
still often ranks a weaker package first.
```

Direct observations:

- `inheritance-evolution-table` improved in the way we hoped: the table package became rank 1 instead of losing internally to a broad heading.
- `inheritance-mitosis-meiosis` improved from a top-3 miss to hit@3, but rank 1 was still incomplete. This suggests propositions help find answer-bearing material, but ranking still needs answerability.
- `inheritance-punnett` was hit@3, but not hit@1. It still ranked weaker title/partial packages above the fully useful visual package.
- `closest-q-r` was hit@3, but not hit@1. The best package included the fuller Q/R setup, but list completion and ranking are still not strong enough.
- `closest-strip-nearby` remained the only miss. The proposition layer still selected generic closest-pair headings instead of the rows/boxes/strip proof.

Important lesson:

```text
Propositions help core selection, but they do not replace closure or
answerability scoring.
```

The remaining failures are not only about finding propositions. They are about ranking complete packages above incomplete packages and forcing structural closure when the query requires a list, proof chain, figure support, or heading body.

Next remedy thesis after v3:

```text
Keep proposition selection.
Add package answerability scoring.
Add list sibling closure.
Add proof/discourse closure.
Demote title-only packages unless they bring answer-bearing descendants.
Use proposition text in package ranking, but cite source elements.
```

### Reconsideration: Context Does Not Have To Be Continuous

New concern:

```text
The current query-time assembler still behaves as if useful context is mostly
continuous in reading order.
```

That assumption is only partly true. It works for many local explanations, proof steps, figure captions, and ordered procedures. But it can fail when the best package needs non-adjacent sibling evidence, a visual plus a distant explanatory caption, a table plus a heading, or multiple elements that belong together semantically but are separated by layout or slide structure.

This does not mean the system should return to broad clustering as the final solution. Previous clustering-style attempts were not enough on their own because clusters can become topic blobs: they gather related material without proving that each included item is needed for the prompt.

The better framing is:

```text
Clustering may help propose candidate context pools.
It should not decide the final package by itself.
```

In other words:

```text
prompt/proposition core selection
-> candidate context pools from structure, layout, and maybe clusters
-> answerability/closure scoring chooses the final evidence package
```

Open question to investigate:

```text
Can the old Verdo HDBSCAN-plus idea help us find non-contiguous context
candidates without falling back into cluster-as-chunk?
```

Initial caution:

```text
If clustering is used, it must stay subordinate to the query-time thesis.
Clusters should suggest possible supporting evidence; they should not become
the final chunking strategy.
```

### Visual/Text Partitioning Investigation

Another active thread:

```text
The current package assembler treats figures, tables, headings, and text too
uniformly during expansion.
```

This causes visual-context drift. A figure package may pull nearby text because it is semantically related, but the nearby text can belong to the next section, next slide, or a different visual. The Verdo visual/text partitioning approach may contain useful ideas for deciding which elements participate in which processing operations.

Open question to investigate:

```text
Can we borrow the idea of separating visual/support elements from ordinary text
when building candidate context pools and closure rules?
```

Likely desired behavior:

```text
Text propositions help identify answer-bearing claims.
Visual/table elements supply support evidence.
Visual support should be attached through explicit support closure, layout,
caption proximity, heading scope, and prompt intent, not by blind continuous
expansion.
```

### Verdo HDBSCAN-plus Review

Reviewed:

```text
C:/Users/dub6m/Documents/verdo/verdo-backend/app/services/ingester/services/HDBSCANplus.py
C:/Users/dub6m/Documents/verdo/verdo-backend/app/services/ingester/services/chunker.py
C:/Users/dub6m/Documents/verdo/verdo-backend/app/services/ingester/prompts/decompose_propositions.txt
C:/Users/dub6m/Documents/verdo/verdo-backend/app/services/ingester/handlers/image_handler.py
```

What Verdo was trying to do:

```text
source elements
-> separate ordinary text from figures/images/math
-> generate standalone propositions from text batches
-> provide nearby figures as contextual placeholders
-> allow propositions to cite [FIGURE id]
-> embed propositions
-> cluster propositions with HDBSCANplus
-> build semantic chunks from proposition clusters
```

The interesting idea is not "use clusters as chunks." That path has already shown the usual weakness: clusters can become broad topical bags. The interesting idea is:

```text
Use clustering to discover non-contiguous related proposition pools.
```

That could help the query-time package assembler because the current implementation mostly expands continuously in reading order. HDBSCAN-style clusters could provide an additional candidate pool:

```text
core proposition
-> nearby reading-order context
-> list/proof/heading/visual closure context
-> cluster-neighbor candidate context
```

But the final package should still be decided by the query-time package scorer, not by the cluster label.

Useful HDBSCANplus details:

- It normalizes embeddings and uses HDBSCAN over proposition embeddings.
- It searches HDBSCAN parameters instead of trusting one fixed `min_cluster_size`.
- It scores trials using DBCV/BIC-like signals with penalties for noise, single-cluster collapse, tiny clusters, and internally mixed clusters.
- It treats noisy points as noise instead of forcing every proposition into a cluster.
- It performs local parameter expansion around the best candidates.

This is useful as a candidate-pool generator because it tries to avoid two common clustering failures:

```text
everything in one giant cluster
many tiny useless clusters
```

But it is not sufficient as the final chunking method because it does not know the user's query and does not prove answerability.

Possible use in Contextus:

```text
Build proposition clusters offline.
At query time, retrieve a core proposition.
Look up propositions in the same cluster as optional non-contiguous support candidates.
Only include cluster candidates if they improve answerability, closure, citation safety, or support coverage.
```

This preserves the query-time thesis:

```text
Clusters suggest.
The query decides.
The final package cites source elements.
```

### Verdo Visual/Text Partitioning Review

Verdo separated figures/images/math from the ordinary text proposition stream:

```text
self.elements       = non-figure textual/structured content
self.figuresById   = visual/support elements
self.order         = all element IDs in reading order
idToElementIndex   = text element ID -> text stream index
```

This is the important part. It avoids treating figures as ordinary paragraphs during proposition generation, while still preserving global reading order so figures can be reintroduced as support.

When generating propositions, Verdo built a context window around each text batch using global order. If a figure appeared in that window, it inserted:

```text
[FIGURE figure_id] <structured figure text>
```

or just:

```text
[FIGURE figure_id]
```

The proposition prompt then explicitly told the model:

```text
If a figure is clearly related to a proposition, include [FIGURE id] in that proposition.
```

This is a better pattern than blind continuous expansion because visual support becomes an explicit reference on a proposition, not just a neighboring element that happened to be added.

Verdo also had visual include/exclude logic:

```text
math_image/math_text: include
decorative_stock_image/unknown_unclassified: exclude
chart/table/flowchart/diagram: include only if informative
screenshot/photo: include only if core/supportive
mixed_figure: include if it has components
```

The key idea for Contextus:

```text
Visuals should be indexed as support assets with typed structured summaries.
They should be offered to proposition generation and package assembly as support candidates.
They should not be treated as ordinary neighboring text unless the prompt/core requires them.
```

Potential Contextus adaptation:

```text
1. Partition source elements into text-like evidence and support-like evidence.
2. Generate propositions primarily from text-like evidence.
3. Provide nearby support-like evidence as context/placeholders.
4. Let propositions carry explicit support references.
5. At query time, if a selected proposition references support, attach that support.
6. If the prompt asks about a figure/table/map/diagram, allow support elements to be candidate cores.
7. Penalize support drift across slide/section boundaries unless explicit support reference or prompt intent justifies it.
```

This may fix the current visual drift problem more cleanly than threshold tuning.

### Current Read After Verdo Review

Verdo should not be adopted wholesale. The clustering method alone is not the answer, and the old chunk output shows some broad-topic behavior. Also, the inspected `buildSemanticChunks` path appears to reference `self.propositionSources`, which is not defined in the class shown, so the exact implementation is not a clean drop-in.

But two ideas are worth carrying forward:

```text
1. Use clusters only as non-contiguous candidate pools.
2. Treat visuals/support as typed support assets, not ordinary text.
```

This suggests the next Contextus design should move from:

```text
continuous expansion around core
```

to:

```text
candidate context pool assembly
```

Where the candidate pool can include:

- immediate left/right neighbors
- heading/body descendants
- list siblings
- proof/discourse predecessors
- explicitly referenced figures/tables/formulas
- nearby visual support candidates
- same-cluster proposition candidates

Then answerability/ranking chooses what actually enters the final package.

### v4: Initial Support-Aware Proposition Assembly

Status:

```text
Implemented as first-pass plumbing.
```

Files:

```text
contextus/builder/query_assembly.py
evaluate_query_proposition_assembly.py
tests/test_builder_query_assembly.py
```

What changed:

```text
1. Support-like elements are now recognized separately from ordinary text.
2. Figures/images/charts/diagrams/flowcharts/tables/formulas are treated as support elements.
3. Support elements are not sent through the LLM proposition generator as if they were normal text.
4. Nearby support assets are shown to proposition generation as [SUPPORT element_id] placeholders.
5. Generated propositions can carry explicit support references.
6. If a selected proposition references support, the final package can attach that support non-contiguously.
```

The important architectural change is this:

```text
support asset attachment is no longer limited to left/right expansion.
```

That matters because a figure/table may be the right evidence even when it is not the next contiguous element after the selected text proposition. This is closer to the Verdo idea that visuals are support assets available to propositions, not ordinary paragraphs in the text stream.

The implementation is intentionally small. It does not yet include HDBSCAN, visual-type filtering, caption classification, or a real support resolver. It adds the pipe that allows a proposition to say:

```text
this claim is supported by support element X
```

and then makes the package assembler honor that source-backed support reference.

Focused tests added:

```text
test_proposition_query_assembler_attaches_explicit_support_reference
test_proposition_query_assembler_does_not_send_support_elements_for_generation
```

Focused verification:

```text
python -m pytest tests/test_builder_query_assembly.py -q
9 passed

python -m py_compile contextus/builder/query_assembly.py evaluate_query_proposition_assembly.py
passed
```

Run:

```text
chunk_runs/query_proposition_assembly_20260516_165738/query_proposition_assembly.json
chunk_runs/query_proposition_assembly_20260516_165738/query_proposition_assembly.md
```

LLM:

```text
OpenAI gpt-5-nano
```

Result on the 12 prompt suite:

```text
hit@1 = 9/12
hit@3 = 11/12
mean best-hit rank = 1.36
misses = 1
```

Compared to the previous proposition run:

```text
previous proposition run:
hit@1 = 8/12
hit@3 = 11/12
mean best-hit rank = 1.45
misses = 1

support-aware proposition run:
hit@1 = 9/12
hit@3 = 11/12
mean best-hit rank = 1.36
misses = 1
```

Plain interpretation:

```text
The ranking got slightly better, but this is not proof that explicit support
attachment is working in the live run.
```

The reason is important:

```text
support_ref_count = 0
```

The model did not emit any `[SUPPORT id]` references in the real OpenAI run, even though the prompt asked it to. So the new explicit support attachment mechanism is tested and available, but it did not actually fire during this evaluation.

That means the observed metric improvement likely came from secondary effects:

- support elements were partitioned out of normal proposition generation
- proposition batches changed
- proposition text/count changed
- candidate ordering changed slightly

It should not be interpreted as:

```text
visual support closure is solved.
```

It should be interpreted as:

```text
we now have the first source-backed support-attachment path, but the generator
interface is too weak to populate it reliably.
```

Concrete case observations from the run:

- `inheritance-evolution-table` remained good. The actual table package was rank 1.
- `closest-above-three-pairs` remained good by the current evaluator and now surfaced the local list/procedure context strongly.
- `inheritance-mitosis-meiosis` became rank 1 by the evaluator, but the package is broad and still includes a lot of neighboring visual/topic material.
- `inheritance-punnett` still ranked title-only packages above the better figure package. This is a ranking/answerability failure.
- `closest-q-r` still had the fuller setup at rank 3, not rank 1. This is list closure plus ranking.
- `closest-contradiction` still returned the contradiction sentence without the proof setup. The evaluator calls it a hit, but the package is not answer-complete.
- `closest-definition` still looks falsely good by keyword expectation. It retrieves algorithm substeps rather than the clean definition.
- `closest-strip-nearby` is still the one outright miss. The system still does not connect "nearby points in the strip" to the source's boxes/rows/Sy proof language.
- Visual drift still exists. Meiosis, DNA unwinding, and sickle-cell-map packages still pull nearby biology/visual material that the prompt does not need.

What this teaches:

```text
Partitioning support elements is necessary but not sufficient.
```

The system needs a stronger way to make support references real. Asking the model to append bracket markers inside proposition strings is too fragile. The better next version should make support references structural:

```json
{
  "element_id": "...",
  "propositions": [
    {
      "text": "The Punnett square illustrates possible allele combinations.",
      "support_element_ids": ["..."]
    }
  ]
}
```

That would remove ambiguity from the LLM output and make support attachment a first-class field instead of a hidden text convention.

We should also add cheap local support inference because the model should not be the only path:

```text
if prompt asks about figure/table/map/diagram
and selected proposition/core is near a support asset
and the support asset shares heading/page/slide scope
then consider the support asset as a candidate attachment
```

This local inference should still be scored. It should not blindly attach every nearby figure.

Current v4 verdict:

```text
Useful implementation step.
Not yet a solved visual-support system.
The next support step is structured support refs plus local support candidate
inference.
```

### v5: Consensus kNN Cluster Candidate Pools

Status:

```text
Implemented as a parallel assembler.
```

Files:

```text
contextus/builder/query_assembly.py
evaluate_query_proposition_assembly.py
tests/test_builder_query_assembly.py
```

New class:

```text
ConsensusKnnPropositionEvidenceAssembler
```

Why this exists:

```text
The previous query-time assembler still treated context mostly as a contiguous
left/right strip. That is too narrow. Some useful context is non-contiguous:
same proof idea, same list family, same visual concept, same table/heading
area, or same proposition cluster.
```

But the old clustering route had a dangerous failure mode:

```text
cluster == chunk
```

That is not what this implementation does. The cluster is only a candidate pool.
The final package is still query-time and source-backed.

The new shape is:

```text
source elements
-> source-mapped propositions
-> proposition embeddings
-> prompt selects candidate proposition cores
-> multi-K consensus graph finds stable proposition neighbors
-> selected neighbor propositions map back to source elements
-> package is assembled from non-contiguous source elements
```

The important difference from HDBSCANplus:

```text
No single cluster run decides the package.
No permanent semantic chunk is created.
No proposition loses its source element mapping.
```

#### Mechanism

The consensus graph does this:

```text
1. Embed all propositions.
2. For several K values, compute each proposition's nearest neighbors.
3. Count how often each proposition pair appears as neighbors.
4. Convert repeated neighbor relationships into stable graph edges.
5. Keep only edges that pass:
   - neighbor stability threshold
   - embedding similarity threshold
   - structural-adjusted similarity threshold
6. Starting from the selected core proposition, collect a small graph neighborhood.
7. Score each candidate proposition against:
   - prompt similarity
   - core similarity
   - neighbor stability
   - structural bonus
   - support/heading penalties
8. Map accepted propositions back to source elements.
```

Current defaults:

```text
adaptive K:
  n < 30       -> 2, 3, 5
  30 <= n <150 -> 3, 5, 8, 13
  n >= 150     -> 5, 8, 13, 21

min_neighbor_stability = 0.4
min_edge_similarity = 0.32
max_cluster_hops = 1
max_cluster_propositions = 10
min_candidate_score = 0.42
```

There was an initial looser run:

```text
max_cluster_hops = 2
max_cluster_propositions = 18
min_candidate_score = 0.28
```

That run improved retrieval rank, but packages were too broad:

```text
average package size ~= 10 elements
max package size = 19 elements
cluster attachments = 539
```

So the defaults were tightened. This matters because the goal is not to make
clusters retrieve everything. The goal is to produce accurate candidate pools
without turning them into topic blobs.

#### Verification

Focused tests:

```text
python -m pytest tests/test_builder_query_assembly.py -q
11 passed
```

Compile check:

```text
python -m py_compile contextus/builder/query_assembly.py evaluate_query_proposition_assembly.py
passed
```

New tests added:

```text
test_consensus_knn_assembler_adds_non_contiguous_cluster_context
test_consensus_knn_assembler_keeps_isolated_noise_as_singleton
```

The second test is important. We do not throw away isolated propositions just
because they do not belong to a cluster. A singleton definition, proof step, or
figure can still be the right answer.

#### Run

Run:

```text
chunk_runs/query_proposition_assembly_20260516_203005/query_proposition_assembly.json
chunk_runs/query_proposition_assembly_20260516_203005/query_proposition_assembly.md
```

LLM:

```text
OpenAI gpt-5-nano
```

Result on the 12 prompt suite:

```text
hit@1 = 11/12
hit@3 = 11/12
mean best-hit rank = 1.0
misses = 1
```

Package size after tightening:

```text
min package size = 2 elements
max package size = 11 elements
average package size ~= 7.58 elements
cluster attachments = 395
cluster skips = 107
```

Support references:

```text
support_ref_props = 0
```

So, again, explicit model-emitted support references are still not firing. Any
visual improvements here come from proposition/embedding neighborhoods, not
from a solved support-reference mechanism.

#### What Improved

`closest-q-r` improved.

Before clustering, Q/R often had the right material in top 3 but not rank 1, or
missed part of the four-list setup. The cluster pool now pulls the recursive
algorithm context, the P_x/P_y setup, and Q/R list material together strongly
enough to rank as a hit at 1.

`closest-contradiction` improved in the way we wanted.

The previous package often returned only:

```text
But this contradicts the assumption that d(s, t) < omega.
```

The cluster package now includes surrounding proof propositions:

```text
q and r are within omega of line L
suppose q and r exist with d(q,r) < omega
rows/box distance setup
contradiction sentence
```

This is the strongest evidence that non-contiguous proposition neighborhoods
can help with proof/discourse closure.

`inheritance-punnett` improved at rank 1.

The cluster package pulled multiple Punnett-related headings/figures together.
This is not a perfect visual-support solution, but it is better than title-only
packages winning.

`inheritance-dna-unwinding` became tighter.

The top packages were mostly DNA diagram variants and directly related support,
instead of pulling a larger mutation/replication section.

#### What Still Failed

`closest-strip-nearby` still missed.

This is still the same underlying problem:

```text
prompt language: nearby points in the strip
source language: boxes, rows, Sy, Z, at most 15 positions
```

The cluster graph found a broad "Closest Pair of Points in the Plane" title
pool instead of the specific boxes/rows proof. This means clustering alone does
not solve retrieval-language mismatch. We likely need generated retrieval text,
query expansion, or a proof-aware proposition rewrite for this case.

`closest-definition` is still falsely flattered by the evaluator.

The top package includes definition-like material, but it is still too broad and
algorithm-heavy. The evaluator counts it as a hit because expected terms appear,
but by eye the cleaner definition package is not consistently ranked first.

`inheritance-meiosis-figure` and `inheritance-mitosis-meiosis` still show visual
sibling drift.

The cluster often groups mitosis and meiosis visuals together. That can be
correct for a comparison query, but for "what does the meiosis figure show" it
still adds mitosis material that is not necessary. This is a reminder that
semantic relatedness is not the same as prompt necessity.

`inheritance-sickle-map` is better than the old broad drift, but still shows
support confusion: the core map can pull a genotype/Punnett-like visual neighbor
because genetics visuals are semantically close. We need typed visual support
selection, not only embedding clusters.

#### Current v5 Verdict

Consensus kNN clustering is a real improvement over the linear-only context
strip. It especially helps when the needed context is semantically connected but
not neatly adjacent.

But the result is not "clustering solved chunking." The right conclusion is:

```text
Consensus clustering is useful as a non-contiguous candidate-pool generator.
It should remain subordinate to query-time answerability and support closure.
```

The next remedies are now clearer:

```text
1. Add query-intent scoring so definition prompts prefer definition propositions.
2. Add proof/list closure rules for cases where cluster neighborhoods are close
   but still structurally incomplete.
3. Add typed visual support selection so figure prompts do not over-attach
   sibling visuals.
4. Add generated retrieval text or query expansion for language mismatch cases
   like strip/boxes/rows/Sy.
5. Make support references structural JSON fields instead of bracket markers.
```

### v6: Document Language Map Retrieval Assist

The next idea we tested was not "ask an LLM to invent document vocabulary."
That would be too easy to turn into hallucinated query expansion.

Instead, the implementation builds a source-grounded language map from the
document propositions themselves.

The mechanism is:

```text
source-backed propositions
-> extract repeated/rare language units from proposition text
-> assign document-local families from the document's own vocabulary
-> compare query language units against document language units
-> optionally rescue one core candidate when embedding retrieval misses a
   vocabulary-specific match
```

The important design choice is that the families are dynamic. They are not a
fixed list such as "noun chunks, verb phrases, symbols, numbers." Those unit
types exist as cheap hints, but the grouping comes from the document's own
repeated terms and symbol-like vocabulary.

For example, in the closest-pair document, units around `Sy`, `Z`, `boxes`,
`rows`, `distance`, and `15 positions` become document-local signals only
because the document actually contains them. The code does not ask the model to
guess that "nearby points in the strip" might mean those terms.

#### Why This Helps The Thesis

The clustering route is strong when the query and document already speak
similar language. The language-map layer is meant to help when they almost
speak the same language but the important terms are small, symbolic, or buried
inside proof wording.

In retrieval terms:

```text
embedding similarity finds the broad neighborhood
document-language scoring tries to rescue exact source vocabulary
clustering then gathers nearby source-backed propositions
source elements remain the final citeable context
```

This keeps the language layer subordinate to chunking. It does not create final
chunks by itself and it does not produce uncited summaries.

#### What Actually Happened

The controlled unit test worked: when the embedding candidates were weak, the
language map could promote the proposition containing the better document
language.

But the real prompt suite exposed a risk.

The first live run with language-map rescue over-promoted broad terms like
proof, overview, and algorithm. That made some packages drift toward generic
nearby material instead of the precise evidence. A tuned version reduced the
weight and added a lexical-overlap gate, but it still did not beat the pure
cluster run.

Observed live runs:

```text
pure tight cluster run:
  chunk_runs/query_proposition_assembly_20260516_203005
  best current behavior on this suite

language-map run:
  chunk_runs/query_proposition_assembly_20260517_124030
  worse; generic vocabulary rescue was too eager

tuned language-map run:
  chunk_runs/query_proposition_assembly_20260517_124556
  still worse than pure clustering on this suite

post-gating default cluster rerun:
  chunk_runs/query_proposition_assembly_20260517_125042
  language map disabled; weaker than the earlier best cluster run

post-gating language-map rerun:
  chunk_runs/query_proposition_assembly_20260517_125839
  language map enabled; recovered one extra case into the top few results, but
  did not improve first-choice ranking
```

In plain terms:

```text
The language map is promising as an experimental rescue tool.
It is not strong enough to be the default selection policy yet.
```

The newer runs also taught us a separate lesson: live proposition generation
adds variance. The same assembler can look better or worse depending on the
propositions produced for that run. For serious comparison, we need a pinned
proposition artifact or deterministic proposition fixture so we can compare
selection strategies without also changing the candidate pool.

So the implementation now leaves the language map off by default for the
consensus assembler. It can be enabled for experiments with:

```text
QUERY_LANGUAGE_MAP=1
```

#### Current v6 Verdict

This was useful, but not because it immediately improved the score.

It taught us that document-local vocabulary is real signal, but raw language
matching is not enough. The language layer needs stricter specificity scoring
before it should steer core selection by default.

The next version should likely use language units as evidence in a reranker or
answerability check, not as a blunt replacement for embedding-based core
ranking.

#### Evidence Discovery Recheck

After the first report, we clarified the actual question:

```text
Did the right evidence enter the candidate set/package at all?
```

That is different from:

```text
Did the best package rank first?
```

Rechecking the latest runs with that lens:

```text
Default cluster, language map off
run: chunk_runs/query_proposition_assembly_20260517_125042

Full expected evidence appears in at least one assembled package: 11/12
A core alone contains all expected evidence: 8/12
At least one core contains some expected evidence: 11/12
No complete package: closest-q-r
```

```text
Cluster with language-map rescue
run: chunk_runs/query_proposition_assembly_20260517_125839

Full expected evidence appears in at least one assembled package: 12/12
A core alone contains all expected evidence: 8/12
At least one core contains some expected evidence: 11/12
No complete package: none
```

So the language map did help the thing we actually meant to test at this stage:
it improved evidence discovery/completeness at the package level.

But it did not improve the stricter core-selection question. The number of cases
where a selected core alone contains the whole expected evidence stayed the
same.

This is especially important for `closest-strip-nearby`. The complete evidence
appears in a package, but not because the assembler chose a clearly correct
core. It is still being rescued by surrounding/cluster context. That means the
language-map layer is not yet a real fix for paraphrased core discovery.

Updated interpretation:

```text
The language map is useful as a recall/completeness assist.
It is not yet a reliable core selector.
```

### v7: Order-Aware Cluster Spans

The next issue was visible by eye in the saved packages. The cluster packages
often contained the right evidence, but they did not read like document context.
They read like semantic grab-bags.

The reason is straightforward:

```text
semantic clustering knows what is related
semantic clustering does not know how the document explains it
```

So v7 changes the responsibility of clustering.

Old behavior:

```text
cluster finds related proposition anchors
-> package directly serializes those cluster members
```

New behavior:

```text
cluster finds related proposition anchors
-> anchors are sorted by reading order
-> nearby anchors become ordered spans
-> the span containing the core is kept
-> other spans attach only if a cheap attachment score accepts them
-> simple closure rules can expand a span by one neighboring element
```

The important design change is:

```text
Clusters propose candidates.
Reading order shapes the package.
```

The cheap v7 rules are intentionally simple:

```text
1. Split ordered anchors when the reading-order gap is too large.
2. Keep the core span.
3. Attach at most a small number of non-core spans.
4. Score extra spans using anchor score, prompt-token overlap, support need,
   distance penalty, heading-only penalty, duplicate penalty, and token budget.
5. Expand a span left/right only for simple closure markers like backward
   references or forward references.
```

This is not the final resolver. It is a cheap test of the architecture.

#### v7 Run

Run:

```text
chunk_runs/query_proposition_assembly_20260517_165106
```

That first run used the evaluator default LLM client. Because the project
preference for this proposition track is OpenAI GPT-5 nano, the same path was
rerun with:

```text
QUERY_PROPOSITION_LLM=openai
OPENAI_MODEL=gpt-5-nano
```

Primary v7 run:

```text
chunk_runs/query_proposition_assembly_20260517_170412
```

Readable full packages for the primary run:

```text
chunk_runs/query_proposition_assembly_20260517_170412/full_packages_by_prompt.md
```

Retrieval-level result:

```text
Right package first: 11/12
Right package in top three: 11/12
Misses: 1
```

Evidence-completeness recheck:

```text
Full expected evidence appears in at least one assembled package: 11/12
A core alone contains all expected evidence: 8/12
At least one core contains some expected evidence: 11/12
No complete package: closest-strip-nearby
```

Package size changed materially:

```text
Complete package size range: 2 to 7 elements
Average complete package size: 4.18 elements
```

That is much cleaner than the earlier cluster packages, which frequently
included broad topic neighborhoods and repeated headings.

#### What Improved

The packages are easier to read. The worst generic cluster behavior was reduced:

```text
less repeated title material
less broad algorithm neighborhood drift
smaller packages
more stable first-choice retrieval in this run
```

The package for `closest-above-three-pairs` became especially clean:

```text
left-half pair
cross-left/right pair
above three pairs
```

That is the exact kind of ordered evidence package this route is supposed to
produce.

#### What Got Worse

`closest-strip-nearby` lost its complete package.

This is the key tradeoff. The old loose cluster could technically recover the
row/box/distance evidence, but it did so inside a messy package. The new
order-aware span layer rejects or fails to attach that distant proof line.

So v7 tells us:

```text
Order-aware spans improve package readability.
The cheap attachment rule is now too conservative for non-local proof support.
```

This is not a failure of the architecture. It is a useful failure of the cheap
attachment rule.

#### Current v7 Verdict

Order-aware clustering has weight.

The evidence is:

```text
packages are smaller
packages read more coherently
first-choice retrieval improved on this live run
```

But it must learn a stronger support/proof attachment rule. Otherwise it will
prefer clean local packages and miss a distant but necessary proof span.

The next remedy should not be "make packages broad again." It should be:

```text
keep ordered spans
add a special proof/support bridge for distant but necessary spans
```

For example, `closest-strip-nearby` needs a bridge that understands:

```text
nearby points in the strip
-> Z / boxes / rows / distance bound
```

The current language map was not enough to make that bridge reliable.

### v8: Candidate Span Competition

The next hypothesis was:

```text
Do not expand spans step by step.
Enumerate possible ordered spans.
Score each candidate span.
Pick the smallest span that actually measures best.
```

This was meant to avoid a brittle rule stack. Instead of saying:

```text
if "this" then add previous
```

the scorer generated span candidates around each anchor group and measured:

```text
prompt similarity
anchor preservation
internal cohesion
boundary strength
evidence density
small closure bias
token cost
duplicate penalty
```

The implementation was added behind an experimental switch:

```text
QUERY_SPAN_COMPETITION=1
```

It is not enabled by default.

#### v8 Run

Run:

```text
chunk_runs/query_proposition_assembly_20260517_194021
```

Readable full packages:

```text
chunk_runs/query_proposition_assembly_20260517_194021/full_packages_by_prompt.md
```

Result:

```text
Right package first: 10/12
Right package in top three: 10/12
Full expected evidence appears in at least one assembled package: 10/12
A core alone contains all expected evidence: 8/12
At least one core contains some expected evidence: 11/12
No complete package: closest-q-r, closest-strip-nearby
Average complete package size: 3.0 elements
```

This is worse than v7.

#### What The Failure Means

The candidate-span scorer made packages smaller, but it became too conservative
and lost necessary context.

That is useful information:

```text
measurable span competition is a good architecture idea
the current score is not a good enough measurement
```

The current score over-trusts local compactness. It can prefer a neat small span
over a slightly broader span that carries necessary proof/setup context.

`closest-q-r` is especially informative. The selected packages had Q/R material,
but the complete expected package was lost. That means the scorer can keep
semantically central anchors while still dropping the small surrounding setup
that makes the answer complete.

`closest-strip-nearby` remains the harder failure. The needed bridge is not just
local expansion. It needs a proof/support bridge from the prompt wording to the
row/box/Z/distance-bound span.

#### Current v8 Verdict

Candidate span competition should stay experimental.

The default should remain v7 order-aware spans with the simpler closure
expansion for now.

The next version of span competition would need better measurements before it
should replace v7:

```text
stronger evidence-completeness reward
better document-language specificity
explicit proof/setup bridge score
penalty for losing expected anchor vocabulary
separate compactness score from completeness score
```

The lesson is not "go back to broad packages." The lesson is:

```text
compactness cannot be optimized before completeness.
```

### v8.1: Completeness-First Span Competition

The v8 failure suggested a sharper scoring shape:

```text
first decide which candidate spans are complete enough
then use compactness/quality as a tiebreaker
```

So v8.1 changed span competition from a single blended score into local
thresholding.

For each anchor group:

```text
1. Enumerate candidate ordered spans within a small radius.
2. Compute completeness for each span.
3. Find the maximum completeness available in that local candidate set.
4. If the best span barely improves over anchor-only, keep anchor-only.
5. Otherwise, keep spans within a small slack of local-best completeness.
6. Among those near-best spans, prefer cleaner/smaller spans.
```

This avoids a global threshold like `0.72`. The threshold is local:

```text
eligible if completeness >= local_best_completeness - slack
```

Run:

```text
chunk_runs/query_proposition_assembly_20260517_213220
```

Readable full packages:

```text
chunk_runs/query_proposition_assembly_20260517_213220/full_packages_by_prompt.md
```

Result:

```text
Right package first: 11/12
Right package in top three: 11/12
Full expected evidence appears in at least one assembled package: 11/12
A core alone contains all expected evidence: 8/12
At least one core contains some expected evidence: 11/12
No complete package: closest-strip-nearby
Average complete package size: 4.0 elements
```

This recovers the v7-level result and fixes the v8 regression on `closest-q-r`.

But it still does not beat v7 and still does not solve
`closest-strip-nearby`.

#### Current v8.1 Verdict

Completeness-first local thresholding is a better shape than the v8 blended
score.

But on this suite it is not yet a clear replacement for v7. It should remain
behind the experimental switch:

```text
QUERY_SPAN_COMPETITION=1
```

The lesson is:

```text
candidate span competition can be made sane
but the hard remaining failure is probably not local span expansion
```

`closest-strip-nearby` continues to point at a different mechanism:

```text
core discovery / proof bridge / distant group attachment
```

### v9: Source-Grounded Query Planner

The next idea came from the observation that the hardest remaining miss was not
really a normal chunking miss. The prompt:

```text
Why can only nearby points in the strip be closest?
```

does not speak in the same vocabulary as the source passage. The source explains
the mechanism with terms like:

```text
S, Sy, Z, boxes, rows, distance, omega, at most 15 positions
```

So the failure is better described as:

```text
user wording
-> hidden information need
-> document vocabulary / proof mechanism
-> source evidence package
```

The first v9 implementation added an optional query planner:

```text
prompt
-> compact document retrieval map
-> LLM retrieval hypothesis
-> source-supported terms / prerequisite ideas / search forms
-> bridge back into propositions
```

The planner is instructed to treat its output as a hypothesis, not as truth, and
to use only vocabulary present in the document map. This is important because a
free query-rewriter would be dangerous here. It would be too easy for the model
to invent better-sounding terminology and then force the retriever to chase it.

The first implementation made a useful discovery but used the discovery badly.
It allowed planned query forms to change the similarity scores for all candidate
cores. That made the hard strip case better, but it also damaged cases that were
already solved.

Live full-suite run:

```text
Run: chunk_runs/query_proposition_assembly_20260518_191313
Right package first: 8/12
Right package in top three: 8/12
Misses by the simple evaluator: 4
```

The important detail is not just the score. The planner found the strip proof
bridge, but it displaced good baseline cores for simpler prompts like:

```text
What are the above three pairs in the closest pair algorithm?
Why does the proof say this contradicts the assumption?
```

That means the LLM plan should not be treated as the new query. It should be a
small source-grounded side lane.

#### v9.1: Bridge Lane, Not Query Replacement

The safer design changes the planner's authority:

```text
normal core discovery = original user prompt only
LLM plan = source-grounded bridge candidate only
bridge candidates = allowed to occupy a small tail slot
```

So the planner can add a missing proof bridge, but it cannot rewrite the whole
retrieval problem and push out already-good cores.

Mechanically:

```text
1. Generate/source-backed propositions as before.
2. Build the normal top core candidates from the original prompt embedding.
3. Ask the planner for document-grounded retrieval hypotheses.
4. Extract bridge propositions by exact overlap with source-supported plan terms.
5. Reserve only one selected-package slot for a bridge proposition.
6. Assemble/read-order packages normally from those cores.
```

The key implementation lesson:

```text
The LLM should help discover candidates.
It should not silently redefine candidate scoring.
```

Cached verification using the previous run's generated propositions and
retrieval plans:

```text
closest-definition: right package first
closest-procedure: right package first
closest-q-r: evaluator miss, but the selected package is visibly about Q/R,
             recursive calls, and combining Q/R cross-pairs
closest-above-three-pairs: right package first
closest-contradiction: right package first
closest-strip-nearby: strip proof bridge appears in the selected five
inheritance-punnett: right package first
inheritance-meiosis-figure: right package first
inheritance-dna-unwinding: right package first
inheritance-sickle-map: right package first
inheritance-mitosis-meiosis: right package first
inheritance-evolution-table: right package first
```

The simple term evaluator reports:

```text
Right package first: 10/12
Right package in top three: 10/12
```

But that number is partly misleading:

```text
closest-q-r is a brittle-label miss
closest-strip-nearby is a ranking/completeness miss, not a discovery miss
```

For `closest-q-r`, the selected package discusses Q, R, recursive calls on Q/R,
and the cross-pair comparison. The evaluator misses it because the expected term
set still wants literal wording like "left half" and "right half".

For `closest-strip-nearby`, the bridge package now appears, but it still lacks
some surrounding language that would make the proof fully comfortable to read.
It includes:

```text
at most one point per box
at least 3 rows of boxes
points in Z
distance at least 3omega/2
therefore d(s,t) > omega
```

This is real progress: the system found the missing proof area. But it also
shows that bridge discovery and package completion are separate mechanisms.

Current v9 verdict:

```text
The document-grounded query planner is promising as a bridge-finder.
It is not safe as a global query-rewriter.
Keep it optional.
Use it to add candidates, not to replace the original prompt signal.
```

Next remedy thesis:

```text
1. Keep original-prompt core discovery as the stable baseline.
2. Let source-grounded plans add a small number of bridge candidates.
3. Improve completion around bridge candidates, especially proof spans.
4. Replace the brittle term evaluator with an answerability/proof check.
5. Add ranking later, after selected-package coverage is stable.
```

### v10: Role-Indexed Completion Repair

The next question was whether the existing expansion mechanism might be good
enough if we added a targeted completion pass after package assembly.

The new distinction is:

```text
Expansion = build a readable local package from selected anchors.
Completion = inspect the built package and attach missing explanation roles.
```

The first completion pass is deliberately cheap and deterministic. It does not
ask an LLM whether a package is complete. It looks for source evidence that fills
specific roles:

```text
definition/setup candidate
proof setup
proof-chain backfill
proof conclusion
support/figure/formula context
```

Mechanically, after the normal cluster/order-aware package is built:

```text
1. Inspect selected source elements.
2. Extract document terms/symbols such as S, Sy, Z, omega, rows, boxes.
3. Check whether those terms appear to be defined inside the package.
4. Search the nearby source window and same-page area for role candidates.
5. Attach only a capped number of high-scoring source elements.
6. Sort the final package back into reading order.
```

This is a partial version of the graph idea without rebuilding the full graph:

```text
package mentions missing term/role
-> search role index candidates
-> attach the best source element(s)
```

The important implementation detail is that completion attaches **specific
source elements**, not everything between the core and the missing setup. This
preserves query-time package flexibility while borrowing one of the graph's best
properties: typed paths to missing support.

#### v10 Run

Run:

```text
chunk_runs/query_proposition_assembly_20260520_035627
```

Settings:

```text
QUERY_PROPOSITION_ASSEMBLER=cluster
QUERY_LANGUAGE_MAP=1
QUERY_RETRIEVAL_PLAN=1
QUERY_RETRIEVAL_PLAN_BRIDGE_SLOTS=1
QUERY_ROLE_COMPLETION=1
QUERY_PROPOSITION_LLM=openai
OPENAI_MODEL=gpt-5-nano
```

Result:

```text
Right package first: 11/12
Right package in top three: 11/12
Right package somewhere in selected five: 12/12
Only remaining ranking issue: closest-strip-nearby at rank 5
```

The important qualitative change is the `closest-strip-nearby` package. It now
contains the real proof chain:

```text
Partition Z into boxes.
A row of Z consists of 4 boxes.
No two points can lie in the same box.
At most one point of S can be in any box.
There are at least 3 rows of boxes separating s and t.
Two points in Z separated by at least 3 rows have distance at least 3omega/2.
This contradicts d(s,t) < omega.
Therefore only a bounded number of nearby Sy positions need to be checked.
```

So completion did what we hoped for this case:

```text
bridge found the right proof area
completion filled the missing setup/proof/conclusion roles
```

But the package is still ranked below a few weaker candidates. That confirms the
next bottleneck is no longer selected-package coverage. It is ranking and
answerability scoring.

#### v10 Verdict

Role-indexed completion is a good direction.

It does not prove the system is solved, but it changes the state of the
experiment:

```text
Before v10:
the hard strip prompt could fail to assemble the full proof package

After v10:
the full proof package exists in the selected set, but ranking still needs work
```

That means the next serious milestone should be:

```text
answerability/reranking over the selected packages
```

not more blind expansion.

### v11: LLM Role Hypotheses During Proposition Generation

The next proposal was to move role detection closer to proposition generation.
Instead of asking deterministic completion code to infer all roles afterward, the
LLM now emits role hypotheses with each proposition.

Previous proposition shape:

```text
source element
-> proposition text
-> source element id
```

New proposition shape:

```text
source element
-> proposition text
-> role hypotheses
-> source element id
```

Example role hypothesis:

```json
{
  "role": "definition",
  "target": "Sy",
  "value": "the list S sorted by increasing y-coordinate",
  "confidence": 0.9,
  "reason": "The source states that Sy denotes this list."
}
```

The schema supports generic roles:

```text
definition
claim
assumption
condition
procedure_step
proof_setup
proof_reason
proof_conclusion
contradiction
quantity_bound
example
visual_support
table_support
formula_support
contrast_exception
other
```

The parser remains backward compatible. Old proposition arrays of strings still
work. New proposition objects carry role hypotheses. The completion pass now uses
these role hypotheses as extra evidence when choosing attachments.

#### v11 Run

Run:

```text
chunk_runs/query_proposition_assembly_20260523_082508
```

Result:

```text
Right package first: 11/12
Right package in top three: 11/12
Right package somewhere in selected five: 12/12
Remaining ranking issue: closest-strip-nearby
```

So v11 did **not** improve the headline numbers over v10.

What it did improve:

```text
completion decisions are more inspectable
the model can identify roles that pattern rules would miss
the strip proof package still appears in the selected set
role labels give us a cleaner future index for completion/reranking
```

What it exposed:

```text
the LLM overuses definition
some targets are too generic, such as "membership test time"
role labels can increase over-attachment when not validated tightly
completion needs role validation/gating before roles should carry much weight
```

The useful lesson is:

```text
LLM role hypotheses are a promising input,
but they should not be trusted directly.
```

The better next shape is:

```text
LLM proposes roles
deterministic code validates roles
validated roles feed completion and reranking
```

Validation should check:

```text
target appears in the source/proposition
target is specific enough, not generic glue
role type matches local structure/metadata
role target overlaps missing package needs
role appears in the same section/proof neighborhood
definition targets are reused later
support roles map to actual support metadata
```

### v12: Role Span Attachment and Stronger Tagging Contract

The next weak link was not ranking. It was that role completion still attached
context too much like isolated pieces.

The design issue:

```text
good query decomposition + good proposition roles
-> we know what explanation jobs need filling
-> but completion still has to decide which source elements fill those jobs
```

The important distinction is:

```text
role tagging says what an element/proposition can do
attachment decides whether that role is needed in this package
```

The implementation now makes two changes.

First, the proposition prompt gives the LLM role definitions instead of only a
flat role-name list. This is meant to reduce the "everything is a definition"
failure. The roles are described by their function in an explanation:

```text
definition = introduces meaning, identity, scope, or notation
proof_setup = introduces objects, cases, variables, or constraints needed before reasoning
proof_reason = explains why a claim follows
proof_conclusion = states the result or final consequence
quantity_bound = states a numeric/count/distance/comparison bound
visual/table/formula support = evidence carried by non-prose structure
```

The role vocabulary is still controlled, with `other` available only when none
of the known roles fit. That keeps downstream code stable while still leaving a
small escape hatch for document-specific structures.

Second, completion no longer treats every candidate element independently. It
now:

```text
scores candidate elements
collapses consecutive compatible candidates into role spans
lets non-consecutive candidates compete by missing role/term key
attaches the best span/candidate only when it fills an unfilled need
```

This encodes the current thesis:

```text
consecutive role-compatible elements probably belong together
distant candidates for the same role should compete
distant candidates should both attach only when they fill different missing jobs
```

During this work, a concrete bug surfaced: text like `Z are close` was being
treated as if it defined `Z`. The definition detector was tightened so generic
`is/are` uses do not falsely satisfy a missing definition.

Focused checks added:

```text
consecutive definition/bound candidates attach as a role span
distant competing definitions do not both attach
role-hypothesis completion still attaches a needed definition
```

This does not solve ranking. It makes the completion layer cleaner before we
ask a ranker to choose among packages.

#### v12 Run

Run:

```text
chunk_runs/query_proposition_assembly_20260523_154846
```

The prompt suite still produced the same retrieval-level shape:

```text
12 prompts tested
11 prompts had the right package first
11 prompts had the right package in the top three
1 prompt still had the right package selected but ranked too low
```

The remaining hard prompt is still:

```text
Why can only nearby points in the strip be closest?
```

The useful lesson is not that v12 "improved the score." It did not change the
headline result. The useful lesson is that role-span completion is now visible
and testable.

Good:

```text
consecutive role-compatible elements can now attach together
distant same-role candidates compete instead of blindly accumulating
generic short words are no longer treated as definition-worthy just because they are short
the hard strip proof package still appears in the selected set
```

Still weak:

```text
role spans can still over-attach when LLM roles are broad
some package cores are still not the cleanest anchor
completion can pull Q/R setup into strip-proof packages when the role signals overlap
visual packages can still be large because image/table descriptions dominate embedding similarity
```

So v12 is a cleanup step, not a ranking step. It supports the next move:

```text
rank selected packages by answerability/completeness/noise,
not only by embedding similarity and cluster score.
```

### v13: Role Labels as Hints, Expansion as Judge

The next correction was conceptual:

```text
role labels should propose attachments
the expansion/completion mechanism should judge attachments
```

The earlier role-span completion had drifted too close to:

```text
role-compatible consecutive elements -> attach
```

That is too strong. Role labels are not law. They are hints. The package builder
should still ask whether the proposed span is compact, relevant, readable, and
worth the tokens.

The first implementation tried to run role-completion spans through the full
measured span-expansion machinery. That was architecturally appealing but too
expensive in practice. Even cached proposition runs became slow because every
candidate span caused extra measurement work.

The implementation was then reduced to a cheaper expansion gate:

```text
single element candidates behave like normal completion
multi-element role spans pass through a lightweight expansion-quality gate
enumerated/list-like spans are kept intact
non-list spans must show role-key coverage, prompt overlap, and lexical cohesion
```

This preserves the intended direction:

```text
role labels propose
expansion gate accepts/rejects
```

without running an expensive embedding/window search for every completion
candidate.

#### v13 Runs

Cached proposition assembly run:

```text
chunk_runs/query_proposition_assembly_cached_20260523_171639
```

This reused the propositions from the previous completed GPT-5 nano run and
tested only the assembly/package logic.

Result:

```text
12 prompts tested
11 prompts had the right package first
11 prompts had the right package in the top three
1 prompt still had the right package selected but ranked too low
```

Fresh GPT-5 nano run:

```text
chunk_runs/query_proposition_assembly_20260523_172042
```

Result:

```text
12 prompts tested
10 prompts had the right package first
10 prompts had the right package in the top three
2 prompts missed the right package in the top three
```

The fresh run regressed on:

```text
closest-q-r
closest-strip-nearby
```

The important interpretation:

```text
the attachment rewire is not enough by itself
fresh LLM role labels still vary enough to disturb completion/ranking
role spans can still over-attach when broad labels like assumption/claim/proof_reason overlap with nearby setup
```

So v13 validates the architecture correction but not the exact mechanism as a
final default. The next weak link is no longer "make role spans attach." It is:

```text
role hypotheses need stronger grounding/gating before they are allowed to affect ranking-sensitive completion
```

That means the earlier role-validation concern cannot be fully postponed. At
minimum, roles used for completion need to be checked for:

```text
target appears in source/proposition
target is specific enough
role target overlaps the package's missing need
generic roles like claim/assumption do not attach unless they also carry concrete missing terms
proof roles are not allowed to pull broad setup into unrelated title/core packages
```

### v14: Query Planner Sub-Needs and Multi-Anchor Packages

The next issue was the case-specific bridge boost.

The old experimental bridge had a closest-pair-specific shortcut:

```text
if prompt mentions nearby/strip
boost Sy / 15 positions / rows / boxes
```

That was useful as a hypothesis test, but it is not a general Contextus
mechanism. The system should not know those terms in code. It should discover
them from the document map and query plan.

The first step was to disable that hardcoded boost. The generic planner still
found the broad strip/band setup, but the package stopped too early:

```text
found: line L, band/strip, Z, partition into boxes
missed or under-ranked: Sy, 15 positions, row separation, 3ω/2 contradiction
```

So the problem was not only expansion. It was that the planner was being used
as a boost, not as a package recipe.

v14 changes the planner contract:

```text
query + document map
-> interpreted need
-> source terms/search forms
-> sub_needs
```

Each `sub_need` contains:

```text
need
search_terms
expected_roles
```

Example shape:

```text
sub_need: define/locate the band near line L
sub_need: explain why points must lie in the band
sub_need: explain the Sy / 15-position / box-row proof
```

The assembler now retrieves anchors for each sub-need and can build a package
from multiple anchors instead of relying on a single core plus accidental
completion.

Implementation notes:

```text
planner schema includes sub_needs
sub-needs retrieve candidate proposition anchors using document-derived terms
role hints can boost sub-need anchors
combined sub-need anchor groups are passed into ordered package assembly
the package core is chosen from the most mechanism-specific anchor, not merely the earliest document element
```

Run:

```text
chunk_runs/query_proposition_assembly_20260524_051021
```

Hardcoded nearby/strip bridge:

```text
disabled
```

Result:

```text
12 prompts tested
10 prompts had the right package first
10 prompts had the right package in the top three
2 prompts missed the crude expected-term check in top three
```

The important package-quality result:

```text
closest-strip-nearby now has a good multi-anchor proof package in the selected set without the hardcoded bridge.
```

In that run, the best-looking strip package is Package 5. It contains:

```text
Q/R recursive setup
ω definition
q/r cross-pair assumption
line L distance formulas
Z definition
box partition
row of Z
row separation
distance at least 3ω/2
```

This is exactly the kind of multi-anchor explanation chain the design wanted.

The remaining issue is ranking:

```text
the good proof package exists
but broad setup/title packages rank above it
```

So v14 partially succeeds:

```text
hardcoded bridge no longer needed to create the right package
multi-anchor construction works
ranking/answerability still cannot reliably choose the best package
```

It also exposes a new weak link:

```text
the planner can over-decompose and include broad/runtime/background sub-needs
```

The prompt now tells the planner not to add broad runtime or background
sub-needs unless the user asks for them, but this will probably need further
validation after ranking work.

## Current Decision

We should not discard the query-time assembler. It is a useful scaffold.

The current strongest path is:

```text
prompt
-> generate/source-backed propositions
-> select likely evidence cores
-> gather non-contiguous proposition clusters
-> map everything back to source elements
-> attach structural/visual support conservatively
-> evaluate whether the assembled package can actually answer the prompt
```

But the next serious improvement should not be more threshold tuning. The
latest failures show that we need better ranking and answerability checks over
already-selected packages.

After v8, the important refinement is:

```text
The default expansion path should remain simple v7 order-aware spans.
Candidate span competition is useful as an experiment. The v8.1 version is much
healthier than v8, but it still should not become the main mechanism until it
beats v7 or solves a failure v7 cannot solve.
```

The likely next step is:

```text
Pin proposition generation for repeatable comparisons.
Then add a package reranker/answerability check.
Then improve typed visual support selection.
Then use the document-language map as a small evidence signal, not the driver.
```

In plain English:

```text
Use propositions to find what the answer is about.
Use source elements to prove it.
Use closure rules to make it complete.
Use answerability scoring to reject packages that only look similar.
Use language units to help with vocabulary mismatch, but only when they are
specific enough to be trusted.
```

### v15: Completion Need Ledger

The next issue was completion over-attachment.

The problem was not that completion could not find useful surrounding material.
It could. The problem was that once completion found one useful role, it could
keep adding nearby material that looked like the same role:

```text
needed: definition(Sy)

bad behavior:
attach definition(Sy)
attach more definition/setup-looking text
attach more broad proof/setup text
```

The fix is a small need ledger.

The ledger tracks:

```text
needed role keys
filled role keys
open role keys
```

Examples:

```text
definition:z
term:omega
proof:setup
proof:reason
proof:conclusion
support
procedure
example
answer:nearby
```

The important behavior is:

```text
candidate roles suggest what an element might provide
the ledger decides whether that thing is still needed
the existing embedding/structure gates decide whether the attachment is safe
```

So completion now follows this shape:

```text
build ledger from selected package
score completion candidates as before
reject candidates that fill no open need
attach a candidate only if it fills an open need
mark those needs as filled
skip repeated same-role/same-target candidates afterward
```

The first implementation was too permissive. It allowed missing prompt words to
act like ordinary missing terms. That made the crude retrieval numbers look
better, but by eye it invited broad procedure/proof material into packages.

That was corrected by separating ordinary terms from answer terms:

```text
term:z
definition:z
answer:nearby
```

An `answer:*` key is only produced by conclusion-like text, not by any candidate
that merely overlaps the prompt. This avoids treating broad prompt overlap as a
license to attach.

The second important correction was inside role spans. A multi-element role span
can pass the overall quality gate while still containing repeated role material.
So v15 now trims a proposed role span element-by-element against the ledger:

```text
span candidate:
  element A fills definition:z
  element B also only fills definition:z
  element C fills proof:reason

after ledger trim:
  keep A
  reject B
  keep C
```

This is still not a perfect completion system, but it is a better architecture.
The role labels are no longer treated as law. They are suggestions. The ledger
asks whether the suggestion is necessary.

Implementation touched:

```text
contextus/builder/query_assembly.py
tests/test_builder_query_assembly.py
```

Focused verification:

```text
.venv/Scripts/python.exe -m pytest tests/test_builder_query_assembly.py -q
21 passed

.venv/Scripts/python.exe -m py_compile contextus/builder/query_assembly.py evaluate_query_proposition_assembly.py
passed
```

Prompt-suite run:

```text
chunk_runs/query_proposition_assembly_20260524_075522
```

Crude expected-term smoke test:

```text
12 prompts total
11 prompts had a matching package at rank 1
11 prompts had a matching package in the top 3
1 prompt missed the top 3 by the hardcoded evaluator
```

Important caveat:

```text
the hardcoded evaluator is still not the judge of package quality
```

Qualitative lesson:

```text
the ledger reduced same-need repetition inside completion spans
but completion can still attach broad proof/setup material when generated roles
are broad and the selected core is in a proof-heavy region
```

For `closest-strip-nearby`, the top package in this run is a compact
cross-strip/band explanation:

```text
omega definition
q/r cross-pair assumption
distance-to-line formula
q and r lie within omega of L
therefore search can be restricted to the band
S is the set of points within omega of L
```

That is a coherent answer to the broad wording of the prompt. It is not the
full Sy/boxes/rows/15-position mechanism. Whether this is sufficient depends on
the intended question:

```text
"why only strip/band points matter?"
  -> current package is good

"why only a bounded number of nearby strip points must be compared?"
  -> package still needs the Sy/boxes/rows/15-position proof chain
```

This distinction matters. It shows that completion is now less blindly greedy,
but package selection still needs better intent/ranking work before we can trust
which explanation depth is chosen.

### v16: Completion Diagnostics

The next issue was not package behavior. It was visibility.

Before this pass, completion could tell us what it attached, but it could not
tell us enough about what it rejected. That made completion failures and ranking
failures blur together:

```text
bad package
-> did completion fail to find the missing context?
-> did completion find it but reject it?
-> did completion attach it but ranking bury the package?
-> did the hardcoded evaluator misunderstand the package?
```

v16 adds diagnostics without changing the assembly decision logic.

Each assembled package now carries:

```text
completion_diagnostics
```

The trace records:

```text
completion enabled / disabled
whether completion was initially needed
per-round selected element ids
needed role keys
filled role keys
open role keys
every candidate considered
candidate role keys
candidate useful open keys
attached / rejected action
explicit rejection reason
token cost
text preview
original span indices
trimmed span indices
```

The main rejection reasons now visible are:

```text
already_selected
below_score_threshold
fills_no_open_need
too_many_attachments
token_budget_exceeded
failed_embedding_or_span_gate
trimmed_to_no_useful_elements
*_after_trim
```

The prompt-suite runner also writes a separate human-readable file:

```text
completion_diagnostics.md
```

So the run artifacts now include:

```text
query_proposition_assembly.json
query_proposition_assembly.md
completion_diagnostics.md
```

This is intentionally diagnostic-only. The trace does not affect ranking,
completion, or package construction.

Implementation touched:

```text
contextus/builder/query_assembly.py
evaluate_query_proposition_assembly.py
tests/test_builder_query_assembly.py
docs/query-time-evidence-package-thesis.md
```

Focused verification:

```text
.venv/Scripts/python.exe -m pytest tests/test_builder_query_assembly.py -q
21 passed

.venv/Scripts/python.exe -m py_compile contextus/builder/query_assembly.py evaluate_query_proposition_assembly.py
passed
```

Full verification:

```text
.venv/Scripts/python.exe -m pytest tests -q
299 passed, 14 skipped
```

Prompt-suite run:

```text
chunk_runs/query_proposition_assembly_20260524_121020
```

Smoke-test result:

```text
12 prompts total
10 prompts had a matching package at rank 1
10 prompts had a matching package in the top 3
2 hardcoded-evaluator misses:
  closest-q-r
  closest-strip-nearby
```

Important interpretation:

```text
v16 should not be judged by hit rate
```

The implementation was diagnostic-only. The different smoke-test numbers are
most likely from fresh proposition/planner variance, not from diagnostics.

The useful result is that we can now inspect why completion did what it did. For
example, the diagnostics show cases where completion rejects long proof chains
because they fill no currently open need, and cases where it leaves open
`answer:*` or `definition:*` keys after attachments.

That gives us a much cleaner base for issue 5:

```text
proposition/role grounding checks
```

because we can now see exactly which roles and candidates are influencing
completion decisions.

### v17: Proposition/Role Grounding Audit

The final pre-ranking issue was proposition/role grounding.

The original worry was:

```text
LLM-generated propositions and roles are upstream-critical.
If a role is wrong, completion and later ranking may trust the wrong signal.
```

But we did not have strong evidence that the proposition prompt was producing
wild hallucinations. So v17 was implemented as **audit only**:

```text
measure and report grounding
do not drop roles
do not lower confidence
do not change completion
do not change ranking
```

Each proposition now carries grounding diagnostics:

```text
source_overlap_ratio
kept_terms
novel_terms
source_symbols
proposition_symbols
role_diagnostics
```

Each role diagnostic records:

```text
role
target
status
severity
target_in_proposition
target_in_source
target_token_overlap
role_symbol_overlap
behavior_match
support_grounded
vague_target
notes
```

The audit uses four cheap evidence layers:

```text
1. exact normalized target phrase match
2. target token overlap
3. symbol/entity overlap across target + value + reason
4. role-behavior evidence
```

The symbol layer is intentionally based on the whole role payload, not only the
role target:

```text
target: "cross-strip pair"
value: "q in Q and r in R with d(q,r) < omega"

role symbols:
q, Q, r, R, d(q,r), omega
```

This prevents the audit from marking abstract targets as ungrounded when their
value/reason carries the actual source symbols.

The prompt-suite runner now also writes:

```text
role_grounding_diagnostics.md
```

Latest run:

```text
chunk_runs/query_proposition_assembly_20260524_151159
```

Grounding audit counts:

```text
support_mismatch: 0
ungrounded: 9
vague_target: 3
weak: 75
grounded: 188
```

Smoke-test result from the same run:

```text
12 prompts total
11 prompts had a matching package at rank 1
11 prompts had a matching package in the top 3
1 hardcoded-evaluator miss:
  closest-strip-nearby
```

Important interpretation:

```text
the audit did not reveal a broad hallucination problem
```

The suspicious cases are mostly:

```text
titles/headings being labeled as definitions
generic section text like "Proof"
weak or vague targets
proposition/source overlap misses caused by symbolic or extraction encoding
small low-value propositions such as separators, headers, or copyright-like text
```

There were no support-role mismatches in the latest run.

So issue 5 should not become heavy enforcement yet. The better next action is:

```text
keep grounding as diagnostics
use it during ranking/error analysis
only add enforcement later for obvious cases, e.g.
  support role with no support evidence
  definition role with vague target
  proposition with very low source overlap and no symbol/role grounding
```

This confirms the user's concern: the prompt/infrastructure is mostly doing the
right thing. The audit is useful as a receipt and warning system, not as a
replacement for better proposition generation.

## v15 - Deterministic package reranker

The old final package score was still mostly an embedding score:

```text
package_prompt_similarity
+ package_core_similarity
+ core_prompt_similarity
- token penalty
+ small attachment/language/answerability bonuses
```

That was useful as a first pass, but it ranked by "looks close to the prompt"
more than by "is this the best answer package?" This created a predictable
failure mode: a compact or highly similar package could outrank a more complete
package that carried setup, proof reason, support, or conclusion material.

The new ranking v1 is deterministic. It does not use an LLM judge. It keeps the
old score as `legacy_score`, but replaces the final `package.score` with a
feature-based answerability score.

The ranker now scores:

```text
plan coverage
role coverage
completion closure
embedding relevance
source-order coherence
role/proposition grounding
support fit
noise/token pressure
```

The score is intentionally universal. It does not contain closest-pair-specific
boosts such as "nearby/strip -> Sy/15/rows/boxes." Instead it asks generic
questions:

```text
Does this package cover the retrieval plan's sub-needs?
Does it contain the expected answer roles?
Are completion needs still open?
Are the included proposition roles grounded?
Are selected elements coherent in reading order?
Is support present when support is needed?
Is the package too noisy or token-expensive?
Is it still semantically relevant to the prompt?
```

Implementation:

```text
contextus/builder/query_assembly.py

PackageRankingDiagnostics
_rank_query_packages()
_package_ranking_diagnostics()
_package_plan_coverage_score()
_package_role_coverage_score()
_package_completion_closure_score()
_package_grounding_score()
_package_support_score()
_package_source_coherence_score()
_package_noise_score()
```

The prompt-suite runner now writes:

```text
ranking_diagnostics.md
```

This report explains every top package with:

```text
final score
legacy score
plan coverage
role coverage
completion closure
relevance
grounding
source coherence
support
noise
positive reasons
concerns
covered sub-needs
missing sub-needs
open completion keys
```

Because the full LLM-backed prompt-suite regeneration timed out during this
iteration, v15 was validated as a downstream rerank over the latest complete
package run:

```text
source run:
chunk_runs/query_proposition_assembly_20260524_151159

reranked run:
chunk_runs/query_proposition_reranked_20260524_170218
```

Rerank smoke result:

```text
12 prompts total
11 prompts had a matching package at rank 1
11 prompts had a matching package in the top 3
1 hardcoded-evaluator miss:
  closest-strip-nearby
```

The important result is not that the crude metric changed dramatically. It did
not. The important result is that the ranking reasons are now inspectable and
mostly aligned with what we actually care about. Packages move up when they
cover roles and completion needs, not only when their embedding is close to the
prompt.

Observed remaining weaknesses:

```text
1. The ranker inherits planner quality.
   If the retrieval plan invents too many broad sub-needs, plan coverage becomes
   noisy.

2. Completion-open keys can still be too literal.
   Keys like answer:does or answer:work are not always meaningful answer gaps.

3. Source coherence is useful but blunt.
   It correctly warns when packages jump around, but some valid packages are
   intentionally multi-span.

4. Support scoring can be over-cautious.
   If the planner expects support but the answer is textual, support_score may
   look worse than the package deserves.

5. The hardcoded evaluator is still only a smoke test.
   It can mark a good package as bad if the expected terms do not match its
   wording.
```

This makes ranking work much less blind. The next ranking work should be tuning
feature weights and pruning noisy completion keys, not adding an LLM judge.

Verification:

```text
.venv/Scripts/python.exe -m py_compile contextus/builder/query_assembly.py evaluate_query_proposition_assembly.py
.venv/Scripts/python.exe -m pytest tests/test_builder_query_assembly.py -q
.venv/Scripts/python.exe -m pytest tests -q

Focused tests:
23 passed

Full tests:
301 passed, 14 skipped
```

## v16 - Profile-alignment reranker

The first deterministic reranker was still too willing to reward generic
richness. A package could win because it had many roles, completion attachments,
or proof material, even when the user's query wanted a more direct evidence
form.

The new ranking pass keeps the deterministic design but changes the center of
gravity:

```text
query demand profile
↔ package evidence profile
↔ directness of the evidence to the core/anchor
↔ assembly confidence from the expansion decisions
```

This is intentionally not a domain-specific patch. There are no boosts like:

```text
if prompt is about sickle-cell maps, boost map X
if prompt is about closest pair, boost Sy/15/boxes
```

Instead, the ranker asks universal questions:

```text
What evidence roles does the query demand?
What evidence roles does this package contain?
Are those roles near the core/cluster/support anchors, or only incidental
completion attachments?
Did expansion naturally assemble this package from strong spans and anchors?
Does the package cover several specific search terms, or only one broad term?
```

Implementation changes:

```text
PackageRankingDiagnostics.profile_alignment_score
PackageRankingDiagnostics.directness_score
PackageRankingDiagnostics.assembly_confidence_score
PackageRankingDiagnostics.expected_roles

_expected_role_profile()
_package_role_profiles()
_profile_alignment_score()
_package_directness_score()
_package_assembly_confidence_score()
_weighted_term_coverage()
```

The plan coverage score was also tightened. Previously a sub-need could look
covered if the package matched one broad search term. Now term coverage combines:

```text
best matching term
average of the best few terms
fraction of terms meaningfully covered
```

This makes a package that contains only "culture" and "biology" less likely to
beat a table that actually contains both comparison columns and row evidence.

The assembly mechanism is now part of ranking. It contributes evidence such as:

```text
core/cluster/support ratio
completion attachment ratio
accepted ordered spans
cluster anchors kept
drift/rollback events
token-budget stops
```

This matters because two packages can contain similar evidence, but one was
assembled naturally around the right anchor while the other only found the answer
through scattered completion patches.

Reranked run:

```text
chunk_runs/query_proposition_reranked_20260524_173820
```

The old hardcoded smoke evaluator is still not trusted as quality truth, but it
remained unchanged:

```text
12 prompts total
11 prompts had a matching package at rank 1
11 prompts had a matching package in the top 3
```

Manual inspection of the previously questionable cases:

```text
closest-definition:
  fixed. Rank 1 is now the actual problem definition package.

closest-procedure:
  improved. Rank 1 is now the broad recursive algorithm package, not the
  strip/15-neighbor subprocedure.

inheritance-sickle-map:
  improved. Rank 1 is now the malaria/sickle-cell map package, not the
  unrelated cell-diagram-core package.

inheritance-evolution-table:
  fixed. Rank 1 is now the biological vs cultural evolution comparison table.
```

Remaining caveat:

```text
visual packages can still tie closely when several nearby figures/headings share
similar roles and terms
```

That is not an immediate failure, but it means future ranking work should
separate "right package" from "best core inside a good package." The answer may
be present and readable while the core choice is still not ideal.

Verification:

```text
.venv/Scripts/python.exe -m py_compile contextus/builder/query_assembly.py evaluate_query_proposition_assembly.py
.venv/Scripts/python.exe -m pytest tests/test_builder_query_assembly.py -q
.venv/Scripts/python.exe -m pytest tests -q

Focused tests:
23 passed

Full tests:
301 passed, 14 skipped
```
