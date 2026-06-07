from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

_TERM_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SYMBOL_RE = re.compile(r"\b[A-Za-z]+_[A-Za-z0-9]+\b")
_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_TERM_SEGMENT_RE = re.compile(r"[^.,;:()\[\]{}\-/+*=<>]+")
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
_TERM_BREAKERS = _STOP_TERMS | {
    "contain",
    "contains",
    "draw",
    "drawn",
    "has",
    "have",
    "split",
    "splits",
}
_SAFE_PLURAL_SUFFIXES = ("ates", "ides", "ines", "ints", "ows", "xes", "sses")
_VERBISH_STEMS = {
    "contain",
    "draw",
    "intersect",
    "split",
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
    cleaned = _ARTICLE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    parts = []
    for token in cleaned.split(" "):
        token = _singularize_term_token(token)
        parts.append(token)
    return " ".join(parts)


def _singularize_term_token(token: str) -> str:
    if token == "series":
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(_SAFE_PLURAL_SUFFIXES):
        return token[:-1]
    return token


def _term_id(normalized: str) -> str:
    return "term:" + re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")


def _looks_like_term_breaker(token: str) -> bool:
    lowered = token.lower()
    if lowered in _TERM_BREAKERS:
        return True
    if lowered.endswith("s") and lowered[:-1] in _VERBISH_STEMS:
        return True
    if lowered.endswith("ed") and lowered[:-2] in _VERBISH_STEMS:
        return True
    if lowered.endswith("ing") and lowered[:-3] in _VERBISH_STEMS:
        return True
    return False


def _candidate_term_spans(text: str) -> list[tuple[str, int, int, str]]:
    spans: list[tuple[str, int, int, str]] = []
    for match in _SYMBOL_RE.finditer(text or ""):
        spans.append((match.group(0), match.start(), match.end(), "symbol"))

    source = text or ""
    for segment in _TERM_SEGMENT_RE.finditer(source):
        spans.extend(_candidate_term_spans_in_segment(source, segment.start(), segment.end()))
    return spans


def _candidate_term_spans_in_segment(text: str, start: int, end: int) -> list[tuple[str, int, int, str]]:
    spans: list[tuple[str, int, int, str]] = []
    segment = text[start:end]
    tokens = list(_TERM_TOKEN_RE.finditer(segment))
    run: list[re.Match[str]] = []
    for token in tokens:
        if _looks_like_term_breaker(token.group(0)):
            spans.extend(_spans_from_token_run(text, run, start))
            run = []
            continue
        if run and not segment[run[-1].end() : token.start()].isspace():
            spans.extend(_spans_from_token_run(text, run, start))
            run = []
        run.append(token)
    spans.extend(_spans_from_token_run(text, run, start))
    return spans


def _spans_from_token_run(text: str, run: list[re.Match[str]], offset: int = 0) -> list[tuple[str, int, int, str]]:
    spans: list[tuple[str, int, int, str]] = []
    for width in (2, 1):
        for index in range(0, max(0, len(run) - width + 1)):
            group = run[index : index + width]
            words = [item.group(0) for item in group]
            lowered = [word.lower() for word in words]
            if any(_looks_like_term_breaker(word) for word in lowered):
                continue
            start = offset + group[0].start()
            end = offset + group[-1].end()
            spans.append((text[start:end], start, end, "nounish_span"))
    return spans


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
        mentions_by_key: dict[str, list[TermMention]] = defaultdict(list)
        mentions_by_element: dict[str, list[TermMention]] = defaultdict(list)
        seen: set[tuple[str, str, int, int]] = set()

        for element_id, text in texts:
            source_text = text or ""
            for surface, start, end, source_signal in _candidate_term_spans(source_text):
                normalized = normalize_term_text(surface)
                if not normalized or normalized in _STOP_TERMS:
                    continue
                key = (element_id, normalized, start, end)
                if key in seen:
                    continue
                seen.add(key)
                words = normalized.split()
                mention = TermMention(
                    text=source_text[start:end],
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
