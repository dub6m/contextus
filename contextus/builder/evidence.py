from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable
import math
import re

from contextus.ingestion.models import ExtractedDocument, ExtractedElement

from .preprocessor import ElementPreprocessor


SUPPORT_TYPES = {"figure", "image", "chart", "diagram", "flowchart", "table", "formula"}
HEADING_TYPES = {"title", "heading", "section_header"}


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)?")
_SENTENCE_RE = re.compile(r"[.!?]+(?:\s+|$)")
_FORMULA_SYMBOL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z](?:_[A-Za-z0-9]+)?(?:\([A-Za-z0-9_+\-*/ ]+\))?|O\([^)]+\))(?![A-Za-z0-9_])"
)
_NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,5})(?:\s+|$)")
_LIST_MARKER_RE = re.compile(r"^\s*((?:[-*\u2022])|(?:\d{1,3}[.)]?)|(?:[A-Za-z][.)])|(?:[ivxlcdmIVXLCDM]{1,6}[.)]))\s+")


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "to",
    "was",
    "were",
    "which",
    "with",
}


@dataclass(frozen=True)
class MarkerPattern:
    category: str
    role: str
    phrase: str
    direction_hint: str
    strength: float


MARKER_PATTERNS = [
    MarkerPattern("support", "visual_reference", "as shown", "support", 0.95),
    MarkerPattern("support", "visual_reference", "shown below", "support", 0.9),
    MarkerPattern("support", "visual_reference", "shown above", "support", 0.9),
    MarkerPattern("support", "visual_reference", "in the figure", "support", 0.9),
    MarkerPattern("support", "table_reference", "in the table", "support", 0.9),
    MarkerPattern("support", "formula_reference", "the formula", "support", 0.85),
    MarkerPattern("support", "equation_reference", "the equation", "support", 0.85),
    MarkerPattern("support", "example_reference", "for example", "either", 0.5),
    MarkerPattern("support", "visual_reference", "figure", "support", 0.7),
    MarkerPattern("support", "table_reference", "table", "support", 0.7),
    MarkerPattern("support", "formula_reference", "formula", "support", 0.7),
    MarkerPattern("support", "diagram_reference", "diagram", "support", 0.7),
    MarkerPattern("support", "chart_reference", "chart", "support", 0.7),
    MarkerPattern("support", "equation_reference", "equation", "support", 0.7),
    MarkerPattern("reference", "backward_pronoun", "the former", "previous", 0.9),
    MarkerPattern("reference", "backward_pronoun", "the latter", "previous", 0.9),
    MarkerPattern("reference", "forward_reference", "the following", "next", 0.85),
    MarkerPattern("reference", "forward_reference", "as follows", "next", 0.85),
    MarkerPattern("reference", "backward_pronoun", "this method", "previous", 0.8),
    MarkerPattern("reference", "backward_pronoun", "this process", "previous", 0.8),
    MarkerPattern("reference", "backward_pronoun", "this", "previous", 0.65),
    MarkerPattern("reference", "backward_pronoun", "that", "previous", 0.55),
    MarkerPattern("reference", "backward_pronoun", "these", "previous", 0.65),
    MarkerPattern("reference", "backward_pronoun", "those", "previous", 0.65),
    MarkerPattern("reference", "backward_pronoun", "it", "previous", 0.55),
    MarkerPattern("reference", "backward_pronoun", "they", "previous", 0.55),
    MarkerPattern("reference", "backward_pronoun", "such", "previous", 0.5),
    MarkerPattern("reference", "spatial_reference", "above", "previous", 0.55),
    MarkerPattern("reference", "spatial_reference", "below", "next", 0.55),
    MarkerPattern("discourse", "causal", "therefore", "previous", 0.7),
    MarkerPattern("discourse", "causal", "thus", "previous", 0.65),
    MarkerPattern("discourse", "causal", "hence", "previous", 0.65),
    MarkerPattern("discourse", "causal", "because", "previous", 0.6),
    MarkerPattern("discourse", "contrast", "however", "previous", 0.65),
    MarkerPattern("discourse", "contrast", "in contrast", "previous", 0.75),
    MarkerPattern("discourse", "contrast", "whereas", "previous", 0.55),
    MarkerPattern("discourse", "sequence", "next", "previous", 0.45),
    MarkerPattern("discourse", "sequence", "finally", "previous", 0.45),
    MarkerPattern("discourse", "sequence", "then", "previous", 0.45),
]


@dataclass(frozen=True)
class MarkerSpan:
    category: str
    role: str
    text: str
    start: int
    end: int
    direction_hint: str
    strength: float


@dataclass(frozen=True)
class ListSignal:
    marker: str
    marker_type: str
    indent: float
    run_id: str | None = None


@dataclass(frozen=True)
class HeadingCandidate:
    element_id: str
    text: str
    level: int | None
    distance: int
    confidence: float


@dataclass(frozen=True)
class ElementSignalRecord:
    element_id: str
    element_index: int
    element_type: str
    page_number: int
    order: int
    bbox: tuple[float, float, float, float]
    confidence: float | None
    asset_path: str | None
    asset_link_exists: bool
    text: str
    token_count: int
    char_count: int
    word_count: int
    content_token_count: int
    unique_content_terms: list[str]
    lexical_keyword_density: float
    boilerplate_score: float
    is_heading: bool
    heading_level: int | None
    heading_path: list[HeadingCandidate] = field(default_factory=list)
    list_signal: ListSignal | None = None
    markers: list[MarkerSpan] = field(default_factory=list)
    formula_symbols: list[str] = field(default_factory=list)
    sentence_count: int = 0


@dataclass(frozen=True)
class ContextAttachment:
    attachment_type: str
    source_element_id: str
    target_element_ids: list[str]
    score: float
    token_cost: int
    marginal_value_per_token: float
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceHandle:
    handle_id: str
    handle_index: int
    core_element_ids: list[str]
    core_text: str
    page_numbers: list[int]
    feature_scores: dict[str, float]
    risk_flags: list[str]
    attachments: list[ContextAttachment] = field(default_factory=list)


@dataclass(frozen=True)
class ContextPackageSegment:
    role: str
    element_id: str
    text: str
    token_count: int
    attachment_type: str | None = None
    attachment_score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceContextPackage:
    package_id: str
    handle_id: str
    core_element_ids: list[str]
    context_element_ids: list[str]
    included_attachment_types: list[str]
    package_text: str
    retrieval_text: str
    token_count: int
    context_token_count: int
    package_scores: dict[str, float]
    risk_flags: list[str]
    segments: list[ContextPackageSegment] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidencePipelineResult:
    document_id: str
    source_name: str
    signals: list[ElementSignalRecord]
    handles: list[EvidenceHandle]
    summary: dict[str, Any]
    packages: list[EvidenceContextPackage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceHandleBuilder:
    """Build promptless evidence handles and context-candidate signals.

    This is a parallel ingestion path. It deliberately does not mutate the existing
    Step 5/Step 6 chunker or decide final graph nodes.
    """

    def __init__(
        self,
        preprocessor: ElementPreprocessor | None = None,
        *,
        max_context_tokens: int = 220,
    ) -> None:
        self.preprocessor = preprocessor or ElementPreprocessor()
        self._token_counter = _TokenCounter()
        self.max_context_tokens = max(0, int(max_context_tokens))

    def build(self, document: ExtractedDocument) -> EvidencePipelineResult:
        elements = self._sorted_elements(document)
        texts = [self.preprocessor.to_text(element) for element in elements]
        normalized_counts = Counter(self._normalize_text(text) for text in texts if text.strip())
        signals = self._build_signal_records(elements, texts, normalized_counts)
        self._assign_list_runs(signals)
        handles = self._build_handles(signals)
        packages = self._build_context_packages(signals, handles)
        return EvidencePipelineResult(
            document_id=document.id,
            source_name=document.source_name,
            signals=signals,
            handles=handles,
            summary=self._summary(signals, handles, packages),
            packages=packages,
        )

    def _sorted_elements(self, document: ExtractedDocument) -> list[ExtractedElement]:
        elements = [element for page in document.pages for element in page.elements]
        return sorted(elements, key=lambda item: (item.page_number, item.order))

    def _build_signal_records(
        self,
        elements: list[ExtractedElement],
        texts: list[str],
        normalized_counts: Counter[str],
    ) -> list[ElementSignalRecord]:
        records: list[ElementSignalRecord] = []
        heading_stack: list[tuple[int | None, ElementSignalRecord]] = []

        for index, (element, text) in enumerate(zip(elements, texts)):
            element_type = (element.type or "").strip().lower()
            is_heading = self._is_heading(element_type, text)
            heading_level = self._heading_level(text) if is_heading else None
            if is_heading and heading_level is not None:
                heading_stack = [
                    (level, record)
                    for level, record in heading_stack
                    if level is None or level < heading_level
                ]

            heading_path = [
                HeadingCandidate(
                    element_id=record.element_id,
                    text=record.text,
                    level=level,
                    distance=index - record.element_index,
                    confidence=self._heading_path_confidence(index - record.element_index, level),
                )
                for level, record in heading_stack[-3:]
            ]
            record = self._signal_record(
                element=element,
                element_index=index,
                element_type=element_type,
                text=text,
                is_heading=is_heading,
                heading_level=heading_level,
                heading_path=heading_path,
                boilerplate_score=self._boilerplate_score(text, normalized_counts),
            )
            records.append(record)
            if is_heading:
                heading_stack.append((heading_level, record))

        return records

    def _signal_record(
        self,
        *,
        element: ExtractedElement,
        element_index: int,
        element_type: str,
        text: str,
        is_heading: bool,
        heading_level: int | None,
        heading_path: list[HeadingCandidate],
        boilerplate_score: float,
    ) -> ElementSignalRecord:
        words = self._tokens(text)
        content_terms = sorted(set(self._content_terms(words)))
        token_count = self._token_counter.count(text)
        content_token_count = len([token for token in words if token.lower() in content_terms])
        markers = self._markers(text)
        formula_symbols = self._formula_symbols(text, element_type)
        lexical_density = self._lexical_keyword_density(
            word_count=len(words),
            content_token_count=content_token_count,
            unique_count=len(content_terms),
            marker_count=len(markers),
            formula_count=len(formula_symbols),
            boilerplate_score=boilerplate_score,
        )
        return ElementSignalRecord(
            element_id=element.id,
            element_index=element_index,
            element_type=element_type,
            page_number=element.page_number,
            order=element.order,
            bbox=tuple(float(value) for value in element.bbox),
            confidence=element.confidence,
            asset_path=element.asset_path,
            asset_link_exists=bool(element.asset_path),
            text=text,
            token_count=token_count,
            char_count=len(text),
            word_count=len(words),
            content_token_count=content_token_count,
            unique_content_terms=content_terms,
            lexical_keyword_density=lexical_density,
            boilerplate_score=boilerplate_score,
            is_heading=is_heading,
            heading_level=heading_level,
            heading_path=heading_path,
            list_signal=self._list_signal(text, element.bbox),
            markers=markers,
            formula_symbols=formula_symbols,
            sentence_count=self._sentence_count(text),
        )

    def _build_handles(self, signals: list[ElementSignalRecord]) -> list[EvidenceHandle]:
        handles = []
        for index, signal in enumerate(signals):
            attachments = self._attachments(signals, index)
            feature_scores = self._feature_scores(signals, index, attachments)
            risk_flags = self._risk_flags(signal, feature_scores)
            handles.append(
                EvidenceHandle(
                    handle_id=f"evidence-handle-{index:05d}",
                    handle_index=index,
                    core_element_ids=[signal.element_id],
                    core_text=signal.text,
                    page_numbers=[signal.page_number],
                    feature_scores=feature_scores,
                    risk_flags=risk_flags,
                    attachments=attachments,
                )
            )
        return handles

    def _attachments(self, signals: list[ElementSignalRecord], index: int) -> list[ContextAttachment]:
        signal = signals[index]
        attachments: list[ContextAttachment] = []

        if signal.heading_path and not signal.is_heading:
            heading = signal.heading_path[-1]
            target = self._record_by_id(signals, heading.element_id)
            if target is not None:
                score = _clamp01(0.35 + self._heading_dependency(signal) * 0.5 + heading.confidence * 0.15)
                attachments.append(
                    self._attachment(
                        attachment_type="heading",
                        source=signal,
                        targets=[target],
                        score=score,
                        reasons=["nearest heading candidate", f"heading_dependency={self._heading_dependency(signal):.2f}"],
                    )
                )

        if index > 0:
            previous = signals[index - 1]
            score = self._neighbor_score(signal, previous, direction="previous")
            if score >= 0.18:
                attachments.append(
                    self._attachment(
                        attachment_type="previous",
                        source=signal,
                        targets=[previous],
                        score=score,
                        reasons=self._neighbor_reasons(signal, previous, direction="previous"),
                    )
                )

        if index + 1 < len(signals):
            next_record = signals[index + 1]
            score = self._neighbor_score(signal, next_record, direction="next")
            if score >= 0.18:
                attachments.append(
                    self._attachment(
                        attachment_type="next",
                        source=signal,
                        targets=[next_record],
                        score=score,
                        reasons=self._neighbor_reasons(signal, next_record, direction="next"),
                    )
                )

        if signal.element_type in SUPPORT_TYPES:
            attachments.extend(self._caption_candidates(signals, index))
        elif self._support_marker_strength(signal) > 0.0:
            support = self._nearest_support(signals, index)
            if support is not None:
                distance = abs(signal.element_index - support.element_index)
                score = _clamp01(0.45 + self._support_marker_strength(signal) * 0.35 + max(0.0, 0.2 - distance * 0.03))
                attachments.append(
                    self._attachment(
                        attachment_type="support",
                        source=signal,
                        targets=[support],
                        score=score,
                        reasons=["text contains support marker", f"distance={distance}"],
                    )
                )

        if signal.list_signal is not None:
            siblings = self._list_siblings(signals, index)
            if siblings:
                score = _clamp01(0.35 + 0.1 * min(len(siblings), 3))
                attachments.append(
                    self._attachment(
                        attachment_type="list_siblings",
                        source=signal,
                        targets=siblings,
                        score=score,
                        reasons=["same local list run"],
                    )
                )

        return sorted(attachments, key=lambda item: item.score, reverse=True)

    def _attachment(
        self,
        *,
        attachment_type: str,
        source: ElementSignalRecord,
        targets: list[ElementSignalRecord],
        score: float,
        reasons: list[str],
    ) -> ContextAttachment:
        token_cost = sum(target.token_count for target in targets)
        noise = self._attachment_noise(source, targets)
        useful_gain = max(0.0, score - noise)
        return ContextAttachment(
            attachment_type=attachment_type,
            source_element_id=source.element_id,
            target_element_ids=[target.element_id for target in targets],
            score=round(_clamp01(score), 4),
            token_cost=token_cost,
            marginal_value_per_token=round(useful_gain / max(1, token_cost), 6),
            reasons=[*reasons, f"noise_penalty={noise:.2f}"],
        )

    def _feature_scores(
        self,
        signals: list[ElementSignalRecord],
        index: int,
        attachments: list[ContextAttachment],
    ) -> dict[str, float]:
        signal = signals[index]
        reference_strength = self._reference_marker_strength(signal)
        support_strength = self._support_marker_strength(signal)
        reference_attachment = max(
            [attachment.score for attachment in attachments if attachment.attachment_type in {"previous", "heading"}],
            default=0.0,
        )
        support_attachment = max(
            [attachment.score for attachment in attachments if attachment.attachment_type in {"support", "caption"}],
            default=0.0,
        )
        reference_closure = 1.0 if reference_strength == 0 else _clamp01(reference_attachment / max(0.1, reference_strength))
        if signal.element_type in SUPPORT_TYPES:
            support_closure = _clamp01(0.45 + support_attachment * 0.55)
        elif support_strength > 0:
            support_closure = _clamp01(support_attachment / max(0.1, support_strength))
        else:
            support_closure = 1.0
        citation = self._citation_completeness(signal, attachments)
        noise = self._noise_risk(signal, attachments)
        return {
            "reference_closure": round(reference_closure, 4),
            "support_closure": round(support_closure, 4),
            "heading_dependency": round(self._heading_dependency(signal), 4),
            "lexical_retrievability": round(signal.lexical_keyword_density, 4),
            "noise_risk": round(noise, 4),
            "citation_completeness": round(citation, 4),
            "atomicity_risk": round(self._atomicity_risk(signal), 4),
            "best_marginal_context_value": round(
                max([attachment.marginal_value_per_token for attachment in attachments], default=0.0),
                6,
            ),
        }

    def _risk_flags(self, signal: ElementSignalRecord, scores: dict[str, float]) -> list[str]:
        flags: list[str] = []
        if scores["reference_closure"] < 0.6:
            flags.append("reference_closure_low")
        if scores["support_closure"] < 0.65:
            flags.append("support_closure_low")
        if scores["lexical_retrievability"] < 0.25:
            flags.append("low_lexical_retrievability")
        if scores["heading_dependency"] >= 0.6:
            flags.append("heading_dependent")
        if scores["noise_risk"] >= 0.55:
            flags.append("noise_risk")
        if scores["atomicity_risk"] >= 0.55:
            flags.append("atomicity_risk")
        if signal.element_type in SUPPORT_TYPES and not signal.asset_link_exists:
            flags.append("support_without_asset_link")
        if signal.boilerplate_score >= 0.4:
            flags.append("boilerplate_like")
        return flags

    def _build_context_packages(
        self,
        signals: list[ElementSignalRecord],
        handles: list[EvidenceHandle],
    ) -> list[EvidenceContextPackage]:
        signal_by_id = {signal.element_id: signal for signal in signals}
        packages: list[EvidenceContextPackage] = []
        for handle in handles:
            core = signal_by_id[handle.core_element_ids[0]]
            selected = self._select_context_attachments(core, handle, signal_by_id)
            segments = self._package_segments(core, selected, signal_by_id)
            package_text = self._render_package_text(segments)
            retrieval_text = self._render_retrieval_text(segments, handle)
            context_ids = [segment.element_id for segment in segments if segment.role != "core"]
            token_count = sum(segment.token_count for segment in segments)
            context_token_count = sum(segment.token_count for segment in segments if segment.role != "core")
            package_scores = self._package_scores(core, handle, selected, token_count, context_token_count)
            risk_flags = self._package_risk_flags(handle, package_scores, context_token_count)
            packages.append(
                EvidenceContextPackage(
                    package_id=f"context-package-{handle.handle_index:05d}",
                    handle_id=handle.handle_id,
                    core_element_ids=list(handle.core_element_ids),
                    context_element_ids=context_ids,
                    included_attachment_types=[attachment.attachment_type for attachment in selected],
                    package_text=package_text,
                    retrieval_text=retrieval_text,
                    token_count=token_count,
                    context_token_count=context_token_count,
                    package_scores=package_scores,
                    risk_flags=risk_flags,
                    segments=segments,
                    provenance={
                        "element_ids": [segment.element_id for segment in segments],
                        "page_numbers": sorted({signal_by_id[segment.element_id].page_number for segment in segments}),
                        "asset_paths": [
                            signal_by_id[segment.element_id].asset_path
                            for segment in segments
                            if signal_by_id[segment.element_id].asset_path
                        ],
                    },
                )
            )
        return packages

    def _select_context_attachments(
        self,
        core: ElementSignalRecord,
        handle: EvidenceHandle,
        signal_by_id: dict[str, ElementSignalRecord],
    ) -> list[ContextAttachment]:
        selected: list[ContextAttachment] = []
        used_ids = {core.element_id}
        remaining_budget = self.max_context_tokens
        candidates = sorted(
            handle.attachments,
            key=lambda attachment: (
                self._attachment_priority(core, handle, attachment),
                attachment.score,
                attachment.marginal_value_per_token,
            ),
            reverse=True,
        )
        for attachment in candidates:
            target_records = [
                signal_by_id[element_id]
                for element_id in attachment.target_element_ids
                if element_id in signal_by_id and element_id not in used_ids
            ]
            if not target_records:
                continue
            if self._targets_duplicate_core(core, target_records):
                continue
            token_cost = sum(record.token_count for record in target_records)
            if token_cost > remaining_budget and not self._is_must_keep_attachment(core, handle, attachment):
                continue
            if not self._should_select_attachment(core, handle, attachment):
                continue
            selected.append(attachment)
            remaining_budget -= token_cost
            used_ids.update(record.element_id for record in target_records)
        return selected

    def _attachment_priority(
        self,
        core: ElementSignalRecord,
        handle: EvidenceHandle,
        attachment: ContextAttachment,
    ) -> float:
        base = {
            "support": 1.0,
            "caption": 0.9,
            "heading": 0.82,
            "previous": 0.75,
            "list_siblings": 0.55,
            "next": 0.48,
        }.get(attachment.attachment_type, 0.3)
        if attachment.attachment_type == "heading" and handle.feature_scores.get("heading_dependency", 0.0) >= 0.45:
            base += 0.2
        if attachment.attachment_type == "heading" and core.element_type in SUPPORT_TYPES:
            base += 0.25
        if attachment.attachment_type == "previous" and self._reference_marker_strength(core) > 0.0:
            base += 0.25
        if attachment.attachment_type == "previous" and core.element_type in SUPPORT_TYPES:
            base -= 0.15
        if attachment.attachment_type == "support" and self._support_marker_strength(core) > 0.0:
            base += 0.25
        if attachment.attachment_type == "next" and core.is_heading and handle.feature_scores.get("lexical_retrievability", 1.0) < 0.25:
            base += 0.12
        return base

    def _is_must_keep_attachment(
        self,
        core: ElementSignalRecord,
        handle: EvidenceHandle,
        attachment: ContextAttachment,
    ) -> bool:
        return (
            attachment.attachment_type == "support"
            and self._support_marker_strength(core) > 0.0
        ) or (
            attachment.attachment_type == "previous"
            and self._reference_marker_strength(core) >= 0.65
        ) or (
            attachment.attachment_type == "heading"
            and handle.feature_scores.get("heading_dependency", 0.0) >= 0.7
        )

    def _should_select_attachment(
        self,
        core: ElementSignalRecord,
        handle: EvidenceHandle,
        attachment: ContextAttachment,
    ) -> bool:
        if self._is_must_keep_attachment(core, handle, attachment):
            return True
        if attachment.attachment_type == "heading":
            if core.element_type in SUPPORT_TYPES:
                return attachment.score >= 0.5
            return (
                attachment.score >= 0.55
                and (
                    handle.feature_scores.get("heading_dependency", 0.0) >= 0.35
                    or handle.feature_scores.get("lexical_retrievability", 1.0) < 0.35
                    or core.element_type in SUPPORT_TYPES
                )
            )
        if attachment.attachment_type == "previous":
            if core.element_type in SUPPORT_TYPES:
                return attachment.score >= 0.55
            return attachment.score >= 0.5 or attachment.marginal_value_per_token >= 0.035
        if attachment.attachment_type == "next":
            if core.boilerplate_score >= 0.4 and attachment.score < 0.42:
                return (
                    core.is_heading
                    and core.word_count >= 2
                    and core.boilerplate_score < 0.8
                    and attachment.score >= 0.25
                    and attachment.token_cost <= 80
                )
            return attachment.score >= 0.55 or (
                core.is_heading
                and core.word_count >= 2
                and (
                    handle.feature_scores.get("lexical_retrievability", 1.0) < 0.55
                    or core.boilerplate_score < 0.4
                )
                and attachment.score >= 0.25
                and attachment.token_cost <= 80
            )
        if attachment.attachment_type == "caption":
            return attachment.score >= 0.45 or (core.element_type in SUPPORT_TYPES and attachment.score >= 0.38)
        if attachment.attachment_type == "support":
            return attachment.score >= 0.45
        if attachment.attachment_type == "list_siblings":
            return attachment.score >= 0.45
        return attachment.score >= 0.55

    def _targets_duplicate_core(
        self,
        core: ElementSignalRecord,
        targets: list[ElementSignalRecord],
    ) -> bool:
        core_text = self._normalize_text(core.text)
        if not core_text:
            return False
        return all(self._normalize_text(target.text) == core_text for target in targets)

    def _package_segments(
        self,
        core: ElementSignalRecord,
        selected: list[ContextAttachment],
        signal_by_id: dict[str, ElementSignalRecord],
    ) -> list[ContextPackageSegment]:
        segments_by_id: dict[str, ContextPackageSegment] = {
            core.element_id: ContextPackageSegment(
                role="core",
                element_id=core.element_id,
                text=core.text,
                token_count=core.token_count,
            )
        }
        for attachment in selected:
            role = self._segment_role(attachment.attachment_type)
            for target_id in attachment.target_element_ids:
                target = signal_by_id.get(target_id)
                if target is None or target_id in segments_by_id:
                    continue
                segments_by_id[target_id] = ContextPackageSegment(
                    role=role,
                    element_id=target_id,
                    text=target.text,
                    token_count=target.token_count,
                    attachment_type=attachment.attachment_type,
                    attachment_score=attachment.score,
                    reasons=list(attachment.reasons),
                )
        return sorted(
            segments_by_id.values(),
            key=lambda segment: signal_by_id[segment.element_id].element_index,
        )

    def _segment_role(self, attachment_type: str) -> str:
        return {
            "heading": "heading",
            "previous": "previous_context",
            "next": "next_context",
            "support": "support",
            "caption": "caption",
            "list_siblings": "sibling_context",
        }.get(attachment_type, "context")

    def _render_package_text(self, segments: list[ContextPackageSegment]) -> str:
        lines: list[str] = []
        for segment in segments:
            label = segment.role.replace("_", " ").title()
            lines.extend([f"[{label} | {segment.element_id}]", segment.text.strip(), ""])
        return "\n".join(lines).strip()

    def _render_retrieval_text(
        self,
        segments: list[ContextPackageSegment],
        handle: EvidenceHandle,
    ) -> str:
        parts = []
        for segment in segments:
            if segment.role == "core":
                parts.append(f"Evidence: {segment.text}")
            elif segment.role in {"heading", "caption", "support"}:
                parts.append(f"{segment.role.replace('_', ' ').title()}: {segment.text}")
        if handle.risk_flags:
            parts.append("Risk flags: " + ", ".join(handle.risk_flags))
        return "\n".join(part.strip() for part in parts if part.strip())

    def _package_scores(
        self,
        core: ElementSignalRecord,
        handle: EvidenceHandle,
        selected: list[ContextAttachment],
        token_count: int,
        context_token_count: int,
    ) -> dict[str, float]:
        selected_types = {attachment.attachment_type for attachment in selected}
        reference_closure = handle.feature_scores.get("reference_closure", 1.0)
        if "previous" in selected_types or "heading" in selected_types:
            reference_closure = max(reference_closure, 0.9 if self._reference_marker_strength(core) else reference_closure)
        support_closure = handle.feature_scores.get("support_closure", 1.0)
        if "support" in selected_types or "caption" in selected_types:
            support_closure = max(support_closure, 0.88)
        if core.element_type in SUPPORT_TYPES and "heading" in selected_types:
            support_closure = max(support_closure, 0.68)
        retrieval_lift = self._retrieval_lift(core, selected)
        cost_penalty = min(0.35, context_token_count / max(1, self.max_context_tokens * 2))
        noise = min(1.0, handle.feature_scores.get("noise_risk", 0.0) + cost_penalty * 0.35)
        package_score = _clamp01(
            reference_closure * 0.22
            + support_closure * 0.22
            + handle.feature_scores.get("citation_completeness", 0.0) * 0.2
            + handle.feature_scores.get("lexical_retrievability", 0.0) * 0.16
            + retrieval_lift * 0.12
            - noise * 0.12
            - cost_penalty * 0.08
        )
        return {
            "package_score": round(package_score, 4),
            "reference_closure": round(_clamp01(reference_closure), 4),
            "support_closure": round(_clamp01(support_closure), 4),
            "retrieval_lift": round(_clamp01(retrieval_lift), 4),
            "noise_risk": round(_clamp01(noise), 4),
            "context_cost_ratio": round(context_token_count / max(1, token_count), 4),
        }

    def _retrieval_lift(self, core: ElementSignalRecord, selected: list[ContextAttachment]) -> float:
        lift = 0.0
        for attachment in selected:
            if attachment.attachment_type == "heading":
                lift += 0.18
            elif attachment.attachment_type in {"support", "caption"}:
                lift += 0.12
            elif attachment.attachment_type == "previous" and self._reference_marker_strength(core) > 0.0:
                lift += 0.14
            elif attachment.attachment_type == "list_siblings":
                lift += 0.08
            elif attachment.attachment_type == "next":
                lift += 0.05
            lift += min(0.08, attachment.marginal_value_per_token * 1.5)
        return _clamp01(lift)

    def _package_risk_flags(
        self,
        handle: EvidenceHandle,
        package_scores: dict[str, float],
        context_token_count: int,
    ) -> list[str]:
        flags = [
            flag
            for flag in handle.risk_flags
            if flag not in {"heading_dependent", "reference_closure_low", "support_closure_low"}
        ]
        if package_scores["reference_closure"] < 0.65:
            flags.append("package_reference_closure_low")
        if package_scores["support_closure"] < 0.65:
            flags.append("package_support_closure_low")
        if package_scores["package_score"] < 0.45:
            flags.append("package_score_low")
        if context_token_count > self.max_context_tokens:
            flags.append("context_budget_exceeded")
        return flags

    def _summary(
        self,
        signals: list[ElementSignalRecord],
        handles: list[EvidenceHandle],
        packages: list[EvidenceContextPackage],
    ) -> dict[str, Any]:
        marker_counts: Counter[str] = Counter()
        attachment_counts: Counter[str] = Counter()
        risk_counts: Counter[str] = Counter()
        package_attachment_counts: Counter[str] = Counter()
        package_risk_counts: Counter[str] = Counter()
        for signal in signals:
            marker_counts.update(marker.category for marker in signal.markers)
        for handle in handles:
            attachment_counts.update(attachment.attachment_type for attachment in handle.attachments)
            risk_counts.update(handle.risk_flags)
        for package in packages:
            package_attachment_counts.update(package.included_attachment_types)
            package_risk_counts.update(package.risk_flags)
        return {
            "element_count": len(signals),
            "handle_count": len(handles),
            "package_count": len(packages),
            "avg_tokens_per_element": round(
                sum(signal.token_count for signal in signals) / len(signals),
                2,
            )
            if signals
            else 0.0,
            "avg_tokens_per_package": round(
                sum(package.token_count for package in packages) / len(packages),
                2,
            )
            if packages
            else 0.0,
            "avg_context_tokens_per_package": round(
                sum(package.context_token_count for package in packages) / len(packages),
                2,
            )
            if packages
            else 0.0,
            "marker_counts": dict(marker_counts),
            "attachment_counts": dict(attachment_counts),
            "risk_counts": dict(risk_counts),
            "package_attachment_counts": dict(package_attachment_counts),
            "package_risk_counts": dict(package_risk_counts),
            "support_elements": sum(1 for signal in signals if signal.element_type in SUPPORT_TYPES),
            "heading_elements": sum(1 for signal in signals if signal.is_heading),
        }

    def _markers(self, text: str) -> list[MarkerSpan]:
        matches: list[MarkerSpan] = []
        occupied: list[tuple[int, int]] = []
        for pattern in sorted(MARKER_PATTERNS, key=lambda item: len(item.phrase), reverse=True):
            regex = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(pattern.phrase)}(?![A-Za-z0-9_])", re.IGNORECASE)
            for match in regex.finditer(text):
                span = (match.start(), match.end())
                if any(not (span[1] <= start or span[0] >= end) for start, end in occupied):
                    continue
                occupied.append(span)
                matches.append(
                    MarkerSpan(
                        category=pattern.category,
                        role=pattern.role,
                        text=match.group(0),
                        start=span[0],
                        end=span[1],
                        direction_hint=pattern.direction_hint,
                        strength=pattern.strength,
                    )
                )
        return sorted(matches, key=lambda item: item.start)

    def _neighbor_score(
        self,
        source: ElementSignalRecord,
        target: ElementSignalRecord,
        *,
        direction: str,
    ) -> float:
        marker_strength = sum(
            marker.strength
            for marker in source.markers
            if marker.direction_hint == direction or (direction == "previous" and marker.category == "discourse")
        )
        overlap = self._term_overlap(source, target)
        same_page = 0.12 if source.page_number == target.page_number else 0.0
        list_bonus = 0.15 if self._same_list_run(source, target) else 0.0
        continuation = 0.15 if direction == "next" and self._ends_mid_thought(source.text) else 0.0
        return _clamp01(marker_strength * 0.55 + overlap * 0.3 + same_page + list_bonus + continuation)

    def _neighbor_reasons(
        self,
        source: ElementSignalRecord,
        target: ElementSignalRecord,
        *,
        direction: str,
    ) -> list[str]:
        reasons = [f"{direction} neighbor"]
        overlap = self._term_overlap(source, target)
        if overlap > 0:
            reasons.append(f"term_overlap={overlap:.2f}")
        if source.page_number == target.page_number:
            reasons.append("same_page")
        if self._same_list_run(source, target):
            reasons.append("same_list_run")
        if direction == "next" and self._ends_mid_thought(source.text):
            reasons.append("source_ends_mid_thought")
        marker_roles = sorted({marker.role for marker in source.markers if marker.direction_hint == direction})
        reasons.extend(marker_roles)
        return reasons

    def _caption_candidates(self, signals: list[ElementSignalRecord], index: int) -> list[ContextAttachment]:
        source = signals[index]
        candidates: list[ContextAttachment] = []
        for offset in (-2, -1, 1, 2):
            target_index = index + offset
            if target_index < 0 or target_index >= len(signals):
                continue
            target = signals[target_index]
            if target.element_type in SUPPORT_TYPES or target.is_heading:
                continue
            if target.page_number != source.page_number:
                continue
            proximity = self._layout_proximity(source, target)
            text_shape = self._caption_text_shape_score(target)
            overlap = self._term_overlap(source, target)
            if proximity < 0.08 and self._support_marker_strength(target) == 0.0 and overlap < 0.08:
                continue
            score = _clamp01(0.25 + proximity * 0.35 + text_shape * 0.3 + overlap * 0.2)
            if score < 0.3:
                continue
            candidates.append(
                self._attachment(
                    attachment_type="caption",
                    source=source,
                    targets=[target],
                    score=score,
                    reasons=[f"nearby_text_offset={offset}", f"layout_proximity={proximity:.2f}", f"text_shape={text_shape:.2f}"],
                )
            )
        return candidates

    def _nearest_support(self, signals: list[ElementSignalRecord], index: int) -> ElementSignalRecord | None:
        source = signals[index]
        candidates = [
            signal
            for signal in signals
            if signal.element_type in SUPPORT_TYPES and signal.page_number == source.page_number
        ]
        if not candidates:
            candidates = [signal for signal in signals if signal.element_type in SUPPORT_TYPES]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                abs(item.element_index - source.element_index),
                -self._layout_proximity(source, item),
            ),
        )

    def _list_siblings(self, signals: list[ElementSignalRecord], index: int) -> list[ElementSignalRecord]:
        source = signals[index]
        if source.list_signal is None or source.list_signal.run_id is None:
            return []
        siblings = []
        for offset in (-1, 1):
            candidate_index = index + offset
            if candidate_index < 0 or candidate_index >= len(signals):
                continue
            candidate = signals[candidate_index]
            if self._same_list_run(source, candidate):
                siblings.append(candidate)
        return siblings

    def _assign_list_runs(self, signals: list[ElementSignalRecord]) -> None:
        current_key: tuple[int, str, int] | None = None
        current_run = 0
        for signal in signals:
            list_signal = signal.list_signal
            if list_signal is None:
                current_key = None
                continue
            key = (signal.page_number, list_signal.marker_type, round(list_signal.indent / 12))
            if key != current_key:
                current_run += 1
                current_key = key
            object.__setattr__(
                signal,
                "list_signal",
                ListSignal(
                    marker=list_signal.marker,
                    marker_type=list_signal.marker_type,
                    indent=list_signal.indent,
                    run_id=f"list-run-{current_run:05d}",
                ),
            )

    def _is_heading(self, element_type: str, text: str) -> bool:
        if element_type in HEADING_TYPES:
            return True
        words = self._tokens(text)
        return bool(words) and len(words) <= 8 and text.rstrip().istitle()

    def _heading_level(self, text: str) -> int | None:
        match = _NUMBERED_HEADING_RE.match(text)
        if match:
            return match.group(1).count(".") + 1
        return None

    def _heading_path_confidence(self, distance: int, level: int | None) -> float:
        distance_score = max(0.2, 1.0 - (distance / 24.0))
        level_score = 0.9 if level is not None else 0.65
        return _clamp01((distance_score * 0.7) + (level_score * 0.3))

    def _list_signal(self, text: str, bbox: tuple[float, float, float, float]) -> ListSignal | None:
        match = _LIST_MARKER_RE.match(text)
        if not match:
            return None
        marker = match.group(1)
        if marker in {"-", "*", "\u2022"}:
            marker_type = "bullet"
        elif marker[0].isdigit():
            marker_type = "numbered"
        elif re.match(r"^[ivxlcdmIVXLCDM]", marker):
            marker_type = "roman"
        else:
            marker_type = "alpha"
        return ListSignal(marker=marker, marker_type=marker_type, indent=float(bbox[0]))

    def _formula_symbols(self, text: str, element_type: str) -> list[str]:
        if element_type != "formula" and not any(symbol in text for symbol in ("=", "(", ")", "_", "^")):
            return []
        symbols = sorted(set(match.group(0) for match in _FORMULA_SYMBOL_RE.finditer(text)))
        return [symbol for symbol in symbols if symbol.lower() not in STOPWORDS][:30]

    def _lexical_keyword_density(
        self,
        *,
        word_count: int,
        content_token_count: int,
        unique_count: int,
        marker_count: int,
        formula_count: int,
        boilerplate_score: float,
    ) -> float:
        if word_count <= 0:
            return 0.0
        content_ratio = content_token_count / max(1, word_count)
        unique_bonus = min(0.35, unique_count / 12.0)
        formula_bonus = min(0.15, formula_count / 30.0)
        marker_penalty = min(0.25, marker_count / max(4.0, word_count))
        return round(_clamp01(content_ratio * 0.55 + unique_bonus + formula_bonus - marker_penalty), 4)

    def _boilerplate_score(self, text: str, counts: Counter[str]) -> float:
        normalized = self._normalize_text(text)
        if not normalized:
            return 0.0
        repeat_count = counts.get(normalized, 0)
        if repeat_count <= 1:
            return 0.0
        words = len(self._tokens(text))
        repetition = min(1.0, (repeat_count - 1) / 5.0)
        short_bonus = 0.25 if words <= 8 else 0.0
        return _clamp01(repetition + short_bonus)

    def _heading_dependency(self, signal: ElementSignalRecord) -> float:
        if signal.is_heading:
            return 0.0
        low_lexical = max(0.0, 0.45 - signal.lexical_keyword_density)
        short_body = 0.2 if signal.word_count <= 12 else 0.0
        marker_strength = min(0.35, self._reference_marker_strength(signal) * 0.25)
        list_bonus = 0.15 if signal.list_signal is not None else 0.0
        lowercase_start = 0.12 if signal.text[:1].islower() else 0.0
        heading_available = 0.15 if signal.heading_path else -0.1
        return _clamp01(low_lexical + short_body + marker_strength + list_bonus + lowercase_start + heading_available)

    def _reference_marker_strength(self, signal: ElementSignalRecord) -> float:
        return min(1.0, sum(marker.strength for marker in signal.markers if marker.category == "reference"))

    def _support_marker_strength(self, signal: ElementSignalRecord) -> float:
        return min(1.0, sum(marker.strength for marker in signal.markers if marker.category == "support"))

    def _noise_risk(self, signal: ElementSignalRecord, attachments: list[ContextAttachment]) -> float:
        attachment_noise = 0.0
        if attachments:
            attachment_noise = max(0.0, 1.0 - max(attachment.score for attachment in attachments))
        return _clamp01(signal.boilerplate_score * 0.6 + self._atomicity_risk(signal) * 0.25 + attachment_noise * 0.15)

    def _attachment_noise(self, source: ElementSignalRecord, targets: list[ElementSignalRecord]) -> float:
        if not targets:
            return 0.0
        penalties = []
        for target in targets:
            if target.is_heading or target.element_type in SUPPORT_TYPES:
                penalties.append(target.boilerplate_score * 0.4)
                continue
            overlap = self._term_overlap(source, target)
            if source.unique_content_terms and target.unique_content_terms and overlap < 0.08:
                penalties.append(0.25)
            penalties.append(target.boilerplate_score * 0.5)
        return _clamp01(max(penalties, default=0.0))

    def _citation_completeness(self, signal: ElementSignalRecord, attachments: list[ContextAttachment]) -> float:
        score = 0.35
        if signal.element_id:
            score += 0.2
        if signal.page_number is not None:
            score += 0.15
        if len(signal.bbox) == 4:
            score += 0.15
        if signal.element_type in SUPPORT_TYPES:
            score += 0.15 if signal.asset_link_exists else 0.03
        else:
            score += 0.1
        if attachments:
            score += 0.05
        return _clamp01(score)

    def _atomicity_risk(self, signal: ElementSignalRecord) -> float:
        length_risk = 0.0
        if signal.word_count > 160:
            length_risk = 0.55
        elif signal.word_count > 100:
            length_risk = 0.35
        elif signal.word_count > 70:
            length_risk = 0.2
        sentence_risk = min(0.3, max(0, signal.sentence_count - 3) * 0.08)
        discourse_count = sum(1 for marker in signal.markers if marker.category == "discourse")
        discourse_risk = min(0.2, discourse_count * 0.05)
        return _clamp01(length_risk + sentence_risk + discourse_risk)

    def _term_overlap(self, left: ElementSignalRecord, right: ElementSignalRecord) -> float:
        left_terms = set(left.unique_content_terms)
        right_terms = set(right.unique_content_terms)
        if not left_terms or not right_terms:
            return 0.0
        return len(left_terms & right_terms) / len(left_terms | right_terms)

    def _layout_proximity(self, left: ElementSignalRecord, right: ElementSignalRecord) -> float:
        if left.page_number != right.page_number:
            return 0.0
        left_center = self._bbox_center(left.bbox)
        right_center = self._bbox_center(right.bbox)
        distance = math.dist(left_center, right_center)
        return _clamp01(1.0 - distance)

    def _caption_text_shape_score(self, signal: ElementSignalRecord) -> float:
        if signal.word_count == 0:
            return 0.0
        short = 0.35 if signal.word_count <= 24 else 0.1 if signal.word_count <= 45 else 0.0
        support_terms = min(0.35, self._support_marker_strength(signal) * 0.35)
        punctuation = 0.15 if signal.text.rstrip().endswith((".", ":", ";")) else 0.05
        return _clamp01(short + support_terms + punctuation + signal.lexical_keyword_density * 0.2)

    def _same_list_run(self, left: ElementSignalRecord, right: ElementSignalRecord) -> bool:
        return (
            left.list_signal is not None
            and right.list_signal is not None
            and left.list_signal.run_id is not None
            and left.list_signal.run_id == right.list_signal.run_id
        )

    def _record_by_id(self, signals: Iterable[ElementSignalRecord], element_id: str) -> ElementSignalRecord | None:
        return next((signal for signal in signals if signal.element_id == element_id), None)

    def _tokens(self, text: str) -> list[str]:
        return _TOKEN_RE.findall(text or "")

    def _content_terms(self, tokens: list[str]) -> list[str]:
        terms = []
        for token in tokens:
            lowered = token.lower()
            if lowered in STOPWORDS or len(lowered) <= 1:
                continue
            terms.append(lowered)
        return terms

    def _sentence_count(self, text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        count = len(_SENTENCE_RE.findall(stripped))
        return max(1, count)

    def _ends_mid_thought(self, text: str) -> bool:
        stripped = text.rstrip()
        if not stripped:
            return False
        lowered = stripped.lower()
        dangling_endings = (
            " where",
            " in the",
            " is given by",
            " is given in",
            " as follows",
            " such that",
            " if",
            " and",
            " or",
            " with",
            " of",
            " to",
        )
        return not stripped.endswith((".", "!", "?", ":", ";", ")", "]")) or any(lowered.endswith(item) for item in dangling_endings)

    def _normalize_text(self, text: str) -> str:
        return " ".join(self._tokens(text.lower()))

    def _bbox_center(self, bbox: tuple[float, float, float, float]) -> tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


class _TokenCounter:
    def __init__(self) -> None:
        self._encoding = None
        try:
            import tiktoken  # type: ignore
        except Exception:
            return
        try:
            self._encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._encoding = None

    def count(self, text: str) -> int:
        if self._encoding is not None:
            return len(self._encoding.encode(text or ""))
        return len(re.findall(r"\w+|[^\s\w]", text or "", flags=re.UNICODE))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
