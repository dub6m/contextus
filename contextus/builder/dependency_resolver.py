from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


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
    status: str = "candidate"
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_frame_ids", tuple(self.candidate_frame_ids))
        object.__setattr__(self, "matched_parts", tuple(self.matched_parts))
        object.__setattr__(self, "rejected_parts", tuple(self.rejected_parts))


@dataclass(frozen=True)
class ResolutionTraceStep:
    action: str
    need_id: str = ""
    frame_ids: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_ids", tuple(self.frame_ids))
