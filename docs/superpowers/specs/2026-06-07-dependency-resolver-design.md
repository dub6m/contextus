# Dependency Resolver Design

## Goal

Build a query-time dependency resolver that lets the document drive expansion.
The resolver starts from a query-selected core, identifies what parts of that
core need support, finds supporting document facts, and recursively expands until
the package is resolved, blocked, cyclic, or out of budget.

The resolver must not let scores or an LLM planner decide that a dependency is
resolved. Scores may order candidate search. Closure must come from explicit
support records.

## Existing Direction

The current query-time system already has useful evidence pieces:

- evidence handles and source attachments
- language units and source traversal vocabulary
- proposition roles and completion ledgers
- relation geometry and consensus-neighbor signals
- package ranking and source coherence diagnostics

These pieces should be reused when helpful, but the resolver should not depend
on the LLM planner as the authority for which cores are needed.

## Pipeline

1. Parse document text into syntax structures.
2. Extract document-native terms and symbols.
3. Turn document text into structured facts.
4. Pick the query-relevant core using the existing query-time machinery.
5. Turn the selected core into the same structured fact format.
6. Find missing, ambiguous, or filled-but-unsupported parts of the core facts.
7. Search document facts for candidate support.
8. Add accepted support facts to the package.
9. Recursively inspect accepted support facts for their own unresolved parts.
10. Stop a branch when it succeeds, fails, cycles, or hits budget.
11. Keep useful cycles as clusters, but do not recurse through them forever.
12. Return a normal evidence package plus a trace of the actions used to build it.

## Main Data Objects

### Syntax Index

The syntax index stores parser output for each element or proposition:

- sentence spans
- token spans
- noun chunks
- heads and modifiers
- subject/object relations
- predicate frames
- quantity and comparison attachments

The first implementation should use spaCy because it is fast, local, and simple
to integrate. Stanza can be added later for comparison if parser quality becomes
a blocker.

### Document Term Index

The term index stores document-native terms, not generic named entities.

Term mentions come from:

- syntax noun chunks
- head-plus-modifier spans
- existing language units
- symbols and formulas
- headings, captions, and list labels
- quantity and comparison spans

Each mention keeps exact source provenance:

- element id
- proposition id when available
- sentence index
- character offsets
- source signal
- head term
- modifiers

Normalization is conservative. It may normalize articles, punctuation,
whitespace, simple plural forms, and symbol spelling. It must not merge unsafe
pairs such as `line` and `median line` or `point` and `candidate point`.

### Fact Frame

A fact frame is a structured statement extracted from document text.

Example:

```text
source text:
The strip contains at most seven candidate points.

frames:
contains(strip, candidate points)
bound(candidate points, <=, seven)
```

Recommended schema:

```text
FactFrame
  id
  source
  predicate
  slots
  constraints
  links
  extraction_status
```

Each slot should track its own state:

```text
FrameSlot
  name
  value
  term_id
  fill_state: filled | missing | ambiguous
  grounding_state: unneeded | self_asserted | grounded | unsupported
  source_span
  evidence_refs
```

This separation matters. A slot can be filled because extraction found a value,
but still unsupported because no acceptable document evidence grounds that value.

Predicates should stay open and document-derived. The resolver may later attach
optional families for convenience, but it must not require a complete predicate
taxonomy.

### Need

A need is a fact-frame part that requires support.

Needs are created from:

- missing frame slots
- ambiguous frame slots
- filled slots whose `grounding_state` is `unsupported`
- unsupported constraints
- unsupported links between facts

Recommended schema:

```text
Need
  id
  frame_id
  target_path
  value
  reason: missing | ambiguous | filled_but_unsupported
  status: open | resolved | failed
```

The need is not primarily a fixed label such as `term_anchor` or
`quantity_bound_support`. Optional labels can exist for debugging, but the real
object is the unresolved frame part.

### Candidate Support

A candidate support record explains why one or more document facts may support a
need.

```text
CandidateSupport
  need_id
  candidate_frame_ids
  matched_parts
  rejected_parts
  status: candidate | accepted | rejected
  reason
```

Candidate search can use scores. Candidate acceptance must explain which need
parts were covered.

### Resolution Trace

The resolver should keep a trace of actions. This trace is the proof trail used
to audit the final package.

```text
ResolutionTraceStep
  action
  need_id
  frame_ids
  reason
```

Useful actions:

- `need_created`
- `candidate_found`
- `candidate_rejected`
- `need_resolved`
- `new_need_created`
- `cycle_detected`
- `branch_stopped`

## Candidate Search

Candidate search starts from an open need and finds document facts that may
support it.

Search signals, from strongest to weakest:

1. Same term id.
2. Same normalized term head and compatible modifiers.
3. Same or compatible frame structure.
4. Same source section, heading path, list run, page, or nearby element.
5. Explicit document links such as heading, support, caption, formula, table, or
   list sibling attachments.
6. Explicit discourse edges, when available.
7. Predicate or text embedding similarity.
8. NLI entailment or contradiction probe on narrowed candidates.

Fuzzy tools may promote candidates, but they must not close a need by
themselves.

## Branch Ordering

A branch is one possible route through dependencies. Branch scoring only decides
which route to try first.

Good branch signals:

- candidate directly fills an open need
- exact term id match
- matching frame slots
- same source section or explicit document link
- fills multiple open needs
- introduces few new needs
- is not just the core repeating itself

Bad branch signals:

- embedding-only match
- far source jump without structural link
- many new unresolved needs
- contradiction signal
- unanchored cycle

This reuses the spirit of the old graph traversal work: queue, visited tracking,
backtracking, budget, and best incomplete result. It changes the scoring target
from neighbor relevance to need support.

## Closure Rules

Closure rules decide when a need is resolved.

General rule:

```text
a need closes only when accepted support covers the exact missing, ambiguous, or
unsupported frame part that created the need.
```

Term slot closure:

- candidate evidence points to the same term id or a safe alias
- candidate evidence introduces, defines, or strongly anchors the term
- the current core itself may close the need only if it contains an introduction
  pattern for the term

Relation closure:

- candidate evidence connects compatible argument terms
- predicate match is exact or structurally justified
- embedding similarity alone is not enough

Constraint closure:

- candidate evidence has the same target term
- candidate evidence supplies a compatible operator and value
- normalized concrete values may close abstract values, such as `<= seven`
  closing `constant-bounded`

Link closure:

- candidate evidence shows why one frame supports another
- explicit discourse edges, source paths, formulas, and NLI can help identify
  candidates
- final closure still requires a traceable source-backed link
- complex link closure is not part of the first slice unless the link is
  directly explicit in the source structure

Cycle handling:

- cycles stop further recursion
- cycles are recorded as clusters
- a cycle can help close a need only if it has an external anchor

## Output

The resolver should return the normal evidence package plus audit data:

```text
ResolvedPackage
  core
  selected_elements
  selected_frames
  resolved_needs
  unresolved_needs
  cycles
  resolution_trace
```

The answer step should receive the selected package and the trace. The trace
shows how dependencies were resolved and which parts remain unresolved.

## Non-Goals For The First Implementation

- full coreference resolution
- full discourse parsing
- LLM-based proof judgment
- complete predicate taxonomy
- universal obligation taxonomy
- exhaustive search across the whole document without indexes or budgets

## First Implementation Slice

The first slice should be narrow:

1. Add data classes for frames, slots, needs, candidate support, and trace steps.
2. Build a small syntax-to-frame projection for simple text patterns:
   subject-verb-object, copular definition, quantity bound, comparison, formula
   equality.
3. Build a simple term index from existing language units plus parser noun
   chunks when available.
4. Create needs from missing, ambiguous, and filled-but-unsupported frame slots.
5. Implement candidate search over frames using term id, frame shape, and source
   proximity.
6. Implement strict closure for term slots and simple quantity constraints.
7. Emit a resolved package trace for tests and inspection.

The first slice should run in parallel to the current query-time path. It should
not replace planner, source traversal, or answer bundle logic until the new
trace shows better package quality.
