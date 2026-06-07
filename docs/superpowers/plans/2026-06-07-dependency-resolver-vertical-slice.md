# Dependency Resolver Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working dependency-resolver slice: structured facts, needs, candidate support, simple closure, and trace output.

**Architecture:** Add one focused builder module that runs in parallel to the current query-time assembler. The first slice uses deterministic indexing and strict closure for simple term and quantity support. It does not replace planner, traversal, ranking, or answer bundle code.

**Correction after Task 2 review:** Do not implement linguistic meaning extraction with finite word lists. No stop-word lists, verb lists, predicate synonym lists, discourse-marker lists, or morphology allow/deny lists should be added to resolver core unless the user explicitly approves that exact bounded use. Term indexing consumes extractor-provided `TermCandidate` spans. Phrase spotting and frame extraction must come from syntax/language-unit/frame candidates, not raw-text n-gram guessing.

**Tech Stack:** Python dataclasses, existing `QueryEvidenceProposition` records, pytest.

---

## File Structure

- Create: `contextus/builder/dependency_resolver.py`
  - Owns resolver data models, term indexing, frame data contracts, need creation, candidate search, closure, and trace output for the first slice.
- Modify: `contextus/builder/__init__.py`
  - Exposes the new public classes for tests and future query-time integration.
- Create: `tests/test_builder_dependency_resolver.py`
  - Covers normalization, term indexing, frame contracts, need creation, quantity closure, cycle recording, and package trace behavior.

This first slice stays in one new module because it is experimental and small. Split it only after the data model stabilizes.

---

### Task 1: Add Resolver Data Models

**Files:**
- Create: `contextus/builder/dependency_resolver.py`
- Test: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Write failing data-model tests**

Add this new test file:

```python
from contextus.builder.dependency_resolver import (
    CandidateSupport,
    FactFrame,
    FrameSlot,
    Need,
    ResolutionTraceStep,
    SourceRef,
)


def test_frame_slot_separates_fill_and_grounding_state():
    slot = FrameSlot(
        name="object",
        value="candidate points",
        term_id="term:candidate_points",
        fill_state="filled",
        grounding_state="unsupported",
        source_text="candidate points",
        char_start=12,
        char_end=28,
    )

    assert slot.fill_state == "filled"
    assert slot.grounding_state == "unsupported"
    assert slot.requires_support is True


def test_need_points_to_exact_frame_part():
    need = Need(
        need_id="need:frame:1:slots.object",
        frame_id="frame:1",
        target_path="slots.object",
        value="candidate points",
        reason="filled_but_unsupported",
    )

    assert need.status == "open"
    assert need.target_path == "slots.object"


def test_candidate_support_records_matched_and_rejected_parts():
    support = CandidateSupport(
        need_id="need:1",
        candidate_frame_ids=["frame:source:1"],
        matched_parts=["target term"],
        rejected_parts=["operator mismatch"],
        status="candidate",
        reason="same target term but incompatible operator",
    )

    assert support.status == "candidate"
    assert support.matched_parts == ["target term"]
    assert support.rejected_parts == ["operator mismatch"]


def test_fact_frame_keeps_source_reference():
    frame = FactFrame(
        frame_id="frame:e1:0",
        source=SourceRef(element_id="e1", text="The strip contains candidate points."),
        predicate="contains",
        slots={
            "subject": FrameSlot(name="subject", value="strip", term_id="term:strip"),
            "object": FrameSlot(name="object", value="candidate points", term_id="term:candidate_points"),
        },
    )

    assert frame.source.element_id == "e1"
    assert frame.slots["subject"].value == "strip"


def test_trace_step_records_action_reason_and_frames():
    step = ResolutionTraceStep(
        action="need_resolved",
        need_id="need:1",
        frame_ids=["frame:e2:0"],
        reason="candidate frame covers the unsupported quantity",
    )

    assert step.action == "need_resolved"
    assert step.frame_ids == ["frame:e2:0"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: import failure because `contextus.builder.dependency_resolver` does not exist.

- [ ] **Step 3: Add the minimal data model implementation**

Create `contextus/builder/dependency_resolver.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceRef:
    element_id: str
    proposition_id: str = ""
    sentence_index: int = 0
    char_start: int = 0
    char_end: int = 0
    text: str = ""


@dataclass(frozen=True)
class FrameSlot:
    name: str
    value: str = ""
    term_id: str = ""
    fill_state: str = "filled"
    grounding_state: str = "unneeded"
    source_text: str = ""
    char_start: int = 0
    char_end: int = 0
    evidence_refs: tuple[str, ...] = ()

    @property
    def requires_support(self) -> bool:
        return self.fill_state in {"missing", "ambiguous"} or self.grounding_state == "unsupported"


@dataclass(frozen=True)
class FrameConstraint:
    target_slot: str
    operator: str
    value: str
    normalized_value: str = ""
    source_text: str = ""
    char_start: int = 0
    char_end: int = 0
    grounding_state: str = "unsupported"
    evidence_refs: tuple[str, ...] = ()

    @property
    def requires_support(self) -> bool:
        return self.grounding_state == "unsupported"


@dataclass(frozen=True)
class FactFrame:
    frame_id: str
    source: SourceRef
    predicate: str
    slots: dict[str, FrameSlot] = field(default_factory=dict)
    constraints: tuple[FrameConstraint, ...] = ()
    links: tuple[str, ...] = ()
    extraction_status: str = "asserted"


@dataclass(frozen=True)
class Need:
    need_id: str
    frame_id: str
    target_path: str
    value: str
    reason: str
    status: str = "open"


@dataclass(frozen=True)
class CandidateSupport:
    need_id: str
    candidate_frame_ids: list[str]
    matched_parts: list[str]
    rejected_parts: list[str] = field(default_factory=list)
    status: str = "candidate"
    reason: str = ""


@dataclass(frozen=True)
class ResolutionTraceStep:
    action: str
    need_id: str = ""
    frame_ids: list[str] = field(default_factory=list)
    reason: str = ""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```powershell
git add contextus/builder/dependency_resolver.py tests/test_builder_dependency_resolver.py
git commit -m "Add dependency resolver data models"
```

---

### Task 2: Add Document Term Index

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing term-index tests**

Append these tests:

```python
from contextus.builder.dependency_resolver import DocumentTermIndex, TermCandidate, normalize_term_text


def _term_candidate(element_id: str, source_text: str, term_text: str) -> TermCandidate:
    start = source_text.index(term_text)
    return TermCandidate(
        element_id=element_id,
        text=term_text,
        char_start=start,
        char_end=start + len(term_text),
        source_signal="syntax_noun_chunk",
    )


def test_normalize_term_text_is_conservative():
    assert normalize_term_text(" Strip. ") == "strip"
    assert normalize_term_text("candidate points") == "candidate points"
    assert normalize_term_text("median line") == "median line"
    assert normalize_term_text("line") == "line"
    assert normalize_term_text("Q_x") == "q_x"


def test_document_term_index_keeps_specific_terms_separate():
    text1 = "The median line splits the points."
    text2 = "The line is drawn vertically."
    index = DocumentTermIndex.from_candidates(
        [
            _term_candidate("e1", text1, "median line"),
            _term_candidate("e2", text2, "line"),
        ]
    )

    assert "term:median_line" in index.terms
    assert "term:line" in index.terms
    assert index.terms["term:median_line"].canonical == "median line"
    assert index.terms["term:line"].canonical == "line"


def test_document_term_index_records_mentions_with_source():
    text = "The vertical strip contains candidate points."
    index = DocumentTermIndex.from_candidates([_term_candidate("e1", text, "vertical strip")])

    strip = index.terms["term:vertical_strip"]
    assert strip.canonical == "vertical strip"
    assert strip.mentions[0].element_id == "e1"
    assert strip.mentions[0].source_signal == "syntax_noun_chunk"


def test_document_term_index_rejects_raw_text_extraction():
    with pytest.raises(ValueError, match="TermCandidate"):
        DocumentTermIndex.from_texts([("e1", "The median line splits the points near Q_x.")])

    assert DocumentTermIndex.from_texts([]).terms == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: import failure for `DocumentTermIndex` and `normalize_term_text`.

- [ ] **Step 3: Add term dataclasses and indexing helpers**

Implement the term index around extractor-provided spans:

- `TermCandidate`: `element_id`, exact `text`, `char_start`, `char_end`, `source_signal`, and upstream-provided `head`/`modifiers` when available.
- `TermMention`: normalized text plus exact provenance.
- `DocumentTermIndex.from_candidates(candidates)`: normalizes supplied spans, deduplicates exact mentions, stores `DocumentTerm`s, and fills `mentions_by_element_id`.
- `DocumentTermIndex.from_texts(texts)`: reject non-empty raw text input. Term indexing must go through explicit `TermCandidate` spans.
- `normalize_term_text(text)`: trim edge punctuation, collapse whitespace, lowercase. Do not strip articles or singularize words with hand-written word/suffix lists.
- Term ids must not conflate different normalized terms that slug to the same shape, such as `q_x` and `q x`.

Do not add stop-word lists, verb lists, discourse-marker lists, regex symbol extraction, or morphology allow/deny lists here. Phrase/symbol spotting and head/modifier analysis belong to the syntax/language-unit extractor, which will feed exact candidates into this index.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add contextus/builder/dependency_resolver.py tests/test_builder_dependency_resolver.py
git commit -m "Add dependency resolver term index"
```

---

### Task 3: Add Frame Candidate Projection

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

This task replaces the rejected raw-text extractor. The resolver must not discover predicates, noun phrases, definitions, discourse roles, or quantity statements from proposition text. It accepts explicit candidates from an upstream syntax/language/frame extractor.

- [x] **Step 1: Add failing frame-candidate contract tests**

Cover:

- `SlotCandidate` stores an upstream slot span.
- `ConstraintCandidate` stores an upstream constraint span/operator/value.
- `FrameCandidate` stores an upstream structured frame.
- `FrameCandidateProjector(term_index).project(candidates)` converts candidates into `FactFrame`s, filling term ids from `DocumentTermIndex`.
- No `SimpleFrameExtractor` exists.

- [x] **Step 2: Implement candidate projection**

Add:

- `SlotCandidate`
- `ConstraintCandidate`
- `FrameCandidate`
- `FrameCandidateProjector`

Projection rules:

- Normalize slot text conservatively.
- Look up `term_id` through `DocumentTermIndex.term_id_for_text`.
- Preserve exact source/proposition/character provenance.
- Preserve upstream predicate/operator/value choices as data; do not infer them from raw text.

- [x] **Step 3: Verify**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

---

### Task 4: Create Needs From Unsupported Frame Parts

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [x] **Step 1: Add failing need-creation tests**

Cover:

- Unsupported slots produce `Need`s.
- Missing/ambiguous slots produce `Need`s.
- Unsupported constraints produce `Need`s.
- Grounded slots/constraints produce no `Need`s.

- [x] **Step 2: Implement `NeedBuilder`**

`NeedBuilder.needs_for_frame(frame)` walks the already-structured frame and emits needs from slot/constraint state only. It does not classify obligation kind from text.

- [x] **Step 3: Verify**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

---

### Task 5: Add Candidate Search And Strict Simple Closure

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [x] **Step 1: Add failing closure tests using explicit frames**

Cover:

- A core `constant_bound(candidate points)` constraint is closed by a document frame with the same target term and a fixed upper-bound operator/value.
- A candidate targeting a different term is rejected.
- A candidate with a variable bound, such as upstream `value_kind="variable"`, does not close a `constant_bound` need.
- Trace records created needs, accepted support, and rejected candidates, including rejected candidates considered before a later accepted support.

- [x] **Step 2: Implement `ResolvedPackage` and `DependencyResolver.resolve`**

Resolver rules:

- Build needs from core frames.
- For slot needs, accept a document frame that explicitly mentions the same target term.
- For constraint needs, accept a document constraint only when the target term matches and the structured operator/value covers the required constraint.
- Use schema operators such as `constant_bound`, `<`, `<=`, and `=` as structured values supplied upstream.
- Use upstream `value_kind` for fixed/variable quantity shape. Do not infer fixed constants from the string value in resolver core.
- Do not use text synonyms such as `constant` vs `bounded` to close support.
- Scores/ranking are not proof. This slice closes only by explicit structured matches.

- [x] **Step 3: Verify**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

---

### Task 6: Add Cycle Recording And Public Exports

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `contextus/builder/__init__.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [x] **Step 1: Add failing cycle/export tests**

Cover:

- Cycles are recorded as frame-id paths without infinite recursion.
- `DependencyResolver` is importable from `contextus.builder`.

- [x] **Step 2: Implement cycle recording**

`DependencyResolver.record_cycles(frames)` follows explicit `FactFrame.links`. It records cycles as useful clusters, deduplicates cycles, and does not recurse forever on long entry paths.

- [x] **Step 3: Export public contract classes**

Export:

- `TermCandidate`, `TermMention`, `DocumentTerm`, `DocumentTermIndex`
- `SlotCandidate`, `ConstraintCandidate`, `FrameCandidate`, `FrameCandidateProjector`
- `SourceRef`, `FrameSlot`, `FrameConstraint`, `FactFrame`
- `Need`, `NeedBuilder`, `CandidateSupport`, `ResolvedPackage`, `ResolutionTraceStep`, `DependencyResolver`
- `normalize_term_text`

Do not export `SimpleFrameExtractor`.

- [x] **Step 4: Verify**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

---

### Task 7: Add Query Proposition Adapter

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [x] **Step 1: Add failing adapter tests**

Cover:

- Adapter resolves query propositions only when supplied a `term_index` or `term_candidates` plus explicit `frame_candidates`.
- Adapter raises `ValueError` when `frame_candidates` are missing.
- Adapter includes the separately supplied `core` proposition id even when `core` is not included in the support proposition list.
- Adapter rejects unscoped frame candidates with blank `proposition_id`.

- [x] **Step 2: Implement `resolve_query_propositions`**

The adapter:

- Filters supplied frame candidates to known propositions.
- Projects candidates through `FrameCandidateProjector`.
- Splits core frames from document frames using proposition ids.
- Calls `resolve`.

It must not call `DocumentTermIndex.from_texts` for phrase terms and must not infer frames from proposition text.

- [x] **Step 3: Verify focused tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

- [x] **Step 4: Verify integration-adjacent tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py tests/test_builder_query_assembly.py tests/test_builder_evidence.py -q
```

---
## Self-Review

Spec coverage:

- Data classes are covered in Task 1.
- Document term indexing from explicit candidates is covered in Task 2.
- Explicit frame-candidate projection is covered in Task 3.
- Need creation is covered in Task 4.
- Candidate search and strict simple closure are covered in Task 5.
- Cycle recording and public exports are covered in Task 6.
- Query-time proposition adapter is covered in Task 7.

First-slice exclusions:

- No full coreference.
- No full discourse parser.
- No LLM proof judgment.
- No complete predicate taxonomy.
- No full integration into package ranking.
- Do not add a raw-text phrase/frame extractor based on finite word lists. The resolver consumes explicit term/frame candidates and does not infer document meaning from proposition text.

Verification commands:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py tests/test_builder_query_assembly.py tests/test_builder_evidence.py -q
```
