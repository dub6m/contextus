from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol


@dataclass(frozen=True)
class TermCandidate:
    element_id: str
    text: str
    char_start: int
    char_end: int
    source_signal: str
    head: str = ""
    modifiers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "modifiers", tuple(self.modifiers))


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "modifiers", tuple(self.modifiers))


@dataclass(frozen=True)
class DocumentTerm:
    term_id: str
    canonical: str
    mentions: tuple[TermMention, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mentions", tuple(self.mentions))


def normalize_term_text(text: str) -> str:
    cleaned = (text or "").strip().strip(".,;:()[]{}")
    return " ".join(cleaned.split()).strip().lower()


def _term_id(normalized: str) -> str:
    normalized_parts = []
    previous_was_separator = False
    for char in normalized:
        if char.isalnum() or char == "_":
            normalized_parts.append(char)
            previous_was_separator = False
        elif not previous_was_separator:
            normalized_parts.append("_")
            previous_was_separator = True
    return "term:" + "".join(normalized_parts).strip("_")


def _term_ids_for_normalized_values(normalized_values: tuple[str, ...]) -> dict[str, str]:
    by_base: dict[str, list[str]] = defaultdict(list)
    for normalized in normalized_values:
        by_base[_term_id(normalized)].append(normalized)

    term_ids: dict[str, str] = {}
    for base_id, values in by_base.items():
        if len(values) == 1:
            term_ids[values[0]] = base_id
            continue
        for normalized in values:
            digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
            term_ids[normalized] = f"{base_id}_{digest}"
    return term_ids


@dataclass(frozen=True)
class DocumentTermIndex:
    terms: Mapping[str, DocumentTerm]
    mentions_by_element_id: Mapping[str, tuple[TermMention, ...]]
    term_ids_by_normalized: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        terms = dict(self.terms)
        object.__setattr__(self, "terms", MappingProxyType(terms))
        mentions_by_element = {key: tuple(value) for key, value in self.mentions_by_element_id.items()}
        object.__setattr__(self, "mentions_by_element_id", MappingProxyType(mentions_by_element))
        term_ids = dict(self.term_ids_by_normalized)
        if not term_ids:
            term_ids = {term.canonical: term_id for term_id, term in terms.items()}
        object.__setattr__(self, "term_ids_by_normalized", MappingProxyType(term_ids))

    @classmethod
    def from_texts(cls, texts: list[tuple[str, str]]) -> "DocumentTermIndex":
        if texts:
            raise ValueError("from_texts is not supported; pass explicit TermCandidate spans to from_candidates")
        return cls.from_candidates([])

    @classmethod
    def from_candidates(cls, candidates: list[TermCandidate]) -> "DocumentTermIndex":
        mentions_by_key: dict[str, list[TermMention]] = defaultdict(list)
        mentions_by_element: dict[str, list[TermMention]] = defaultdict(list)
        seen: set[tuple[str, str, int, int]] = set()

        for candidate in candidates:
            normalized = normalize_term_text(candidate.text)
            if not normalized:
                continue
            key = (candidate.element_id, normalized, candidate.char_start, candidate.char_end)
            if key in seen:
                continue
            seen.add(key)
            mention = TermMention(
                text=candidate.text,
                normalized=normalized,
                element_id=candidate.element_id,
                char_start=candidate.char_start,
                char_end=candidate.char_end,
                source_signal=candidate.source_signal,
                head=candidate.head,
                modifiers=candidate.modifiers,
            )
            mentions_by_key[normalized].append(mention)
            mentions_by_element[candidate.element_id].append(mention)

        term_ids = _term_ids_for_normalized_values(tuple(mentions_by_key))
        terms = {
            term_ids[normalized]: DocumentTerm(
                term_id=term_ids[normalized],
                canonical=normalized,
                mentions=tuple(mentions),
            )
            for normalized, mentions in mentions_by_key.items()
        }
        return cls(
            terms=terms,
            mentions_by_element_id={key: tuple(value) for key, value in mentions_by_element.items()},
            term_ids_by_normalized=term_ids,
        )

    def term_id_for_text(self, text: str) -> str:
        normalized = normalize_term_text(text)
        return self.term_ids_by_normalized.get(normalized, "")


@dataclass(frozen=True)
class SlotCandidate:
    name: str
    text: str
    char_start: int = 0
    char_end: int = 0
    fill_state: str = "filled"
    grounding_state: str = "unsupported"
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


@dataclass(frozen=True)
class ConstraintCandidate:
    target_slot: str
    operator: str
    value: str
    normalized_value: str = ""
    value_kind: str = ""
    source_text: str = ""
    char_start: int = 0
    char_end: int = 0
    grounding_state: str = "unsupported"
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


@dataclass(frozen=True)
class FrameCandidate:
    frame_id: str
    element_id: str
    predicate: str
    slots: Mapping[str, SlotCandidate] = field(default_factory=dict)
    constraints: tuple[ConstraintCandidate, ...] = ()
    links: tuple[str, ...] = ()
    proposition_id: str = ""
    sentence_index: int = 0
    char_start: int = 0
    char_end: int = 0
    text: str = ""
    extraction_status: str = "candidate"

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "links", tuple(self.links))


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


@dataclass(frozen=True)
class FrameConstraint:
    target_slot: str
    operator: str
    value: str
    normalized_value: str = ""
    value_kind: str = ""
    source_text: str = ""
    char_start: int = 0
    char_end: int = 0
    grounding_state: str = "unsupported"
    evidence_refs: tuple[str, ...] = ()

    @property
    def requires_support(self) -> bool:
        return self.grounding_state == "unsupported"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


@dataclass(frozen=True)
class FactFrame:
    frame_id: str
    source: SourceRef
    predicate: str
    slots: Mapping[str, FrameSlot] = field(default_factory=dict)
    constraints: tuple[FrameConstraint, ...] = ()
    links: tuple[str, ...] = ()
    extraction_status: str = "asserted"

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "links", tuple(self.links))


class FrameCandidateProjector:
    def __init__(self, term_index: DocumentTermIndex) -> None:
        self.term_index = term_index

    def project(self, candidates: list[FrameCandidate]) -> list[FactFrame]:
        return [self._project_one(candidate) for candidate in candidates]

    def _project_one(self, candidate: FrameCandidate) -> FactFrame:
        source = SourceRef(
            element_id=candidate.element_id,
            proposition_id=candidate.proposition_id,
            sentence_index=candidate.sentence_index,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
            text=candidate.text,
        )
        slots = {
            name: self._project_slot(slot)
            for name, slot in candidate.slots.items()
        }
        constraints = tuple(self._project_constraint(constraint) for constraint in candidate.constraints)
        return FactFrame(
            frame_id=candidate.frame_id,
            source=source,
            predicate=candidate.predicate,
            slots=slots,
            constraints=constraints,
            links=candidate.links,
            extraction_status=candidate.extraction_status,
        )

    def _project_slot(self, slot: SlotCandidate) -> FrameSlot:
        normalized = normalize_term_text(slot.text)
        return FrameSlot(
            name=slot.name,
            value=normalized,
            term_id=self.term_index.term_id_for_text(normalized),
            fill_state=slot.fill_state,
            grounding_state=slot.grounding_state,
            source_text=slot.text,
            char_start=slot.char_start,
            char_end=slot.char_end,
            evidence_refs=slot.evidence_refs,
        )

    def _project_constraint(self, constraint: ConstraintCandidate) -> FrameConstraint:
        return FrameConstraint(
            target_slot=constraint.target_slot,
            operator=constraint.operator,
            value=constraint.value,
            normalized_value=constraint.normalized_value or normalize_term_text(constraint.value),
            value_kind=constraint.value_kind,
            source_text=constraint.source_text,
            char_start=constraint.char_start,
            char_end=constraint.char_end,
            grounding_state=constraint.grounding_state,
            evidence_refs=constraint.evidence_refs,
        )


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
    candidate_frame_ids: tuple[str, ...]
    matched_parts: tuple[str, ...]
    rejected_parts: tuple[str, ...] = ()
    rejected_candidate_frame_ids: tuple[str, ...] = ()
    status: str = "candidate"
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_frame_ids", tuple(self.candidate_frame_ids))
        object.__setattr__(self, "matched_parts", tuple(self.matched_parts))
        object.__setattr__(self, "rejected_parts", tuple(self.rejected_parts))
        object.__setattr__(self, "rejected_candidate_frame_ids", tuple(self.rejected_candidate_frame_ids))


@dataclass(frozen=True)
class ResolutionTraceStep:
    action: str
    need_id: str = ""
    frame_ids: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_ids", tuple(self.frame_ids))


@dataclass(frozen=True)
class ResolvedPackage:
    core_frames: tuple[FactFrame, ...]
    selected_frames: tuple[FactFrame, ...]
    selected_elements: tuple[str, ...]
    resolved_needs: tuple[Need, ...]
    unresolved_needs: tuple[Need, ...]
    cycles: tuple[tuple[str, ...], ...] = ()
    resolution_trace: tuple[ResolutionTraceStep, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "core_frames", tuple(self.core_frames))
        object.__setattr__(self, "selected_frames", tuple(self.selected_frames))
        object.__setattr__(self, "selected_elements", tuple(self.selected_elements))
        object.__setattr__(self, "resolved_needs", tuple(self.resolved_needs))
        object.__setattr__(self, "unresolved_needs", tuple(self.unresolved_needs))
        object.__setattr__(self, "cycles", tuple(tuple(cycle) for cycle in self.cycles))
        object.__setattr__(self, "resolution_trace", tuple(self.resolution_trace))


class SupportVerifier(Protocol):
    def supports(self, *, need: Need, source_frame: FactFrame, candidate_frame: FactFrame) -> bool:
        ...


class CrossEncoderNliSupportVerifier:
    def __init__(
        self,
        model_name: str = "cross-encoder/nli-deberta-v3-base",
        *,
        entailment_threshold: float = 0.55,
        contradiction_ceiling: float = 0.35,
    ) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)
        self.entailment_threshold = float(entailment_threshold)
        self.contradiction_ceiling = float(contradiction_ceiling)
        self._cache: dict[tuple[str, str], bool] = {}
        self._labels = {
            int(index): str(label).lower()
            for index, label in getattr(getattr(self.model, "model", None), "config", object()).id2label.items()
        } if hasattr(getattr(getattr(self.model, "model", None), "config", object()), "id2label") else {}

    def supports(self, *, need: Need, source_frame: FactFrame, candidate_frame: FactFrame) -> bool:
        premise = candidate_frame.source.text.strip()
        hypothesis = _candidate_support_statement(candidate_frame)
        if not premise or not hypothesis:
            return False
        key = (premise, hypothesis)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw_scores = self.model.predict([(premise, hypothesis)], apply_softmax=True)
        scores = list(raw_scores[0] if hasattr(raw_scores[0], "__iter__") else raw_scores)
        entailment_index = _label_index(self._labels, "entail", fallback=1 if len(scores) > 1 else 0)
        contradiction_index = _label_index(self._labels, "contrad", fallback=0)
        entailment = float(scores[entailment_index]) if entailment_index < len(scores) else 0.0
        contradiction = float(scores[contradiction_index]) if contradiction_index < len(scores) else 0.0
        accepted = entailment >= self.entailment_threshold and contradiction <= self.contradiction_ceiling
        self._cache[key] = accepted
        return accepted


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
            if not constraint.requires_support:
                continue
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


class DependencyResolver:
    def __init__(
        self,
        *,
        max_depth: int = 0,
        max_selected_frames: int = 32,
        support_verifier: SupportVerifier | None = None,
    ) -> None:
        self.max_depth = max(0, int(max_depth))
        self.max_selected_frames = max(1, int(max_selected_frames))
        self.support_verifier = support_verifier

    def resolve(self, *, core_frames: list[FactFrame], document_frames: list[FactFrame]) -> ResolvedPackage:
        need_builder = NeedBuilder()
        trace: list[ResolutionTraceStep] = []
        frame_by_id = {frame.frame_id: frame for frame in core_frames}
        document_frame_by_id = {frame.frame_id: frame for frame in document_frames}
        all_frame_by_id = {**document_frame_by_id, **frame_by_id}
        worklist: list[tuple[FactFrame, int]] = [(frame, 0) for frame in core_frames]
        processed_frame_ids: set[str] = set()

        resolved: list[Need] = []
        unresolved: list[Need] = []
        selected_by_id: dict[str, FactFrame] = {}

        while worklist:
            frame, depth = worklist.pop(0)
            if frame.frame_id in processed_frame_ids:
                continue
            processed_frame_ids.add(frame.frame_id)
            created = need_builder.needs_for_frame(frame)
            for need in created:
                trace.append(
                    ResolutionTraceStep(
                        action="need_created",
                        need_id=need.need_id,
                        frame_ids=(frame.frame_id,),
                        reason=f"{need.target_path} is {need.reason}",
                    )
                )
                candidate_frames = [
                    candidate
                    for candidate in all_frame_by_id.values()
                    if candidate.frame_id != frame.frame_id
                ]
                support = self._find_support(need, source_frame=frame, document_frames=candidate_frames)
                if support.rejected_candidate_frame_ids:
                    trace.append(
                        ResolutionTraceStep(
                            action="candidate_rejected",
                            need_id=need.need_id,
                            frame_ids=support.rejected_candidate_frame_ids,
                            reason="; ".join(support.rejected_parts) or "candidate rejected",
                        )
                    )
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
                    for candidate_frame_id in support.candidate_frame_ids:
                        candidate_frame = all_frame_by_id.get(candidate_frame_id)
                        if candidate_frame is None:
                            continue
                        if candidate_frame_id in document_frame_by_id:
                            selected_by_id[candidate_frame_id] = candidate_frame
                        if depth < self.max_depth and candidate_frame_id not in processed_frame_ids:
                            if len(selected_by_id) <= self.max_selected_frames:
                                worklist.append((candidate_frame, depth + 1))
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
                            frame_ids=support.candidate_frame_ids or support.rejected_candidate_frame_ids,
                            reason=support.reason or "no acceptable candidate support",
                        )
                    )

        selected_frames = tuple(selected_by_id.values())
        combined_frames = tuple(core_frames) + selected_frames
        return ResolvedPackage(
            core_frames=tuple(core_frames),
            selected_frames=selected_frames,
            selected_elements=tuple(sorted({frame.source.element_id for frame in selected_frames})),
            resolved_needs=tuple(resolved),
            unresolved_needs=tuple(unresolved),
            cycles=self.record_cycles(list(combined_frames)),
            resolution_trace=tuple(trace),
        )

    def resolve_query_propositions(
        self,
        *,
        core: object,
        propositions: list[object],
        term_index: DocumentTermIndex | None = None,
        term_candidates: list[TermCandidate] | None = None,
        frame_candidates: list[FrameCandidate] | None = None,
    ) -> ResolvedPackage:
        if frame_candidates is None:
            raise ValueError("frame_candidates are required; resolver does not infer frames from proposition text")
        if term_index is None:
            if term_candidates is None:
                raise ValueError("term_index or term_candidates are required")
            term_index = DocumentTermIndex.from_candidates(term_candidates)

        core_proposition_id = str(core.proposition_id)
        known_proposition_ids = {core_proposition_id}
        known_proposition_ids.update(str(item.proposition_id) for item in propositions if hasattr(item, "proposition_id"))
        if any(not candidate.proposition_id for candidate in frame_candidates):
            raise ValueError("frame_candidates must include proposition_id")
        relevant_candidates = [
            candidate
            for candidate in frame_candidates
            if candidate.proposition_id in known_proposition_ids
        ]
        frames = FrameCandidateProjector(term_index).project(relevant_candidates)
        core_frames = [frame for frame in frames if frame.source.proposition_id == core_proposition_id]
        document_frames = [frame for frame in frames if frame.source.proposition_id != core_proposition_id]
        return self.resolve(core_frames=core_frames, document_frames=document_frames)

    def record_cycles(self, frames: list[FactFrame]) -> tuple[tuple[str, ...], ...]:
        by_id = {frame.frame_id: frame for frame in frames}
        cycles: list[tuple[str, ...]] = []
        seen: set[tuple[str, ...]] = set()
        visited: set[str] = set()
        active_index: dict[str, int] = {}
        stack: list[str] = []

        def visit(frame_id: str) -> None:
            if frame_id in active_index:
                start = active_index[frame_id]
                cycle = tuple(stack[start:] + [frame_id])
                key = _canonical_cycle(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
                return
            if frame_id in visited:
                return
            frame = by_id.get(frame_id)
            if frame is None:
                return
            active_index[frame_id] = len(stack)
            stack.append(frame_id)
            for target_id in frame.links:
                visit(target_id)
            stack.pop()
            active_index.pop(frame_id, None)
            visited.add(frame_id)

        for frame in frames:
            visit(frame.frame_id)
        return tuple(cycles)

    def _find_support(
        self,
        need: Need,
        *,
        source_frame: FactFrame | None,
        document_frames: list[FactFrame],
    ) -> CandidateSupport:
        if source_frame is None:
            return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="source frame missing")
        if need.target_path.startswith("slots."):
            return self._find_slot_support(need, source_frame=source_frame, document_frames=document_frames)
        if need.target_path.startswith("constraints."):
            return self._find_constraint_support(need, source_frame=source_frame, document_frames=document_frames)
        return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="unsupported need target path")

    def _find_slot_support(
        self,
        need: Need,
        *,
        source_frame: FactFrame,
        document_frames: list[FactFrame],
    ) -> CandidateSupport:
        slot_name = need.target_path.split(".", 1)[1]
        source_slot = source_frame.slots.get(slot_name)
        if source_slot is None:
            return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="source slot missing")
        rejected_frame_ids: list[str] = []
        rejected_parts: list[str] = []
        for candidate in document_frames:
            for candidate_slot_name, candidate_slot in candidate.slots.items():
                if _same_slot_target(source_slot, candidate_slot):
                    proof_rejection = _proof_rejection_reason(source_frame=source_frame, candidate_frame=candidate)
                    if proof_rejection:
                        rejected_frame_ids.append(candidate.frame_id)
                        rejected_parts.append(f"{candidate.frame_id}: {proof_rejection}")
                        continue
                    if not _candidate_adds_information(
                        source_slot=source_slot,
                        source_frame=source_frame,
                        candidate_frame=candidate,
                        matched_slot_name=candidate_slot_name,
                    ):
                        rejected_frame_ids.append(candidate.frame_id)
                        rejected_parts.append(f"{candidate.frame_id}: same target without added information")
                        continue
                    if not self._verifier_accepts(need=need, source_frame=source_frame, candidate_frame=candidate):
                        rejected_frame_ids.append(candidate.frame_id)
                        rejected_parts.append(f"{candidate.frame_id}: verifier rejected candidate support")
                        continue
                    return CandidateSupport(
                        need_id=need.need_id,
                        candidate_frame_ids=(candidate.frame_id,),
                        matched_parts=("target term", "added information"),
                        rejected_parts=tuple(rejected_parts),
                        rejected_candidate_frame_ids=tuple(rejected_frame_ids),
                        status="accepted",
                        reason="candidate frame targets the missing term and adds information",
                    )
        if rejected_frame_ids:
            return CandidateSupport(
                need_id=need.need_id,
                candidate_frame_ids=tuple(rejected_frame_ids),
                matched_parts=(),
                rejected_parts=tuple(rejected_parts),
                rejected_candidate_frame_ids=tuple(rejected_frame_ids),
                status="rejected",
                reason="no candidate with the same target added usable information",
            )
        return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="no matching support frame")

    def _find_constraint_support(
        self,
        need: Need,
        *,
        source_frame: FactFrame,
        document_frames: list[FactFrame],
    ) -> CandidateSupport:
        index = int(need.target_path.split(".", 1)[1])
        if index >= len(source_frame.constraints):
            return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="source constraint missing")
        source_constraint = source_frame.constraints[index]
        source_target = source_frame.slots.get(source_constraint.target_slot)
        if source_target is None:
            return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="constraint target slot missing")

        rejected_frame_ids: list[str] = []
        rejected_parts: list[str] = []
        for candidate in document_frames:
            for candidate_constraint in candidate.constraints:
                candidate_target = candidate.slots.get(candidate_constraint.target_slot)
                if candidate_target is None:
                    continue
                if not _same_slot_target(source_target, candidate_target):
                    rejected_frame_ids.append(candidate.frame_id)
                    rejected_parts.append(f"{candidate.frame_id}: target term mismatch")
                    continue
                if _constraint_covers(source_constraint, candidate_constraint):
                    if not self._verifier_accepts(need=need, source_frame=source_frame, candidate_frame=candidate):
                        rejected_frame_ids.append(candidate.frame_id)
                        rejected_parts.append(f"{candidate.frame_id}: verifier rejected candidate support")
                        continue
                    return CandidateSupport(
                        need_id=need.need_id,
                        candidate_frame_ids=(candidate.frame_id,),
                        matched_parts=("target term", "compatible constraint"),
                        rejected_parts=tuple(rejected_parts),
                        rejected_candidate_frame_ids=tuple(rejected_frame_ids),
                        status="accepted",
                        reason="candidate constraint covers the unsupported constraint",
                    )
                rejected_frame_ids.append(candidate.frame_id)
                rejected_parts.append(f"{candidate.frame_id}: constraint mismatch")
        if rejected_frame_ids:
            return CandidateSupport(
                need_id=need.need_id,
                candidate_frame_ids=tuple(rejected_frame_ids),
                matched_parts=(),
                rejected_parts=tuple(rejected_parts),
                rejected_candidate_frame_ids=tuple(rejected_frame_ids),
                status="rejected",
                reason="no candidate constraint covers the unsupported constraint",
            )
        return CandidateSupport(need_id=need.need_id, candidate_frame_ids=(), matched_parts=(), reason="no matching support frame")

    def _verifier_accepts(self, *, need: Need, source_frame: FactFrame, candidate_frame: FactFrame) -> bool:
        if self.support_verifier is None:
            return True
        return bool(
            self.support_verifier.supports(
                need=need,
                source_frame=source_frame,
                candidate_frame=candidate_frame,
            )
        )


def _same_slot_target(left: FrameSlot, right: FrameSlot) -> bool:
    if left.term_id and right.term_id:
        return left.term_id == right.term_id
    return normalize_term_text(left.value) == normalize_term_text(right.value)


def _constraint_covers(required: FrameConstraint, candidate: FrameConstraint) -> bool:
    if required.operator == candidate.operator:
        return normalize_term_text(required.normalized_value or required.value) == normalize_term_text(
            candidate.normalized_value or candidate.value
        )
    if required.operator == "constant_bound":
        return candidate.operator in {"<", "<=", "="} and candidate.value_kind == "constant"
    return False


ROUTE_PREDICATES = frozenset(
    {
        "adjacent_to",
        "caption_of",
        "heading_of",
        "references",
        "same_list",
        "same_section",
    }
)

STRICT_PROOF_FAMILIES = {
    "definition": frozenset({"definition"}),
    "procedure_step": frozenset({"procedure_step"}),
    "bound": frozenset({"bound", "quantity_bound"}),
    "quantity_bound": frozenset({"bound", "quantity_bound"}),
    "contrast": frozenset({"contrast"}),
    "shows": frozenset({"shows", "caption_claim", "supports_claim"}),
    "caption_claim": frozenset({"shows", "caption_claim", "supports_claim"}),
    "supports_claim": frozenset({"shows", "caption_claim", "supports_claim"}),
}


def _proof_rejection_reason(*, source_frame: FactFrame, candidate_frame: FactFrame) -> str:
    candidate_predicate = normalize_term_text(candidate_frame.predicate)
    if candidate_predicate in ROUTE_PREDICATES or candidate_frame.extraction_status == "syntax_route":
        return "route frame cannot prove a dependency"
    source_predicate = normalize_term_text(source_frame.predicate)
    accepted = STRICT_PROOF_FAMILIES.get(source_predicate)
    if accepted is not None and candidate_predicate not in accepted:
        return "predicate family mismatch"
    return ""


def _candidate_adds_information(
    *,
    source_slot: FrameSlot,
    source_frame: FactFrame,
    candidate_frame: FactFrame,
    matched_slot_name: str,
) -> bool:
    if candidate_frame.constraints:
        return True
    source_values = {
        normalize_term_text(slot.value)
        for slot in source_frame.slots.values()
        if slot.value
    }
    source_values.add(normalize_term_text(source_slot.value))
    for slot_name, slot in candidate_frame.slots.items():
        if slot_name == matched_slot_name:
            continue
        normalized = normalize_term_text(slot.value)
        if normalized and normalized not in source_values:
            return True
    return False


def _candidate_support_statement(frame: FactFrame) -> str:
    target = frame.slots.get("target")
    value = frame.slots.get("value")
    if target is not None and value is not None and target.value and value.value:
        return f"{target.source_text or target.value} is supported by {value.source_text or value.value}"
    if target is not None and frame.constraints:
        constraint_text = "; ".join(
            " ".join(part for part in (target.source_text or target.value, constraint.operator, constraint.source_text or constraint.value) if part)
            for constraint in frame.constraints
        )
        return constraint_text.strip()
    parts = [frame.predicate]
    parts.extend(slot.source_text or slot.value for slot in frame.slots.values() if slot.value)
    return "; ".join(part for part in parts if part).strip()


def _label_index(labels: Mapping[int, str], needle: str, *, fallback: int) -> int:
    for index, label in labels.items():
        if needle in label:
            return index
    return fallback


def _canonical_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    if len(cycle) <= 1:
        return cycle
    body = cycle[:-1]
    rotations = [body[index:] + body[:index] for index in range(len(body))]
    canonical = min(rotations)
    return canonical + (canonical[0],)
