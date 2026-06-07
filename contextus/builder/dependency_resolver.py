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
