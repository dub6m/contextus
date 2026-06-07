from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

_SYMBOL_RE = re.compile(r"\b[A-Za-z]+_[A-Za-z0-9]+\b")


@dataclass(frozen=True)
class TermCandidate:
    element_id: str
    text: str
    char_start: int
    char_end: int
    source_signal: str


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
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _term_id(normalized: str) -> str:
    return "term:" + re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")


def _symbol_term_candidates(element_id: str, text: str) -> list[TermCandidate]:
    candidates: list[TermCandidate] = []
    for match in _SYMBOL_RE.finditer(text or ""):
        candidates.append(
            TermCandidate(
                element_id=element_id,
                text=match.group(0),
                char_start=match.start(),
                char_end=match.end(),
                source_signal="symbol",
            )
        )
    return candidates


@dataclass(frozen=True)
class DocumentTermIndex:
    terms: Mapping[str, DocumentTerm]
    mentions_by_element_id: Mapping[str, tuple[TermMention, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "terms", MappingProxyType(dict(self.terms)))
        mentions_by_element = {key: tuple(value) for key, value in self.mentions_by_element_id.items()}
        object.__setattr__(self, "mentions_by_element_id", MappingProxyType(mentions_by_element))

    @classmethod
    def from_texts(cls, texts: list[tuple[str, str]]) -> "DocumentTermIndex":
        candidates: list[TermCandidate] = []
        for element_id, text in texts:
            candidates.extend(_symbol_term_candidates(element_id, text or ""))
        return cls.from_candidates(candidates)

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
            words = normalized.split()
            mention = TermMention(
                text=candidate.text,
                normalized=normalized,
                element_id=candidate.element_id,
                char_start=candidate.char_start,
                char_end=candidate.char_end,
                source_signal=candidate.source_signal,
                head=words[-1] if words else "",
                modifiers=tuple(words[:-1]),
            )
            mentions_by_key[normalized].append(mention)
            mentions_by_element[candidate.element_id].append(mention)

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
