# Dependency Resolver Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working dependency-resolver slice: structured facts, needs, candidate support, simple closure, and trace output.

**Architecture:** Add one focused builder module that runs in parallel to the current query-time assembler. The first slice uses deterministic term/frame extraction and strict closure for simple term and quantity support. It does not replace planner, traversal, ranking, or answer bundle code.

**Tech Stack:** Python dataclasses, regex helpers, existing `QueryEvidenceProposition` records, pytest.

---

## File Structure

- Create: `contextus/builder/dependency_resolver.py`
  - Owns resolver data models, term extraction, simple frame extraction, need creation, candidate search, closure, and trace output for the first slice.
- Modify: `contextus/builder/__init__.py`
  - Exposes the new public classes for tests and future query-time integration.
- Create: `tests/test_builder_dependency_resolver.py`
  - Covers normalization, frame extraction, need creation, quantity closure, cycle recording, and package trace behavior.

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
        term_id="term:candidate_point",
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
            "object": FrameSlot(name="object", value="candidate points", term_id="term:candidate_point"),
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

### Task 2: Add Conservative Term Extraction

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing term-index tests**

Append these tests:

```python
from contextus.builder.dependency_resolver import DocumentTermIndex, normalize_term_text


def test_normalize_term_text_is_conservative():
    assert normalize_term_text("The strip.") == "strip"
    assert normalize_term_text("candidate points") == "candidate point"
    assert normalize_term_text("median line") == "median line"
    assert normalize_term_text("line") == "line"
    assert normalize_term_text("Q_x") == "q_x"


def test_document_term_index_keeps_specific_terms_separate():
    index = DocumentTermIndex.from_texts(
        [
            ("e1", "The median line splits the points."),
            ("e2", "The line is drawn vertically."),
        ]
    )

    assert "term:median_line" in index.terms
    assert "term:line" in index.terms
    assert index.terms["term:median_line"].canonical == "median line"
    assert index.terms["term:line"].canonical == "line"


def test_document_term_index_records_mentions_with_source():
    index = DocumentTermIndex.from_texts([("e1", "The vertical strip contains candidate points.")])

    strip = index.terms["term:vertical_strip"]
    assert strip.canonical == "vertical strip"
    assert strip.mentions[0].element_id == "e1"
    assert strip.mentions[0].source_signal == "nounish_span"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: import failure for `DocumentTermIndex` and `normalize_term_text`.

- [ ] **Step 3: Add term dataclasses and extraction helpers**

Append this code to `contextus/builder/dependency_resolver.py`:

```python
import re
from collections import defaultdict


_TERM_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SYMBOL_RE = re.compile(r"\b[A-Za-z]+_[A-Za-z0-9]+\b")
_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_STOP_TERMS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class TermMention:
    text: str
    normalized: str
    element_id: str
    char_start: int
    char_end: int
    source_signal: str
    head: str = ""
    modifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentTerm:
    term_id: str
    canonical: str
    mentions: tuple[TermMention, ...] = ()


def normalize_term_text(text: str) -> str:
    cleaned = (text or "").strip().strip(".,;:()[]{}")
    cleaned = _ARTICLE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    parts = []
    for token in cleaned.split(" "):
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        parts.append(token)
    return " ".join(parts)


def _term_id(normalized: str) -> str:
    return "term:" + re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")


def _candidate_term_spans(text: str) -> list[tuple[str, int, int, str]]:
    spans: list[tuple[str, int, int, str]] = []
    for match in _SYMBOL_RE.finditer(text or ""):
        spans.append((match.group(0), match.start(), match.end(), "symbol"))

    tokens = list(_TERM_TOKEN_RE.finditer(text or ""))
    for width in (3, 2, 1):
        for index in range(0, max(0, len(tokens) - width + 1)):
            group = tokens[index : index + width]
            words = [item.group(0) for item in group]
            lowered = [word.lower() for word in words]
            if all(word in _STOP_TERMS for word in lowered):
                continue
            if lowered[0] in _STOP_TERMS and width == 1:
                continue
            if width > 1 and any(word in {"and", "or", "but"} for word in lowered):
                continue
            spans.append((" ".join(words), group[0].start(), group[-1].end(), "nounish_span"))
    return spans


@dataclass(frozen=True)
class DocumentTermIndex:
    terms: dict[str, DocumentTerm]
    mentions_by_element_id: dict[str, tuple[TermMention, ...]]

    @classmethod
    def from_texts(cls, texts: list[tuple[str, str]]) -> "DocumentTermIndex":
        mentions_by_key: dict[str, list[TermMention]] = defaultdict(list)
        mentions_by_element: dict[str, list[TermMention]] = defaultdict(list)
        seen: set[tuple[str, str, int, int]] = set()

        for element_id, text in texts:
            for surface, start, end, source_signal in _candidate_term_spans(text):
                normalized = normalize_term_text(surface)
                if not normalized or normalized in _STOP_TERMS:
                    continue
                key = (element_id, normalized, start, end)
                if key in seen:
                    continue
                seen.add(key)
                words = normalized.split()
                mention = TermMention(
                    text=surface,
                    normalized=normalized,
                    element_id=element_id,
                    char_start=start,
                    char_end=end,
                    source_signal=source_signal,
                    head=words[-1] if words else "",
                    modifiers=tuple(words[:-1]),
                )
                mentions_by_key[normalized].append(mention)
                mentions_by_element[element_id].append(mention)

        terms = {
            _term_id(normalized): DocumentTerm(
                term_id=_term_id(normalized),
                canonical=normalized,
                mentions=tuple(mentions),
            )
            for normalized, mentions in mentions_by_key.items()
        }
        return cls(
            terms=terms,
            mentions_by_element_id={key: tuple(value) for key, value in mentions_by_element.items()},
        )

    def term_id_for_text(self, text: str) -> str:
        normalized = normalize_term_text(text)
        term_id = _term_id(normalized)
        return term_id if term_id in self.terms else ""
```

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

### Task 3: Add Simple Frame Extraction

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing frame extraction tests**

Append these tests:

```python
from contextus.builder.dependency_resolver import SimpleFrameExtractor


def test_extracts_contains_and_quantity_bound_frames():
    text = "The strip contains at most seven candidate points."
    term_index = DocumentTermIndex.from_texts([("e1", text)])
    frames = SimpleFrameExtractor(term_index).extract("e1", text)

    contains = [frame for frame in frames if frame.predicate == "contains"]
    bounds = [frame for frame in frames if frame.predicate == "bound"]

    assert len(contains) == 1
    assert contains[0].slots["subject"].value == "strip"
    assert contains[0].slots["object"].value == "candidate points"
    assert len(bounds) == 1
    assert bounds[0].slots["target"].value == "candidate points"
    assert bounds[0].constraints[0].operator == "<="
    assert bounds[0].constraints[0].value == "seven"


def test_extracts_copular_definition_frame():
    text = "The strip is the region within delta of the median line."
    term_index = DocumentTermIndex.from_texts([("e1", text)])
    frames = SimpleFrameExtractor(term_index).extract("e1", text)

    definitions = [frame for frame in frames if frame.predicate == "defines"]

    assert len(definitions) == 1
    assert definitions[0].slots["subject"].value == "strip"
    assert definitions[0].slots["object"].value == "region within delta"


def test_extracts_formula_equality_frame():
    text = "T(n) = 2T(n/2) + O(n)"
    term_index = DocumentTermIndex.from_texts([("e1", text)])
    frames = SimpleFrameExtractor(term_index).extract("e1", text)

    equalities = [frame for frame in frames if frame.predicate == "="]

    assert len(equalities) == 1
    assert equalities[0].slots["left"].value == "T(n)"
    assert equalities[0].slots["right"].value == "2T(n/2) + O(n)"


def test_extracts_constant_bound_frame_from_core_language():
    text = "The strip has a constant number of candidate points."
    term_index = DocumentTermIndex.from_texts([("core", text)])
    frames = SimpleFrameExtractor(term_index).extract("core", text)

    bounds = [frame for frame in frames if frame.predicate == "bound"]

    assert len(bounds) == 1
    assert bounds[0].slots["target"].value == "candidate points"
    assert bounds[0].constraints[0].value == "constant"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: import failure for `SimpleFrameExtractor`.

- [ ] **Step 3: Add frame extraction helpers**

Append this code to `contextus/builder/dependency_resolver.py`:

```python
_CONTAINS_RE = re.compile(
    r"\b(?:the\s+)?(?P<subject>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,2})\s+"
    r"(?P<predicate>contains?|includes?|has|have)\s+"
    r"(?:(?P<bound>at\s+most|no\s+more\s+than|at\s+least|no\s+less\s+than)\s+)?"
    r"(?:(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+)?"
    r"(?P<object>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,2})",
    re.IGNORECASE,
)
_DEFINITION_RE = re.compile(
    r"\b(?:the\s+)?(?P<subject>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,1})\s+"
    r"(?:is|means|denotes|refers\s+to)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?P<object>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,3})",
    re.IGNORECASE,
)
_FORMULA_EQUALITY_RE = re.compile(r"(?P<left>[A-Za-z]\([^=]{0,20}\)|[A-Za-z][A-Za-z0-9_]*)\s*=\s*(?P<right>.+)")
_CONSTANT_BOUND_RE = re.compile(
    r"\bconstant\s+(?:number\s+of|bound\s+on\s+)?(?P<target>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,2})",
    re.IGNORECASE,
)
_TARGET_HAS_CONSTANT_RE = re.compile(
    r"\b(?P<target>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,2})\s+"
    r"(?:has|have|is|are)\s+(?:a\s+)?constant\s+(?:bound|number)",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def _slot(name: str, value: str, term_index: DocumentTermIndex, *, grounding_state: str = "unsupported") -> FrameSlot:
    normalized = normalize_term_text(value)
    return FrameSlot(
        name=name,
        value=normalized,
        term_id=term_index.term_id_for_text(normalized),
        grounding_state=grounding_state,
        source_text=value,
    )


def _operator_for_bound(bound: str) -> str:
    lowered = (bound or "").lower()
    if lowered in {"at most", "no more than"}:
        return "<="
    if lowered in {"at least", "no less than"}:
        return ">="
    return ""


def _normalized_number(value: str) -> str:
    lowered = (value or "").lower()
    return _NUMBER_WORDS.get(lowered, lowered)


class SimpleFrameExtractor:
    def __init__(self, term_index: DocumentTermIndex):
        self.term_index = term_index

    def extract(self, element_id: str, text: str, *, proposition_id: str = "") -> list[FactFrame]:
        frames: list[FactFrame] = []
        frames.extend(self._extract_contains(element_id, text, proposition_id=proposition_id))
        frames.extend(self._extract_constant_bounds(element_id, text, proposition_id=proposition_id))
        frames.extend(self._extract_definitions(element_id, text, proposition_id=proposition_id))
        frames.extend(self._extract_formula_equalities(element_id, text, proposition_id=proposition_id))
        return frames

    def _source(self, element_id: str, text: str, *, proposition_id: str, start: int, end: int) -> SourceRef:
        return SourceRef(
            element_id=element_id,
            proposition_id=proposition_id,
            char_start=start,
            char_end=end,
            text=text[start:end],
        )

    def _extract_contains(self, element_id: str, text: str, *, proposition_id: str) -> list[FactFrame]:
        frames: list[FactFrame] = []
        for index, match in enumerate(_CONTAINS_RE.finditer(text or "")):
            subject = match.group("subject")
            obj = match.group("object")
            frame_id = f"frame:{element_id}:contains:{index}"
            frames.append(
                FactFrame(
                    frame_id=frame_id,
                    source=self._source(element_id, text, proposition_id=proposition_id, start=match.start(), end=match.end()),
                    predicate="contains",
                    slots={
                        "subject": _slot("subject", subject, self.term_index),
                        "object": _slot("object", obj, self.term_index),
                    },
                )
            )
            bound = match.group("bound") or ""
            value = match.group("value") or ""
            operator = _operator_for_bound(bound)
            if operator and value:
                frames.append(
                    FactFrame(
                        frame_id=f"frame:{element_id}:bound:{index}",
                        source=self._source(element_id, text, proposition_id=proposition_id, start=match.start(), end=match.end()),
                        predicate="bound",
                        slots={"target": _slot("target", obj, self.term_index)},
                        constraints=(
                            FrameConstraint(
                                target_slot="target",
                                operator=operator,
                                value=value.lower(),
                                normalized_value=_normalized_number(value),
                                source_text=match.group(0),
                            ),
                        ),
                    )
                )
        return frames

    def _extract_constant_bounds(self, element_id: str, text: str, *, proposition_id: str) -> list[FactFrame]:
        frames: list[FactFrame] = []
        matches = list(_CONSTANT_BOUND_RE.finditer(text or "")) + list(_TARGET_HAS_CONSTANT_RE.finditer(text or ""))
        for index, match in enumerate(matches):
            target = match.group("target")
            frames.append(
                FactFrame(
                    frame_id=f"frame:{element_id}:constant-bound:{index}",
                    source=self._source(element_id, text, proposition_id=proposition_id, start=match.start(), end=match.end()),
                    predicate="bound",
                    slots={"target": _slot("target", target, self.term_index)},
                    constraints=(
                        FrameConstraint(
                            target_slot="target",
                            operator="<=",
                            value="constant",
                            normalized_value="constant",
                            source_text=match.group(0),
                        ),
                    ),
                )
            )
        return frames

    def _extract_definitions(self, element_id: str, text: str, *, proposition_id: str) -> list[FactFrame]:
        frames: list[FactFrame] = []
        for index, match in enumerate(_DEFINITION_RE.finditer(text or "")):
            frames.append(
                FactFrame(
                    frame_id=f"frame:{element_id}:defines:{index}",
                    source=self._source(element_id, text, proposition_id=proposition_id, start=match.start(), end=match.end()),
                    predicate="defines",
                    slots={
                        "subject": _slot("subject", match.group("subject"), self.term_index, grounding_state="grounded"),
                        "object": _slot("object", match.group("object"), self.term_index, grounding_state="grounded"),
                    },
                )
            )
        return frames

    def _extract_formula_equalities(self, element_id: str, text: str, *, proposition_id: str) -> list[FactFrame]:
        match = _FORMULA_EQUALITY_RE.search(text or "")
        if not match:
            return []
        return [
            FactFrame(
                frame_id=f"frame:{element_id}:formula:0",
                source=self._source(element_id, text, proposition_id=proposition_id, start=match.start(), end=match.end()),
                predicate="=",
                slots={
                    "left": FrameSlot(name="left", value=match.group("left").strip(), source_text=match.group("left").strip()),
                    "right": FrameSlot(name="right", value=match.group("right").strip(), source_text=match.group("right").strip()),
                },
            )
        ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add contextus/builder/dependency_resolver.py tests/test_builder_dependency_resolver.py
git commit -m "Add simple dependency fact extraction"
```

---

### Task 4: Create Needs From Unsupported Frame Parts

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing need-creation tests**

Append these tests:

```python
from contextus.builder.dependency_resolver import NeedBuilder


def test_need_builder_creates_need_for_unsupported_slot():
    frame = FactFrame(
        frame_id="frame:core:0",
        source=SourceRef(element_id="core", text="The strip contains candidate points."),
        predicate="contains",
        slots={
            "subject": FrameSlot(name="subject", value="strip", term_id="term:strip", grounding_state="unsupported"),
            "object": FrameSlot(name="object", value="candidate points", term_id="term:candidate_point", grounding_state="unsupported"),
        },
    )

    needs = NeedBuilder().needs_for_frame(frame)

    assert [need.target_path for need in needs] == ["slots.subject", "slots.object"]
    assert all(need.reason == "filled_but_unsupported" for need in needs)


def test_need_builder_creates_need_for_unsupported_constraint():
    frame = FactFrame(
        frame_id="frame:core:bound",
        source=SourceRef(element_id="core", text="constant candidate points"),
        predicate="bound",
        slots={"target": FrameSlot(name="target", value="candidate points", term_id="term:candidate_point")},
        constraints=(
            FrameConstraint(target_slot="target", operator="<=", value="constant", normalized_value="constant"),
        ),
    )

    needs = NeedBuilder().needs_for_frame(frame)

    assert len(needs) == 1
    assert needs[0].target_path == "constraints.0"
    assert needs[0].value == "constant"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: import failure for `NeedBuilder`.

- [ ] **Step 3: Add the need builder**

Append this code to `contextus/builder/dependency_resolver.py`:

```python
class NeedBuilder:
    def needs_for_frame(self, frame: FactFrame) -> list[Need]:
        needs: list[Need] = []
        for slot_name, slot in frame.slots.items():
            if slot.fill_state == "missing":
                reason = "missing"
            elif slot.fill_state == "ambiguous":
                reason = "ambiguous"
            elif slot.grounding_state == "unsupported":
                reason = "filled_but_unsupported"
            else:
                continue
            needs.append(
                Need(
                    need_id=f"need:{frame.frame_id}:slots.{slot_name}",
                    frame_id=frame.frame_id,
                    target_path=f"slots.{slot_name}",
                    value=slot.value,
                    reason=reason,
                )
            )

        for index, constraint in enumerate(frame.constraints):
            if constraint.requires_support:
                needs.append(
                    Need(
                        need_id=f"need:{frame.frame_id}:constraints.{index}",
                        frame_id=frame.frame_id,
                        target_path=f"constraints.{index}",
                        value=constraint.value,
                        reason="filled_but_unsupported",
                    )
                )
        return needs
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add contextus/builder/dependency_resolver.py tests/test_builder_dependency_resolver.py
git commit -m "Add dependency need creation"
```

---

### Task 5: Add Candidate Search And Strict Simple Closure

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing candidate search and closure tests**

Append these tests:

```python
from contextus.builder.dependency_resolver import DependencyResolver


def test_resolver_closes_constant_need_with_fixed_upper_bound():
    core_text = "The strip has a constant number of candidate points."
    source_text = "The strip contains at most seven candidate points."
    texts = [("core", core_text), ("source", source_text)]
    term_index = DocumentTermIndex.from_texts(texts)
    extractor = SimpleFrameExtractor(term_index)
    core_frames = extractor.extract("core", core_text)
    document_frames = extractor.extract("source", source_text)

    result = DependencyResolver().resolve(core_frames=core_frames, document_frames=document_frames)

    assert result.resolved_needs
    assert not result.unresolved_needs
    assert any(step.action == "need_resolved" for step in result.resolution_trace)
    assert "source" in result.selected_elements


def test_resolver_does_not_close_with_target_mismatch():
    core_text = "Candidate points have a constant bound."
    source_text = "The strip contains at most seven rows."
    texts = [("core", core_text), ("source", source_text)]
    term_index = DocumentTermIndex.from_texts(texts)
    extractor = SimpleFrameExtractor(term_index)
    core_frames = [
        FactFrame(
            frame_id="frame:core:bound",
            source=SourceRef(element_id="core", text=core_text),
            predicate="bound",
            slots={"target": FrameSlot(name="target", value="candidate points", term_id=term_index.term_id_for_text("candidate points"))},
            constraints=(FrameConstraint(target_slot="target", operator="<=", value="constant", normalized_value="constant"),),
        )
    ]
    document_frames = extractor.extract("source", source_text)

    result = DependencyResolver().resolve(core_frames=core_frames, document_frames=document_frames)

    assert not result.resolved_needs
    assert result.unresolved_needs
    assert any(step.action == "candidate_rejected" for step in result.resolution_trace)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: import failure for `DependencyResolver`.

- [ ] **Step 3: Add result model and resolver**

Append this code to `contextus/builder/dependency_resolver.py`:

```python
@dataclass(frozen=True)
class ResolvedPackage:
    core_frames: list[FactFrame]
    selected_frames: list[FactFrame]
    selected_elements: list[str]
    resolved_needs: list[Need]
    unresolved_needs: list[Need]
    cycles: list[list[str]] = field(default_factory=list)
    resolution_trace: list[ResolutionTraceStep] = field(default_factory=list)


def _constraint_is_constant_compatible(candidate: FrameConstraint, need_value: str) -> bool:
    if normalize_term_text(need_value) != "constant":
        return candidate.value.lower() == need_value.lower() or candidate.normalized_value == need_value
    if candidate.normalized_value.isdigit() and candidate.operator in {"<=", "<"}:
        return True
    if candidate.value.lower() in {"constant", "bounded"}:
        return True
    return False


class DependencyResolver:
    def resolve(self, *, core_frames: list[FactFrame], document_frames: list[FactFrame]) -> ResolvedPackage:
        needs: list[Need] = []
        trace: list[ResolutionTraceStep] = []
        builder = NeedBuilder()
        for frame in core_frames:
            created = builder.needs_for_frame(frame)
            needs.extend(created)
            for need in created:
                trace.append(
                    ResolutionTraceStep(
                        action="need_created",
                        need_id=need.need_id,
                        frame_ids=[frame.frame_id],
                        reason=f"{need.target_path} is {need.reason}",
                    )
                )

        resolved: list[Need] = []
        unresolved: list[Need] = []
        selected_frames: list[FactFrame] = []

        for need in needs:
            support = self._find_support(need, core_frames=core_frames, document_frames=document_frames)
            if support.status == "accepted":
                resolved_need = Need(
                    need_id=need.need_id,
                    frame_id=need.frame_id,
                    target_path=need.target_path,
                    value=need.value,
                    reason=need.reason,
                    status="resolved",
                )
                resolved.append(resolved_need)
                matched = [frame for frame in document_frames if frame.frame_id in support.candidate_frame_ids]
                selected_frames.extend(matched)
                trace.append(
                    ResolutionTraceStep(
                        action="need_resolved",
                        need_id=need.need_id,
                        frame_ids=support.candidate_frame_ids,
                        reason=support.reason,
                    )
                )
            else:
                unresolved.append(need)
                trace.append(
                    ResolutionTraceStep(
                        action="candidate_rejected",
                        need_id=need.need_id,
                        frame_ids=support.candidate_frame_ids,
                        reason=support.reason or "no acceptable candidate support",
                    )
                )

        selected_by_id = {frame.frame_id: frame for frame in selected_frames}
        return ResolvedPackage(
            core_frames=core_frames,
            selected_frames=list(selected_by_id.values()),
            selected_elements=sorted({frame.source.element_id for frame in selected_by_id.values()}),
            resolved_needs=resolved,
            unresolved_needs=unresolved,
            resolution_trace=trace,
        )

    def _find_support(
        self,
        need: Need,
        *,
        core_frames: list[FactFrame],
        document_frames: list[FactFrame],
    ) -> CandidateSupport:
        source_frame = next((frame for frame in core_frames if frame.frame_id == need.frame_id), None)
        if source_frame is None:
            return CandidateSupport(need_id=need.need_id, candidate_frame_ids=[], matched_parts=[], reason="source frame missing")

        if need.target_path.startswith("constraints."):
            index = int(need.target_path.split(".", 1)[1])
            source_constraint = source_frame.constraints[index]
            source_target = source_frame.slots.get(source_constraint.target_slot)
            if source_target is None:
                return CandidateSupport(need_id=need.need_id, candidate_frame_ids=[], matched_parts=[], reason="constraint target slot missing")
            for candidate in document_frames:
                if candidate.frame_id == source_frame.frame_id:
                    continue
                for candidate_constraint in candidate.constraints:
                    candidate_target = candidate.slots.get(candidate_constraint.target_slot)
                    if candidate_target is None:
                        continue
                    if candidate_target.term_id and source_target.term_id and candidate_target.term_id != source_target.term_id:
                        return CandidateSupport(
                            need_id=need.need_id,
                            candidate_frame_ids=[candidate.frame_id],
                            matched_parts=[],
                            rejected_parts=["target term mismatch"],
                            status="rejected",
                            reason="candidate bound targets a different term",
                        )
                    if candidate_target.value != source_target.value:
                        continue
                    if _constraint_is_constant_compatible(candidate_constraint, source_constraint.value):
                        return CandidateSupport(
                            need_id=need.need_id,
                            candidate_frame_ids=[candidate.frame_id],
                            matched_parts=["target term", "compatible constraint"],
                            status="accepted",
                            reason="candidate constraint covers the unsupported bound",
                        )
        return CandidateSupport(need_id=need.need_id, candidate_frame_ids=[], matched_parts=[], reason="no matching support frame")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add contextus/builder/dependency_resolver.py tests/test_builder_dependency_resolver.py
git commit -m "Add simple dependency support closure"
```

---

### Task 6: Add Cycle Recording And Public Exports

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `contextus/builder/__init__.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing tests for cycle recording and public imports**

Append these tests:

```python
from contextus.builder import DependencyResolver as PublicDependencyResolver


def test_resolver_records_cycle_without_expanding_forever():
    frame_a = FactFrame(
        frame_id="frame:a",
        source=SourceRef(element_id="a", text="A depends on B."),
        predicate="depends_on",
        links=("frame:b",),
    )
    frame_b = FactFrame(
        frame_id="frame:b",
        source=SourceRef(element_id="b", text="B depends on A."),
        predicate="depends_on",
        links=("frame:a",),
    )

    result = DependencyResolver().record_cycles([frame_a, frame_b])

    assert result == [["frame:a", "frame:b", "frame:a"]]


def test_dependency_resolver_is_public_builder_export():
    assert PublicDependencyResolver is DependencyResolver
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: `record_cycles` missing and public import missing.

- [ ] **Step 3: Add cycle recording**

Append this method inside `DependencyResolver`:

```python
    def record_cycles(self, frames: list[FactFrame]) -> list[list[str]]:
        by_id = {frame.frame_id: frame for frame in frames}
        cycles: list[list[str]] = []

        def visit(frame_id: str, path: list[str]) -> None:
            if frame_id in path:
                start = path.index(frame_id)
                cycle = path[start:] + [frame_id]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            frame = by_id.get(frame_id)
            if frame is None:
                return
            for target_id in frame.links:
                visit(target_id, path + [frame_id])

        for frame in frames:
            visit(frame.frame_id, [])
        return cycles
```

Also update the `resolve` return so it records cycles across core and selected frames:

```python
        combined_frames = core_frames + list(selected_by_id.values())
        return ResolvedPackage(
            core_frames=core_frames,
            selected_frames=list(selected_by_id.values()),
            selected_elements=sorted({frame.source.element_id for frame in selected_by_id.values()}),
            resolved_needs=resolved,
            unresolved_needs=unresolved,
            cycles=self.record_cycles(combined_frames),
            resolution_trace=trace,
        )
```

- [ ] **Step 4: Export the public classes**

Modify `contextus/builder/__init__.py` imports:

```python
from .dependency_resolver import (
    CandidateSupport,
    DependencyResolver,
    DocumentTerm,
    DocumentTermIndex,
    FactFrame,
    FrameConstraint,
    FrameSlot,
    Need,
    NeedBuilder,
    ResolvedPackage,
    ResolutionTraceStep,
    SimpleFrameExtractor,
    SourceRef,
    TermMention,
    normalize_term_text,
)
```

Add these names to `__all__`:

```python
    "CandidateSupport",
    "DependencyResolver",
    "DocumentTerm",
    "DocumentTermIndex",
    "FactFrame",
    "FrameConstraint",
    "FrameSlot",
    "Need",
    "NeedBuilder",
    "ResolvedPackage",
    "ResolutionTraceStep",
    "SimpleFrameExtractor",
    "SourceRef",
    "TermMention",
    "normalize_term_text",
```

- [ ] **Step 5: Run tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
```

Expected: all dependency resolver tests pass.

- [ ] **Step 6: Run focused existing tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_query_assembly.py tests/test_builder_evidence.py tests/test_builder_dependency_resolver.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add contextus/builder/dependency_resolver.py contextus/builder/__init__.py tests/test_builder_dependency_resolver.py
git commit -m "Expose dependency resolver vertical slice"
```

---

### Task 7: Add A Query Proposition Adapter

**Files:**
- Modify: `contextus/builder/dependency_resolver.py`
- Modify: `tests/test_builder_dependency_resolver.py`

- [ ] **Step 1: Add failing adapter test**

Append this test:

```python
from contextus.builder.query_assembly import QueryEvidenceProposition


def test_build_resolved_package_from_query_propositions():
    core = QueryEvidenceProposition(
        proposition_id="core::p00",
        element_id="core",
        element_index=0,
        text="Candidate points have a constant bound.",
    )
    source = QueryEvidenceProposition(
        proposition_id="source::p00",
        element_id="source",
        element_index=1,
        text="The strip contains at most seven candidate points.",
    )

    result = DependencyResolver().resolve_query_propositions(core=core, propositions=[core, source])

    assert result.resolved_needs
    assert result.selected_elements == ["source"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py::test_build_resolved_package_from_query_propositions -q
```

Expected: `resolve_query_propositions` missing.

- [ ] **Step 3: Add the adapter**

Append this method inside `DependencyResolver`:

```python
    def resolve_query_propositions(self, *, core: object, propositions: list[object]) -> ResolvedPackage:
        texts = [(str(item.element_id), str(item.text)) for item in propositions]
        term_index = DocumentTermIndex.from_texts(texts)
        extractor = SimpleFrameExtractor(term_index)

        core_frames = extractor.extract(
            str(core.element_id),
            str(core.text),
            proposition_id=str(core.proposition_id),
        )
        document_frames: list[FactFrame] = []
        for proposition in propositions:
            if proposition.proposition_id == core.proposition_id:
                continue
            document_frames.extend(
                extractor.extract(
                    str(proposition.element_id),
                    str(proposition.text),
                    proposition_id=str(proposition.proposition_id),
                )
            )
        return self.resolve(core_frames=core_frames, document_frames=document_frames)
```

- [ ] **Step 4: Run the adapter test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py::test_build_resolved_package_from_query_propositions -q
```

Expected: pass.

- [ ] **Step 5: Run full focused test set**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py tests/test_builder_query_assembly.py tests/test_builder_evidence.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add contextus/builder/dependency_resolver.py tests/test_builder_dependency_resolver.py
git commit -m "Add query proposition dependency adapter"
```

---

## Self-Review

Spec coverage:

- Data classes are covered in Task 1.
- Conservative term extraction is covered in Task 2.
- Simple syntax-to-frame projection is covered in Task 3.
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
- No spaCy dependency is required for this first slice; parser-backed extraction can replace the deterministic extractor after this traceable vertical slice works.

Verification commands:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py -q
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py tests/test_builder_query_assembly.py tests/test_builder_evidence.py -q
```
