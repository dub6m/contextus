from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping
import hashlib
import json
import math
import re

import numpy as np

from contextus.llm import LLMClient, LLMRequest
from contextus.ingestion.models import ExtractedDocument

from .config import BuilderConfig
from .dependency_resolver import (
    DependencyResolver,
    DocumentTermIndex,
    FrameCandidate,
    ResolvedPackage,
    SlotCandidate,
    SupportVerifier,
    TermCandidate,
    normalize_term_text,
)
from .evidence import ElementSignalRecord, EvidenceHandleBuilder
from .preprocessor import ElementPreprocessor


SUPPORT_ELEMENT_TYPES = {"figure", "image", "chart", "diagram", "flowchart", "table", "formula"}
SUPPORT_REF_RE = re.compile(r"\[(?:SUPPORT|FIGURE)\s+([^\]]+)\]", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+(?:\.\d+)?")
SYMBOL_RE = re.compile(r"\b(?:[A-Z][a-z]?|[A-Za-z]\([^)]{1,24}\)|[A-Za-z]+_[A-Za-z0-9]+)\b")
COMPARISON_RE = re.compile(
    r"\b(?:at\s+most|at\s+least|less\s+than|greater\s+than|no\s+more\s+than|no\s+less\s+than|"
    r"within|between|because|therefore|contradict\w*|assum\w*|define\w*|consist\w*|"
    r"sorted\s+by|bounded|minimum|maximum|minimizes?|maximizes?)\b",
    re.IGNORECASE,
)
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
    "how",
    "if",
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
    "those",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "while",
    "why",
    "will",
    "with",
}
COMPLETION_NOISE_TERMS = {
    "all",
    "any",
    "each",
    "goal",
    "here",
    "let",
    "list",
    "make",
    "most",
    "our",
    "same",
    "set",
    "time",
    "two",
    "use",
    "used",
    "we",
}
VAGUE_ROLE_TARGETS = {
    "",
    "algorithm",
    "claim",
    "concept",
    "data",
    "example",
    "fact",
    "figure",
    "idea",
    "method",
    "point",
    "points",
    "process",
    "proof",
    "result",
    "step",
    "support",
    "table",
    "term",
    "text",
    "thing",
}
SOURCE_TRAVERSAL_GENERIC_CLAIM_UNITS = {
    "annotation",
    "annotations",
    "arrow",
    "arrows",
    "bordered",
    "bottom",
    "cell",
    "cells",
    "chart",
    "column",
    "columns",
    "content",
    "diagram",
    "figure",
    "figures",
    "grid",
    "grey",
    "image",
    "images",
    "label",
    "labeled",
    "labels",
    "left",
    "light",
    "map",
    "panel",
    "panels",
    "picture",
    "pictures",
    "right",
    "row",
    "rows",
    "show",
    "showing",
    "shows",
    "source",
    "table",
    "text",
    "top",
}


@dataclass(frozen=True)
class QueryAssemblyDecision:
    element_id: str
    direction: str
    action: str
    query_similarity: float
    core_similarity: float
    query_delta: float
    core_delta: float
    reason: str


@dataclass(frozen=True)
class CompletionCandidateTrace:
    element_ids: list[str]
    element_indices: list[int]
    score: float
    role_keys: list[str]
    useful_open_keys: list[str]
    token_cost: int
    action: str
    reason: str
    rejection_reason: str = ""
    original_element_indices: list[int] = field(default_factory=list)
    trimmed_element_indices: list[int] = field(default_factory=list)
    text_preview: str = ""


@dataclass
class CompletionRoundTrace:
    round_number: int
    selected_before: list[str]
    needed_before: list[str]
    filled_before: list[str]
    open_before: list[str]
    candidates: list[CompletionCandidateTrace] = field(default_factory=list)
    attached_element_ids: list[str] = field(default_factory=list)
    selected_after: list[str] = field(default_factory=list)
    needed_after: list[str] = field(default_factory=list)
    filled_after: list[str] = field(default_factory=list)
    open_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompletionDiagnostics:
    enabled: bool
    disabled_reason: str = ""
    completion_needed_initial: bool = False
    rounds: list[CompletionRoundTrace] = field(default_factory=list)


@dataclass(frozen=True)
class PackageRankingDiagnostics:
    legacy_score: float
    final_score: float
    relevance_score: float
    plan_coverage_score: float
    profile_alignment_score: float
    directness_score: float
    assembly_confidence_score: float
    role_coverage_score: float
    completion_closure_score: float
    grounding_score: float
    support_score: float
    source_coherence_score: float
    noise_score: float
    token_efficiency_score: float
    covered_sub_needs: list[str] = field(default_factory=list)
    missing_sub_needs: list[str] = field(default_factory=list)
    package_roles: list[str] = field(default_factory=list)
    expected_roles: list[str] = field(default_factory=list)
    open_completion_keys: list[str] = field(default_factory=list)
    positive_reasons: list[str] = field(default_factory=list)
    negative_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryAssembledPackage:
    package_id: str
    core_element_id: str
    core_index: int
    core_prompt_similarity: float
    package_prompt_similarity: float
    package_core_similarity: float
    element_ids: list[str]
    package_text: str
    token_count: int
    score: float
    decisions: list[QueryAssemblyDecision] = field(default_factory=list)
    completion_diagnostics: CompletionDiagnostics | None = None
    ranking_diagnostics: PackageRankingDiagnostics | None = None
    seed_core_element_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QueryAnswerBundlePart:
    sub_need: str
    search_terms: list[str]
    expected_roles: list[str]
    package: QueryAssembledPackage


@dataclass(frozen=True)
class QueryAnswerBundle:
    bundle_id: str
    prompt: str
    parts: list[QueryAnswerBundlePart]

    @property
    def packages(self) -> list[QueryAssembledPackage]:
        return [part.package for part in self.parts]


@dataclass(frozen=True)
class SourceTraversalAnswerBundlePart:
    part_id: str
    role: str
    display_label: str
    center_id: str
    trace_anchor_element_id: str
    topic_terms: list[str]
    claim_units: list[str]
    evidence_element_ids: list[str]
    package: QueryAssembledPackage


@dataclass(frozen=True)
class SourceTraversalAnswerBundle:
    bundle_id: str
    prompt: str
    parts: list[SourceTraversalAnswerBundlePart]

    @property
    def packages(self) -> list[QueryAssembledPackage]:
        return [part.package for part in self.parts]


@dataclass(frozen=True)
class SourceTraversalCandidateTrace:
    round_number: int
    proposition_id: str
    element_id: str
    center_id: str
    center_decision: str
    relation_tags: list[str]
    prompt_similarity: float
    state_similarity: float
    novelty_score: float
    redundancy_score: float
    relation_score: float
    role_contribution_score: float
    token_count: int
    action: str
    reason: str
    text_preview: str = ""
    answer_contribution: str = ""
    matched_claim_units: list[str] = field(default_factory=list)
    new_needed_units: list[str] = field(default_factory=list)
    foreign_claim_tokens: list[str] = field(default_factory=list)
    frame_continuation: str = ""


@dataclass(frozen=True)
class SourceTraversalTrace:
    anchor_proposition_id: str
    anchor_element_id: str
    anchor_text_preview: str
    accepted_proposition_ids: list[str]
    accepted_element_ids: list[str]
    centers: list[dict[str, object]] = field(default_factory=list)
    candidates: list[SourceTraversalCandidateTrace] = field(default_factory=list)
    dead_end_reason: str = ""


@dataclass(frozen=True)
class _SourceTraversalVocabularyCache:
    key: str
    unit_counts: Counter[str]
    claim_unit_counts: Counter[str]
    units_by_index: tuple[frozenset[str], ...]
    claim_units_by_index: tuple[frozenset[str], ...]


@dataclass(frozen=True)
class _DocumentAssemblyCache:
    key: str
    proposition_embeddings: np.ndarray
    graph: dict[int, dict[int, "_ConsensusEdge"]]
    relation_geometry: "_DocumentRelationGeometry | None"


@dataclass(frozen=True)
class _DocumentLanguageCache:
    key: str
    language_map: "_DocumentLanguageMap"
    unit_embeddings: np.ndarray


@dataclass(frozen=True)
class QueryAssemblyResult:
    prompt: str
    packages: list[QueryAssembledPackage]
    propositions: list["QueryEvidenceProposition"] = field(default_factory=list)
    retrieval_plan: "QueryRetrievalPlan | None" = None
    dependency_packages: list[ResolvedPackage] = field(default_factory=list)
    answer_bundle: QueryAnswerBundle | None = None
    source_traversals: list[SourceTraversalTrace] = field(default_factory=list)
    source_traversal_packages: list[QueryAssembledPackage] = field(default_factory=list)
    source_traversal_answer_bundle: SourceTraversalAnswerBundle | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(replace(self, dependency_packages=[]))
        payload["dependency_packages"] = [
            _resolved_package_to_dict(package)
            for package in self.dependency_packages
        ]
        return payload


def _resolved_package_to_dict(package: ResolvedPackage) -> dict[str, object]:
    return {
        "core_frames": [_fact_frame_to_dict(frame) for frame in package.core_frames],
        "selected_frames": [_fact_frame_to_dict(frame) for frame in package.selected_frames],
        "selected_elements": list(package.selected_elements),
        "resolved_needs": [asdict(need) for need in package.resolved_needs],
        "unresolved_needs": [asdict(need) for need in package.unresolved_needs],
        "cycles": [list(cycle) for cycle in package.cycles],
        "resolution_trace": [asdict(step) for step in package.resolution_trace],
    }


def _fact_frame_to_dict(frame: object) -> dict[str, object]:
    return {
        "frame_id": getattr(frame, "frame_id", ""),
        "source": asdict(getattr(frame, "source")),
        "predicate": getattr(frame, "predicate", ""),
        "slots": {
            name: asdict(slot)
            for name, slot in getattr(frame, "slots", {}).items()
        },
        "constraints": [
            asdict(constraint)
            for constraint in getattr(frame, "constraints", ())
        ],
        "links": list(getattr(frame, "links", ())),
        "extraction_status": getattr(frame, "extraction_status", ""),
    }


@dataclass(frozen=True)
class QueryEvidenceProposition:
    proposition_id: str
    element_id: str
    element_index: int
    text: str
    support_element_ids: list[str] = field(default_factory=list)
    roles: list["PropositionRoleHypothesis"] = field(default_factory=list)
    grounding: "PropositionGroundingDiagnostics | None" = None


@dataclass(frozen=True)
class PropositionRoleHypothesis:
    role: str
    target: str = ""
    value: str = ""
    confidence: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class RoleGroundingDiagnostics:
    role: str
    target: str
    status: str
    severity: str
    target_in_proposition: bool
    target_in_source: bool
    target_token_overlap: float
    role_symbol_overlap: float
    behavior_match: bool
    support_grounded: bool | None = None
    vague_target: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PropositionGroundingDiagnostics:
    status: str
    severity: str
    source_overlap_ratio: float
    kept_terms: list[str] = field(default_factory=list)
    novel_terms: list[str] = field(default_factory=list)
    source_symbols: list[str] = field(default_factory=list)
    proposition_symbols: list[str] = field(default_factory=list)
    role_diagnostics: list[RoleGroundingDiagnostics] = field(default_factory=list)


@dataclass(frozen=True)
class _PropositionDraft:
    text: str
    roles: list[PropositionRoleHypothesis] = field(default_factory=list)


@dataclass(frozen=True)
class _RoleCompletionCandidate:
    element_indices: tuple[int, ...]
    score: float
    reason: str
    role_keys: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class _DependencyTermSeed:
    text: str
    char_start: int
    char_end: int
    source_signal: str
    priority: float = 0.0


@dataclass
class _CompletionNeedLedger:
    needed_keys: set[str] = field(default_factory=set)
    filled_keys: set[str] = field(default_factory=set)

    @property
    def open_keys(self) -> set[str]:
        return self.needed_keys - self.filled_keys

    def fill(self, keys: Iterable[str]) -> None:
        self.filled_keys.update(_expanded_completion_fill_keys(keys))


@dataclass(frozen=True)
class QueryRetrievalPlan:
    interpreted_need: str
    query_type: str
    source_supported_terms: list[str] = field(default_factory=list)
    possible_missing_prerequisites: list[str] = field(default_factory=list)
    search_forms: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    sub_needs: list["QueryRetrievalSubNeed"] = field(default_factory=list)


@dataclass(frozen=True)
class QueryRetrievalSubNeed:
    need: str
    search_terms: list[str] = field(default_factory=list)
    expected_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _CoreCandidate:
    element_index: int
    prompt_similarity: float
    core_embedding: np.ndarray
    proposition_id: str | None = None
    proposition_index: int | None = None
    proposition_text: str | None = None
    support_element_ids: list[str] = field(default_factory=list)
    anchor_prop_indices: tuple[int, ...] = ()


class QueryTimeEvidenceAssembler:
    """Build prompt-conditioned evidence packages with cheap embedding expansion."""

    def __init__(
        self,
        *,
        preprocessor: ElementPreprocessor | None = None,
        embed_texts: Callable[[list[str]], np.ndarray] | None = None,
        top_k_cores: int = 5,
        lookahead_after_mark: int = 3,
        major_query_drop: float = 0.04,
        major_core_shift: float = 0.08,
        recovery_slack: float = 0.015,
        max_side_elements: int = 10,
        max_package_tokens: int = 280,
        stagnant_addition_limit: int = 2,
        use_role_completion: bool = False,
        role_completion_max_attachments: int = 8,
        role_completion_max_extra_tokens: int = 300,
        role_completion_search_radius: int = 28,
        config: BuilderConfig | None = None,
    ) -> None:
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.top_k_cores = max(1, int(top_k_cores))
        self.lookahead_after_mark = max(0, int(lookahead_after_mark))
        self.major_query_drop = max(0.0, float(major_query_drop))
        self.major_core_shift = max(0.0, float(major_core_shift))
        self.recovery_slack = max(0.0, float(recovery_slack))
        self.max_side_elements = max(0, int(max_side_elements))
        self.max_package_tokens = max(1, int(max_package_tokens))
        self.stagnant_addition_limit = max(1, int(stagnant_addition_limit))
        self.use_role_completion = bool(use_role_completion)
        self.role_completion_max_attachments = max(0, int(role_completion_max_attachments))
        self.role_completion_max_extra_tokens = max(0, int(role_completion_max_extra_tokens))
        self.role_completion_search_radius = max(1, int(role_completion_search_radius))
        self._embed_texts = embed_texts
        self._embedding_backend = None if embed_texts is not None else _EmbeddingBackend(config or BuilderConfig())
        self._signal_builder = EvidenceHandleBuilder(preprocessor=self.preprocessor)

    def assemble(self, document: ExtractedDocument, prompt: str) -> QueryAssemblyResult:
        pipeline = self._signal_builder.build(document)
        signals = [signal for signal in pipeline.signals if signal.text.strip()]
        if not signals:
            return QueryAssemblyResult(prompt=prompt, packages=[])

        embeddings = self._embed([prompt, *[signal.text for signal in signals]])
        prompt_embedding = embeddings[0]
        element_embeddings = embeddings[1:]
        prompt_similarities = element_embeddings @ prompt_embedding
        core_indices = self._top_core_indices(signals, prompt_similarities)
        core_candidates = [
            _CoreCandidate(
                element_index=core_index,
                prompt_similarity=float(prompt_similarities[core_index]),
                core_embedding=element_embeddings[core_index],
                proposition_index=None,
            )
            for core_index in core_indices
        ]
        packages = [
            self._assemble_for_core(
                signals=signals,
                prompt_embedding=prompt_embedding,
                core_candidate=core_candidate,
                package_index=index,
            )
            for index, core_candidate in enumerate(core_candidates)
        ]
        ranked = self._rank_query_packages(
            packages=packages,
            prompt=prompt,
            signals=signals,
        )
        return QueryAssemblyResult(prompt=prompt, packages=ranked)

    def _assemble_for_core(
        self,
        *,
        signals: list[ElementSignalRecord],
        prompt_embedding: np.ndarray,
        core_candidate: _CoreCandidate,
        package_index: int,
    ) -> QueryAssembledPackage:
        core_index = core_candidate.element_index
        core_embedding = core_candidate.core_embedding
        state = _ExpansionState(
            start=core_index,
            end=core_index,
            query_similarity=core_candidate.prompt_similarity,
            core_similarity=1.0,
        )
        decisions: list[QueryAssemblyDecision] = []

        state, left_decisions = self._expand_direction(
            signals=signals,
            prompt_embedding=prompt_embedding,
            core_embedding=core_embedding,
            state=state,
            direction="left",
        )
        decisions.extend(left_decisions)
        state, right_decisions = self._expand_direction(
            signals=signals,
            prompt_embedding=prompt_embedding,
            core_embedding=core_embedding,
            state=state,
            direction="right",
        )
        decisions.extend(right_decisions)

        selected = signals[state.start : state.end + 1]
        selected, support_decisions = self._attach_explicit_support(
            signals=signals,
            selected=selected,
            core_candidate=core_candidate,
        )
        decisions.extend(support_decisions)
        role_by_id = {
            support_id: "Support"
            for support_id in core_candidate.support_element_ids
            if support_id != signals[core_index].element_id
        }
        final_core_signal, final_core_embedding = self._select_final_core(
            selected,
            seed_core_element_id=signals[core_index].element_id,
        )
        package_text = self._package_text(
            selected,
            core_element_id=final_core_signal.element_id,
            role_by_id=role_by_id,
        )
        package_embedding = self._embed([package_text])[0]
        package_prompt_similarity = float(np.dot(package_embedding, prompt_embedding))
        package_core_similarity = float(np.dot(package_embedding, final_core_embedding))
        final_core_prompt_similarity = float(np.dot(final_core_embedding, prompt_embedding))
        token_count = sum(signal.token_count for signal in selected)
        score = self._package_score(
            package_prompt_similarity=package_prompt_similarity,
            package_core_similarity=package_core_similarity,
            core_prompt_similarity=final_core_prompt_similarity,
            token_count=token_count,
        )
        package_id = f"query-package-{package_index:05d}"
        if core_candidate.proposition_id is not None:
            package_id = f"query-proposition-package-{package_index:05d}"
        return QueryAssembledPackage(
            package_id=package_id,
            core_element_id=final_core_signal.element_id,
            core_index=final_core_signal.element_index,
            seed_core_element_id=signals[core_index].element_id,
            core_prompt_similarity=round(final_core_prompt_similarity, 4),
            package_prompt_similarity=round(package_prompt_similarity, 4),
            package_core_similarity=round(package_core_similarity, 4),
            element_ids=[signal.element_id for signal in selected],
            package_text=package_text,
            token_count=token_count,
            score=round(
                score
                + self._answerability_bonus(
                    signals=selected,
                    core_element_id=final_core_signal.element_id,
                    proposition_text=core_candidate.proposition_text,
                ),
                4,
            ),
            decisions=decisions,
        )

    def _select_final_core(
        self,
        selected: list[ElementSignalRecord],
        *,
        seed_core_element_id: str,
        propositions: list[QueryEvidenceProposition] | None = None,
    ) -> tuple[ElementSignalRecord, np.ndarray]:
        if not selected:
            raise ValueError("cannot select a final core from an empty package")
        seed_signal = next((signal for signal in selected if signal.element_id == seed_core_element_id), selected[0])
        embeddings = self._embed([signal.text for signal in selected])
        if len(selected) == 1:
            return selected[0], embeddings[0]
        element_winner = self._medoid_element_id(
            element_ids=[signal.element_id for signal in selected],
            texts=[signal.text for signal in selected],
        )
        proposition_winner = self._proposition_medoid_element_id(
            selected=selected,
            propositions=propositions or [],
        )
        if element_winner is None or proposition_winner is None or element_winner != proposition_winner:
            seed_index = next(
                (index for index, signal in enumerate(selected) if signal.element_id == seed_signal.element_id),
                0,
            )
            return seed_signal, embeddings[seed_index]
        final_index = next(
            (index for index, signal in enumerate(selected) if signal.element_id == element_winner),
            0,
        )
        return selected[final_index], embeddings[final_index]

    def _medoid_element_id(self, *, element_ids: list[str], texts: list[str]) -> str | None:
        if not element_ids or len(element_ids) != len(texts):
            return None
        embeddings = self._embed(texts)
        if len(element_ids) == 1:
            return element_ids[0]
        centroid = _normalize(np.mean(embeddings, axis=0))[0]
        similarities = embeddings @ centroid
        ranked = np.argsort(-similarities)
        best_index = int(ranked[0])
        if len(ranked) > 1 and np.isclose(similarities[best_index], similarities[int(ranked[1])]):
            return None
        return element_ids[best_index]

    def _proposition_medoid_element_id(
        self,
        *,
        selected: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
    ) -> str | None:
        if not propositions:
            return None
        selected_ids = {signal.element_id for signal in selected}
        by_element: dict[str, list[str]] = defaultdict(list)
        for proposition in propositions:
            if proposition.element_id in selected_ids and proposition.text.strip():
                by_element[proposition.element_id].append(proposition.text)
        element_ids: list[str] = []
        texts: list[str] = []
        for signal in selected:
            proposition_texts = by_element.get(signal.element_id)
            if not proposition_texts:
                continue
            element_ids.append(signal.element_id)
            texts.append(" ".join(proposition_texts))
        if len(element_ids) != len(selected):
            return None
        return self._medoid_element_id(element_ids=element_ids, texts=texts)

    def _attach_explicit_support(
        self,
        *,
        signals: list[ElementSignalRecord],
        selected: list[ElementSignalRecord],
        core_candidate: _CoreCandidate,
    ) -> tuple[list[ElementSignalRecord], list[QueryAssemblyDecision]]:
        if not core_candidate.support_element_ids:
            return selected, []
        selected_by_id = {signal.element_id: signal for signal in selected}
        signal_by_id = {signal.element_id: signal for signal in signals}
        token_count = sum(signal.token_count for signal in selected)
        decisions: list[QueryAssemblyDecision] = []

        for support_id in core_candidate.support_element_ids:
            if support_id in selected_by_id:
                continue
            support = signal_by_id.get(support_id)
            if support is None or support.element_type not in SUPPORT_ELEMENT_TYPES:
                continue
            if token_count + support.token_count > self.max_package_tokens:
                decisions.append(
                    self._decision(
                        support,
                        direction="support",
                        action="skipped",
                        query_similarity=0.0,
                        core_similarity=0.0,
                        previous_query_similarity=0.0,
                        previous_core_similarity=0.0,
                        reason="explicit support reference exceeded token budget",
                    )
                )
                continue
            selected_by_id[support.element_id] = support
            token_count += support.token_count
            decisions.append(
                self._decision(
                    support,
                    direction="support",
                    action="attached",
                    query_similarity=0.0,
                    core_similarity=0.0,
                    previous_query_similarity=0.0,
                    previous_core_similarity=0.0,
                    reason="attached explicit proposition support reference",
                )
            )

        ordered = sorted(selected_by_id.values(), key=lambda signal: signal.element_index)
        return ordered, decisions

    def _expand_direction(
        self,
        *,
        signals: list[ElementSignalRecord],
        prompt_embedding: np.ndarray,
        core_embedding: np.ndarray,
        state: "_ExpansionState",
        direction: str,
    ) -> tuple["_ExpansionState", list[QueryAssemblyDecision]]:
        decisions: list[QueryAssemblyDecision] = []
        pending: _MarkedDrift | None = None
        stagnant_additions = 0
        steps = 0

        while steps < self.max_side_elements:
            candidate_index = state.start - 1 if direction == "left" else state.end + 1
            if candidate_index < 0 or candidate_index >= len(signals):
                break
            candidate = signals[candidate_index]
            if state.token_count(signals) + candidate.token_count > self.max_package_tokens:
                decisions.append(
                    self._decision(
                        candidate,
                        direction=direction,
                        action="stopped",
                        query_similarity=state.query_similarity,
                        core_similarity=state.core_similarity,
                        previous_query_similarity=state.query_similarity,
                        previous_core_similarity=state.core_similarity,
                        reason="token budget reached",
                    )
                )
                break

            new_state = state.with_added(candidate_index, direction=direction)
            query_similarity, core_similarity = self._state_similarities(
                signals=signals,
                state=new_state,
                prompt_embedding=prompt_embedding,
                core_embedding=core_embedding,
            )
            query_delta = query_similarity - state.query_similarity
            core_delta = core_similarity - state.core_similarity
            drift = query_delta <= -self.major_query_drop and core_delta <= -self.major_core_shift

            if pending is None and drift:
                pending = _MarkedDrift(
                    rollback_state=state,
                    baseline_query_similarity=state.query_similarity,
                    baseline_core_similarity=state.core_similarity,
                    remaining_lookahead=self.lookahead_after_mark,
                )
                state = _ExpansionState(new_state.start, new_state.end, query_similarity, core_similarity)
                decisions.append(
                    self._decision(
                        candidate,
                        direction=direction,
                        action="marked",
                        query_similarity=query_similarity,
                        core_similarity=core_similarity,
                        previous_query_similarity=pending.baseline_query_similarity,
                        previous_core_similarity=pending.baseline_core_similarity,
                        reason="major prompt/core drift; starting lookahead",
                    )
                )
                steps += 1
                continue

            if pending is not None:
                state = _ExpansionState(new_state.start, new_state.end, query_similarity, core_similarity)
                recovered = query_similarity >= pending.baseline_query_similarity - self.recovery_slack
                if recovered:
                    decisions.append(
                        self._decision(
                            candidate,
                            direction=direction,
                            action="recovered",
                            query_similarity=query_similarity,
                            core_similarity=core_similarity,
                            previous_query_similarity=pending.baseline_query_similarity,
                            previous_core_similarity=pending.baseline_core_similarity,
                            reason="marked span recovered prompt similarity",
                        )
                    )
                    pending = None
                elif pending.remaining_lookahead <= 1:
                    decisions.append(
                        self._decision(
                            candidate,
                            direction=direction,
                            action="rolled_back",
                            query_similarity=query_similarity,
                            core_similarity=core_similarity,
                            previous_query_similarity=pending.baseline_query_similarity,
                            previous_core_similarity=pending.baseline_core_similarity,
                            reason="marked span did not recover within lookahead",
                        )
                    )
                    state = pending.rollback_state
                    break
                else:
                    decisions.append(
                        self._decision(
                            candidate,
                            direction=direction,
                            action="lookahead",
                            query_similarity=query_similarity,
                            core_similarity=core_similarity,
                            previous_query_similarity=pending.baseline_query_similarity,
                            previous_core_similarity=pending.baseline_core_similarity,
                            reason=f"waiting for recovery; remaining={pending.remaining_lookahead}",
                        )
                    )
                    pending = _MarkedDrift(
                        rollback_state=pending.rollback_state,
                        baseline_query_similarity=pending.baseline_query_similarity,
                        baseline_core_similarity=pending.baseline_core_similarity,
                        remaining_lookahead=pending.remaining_lookahead - 1,
                    )
                steps += 1
                continue

            state = _ExpansionState(new_state.start, new_state.end, query_similarity, core_similarity)
            if query_delta <= 0.0 and core_delta <= 0.0:
                stagnant_additions += 1
            else:
                stagnant_additions = 0
            decisions.append(
                self._decision(
                    candidate,
                    direction=direction,
                    action="kept",
                    query_similarity=query_similarity,
                    core_similarity=core_similarity,
                    previous_query_similarity=state.query_similarity - query_delta,
                    previous_core_similarity=state.core_similarity - core_delta,
                    reason="prompt/core similarity stayed stable enough",
                )
            )
            steps += 1
            if stagnant_additions >= self.stagnant_addition_limit:
                decisions.append(
                    self._decision(
                        candidate,
                        direction=direction,
                        action="stopped",
                        query_similarity=state.query_similarity,
                        core_similarity=state.core_similarity,
                        previous_query_similarity=state.query_similarity,
                        previous_core_similarity=state.core_similarity,
                        reason="prompt/core similarity stopped improving",
                    )
                )
                break

        return state, decisions

    def _state_similarities(
        self,
        *,
        signals: list[ElementSignalRecord],
        state: "_ExpansionState",
        prompt_embedding: np.ndarray,
        core_embedding: np.ndarray,
    ) -> tuple[float, float]:
        text = "\n".join(signal.text for signal in signals[state.start : state.end + 1])
        embedding = self._embed([text])[0]
        return float(np.dot(embedding, prompt_embedding)), float(np.dot(embedding, core_embedding))

    def _top_core_indices(self, signals: list[ElementSignalRecord], prompt_similarities: np.ndarray) -> list[int]:
        ranked = sorted(
            range(len(signals)),
            key=lambda index: (
                float(prompt_similarities[index]) - signals[index].boilerplate_score * 0.05,
                signals[index].lexical_keyword_density,
            ),
            reverse=True,
        )
        return ranked[: self.top_k_cores]

    def _package_text(
        self,
        signals: list[ElementSignalRecord],
        *,
        core_element_id: str,
        role_by_id: Mapping[str, str] | None = None,
    ) -> str:
        lines: list[str] = []
        role_by_id = role_by_id or {}
        for signal in signals:
            role = "Core" if signal.element_id == core_element_id else role_by_id.get(signal.element_id, "Context")
            lines.extend([f"[{role} | {signal.element_id}]", signal.text.strip(), ""])
        return "\n".join(lines).strip()

    def _package_score(
        self,
        *,
        package_prompt_similarity: float,
        package_core_similarity: float,
        core_prompt_similarity: float,
        token_count: int,
    ) -> float:
        token_penalty = min(0.1, token_count / 4000.0)
        return package_prompt_similarity * 0.7 + package_core_similarity * 0.15 + core_prompt_similarity * 0.15 - token_penalty

    def _answerability_bonus(
        self,
        *,
        signals: list[ElementSignalRecord],
        core_element_id: str,
        proposition_text: str | None = None,
    ) -> float:
        core = next((signal for signal in signals if signal.element_id == core_element_id), None)
        if core is None:
            return 0.0
        bonus = 0.0
        if core.is_heading and len(signals) <= 2:
            bonus -= 0.18
        if core.element_type in {"table", "figure", "image", "chart", "diagram"}:
            bonus += 0.06
        if proposition_text:
            bonus += min(0.08, max(0.0, (len(proposition_text.split()) - 3) / 100.0))
        if any(signal.element_type in {"table", "figure", "image", "chart", "diagram"} for signal in signals):
            bonus += 0.03
        return bonus

    def _prompt_wants_support(self, prompt: str) -> bool:
        return bool(
            re.search(
                r"\b(figure|image|diagram|chart|table|formula|map|visual|punnett|shown|illustrate|illustrates)\b",
                prompt,
                re.IGNORECASE,
            )
        )

    def _rank_query_packages(
        self,
        *,
        packages: list[QueryAssembledPackage],
        prompt: str,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition] | None = None,
        retrieval_plan: QueryRetrievalPlan | None = None,
    ) -> list[QueryAssembledPackage]:
        if not packages:
            return []
        signal_by_id = {signal.element_id: signal for signal in signals}
        propositions = propositions or []
        ranked: list[QueryAssembledPackage] = []
        for package in packages:
            selected = [signal_by_id[element_id] for element_id in package.element_ids if element_id in signal_by_id]
            diagnostics = self._package_ranking_diagnostics(
                package=package,
                prompt=prompt,
                selected=selected,
                propositions=propositions,
                retrieval_plan=retrieval_plan,
            )
            ranked.append(
                replace(
                    package,
                    score=round(diagnostics.final_score, 4),
                    ranking_diagnostics=diagnostics,
                )
            )
        return sorted(
            ranked,
            key=lambda item: (
                item.score,
                item.ranking_diagnostics.relevance_score if item.ranking_diagnostics else 0.0,
                -item.token_count,
            ),
            reverse=True,
        )

    def _package_ranking_diagnostics(
        self,
        *,
        package: QueryAssembledPackage,
        prompt: str,
        selected: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> PackageRankingDiagnostics:
        text = package.package_text
        package_tokens = set(_completion_tokens(text))
        prompt_tokens = set(_completion_tokens(prompt))
        selected_ids = {signal.element_id for signal in selected}
        selected_propositions = [proposition for proposition in propositions if proposition.element_id in selected_ids]
        proposition_by_element: dict[str, list[QueryEvidenceProposition]] = defaultdict(list)
        for proposition in selected_propositions:
            proposition_by_element[proposition.element_id].append(proposition)
        label_by_element = _package_element_labels(text)
        role_names = self._package_role_names(
            selected=selected,
            selected_propositions=selected_propositions,
            package_text=text,
        )
        expected_profile = self._expected_role_profile(prompt=prompt, retrieval_plan=retrieval_plan)
        package_profile, direct_profile = self._package_role_profiles(
            selected=selected,
            proposition_by_element=proposition_by_element,
            label_by_element=label_by_element,
        )
        profile_alignment_score = self._profile_alignment_score(
            expected_profile=expected_profile,
            package_profile=package_profile,
        )
        plan_score, covered_sub_needs, missing_sub_needs = self._package_plan_coverage_score(
            package_tokens=package_tokens,
            package_text=text,
            role_names=role_names,
            prompt=prompt,
            retrieval_plan=retrieval_plan,
        )
        directness_score = self._package_directness_score(
            package=package,
            selected=selected,
            label_by_element=label_by_element,
            expected_profile=expected_profile,
            direct_profile=direct_profile,
            prompt=prompt,
            retrieval_plan=retrieval_plan,
        )
        assembly_confidence_score = self._package_assembly_confidence_score(
            package=package,
            label_by_element=label_by_element,
        )
        role_score = self._package_role_coverage_score(
            prompt=prompt,
            role_names=role_names,
            retrieval_plan=retrieval_plan,
        )
        completion_score, open_keys = self._package_completion_closure_score(package)
        grounding_score = self._package_grounding_score(selected_propositions)
        support_score = self._package_support_score(
            prompt=prompt,
            selected=selected,
            package_text=text,
            role_names=role_names,
            retrieval_plan=retrieval_plan,
        )
        coherence_score = self._package_source_coherence_score(selected)
        noise_score, token_efficiency = self._package_noise_score(selected=selected, package=package)
        relevance_score = _clamp01(
            package.package_prompt_similarity * 0.62
            + package.core_prompt_similarity * 0.25
            + package.package_core_similarity * 0.13
        )

        final_score = (
            profile_alignment_score * 0.22
            + directness_score * 0.18
            + plan_score * 0.16
            + assembly_confidence_score * 0.12
            + completion_score * 0.10
            + relevance_score * 0.10
            + coherence_score * 0.05
            + grounding_score * 0.04
            + support_score * 0.02
            + noise_score * 0.01
        )
        positive_reasons: list[str] = []
        negative_reasons: list[str] = []
        if covered_sub_needs:
            positive_reasons.append(f"covers {len(covered_sub_needs)} planned need(s)")
        if profile_alignment_score >= 0.72:
            positive_reasons.append("package evidence profile matches query demand")
        if directness_score >= 0.70:
            positive_reasons.append("answer evidence is near the core")
        if assembly_confidence_score >= 0.72:
            positive_reasons.append("assembled from strong anchors/spans")
        if completion_score >= 0.85:
            positive_reasons.append("completion ledger mostly closed")
        if relevance_score >= 0.62:
            positive_reasons.append("embedding relevance is strong enough")
        if missing_sub_needs:
            negative_reasons.append(f"misses {len(missing_sub_needs)} planned need(s)")
        if open_keys:
            negative_reasons.append(f"open completion needs: {', '.join(open_keys[:5])}")
        if grounding_score < 0.65:
            negative_reasons.append("included proposition roles have weak grounding")
        if coherence_score < 0.55:
            negative_reasons.append("selected elements are source-order jumpy")
        if support_score < 0.6:
            negative_reasons.append("support need is not clearly satisfied")
        if noise_score < 0.55:
            negative_reasons.append("token/noise pressure is high")
        if profile_alignment_score < 0.52:
            negative_reasons.append("package evidence profile only weakly matches query demand")
        if directness_score < 0.48:
            negative_reasons.append("answer evidence is not direct to the core")
        if assembly_confidence_score < 0.52:
            negative_reasons.append("assembly relies too much on weak/patchy attachments")

        return PackageRankingDiagnostics(
            legacy_score=round(float(package.score), 4),
            final_score=round(float(final_score), 4),
            relevance_score=round(relevance_score, 4),
            plan_coverage_score=round(plan_score, 4),
            profile_alignment_score=round(profile_alignment_score, 4),
            directness_score=round(directness_score, 4),
            assembly_confidence_score=round(assembly_confidence_score, 4),
            role_coverage_score=round(role_score, 4),
            completion_closure_score=round(completion_score, 4),
            grounding_score=round(grounding_score, 4),
            support_score=round(support_score, 4),
            source_coherence_score=round(coherence_score, 4),
            noise_score=round(noise_score, 4),
            token_efficiency_score=round(token_efficiency, 4),
            covered_sub_needs=covered_sub_needs,
            missing_sub_needs=missing_sub_needs,
            package_roles=sorted(role_names),
            expected_roles=sorted(expected_profile),
            open_completion_keys=open_keys,
            positive_reasons=positive_reasons,
            negative_reasons=negative_reasons,
        )

    def _package_role_names(
        self,
        *,
        selected: list[ElementSignalRecord],
        selected_propositions: list[QueryEvidenceProposition],
        package_text: str,
    ) -> set[str]:
        roles: set[str] = set()
        lowered = package_text.lower()
        for proposition in selected_propositions:
            for role in proposition.roles:
                roles.add(role.role.strip().lower())
        if any(signal.element_type in SUPPORT_ELEMENT_TYPES for signal in selected):
            roles.add("support")
        if re.search(r"\b(figure|image|diagram|chart|table|formula|equation|shown)\b", lowered):
            roles.add("support")
        if re.search(r"\b(let|denote\w*|defined\s+as|means?|refers?\s+to|is\s+(?:a|an|the))\b", lowered):
            roles.add("definition")
        if re.search(r"\b(claim|proof|suppose|assum\w*|consider)\b", lowered):
            roles.add("proof_setup")
        if re.search(r"\b(since|because|as|at\s+least|at\s+most|bounded|within|contradict\w*)\b", lowered):
            roles.add("proof_reason")
        if re.search(r"\b(therefore|thus|hence|so|implies?|this means)\b", lowered):
            roles.add("proof_conclusion")
        if re.search(r"\b(compute|sort|partition|call|return|repeat|step)\b", lowered):
            roles.add("procedure_step")
        if re.search(r"\b(compare|contrast|differ\w*|versus|vs\.?|columns?|rows?)\b", lowered):
            roles.add("comparison")
        if re.search(r"\b(example|for instance)\b", lowered):
            roles.add("example")
        return roles

    def _expected_role_profile(
        self,
        *,
        prompt: str,
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> Counter[str]:
        profile: Counter[str] = Counter()
        prompt_tokens = set(_completion_tokens(prompt))
        if retrieval_plan is not None:
            query_type_roles = _roles_from_query_type(retrieval_plan.query_type)
            for role in query_type_roles:
                profile[role] += 1.4
            for sub_need in retrieval_plan.sub_needs:
                weight = self._sub_need_prompt_weight(prompt_tokens=prompt_tokens, sub_need=sub_need)
                for role in sub_need.expected_roles:
                    family = _role_family(role)
                    if family:
                        profile[family] += weight

        if profile:
            return profile

        fallback_roles = _roles_from_query_type(prompt)
        for role in fallback_roles:
            profile[role] += 1.0
        if _prompt_asks_why(prompt) and "procedure" not in fallback_roles:
            profile["proof_reason"] += 1.0
            profile["proof_conclusion"] += 0.7
        if self._prompt_wants_support(prompt):
            profile["support"] += 1.0
        return profile

    def _sub_need_prompt_weight(self, *, prompt_tokens: set[str], sub_need: QueryRetrievalSubNeed) -> float:
        need_tokens = set(_completion_tokens(sub_need.need))
        term_tokens: set[str] = set()
        for term in sub_need.search_terms:
            term_tokens.update(_completion_tokens(term))
        lexical = max(_jaccard(prompt_tokens, need_tokens), _jaccard(prompt_tokens, term_tokens))
        exact_overlap = len(prompt_tokens & (need_tokens | term_tokens))
        return _clamp01(0.25 + min(0.55, lexical * 2.2) + min(0.2, exact_overlap * 0.04))

    def _package_role_profiles(
        self,
        *,
        selected: list[ElementSignalRecord],
        proposition_by_element: Mapping[str, list[QueryEvidenceProposition]],
        label_by_element: Mapping[str, str],
    ) -> tuple[Counter[str], Counter[str]]:
        package_profile: Counter[str] = Counter()
        direct_profile: Counter[str] = Counter()
        for signal in selected:
            label = label_by_element.get(signal.element_id, "Context")
            label_weight = _rank_label_weight(label)
            roles = self._element_role_families(
                signal=signal,
                propositions=proposition_by_element.get(signal.element_id, []),
            )
            if not roles:
                continue
            for role in roles:
                package_profile[role] += label_weight
                if label in {"Core", "Cluster", "Support"}:
                    direct_profile[role] += label_weight
        return package_profile, direct_profile

    def _element_role_families(
        self,
        *,
        signal: ElementSignalRecord,
        propositions: list[QueryEvidenceProposition],
    ) -> set[str]:
        roles: set[str] = set()
        text = signal.text.lower()
        for proposition in propositions:
            for role in proposition.roles:
                family = _role_family(role.role)
                if family:
                    roles.add(family)
        if signal.element_type in SUPPORT_ELEMENT_TYPES:
            roles.add("support")
        if re.search(r"\b(figure|image|diagram|chart|table|formula|equation|shown)\b", text):
            roles.add("support")
        if re.search(r"\b(let|denote\w*|defined\s+as|means?|refers?\s+to|is\s+(?:called|defined\s+as|a|an|the))\b", text):
            roles.add("definition")
        if re.search(r"\b(claim|proof|suppose|assum\w*|consider)\b", text):
            roles.add("proof_setup")
        if re.search(r"\b(since|because|as|at\s+least|at\s+most|bounded|within|contradict\w*)\b", text):
            roles.add("proof_reason")
        if re.search(r"\b(therefore|thus|hence|so|implies?|this means)\b", text):
            roles.add("proof_conclusion")
        if re.search(r"\b(compute|sort|partition|call|return|repeat|step|algorithm)\b", text):
            roles.add("procedure")
        if re.search(r"\b(compare|contrast|differ\w*|versus|vs\.?|columns?|rows?)\b", text):
            roles.add("comparison")
        if re.search(r"\b(example|for instance)\b", text):
            roles.add("example")
        return roles

    def _profile_alignment_score(
        self,
        *,
        expected_profile: Counter[str],
        package_profile: Counter[str],
    ) -> float:
        if not expected_profile:
            return 0.68
        expected_total = sum(expected_profile.values())
        package_total = sum(package_profile.values())
        if expected_total <= 0.0 or package_total <= 0.0:
            return 0.0
        overlap = sum(min(expected_profile[role], package_profile.get(role, 0.0)) for role in expected_profile)
        recall = overlap / expected_total
        precision = overlap / package_total
        return _clamp01(recall * 0.72 + precision * 0.28)

    def _package_directness_score(
        self,
        *,
        package: QueryAssembledPackage,
        selected: list[ElementSignalRecord],
        label_by_element: Mapping[str, str],
        expected_profile: Counter[str],
        direct_profile: Counter[str],
        prompt: str,
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> float:
        if expected_profile:
            expected_total = sum(expected_profile.values())
            direct_role_overlap = sum(min(expected_profile[role], direct_profile.get(role, 0.0)) for role in expected_profile)
            role_directness = direct_role_overlap / max(0.01, expected_total)
        else:
            role_directness = 0.62

        important_terms = self._ranking_query_terms(prompt=prompt, retrieval_plan=retrieval_plan)
        if not important_terms:
            term_directness = 0.62
            core_term_score = 0.62
        else:
            direct_text = " ".join(
                signal.text
                for signal in selected
                if label_by_element.get(signal.element_id, "Context") in {"Core", "Cluster", "Support"}
            )
            core_text = " ".join(signal.text for signal in selected if signal.element_id == package.core_element_id)
            direct_tokens = set(_completion_tokens(direct_text))
            core_tokens = set(_completion_tokens(core_text))
            term_directness = _weighted_term_coverage(important_terms, direct_text, direct_tokens)
            core_term_score = _weighted_term_coverage(important_terms, core_text, core_tokens)

        return _clamp01(role_directness * 0.42 + term_directness * 0.38 + core_term_score * 0.20)

    def _ranking_query_terms(
        self,
        *,
        prompt: str,
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> list[str]:
        terms: list[str] = []
        if retrieval_plan is not None:
            terms.extend(retrieval_plan.source_supported_terms[:8])
            for sub_need in retrieval_plan.sub_needs:
                terms.extend(sub_need.search_terms[:6])
        terms.extend(_content_chunks(prompt))
        terms.extend(_content_tokens(prompt))
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = _completion_normalized_text(term)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(term)
        return deduped[:48]

    def _package_assembly_confidence_score(
        self,
        *,
        package: QueryAssembledPackage,
        label_by_element: Mapping[str, str],
    ) -> float:
        label_counts = Counter(label_by_element.get(element_id, "Context") for element_id in package.element_ids)
        selected_count = max(1, len(package.element_ids))
        anchored_ratio = (
            label_counts.get("Core", 0)
            + label_counts.get("Cluster", 0)
            + label_counts.get("Support", 0)
        ) / selected_count
        completion_ratio = label_counts.get("Completion", 0) / selected_count
        span_attached = sum(
            1
            for decision in package.decisions
            if _decision_value(decision, "direction") == "span" and _decision_value(decision, "action") == "attached"
        )
        cluster_attached = sum(
            1
            for decision in package.decisions
            if _decision_value(decision, "direction") == "cluster" and _decision_value(decision, "action") == "attached"
        )
        completion_attached = sum(
            1
            for decision in package.decisions
            if _decision_value(decision, "direction") == "completion" and _decision_value(decision, "action") == "attached"
        )
        drift_events = sum(
            1 for decision in package.decisions if _decision_value(decision, "action") in {"marked", "rolled_back"}
        )
        budget_stops = sum(1 for decision in package.decisions if "token budget" in _decision_value(decision, "reason").lower())
        accepted_signal = min(0.22, span_attached * 0.05 + cluster_attached * 0.025)
        completion_patch_credit = min(0.1, completion_attached * 0.018)
        patch_penalty = min(0.24, completion_ratio * 0.3)
        drift_penalty = min(0.16, drift_events * 0.06 + budget_stops * 0.035)
        score = 0.46 + anchored_ratio * 0.36 + accepted_signal + completion_patch_credit - patch_penalty - drift_penalty
        return _clamp01(score)

    def _package_plan_coverage_score(
        self,
        *,
        package_tokens: set[str],
        package_text: str,
        role_names: set[str],
        prompt: str,
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> tuple[float, list[str], list[str]]:
        if retrieval_plan is None or not retrieval_plan.sub_needs:
            prompt_tokens = set(_completion_tokens(prompt))
            lexical = _jaccard(package_tokens, prompt_tokens)
            return _clamp01(0.5 + lexical), [], []

        normalized_text = _completion_normalized_text(package_text)
        scores: list[float] = []
        covered: list[str] = []
        missing: list[str] = []
        for sub_need in retrieval_plan.sub_needs:
            term_scores: list[float] = []
            terms = sub_need.search_terms or [sub_need.need]
            for term in terms:
                term_norm = _completion_normalized_text(term)
                term_tokens = set(_completion_tokens(term))
                if not term_tokens:
                    continue
                if term_norm and term_norm in normalized_text:
                    term_scores.append(1.0)
                else:
                    term_scores.append(_jaccard(package_tokens, term_tokens))
            if term_scores:
                ranked_terms = sorted(term_scores, reverse=True)
                best_term = ranked_terms[0]
                top_terms = ranked_terms[:3]
                mean_top_terms = sum(top_terms) / len(top_terms)
                covered_fraction = sum(1 for value in term_scores if value >= 0.42) / len(term_scores)
                term_score = _clamp01(best_term * 0.46 + mean_top_terms * 0.34 + covered_fraction * 0.20)
            else:
                term_score = _jaccard(package_tokens, _completion_tokens(sub_need.need))
            expected = {_role_family(role) for role in sub_need.expected_roles if role}
            role_families = {_role_family(role) for role in role_names}
            role_score = len(expected & role_families) / len(expected) if expected else 0.75
            score = _clamp01(term_score * 0.68 + role_score * 0.32)
            scores.append(score)
            if score >= 0.42:
                covered.append(sub_need.need)
            else:
                missing.append(sub_need.need)
        if not scores:
            return 0.55, covered, missing
        return _clamp01(sum(scores) / len(scores)), covered, missing

    def _package_role_coverage_score(
        self,
        *,
        prompt: str,
        role_names: set[str],
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> float:
        expected: set[str] = set()
        if retrieval_plan is not None:
            for sub_need in retrieval_plan.sub_needs:
                expected.update(_role_family(role) for role in sub_need.expected_roles if role)
        prompt_tokens = set(_completion_tokens(prompt))
        if _prompt_asks_why(prompt):
            expected.update({"proof_setup", "proof_reason", "proof_conclusion"})
        if {"define", "definition", "meaning", "mean"} & prompt_tokens:
            expected.add("definition")
        if {"step", "steps", "procedure", "process", "algorithm"} & prompt_tokens:
            expected.add("procedure")
        if {"example", "examples"} & prompt_tokens:
            expected.add("example")
        if self._prompt_wants_support(prompt):
            expected.add("support")
        if not expected:
            return 0.72
        role_families = {_role_family(role) for role in role_names}
        covered = expected & role_families
        return _clamp01(len(covered) / len(expected))

    def _package_completion_closure_score(self, package: QueryAssembledPackage) -> tuple[float, list[str]]:
        diagnostics = package.completion_diagnostics
        if diagnostics is None or not diagnostics.enabled:
            return 0.74, []
        if not diagnostics.rounds:
            return 1.0 if not diagnostics.completion_needed_initial else 0.72, []
        last_round = diagnostics.rounds[-1]
        needed = set(last_round.needed_after or last_round.needed_before)
        open_keys = set(last_round.open_after)
        if not needed:
            return 1.0, []
        needed_weight = sum(_completion_key_weight(key) for key in needed)
        open_weight = sum(_completion_key_weight(key) for key in open_keys)
        score = 1.0 - open_weight / max(0.01, needed_weight)
        return _clamp01(score), sorted(open_keys)

    def _package_grounding_score(self, selected_propositions: list[QueryEvidenceProposition]) -> float:
        scored: list[float] = []
        severity_scores = {
            "grounded": 1.0,
            "weak": 0.76,
            "vague_target": 0.58,
            "ungrounded": 0.38,
            "support_mismatch": 0.25,
        }
        for proposition in selected_propositions:
            if proposition.grounding is None:
                continue
            scored.append(severity_scores.get(proposition.grounding.severity, 0.68))
            for role in proposition.grounding.role_diagnostics:
                scored.append(severity_scores.get(role.severity, 0.68))
        if not scored:
            return 0.74
        return _clamp01(sum(scored) / len(scored))

    def _package_support_score(
        self,
        *,
        prompt: str,
        selected: list[ElementSignalRecord],
        package_text: str,
        role_names: set[str],
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> float:
        expected_roles: set[str] = set()
        if retrieval_plan is not None:
            for sub_need in retrieval_plan.sub_needs:
                expected_roles.update(_role_family(role) for role in sub_need.expected_roles)
        support_needed = self._prompt_wants_support(prompt) or "support" in expected_roles
        support_present = "support" in {_role_family(role) for role in role_names} or any(
            signal.element_type in SUPPORT_ELEMENT_TYPES for signal in selected
        )
        support_referenced = bool(re.search(r"\b(figure|image|diagram|chart|table|formula|equation|shown)\b", package_text, re.IGNORECASE))
        if support_needed:
            return 1.0 if support_present else 0.42
        if support_present and not support_referenced and len(selected) > 2:
            return 0.68
        return 0.88 if support_present else 0.82

    def _package_source_coherence_score(self, selected: list[ElementSignalRecord]) -> float:
        if len(selected) <= 1:
            return 0.7
        indices = sorted(signal.element_index for signal in selected)
        gaps = [right - left for left, right in zip(indices, indices[1:])]
        if not gaps:
            return 0.7
        large_gaps = sum(1 for gap in gaps if gap > 3)
        max_gap = max(gaps)
        contiguous_ratio = sum(1 for gap in gaps if gap <= 1) / len(gaps)
        score = 0.58 + contiguous_ratio * 0.34 - min(0.28, large_gaps * 0.08) - min(0.18, max(0, max_gap - 8) * 0.015)
        return _clamp01(score)

    def _package_noise_score(
        self,
        *,
        selected: list[ElementSignalRecord],
        package: QueryAssembledPackage,
    ) -> tuple[float, float]:
        if not selected:
            return 0.0, 0.0
        boilerplate = sum(signal.boilerplate_score for signal in selected) / len(selected)
        heading_only_penalty = 0.22 if len(selected) <= 2 and any(signal.is_heading for signal in selected) else 0.0
        token_efficiency = _clamp01(1.0 - max(0, package.token_count - self.max_package_tokens) / max(200, self.max_package_tokens * 2))
        duplicate_texts = Counter(_completion_normalized_text(signal.text) for signal in selected)
        duplicate_penalty = min(0.18, sum(count - 1 for count in duplicate_texts.values() if count > 1) * 0.06)
        noise = token_efficiency * 0.58 + (1.0 - _clamp01(boilerplate)) * 0.28 + 0.14
        noise -= heading_only_penalty + duplicate_penalty
        return _clamp01(noise), token_efficiency

    def _decision(
        self,
        signal: ElementSignalRecord,
        *,
        direction: str,
        action: str,
        query_similarity: float,
        core_similarity: float,
        previous_query_similarity: float,
        previous_core_similarity: float,
        reason: str,
    ) -> QueryAssemblyDecision:
        return QueryAssemblyDecision(
            element_id=signal.element_id,
            direction=direction,
            action=action,
            query_similarity=round(query_similarity, 4),
            core_similarity=round(core_similarity, 4),
            query_delta=round(query_similarity - previous_query_similarity, 4),
            core_delta=round(core_similarity - previous_core_similarity, 4),
            reason=reason,
        )

    def _embed(self, texts: list[str]) -> np.ndarray:
        if self._embed_texts is not None:
            embeddings = self._embed_texts(texts)
        else:
            embeddings = self._embedding_backend.encode(texts)  # type: ignore[union-attr]
        return _normalize(np.asarray(embeddings, dtype=float))


class PropositionQueryTimeEvidenceAssembler(QueryTimeEvidenceAssembler):
    """Select query cores from generated propositions, then return source-backed packages."""

    PROPOSITION_PROMPT_VERSION = "query_proposition_assembly_v2_roles"

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        proposition_batch_size: int = 12,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.llm_client = llm_client
        self.proposition_batch_size = max(1, int(proposition_batch_size))
        self._proposition_cache: dict[str, list[_PropositionDraft]] = {}

    def assemble(self, document: ExtractedDocument, prompt: str) -> QueryAssemblyResult:
        pipeline = self._signal_builder.build(document)
        signals = [signal for signal in pipeline.signals if signal.text.strip()]
        if not signals:
            return QueryAssemblyResult(prompt=prompt, packages=[], propositions=[])

        propositions = self._propositions_for_signals(signals)
        if not propositions:
            return super().assemble(document, prompt)

        embeddings = self._embed([prompt, *[proposition.text for proposition in propositions]])
        prompt_embedding = embeddings[0]
        proposition_embeddings = embeddings[1:]
        proposition_similarities = proposition_embeddings @ prompt_embedding
        core_candidates = self._top_proposition_core_candidates(
            signals=signals,
            propositions=propositions,
            proposition_embeddings=proposition_embeddings,
            proposition_similarities=proposition_similarities,
        )
        packages = [
            self._assemble_for_core(
                signals=signals,
                prompt_embedding=prompt_embedding,
                core_candidate=core_candidate,
                package_index=index,
            )
            for index, core_candidate in enumerate(core_candidates)
        ]
        ranked = self._rank_query_packages(
            packages=packages,
            prompt=prompt,
            signals=signals,
            propositions=propositions,
        )
        return QueryAssemblyResult(prompt=prompt, packages=ranked, propositions=propositions)

    def _top_proposition_core_candidates(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_embeddings: np.ndarray,
        proposition_similarities: np.ndarray,
    ) -> list[_CoreCandidate]:
        ranked = sorted(
            range(len(propositions)),
            key=lambda index: self._proposition_core_score(
                signals=signals,
                proposition=propositions[index],
                similarity=float(proposition_similarities[index]),
            ),
            reverse=True,
        )
        candidates: list[_CoreCandidate] = []
        used_elements: set[str] = set()
        for index in ranked:
            proposition = propositions[index]
            if proposition.element_id in used_elements:
                continue
            candidates.append(
                _CoreCandidate(
                    element_index=proposition.element_index,
                    prompt_similarity=float(proposition_similarities[index]),
                    core_embedding=proposition_embeddings[index],
                    proposition_id=proposition.proposition_id,
                    proposition_index=index,
                    proposition_text=proposition.text,
                    support_element_ids=list(proposition.support_element_ids),
                )
            )
            used_elements.add(proposition.element_id)
            if len(candidates) >= self.top_k_cores:
                break
        return candidates

    def _proposition_core_score(
        self,
        *,
        signals: list[ElementSignalRecord],
        proposition: QueryEvidenceProposition,
        similarity: float,
    ) -> tuple[float, float, int]:
        signal = signals[proposition.element_index]
        score = similarity
        if signal.is_heading and len(proposition.text.split()) <= 5:
            score -= 0.12
        if signal.element_type in {"table", "figure", "image", "chart", "diagram"}:
            score += 0.04
        if len(proposition.text.split()) >= 6:
            score += 0.03
        return (score, signal.lexical_keyword_density, -signal.token_count)

    def _propositions_for_signals(self, signals: list[ElementSignalRecord]) -> list[QueryEvidenceProposition]:
        by_element: dict[str, list[_PropositionDraft]] = {}
        support_ids = {signal.element_id for signal in signals if signal.element_type in SUPPORT_ELEMENT_TYPES}
        missing = []
        for signal in signals:
            cache_key = self._proposition_cache_key(signal)
            cached = self._proposition_cache.get(cache_key)
            if cached is None:
                if signal.element_type in SUPPORT_ELEMENT_TYPES:
                    by_element[signal.element_id] = self._fallback_propositions(signal)
                    self._proposition_cache[cache_key] = by_element[signal.element_id]
                else:
                    missing.append(signal)
            else:
                by_element[signal.element_id] = list(cached)

        if missing:
            if self.llm_client is None:
                for signal in missing:
                    by_element[signal.element_id] = self._fallback_propositions(signal)
                    self._proposition_cache[self._proposition_cache_key(signal)] = by_element[signal.element_id]
            else:
                self._generate_missing_propositions(missing, by_element, all_signals=signals)

        propositions: list[QueryEvidenceProposition] = []
        for signal_index, signal in enumerate(signals):
            drafts = by_element.get(signal.element_id) or self._fallback_propositions(signal)
            for index, draft in enumerate(drafts):
                proposition_text, support_refs = self._split_support_refs(draft.text, support_ids=support_ids)
                if not proposition_text:
                    continue
                propositions.append(
                    QueryEvidenceProposition(
                        proposition_id=f"{signal.element_id}::p{index:02d}",
                        element_id=signal.element_id,
                        element_index=signal_index,
                        text=proposition_text,
                        support_element_ids=support_refs,
                        roles=draft.roles,
                        grounding=self._ground_proposition(
                            signal=signal,
                            proposition_text=proposition_text,
                            roles=draft.roles,
                            support_element_ids=support_refs,
                        ),
                    )
                )
        return propositions

    def _generate_missing_propositions(
        self,
        missing: list[ElementSignalRecord],
        by_element: dict[str, list[_PropositionDraft]],
        *,
        all_signals: list[ElementSignalRecord],
    ) -> None:
        batches = [
            missing[index : index + self.proposition_batch_size]
            for index in range(0, len(missing), self.proposition_batch_size)
        ]
        requests = [
            LLMRequest(
                system=(
                    "You decompose document content into source-faithful standalone propositions. "
                    "Return only JSON matching the requested schema."
                ),
                user=self._proposition_generation_prompt(batch, all_signals=all_signals),
                temperature=0.0,
                response_format=self._proposition_response_format(),
            )
            for batch in batches
        ]
        responses = self.llm_client.complete_many(requests) if self.llm_client is not None else []
        for batch, response in zip(batches, responses):
            parsed = self._parse_proposition_response(getattr(response, "content", str(response)))
            if parsed is None:
                parsed = {}
            for signal in batch:
                propositions = parsed.get(signal.element_id) or self._fallback_propositions(signal)
                cleaned = self._clean_propositions(propositions)
                by_element[signal.element_id] = cleaned
                self._proposition_cache[self._proposition_cache_key(signal)] = cleaned

    def _proposition_generation_prompt(
        self,
        signals: list[ElementSignalRecord],
        *,
        all_signals: list[ElementSignalRecord] | None = None,
    ) -> str:
        lines: list[str] = []
        for signal in signals:
            text = signal.text.strip()
            if len(text) > 1600:
                text = text[:1597].rstrip() + "..."
            lines.extend(
                [
                    f"Element ID: {signal.element_id}",
                    f"Type: {signal.element_type}",
                    f"Page: {signal.page_number}",
                    f"Content: {text}",
                    "",
                ]
            )
        support_context = self._support_context_for_batch(signals, all_signals or signals)
        return "\n".join(
            [
                'Decompose each "Content" into clear, simple, source-faithful propositions.',
                "Each proposition must be interpretable out of context.",
                "Split compound content into separate propositions when useful.",
                'Replace pronouns or vague references such as "this", "that", "it", "they", and "above" with the source referent when the referent is present in the content.',
                "For each proposition, include role hypotheses that describe what job the proposition plays in the document.",
                "Prefer the controlled roles below. Use other only when none fit, and explain the custom function in reason.",
                "Role definitions:",
                "- definition: introduces the meaning, identity, scope, or notation of a term, symbol, object, variable, or concept.",
                "- claim: states an assertion or result that may need support.",
                "- assumption: states a given condition accepted before reasoning starts.",
                "- condition: states a constraint, requirement, case, or if/when condition.",
                "- procedure_step: states an ordered action in a method or algorithm.",
                "- proof_setup: introduces objects, cases, variables, or constraints needed before proof reasoning.",
                "- proof_reason: explains why a claim follows from earlier setup, conditions, or facts.",
                "- proof_conclusion: states the result, implication, contradiction, or final consequence reached by reasoning.",
                "- contradiction: states an impossible conflict used by proof.",
                "- quantity_bound: states a numeric, asymptotic, distance, count, or comparison bound.",
                "- example: gives a concrete instance or illustration.",
                "- visual_support/table_support/formula_support: carries evidence or explanation through a visual, table, or formula.",
                "- contrast_exception: states a distinction, exception, limitation, or contrast.",
                "Do not tag every proposition as definition. Only use definition when the proposition actually introduces or explains a target.",
                "Roles are hypotheses, not summaries. Keep targets and values short and copied from or tightly grounded in the source text.",
                "Nearby support assets are listed as [SUPPORT element_id]. If a support asset clearly illustrates or proves a proposition, append the exact support reference to that proposition.",
                "Do not invent facts that are not supported by the content.",
                "Use an empty propositions array only when the content has no meaningful proposition.",
                "",
                "Return one entry for every Element ID.",
                "",
                "Nearby Support Context:",
                support_context or "None.",
                "",
                "Elements:",
                "\n".join(lines).strip(),
            ]
        )

    def _support_context_for_batch(
        self,
        batch: list[ElementSignalRecord],
        all_signals: list[ElementSignalRecord],
        *,
        radius: int = 5,
    ) -> str:
        if not batch:
            return ""
        positions = {signal.element_id: index for index, signal in enumerate(all_signals)}
        batch_positions = [positions[signal.element_id] for signal in batch if signal.element_id in positions]
        if not batch_positions:
            return ""
        start = min(batch_positions)
        end = max(batch_positions)
        lower = max(0, start - radius)
        upper = min(len(all_signals) - 1, end + radius)
        lines: list[str] = []
        for signal in all_signals[lower : upper + 1]:
            if signal.element_type not in SUPPORT_ELEMENT_TYPES:
                continue
            text = re.sub(r"\s+", " ", signal.text).strip()
            if len(text) > 500:
                text = text[:497].rstrip() + "..."
            if text:
                lines.append(f"[SUPPORT {signal.element_id}] Type: {signal.element_type}. Content: {text}")
            else:
                lines.append(f"[SUPPORT {signal.element_id}] Type: {signal.element_type}.")
        return "\n".join(lines)

    def _proposition_response_format(self) -> Mapping[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "query_element_propositions",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "elements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "element_id": {"type": "string"},
                                    "propositions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "text": {"type": "string"},
                                                "roles": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "role": {
                                                                "type": "string",
                                                                "enum": [
                                                                    "definition",
                                                                    "claim",
                                                                    "assumption",
                                                                    "condition",
                                                                    "procedure_step",
                                                                    "proof_setup",
                                                                    "proof_reason",
                                                                    "proof_conclusion",
                                                                    "contradiction",
                                                                    "quantity_bound",
                                                                    "example",
                                                                    "visual_support",
                                                                    "table_support",
                                                                    "formula_support",
                                                                    "contrast_exception",
                                                                    "other",
                                                                ],
                                                            },
                                                            "target": {"type": "string"},
                                                            "value": {"type": "string"},
                                                            "confidence": {"type": "number"},
                                                            "reason": {"type": "string"},
                                                        },
                                                        "required": ["role", "target", "value", "confidence", "reason"],
                                                        "additionalProperties": False,
                                                    },
                                                },
                                            },
                                            "required": ["text", "roles"],
                                            "additionalProperties": False,
                                        },
                                    },
                                },
                                "required": ["element_id", "propositions"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["elements"],
                    "additionalProperties": False,
                },
            },
        }

    def _parse_proposition_response(self, content: str) -> dict[str, list[_PropositionDraft]] | None:
        payload = _extract_json_payload(content)
        if payload is None:
            return None
        if isinstance(payload, dict) and isinstance(payload.get("elements"), list):
            items = payload["elements"]
        elif isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and "element_id" in payload:
            items = [payload]
        elif isinstance(payload, dict):
            return {
                str(element_id): self._clean_propositions(propositions)
                for element_id, propositions in payload.items()
                if isinstance(propositions, list)
            }
        else:
            return None

        parsed: dict[str, list[str]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            element_id = str(item.get("element_id") or "").strip()
            if not element_id:
                continue
            propositions = item.get("propositions", [])
            parsed[element_id] = self._clean_propositions(propositions if isinstance(propositions, list) else [])
        return parsed

    def _clean_propositions(self, propositions: Iterable[Any]) -> list[_PropositionDraft]:
        cleaned: list[_PropositionDraft] = []
        for proposition in propositions:
            roles: list[PropositionRoleHypothesis] = []
            if isinstance(proposition, _PropositionDraft):
                text_value = proposition.text
                roles = list(proposition.roles)
            elif isinstance(proposition, Mapping):
                text_value = proposition.get("text", "")
                roles = self._clean_role_hypotheses(proposition.get("roles", []))
            else:
                text_value = proposition
            text = re.sub(r"\s+", " ", str(text_value)).strip()
            if text:
                cleaned.append(_PropositionDraft(text=text, roles=roles))
        return cleaned

    def _clean_role_hypotheses(self, roles: Any) -> list[PropositionRoleHypothesis]:
        if not isinstance(roles, list):
            return []
        cleaned: list[PropositionRoleHypothesis] = []
        for item in roles:
            if not isinstance(item, Mapping):
                continue
            role = re.sub(r"\s+", "_", str(item.get("role", ""))).strip().lower()
            if not role:
                continue
            target = re.sub(r"\s+", " ", str(item.get("target", ""))).strip()
            value = re.sub(r"\s+", " ", str(item.get("value", ""))).strip()
            reason = re.sub(r"\s+", " ", str(item.get("reason", ""))).strip()
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            cleaned.append(
                PropositionRoleHypothesis(
                    role=role,
                    target=target[:120],
                    value=value[:220],
                    confidence=max(0.0, min(1.0, confidence)),
                    reason=reason[:220],
                )
            )
            if len(cleaned) >= 5:
                break
        return cleaned

    def _fallback_propositions(self, signal: ElementSignalRecord) -> list[_PropositionDraft]:
        text = re.sub(r"\s+", " ", signal.text).strip()
        if not text:
            return []
        if signal.is_heading:
            return [_PropositionDraft(text=text)]
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
        return [_PropositionDraft(text=sentence) for sentence in (sentences or [text])]

    def _split_support_refs(self, text: str, *, support_ids: set[str]) -> tuple[str, list[str]]:
        refs: list[str] = []
        for match in SUPPORT_REF_RE.finditer(text):
            support_id = match.group(1).strip()
            if support_id in support_ids and support_id not in refs:
                refs.append(support_id)
        cleaned = SUPPORT_REF_RE.sub("", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned, refs

    def _ground_proposition(
        self,
        *,
        signal: ElementSignalRecord,
        proposition_text: str,
        roles: list[PropositionRoleHypothesis],
        support_element_ids: list[str],
    ) -> PropositionGroundingDiagnostics:
        source_tokens = set(_completion_tokens(signal.text))
        proposition_tokens = set(_completion_tokens(proposition_text))
        kept_terms = sorted((source_tokens & proposition_tokens) - STOPWORDS)[:16]
        novel_terms = sorted(
            token
            for token in proposition_tokens - source_tokens
            if token not in STOPWORDS and token not in COMPLETION_NOISE_TERMS
        )[:16]
        overlap_ratio = len(source_tokens & proposition_tokens) / max(1, len(proposition_tokens))
        source_symbols = sorted(_grounding_symbols(signal.text))
        proposition_symbols = sorted(_grounding_symbols(proposition_text))
        role_diagnostics = [
            self._ground_role(
                signal=signal,
                proposition_text=proposition_text,
                role=role,
                support_element_ids=support_element_ids,
            )
            for role in roles
        ]
        severe_roles = {item.severity for item in role_diagnostics}
        if "support_mismatch" in severe_roles:
            status = "support_mismatch"
            severity = "support_mismatch"
        elif "ungrounded" in severe_roles or (overlap_ratio < 0.16 and not (set(source_symbols) & set(proposition_symbols))):
            status = "ungrounded"
            severity = "ungrounded"
        elif "vague_target" in severe_roles:
            status = "vague_target"
            severity = "vague_target"
        elif "weak" in severe_roles or overlap_ratio < 0.32:
            status = "weak"
            severity = "weak"
        else:
            status = "grounded"
            severity = "grounded"
        return PropositionGroundingDiagnostics(
            status=status,
            severity=severity,
            source_overlap_ratio=round(overlap_ratio, 4),
            kept_terms=kept_terms,
            novel_terms=novel_terms,
            source_symbols=source_symbols,
            proposition_symbols=proposition_symbols,
            role_diagnostics=role_diagnostics,
        )

    def _ground_role(
        self,
        *,
        signal: ElementSignalRecord,
        proposition_text: str,
        role: PropositionRoleHypothesis,
        support_element_ids: list[str],
    ) -> RoleGroundingDiagnostics:
        source_text = signal.text
        combined_source = " ".join([source_text, proposition_text])
        role_payload = " ".join([role.target, role.value, role.reason])
        target_normalized = _completion_normalized_text(role.target)
        source_normalized = _completion_normalized_text(source_text)
        proposition_normalized = _completion_normalized_text(proposition_text)
        target_in_source = bool(target_normalized and target_normalized in source_normalized)
        target_in_proposition = bool(target_normalized and target_normalized in proposition_normalized)
        target_tokens = set(_completion_tokens(role.target))
        combined_tokens = set(_completion_tokens(combined_source))
        token_overlap = len(target_tokens & combined_tokens) / max(1, len(target_tokens))
        role_symbols = _grounding_symbols(role_payload)
        source_symbols = _grounding_symbols(combined_source)
        symbol_overlap = len(role_symbols & source_symbols) / max(1, len(role_symbols)) if role_symbols else 0.0
        behavior_match, behavior_note = self._role_behavior_match(role=role.role, text=combined_source, signal=signal)
        support_grounded = None
        notes: list[str] = []
        if behavior_note:
            notes.append(behavior_note)
        if target_in_proposition:
            notes.append("target appears in proposition")
        if target_in_source:
            notes.append("target appears in source")
        if role_symbols:
            notes.append(f"role symbols: {', '.join(sorted(role_symbols)[:6])}")
        if source_symbols & role_symbols:
            notes.append(f"symbol overlap: {', '.join(sorted(source_symbols & role_symbols)[:6])}")

        role_name = role.role.strip().lower()
        if role_name in {"visual_support", "table_support", "formula_support"}:
            support_grounded = self._role_support_grounded(
                signal=signal,
                text=combined_source,
                support_element_ids=support_element_ids,
                role_name=role_name,
            )
            if not support_grounded:
                return RoleGroundingDiagnostics(
                    role=role_name,
                    target=role.target,
                    status="support_mismatch",
                    severity="support_mismatch",
                    target_in_proposition=target_in_proposition,
                    target_in_source=target_in_source,
                    target_token_overlap=round(token_overlap, 4),
                    role_symbol_overlap=round(symbol_overlap, 4),
                    behavior_match=behavior_match,
                    support_grounded=support_grounded,
                    vague_target=False,
                    notes=[*notes, "support role lacks support element/type/reference evidence"],
                )

        vague_target = self._role_target_is_vague(role.target)
        targeted_role = role_name in {
            "definition",
            "condition",
            "quantity_bound",
            "visual_support",
            "table_support",
            "formula_support",
        }
        if vague_target and targeted_role:
            return RoleGroundingDiagnostics(
                role=role_name,
                target=role.target,
                status="vague_target",
                severity="vague_target",
                target_in_proposition=target_in_proposition,
                target_in_source=target_in_source,
                target_token_overlap=round(token_overlap, 4),
                role_symbol_overlap=round(symbol_overlap, 4),
                behavior_match=behavior_match,
                support_grounded=support_grounded,
                vague_target=True,
                notes=[*notes, "target is too broad to validate confidently"],
            )

        exact_or_token = target_in_source or target_in_proposition or token_overlap >= 0.67
        symbolic = bool(role_symbols) and symbol_overlap >= 0.5
        if (exact_or_token or symbolic) and behavior_match:
            status = "grounded"
            severity = "grounded"
        elif exact_or_token or symbolic or behavior_match:
            status = "weak"
            severity = "weak"
        elif role_payload.strip() and target_tokens:
            status = "ungrounded"
            severity = "ungrounded"
        else:
            status = "weak"
            severity = "weak"
            notes.append("semantic or empty target; cheap audit cannot validate")

        return RoleGroundingDiagnostics(
            role=role_name,
            target=role.target,
            status=status,
            severity=severity,
            target_in_proposition=target_in_proposition,
            target_in_source=target_in_source,
            target_token_overlap=round(token_overlap, 4),
            role_symbol_overlap=round(symbol_overlap, 4),
            behavior_match=behavior_match,
            support_grounded=support_grounded,
            vague_target=vague_target,
            notes=notes,
        )

    def _role_behavior_match(
        self,
        *,
        role: str,
        text: str,
        signal: ElementSignalRecord,
    ) -> tuple[bool, str]:
        role_name = role.strip().lower()
        normalized = _completion_normalized_text(text)
        if role_name == "definition":
            matched = bool(re.search(r"\b(let|denote\w*|means?|refers?\s+to|defined\s+as|consists?\s+of|is\s+(?:a|an|the|called))\b", normalized))
            return matched, "definition-like language" if matched else "no definition-like language"
        if role_name in {"proof_setup", "assumption", "condition", "claim"}:
            matched = bool(re.search(r"\b(suppose|assum\w*|let|consider|given|claim|if|when)\b", normalized))
            return matched, "setup/condition-like language" if matched else "no setup/condition-like language"
        if role_name in {"proof_reason", "contradiction"}:
            matched = bool(re.search(r"\b(since|because|as|therefore|thus|hence|contradict\w*|implies?|<=|>=|<|>|at\s+least|at\s+most)\b", normalized))
            return matched, "reasoning/derivation-like language" if matched else "no reasoning/derivation-like language"
        if role_name == "proof_conclusion":
            matched = bool(re.search(r"\b(therefore|thus|hence|this\s+(?:means|implies)|implies?|contradict\w*)\b", normalized))
            return matched, "conclusion-like language" if matched else "no conclusion-like language"
        if role_name == "quantity_bound":
            matched = bool(re.search(r"\b(\d+|at\s+least|at\s+most|within|bounded|less\s+than|greater\s+than|<=|>=|<|>|omega|delta)\b", normalized))
            return matched, "quantity/bound-like language" if matched else "no quantity/bound-like language"
        if role_name == "procedure_step":
            matched = bool(re.search(r"\b(compute|sort|partition|call|return|create|construct|compare|recursively|step)\b", normalized))
            return matched, "procedure-like language" if matched else "no procedure-like language"
        if role_name in {"visual_support", "table_support", "formula_support"}:
            return self._role_support_grounded(signal=signal, text=text, support_element_ids=[], role_name=role_name), "support-like evidence"
        if role_name in {"example", "contrast_exception", "other"}:
            return True, "generic role"
        return False, "unknown role behavior"

    def _role_support_grounded(
        self,
        *,
        signal: ElementSignalRecord,
        text: str,
        support_element_ids: list[str],
        role_name: str,
    ) -> bool:
        if support_element_ids:
            return True
        if role_name == "table_support" and signal.element_type == "table":
            return True
        if role_name == "formula_support" and signal.element_type == "formula":
            return True
        if role_name == "visual_support" and signal.element_type in SUPPORT_ELEMENT_TYPES:
            return True
        return bool(re.search(r"\b(figure|table|formula|equation|diagram|chart|shown|illustrat\w*)\b", text, re.IGNORECASE))

    def _role_target_is_vague(self, target: str) -> bool:
        tokens = _completion_tokens(target)
        if not tokens:
            return True
        if len(tokens) == 1 and tokens[0] in VAGUE_ROLE_TARGETS:
            return True
        if set(tokens) <= VAGUE_ROLE_TARGETS:
            return True
        return False

    def _proposition_cache_key(self, signal: ElementSignalRecord) -> str:
        payload = "\n".join([self.PROPOSITION_PROMPT_VERSION, signal.element_id, signal.text])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ConsensusKnnPropositionEvidenceAssembler(PropositionQueryTimeEvidenceAssembler):
    """Build packages from proposition cores plus stable non-contiguous kNN pools."""

    def __init__(
        self,
        *,
        k_values: tuple[int, ...] | None = None,
        min_neighbor_stability: float = 0.4,
        min_edge_similarity: float = 0.32,
        max_cluster_hops: int = 1,
        max_cluster_propositions: int = 10,
        min_candidate_score: float = 0.42,
        max_order_gap_for_span: int = 2,
        max_attached_spans: int = 2,
        min_span_attach_score: float = 0.38,
        span_expansion_radius: int = 3,
        min_span_expansion_gain: float = 0.035,
        span_completeness_slack: float = 0.05,
        use_span_competition: bool = False,
        use_language_map: bool = False,
        use_query_planner: bool = False,
        query_planner_bridge_slots: int = 1,
        query_planner_max_map_items: int = 140,
        query_planner_max_search_forms: int = 12,
        language_core_weight: float = 0.12,
        language_candidate_weight: float = 0.06,
        language_candidate_slots: int = 1,
        min_language_core_score: float = 0.45,
        use_relation_geometry: bool = True,
        relation_geometry_weight: float = 0.06,
        relation_family_similarity: float = 0.82,
        min_relation_family_size: int = 3,
        use_source_traversal_audit: bool = True,
        source_traversal_anchor_limit: int = 3,
        source_traversal_rounds: int = 2,
        source_traversal_accepts_per_round: int = 3,
        source_traversal_candidate_limit: int = 16,
        use_dependency_resolver: bool = False,
        dependency_resolver_depth: int = 2,
        dependency_resolver_max_frames: int = 32,
        dependency_support_verifier: SupportVerifier | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.k_values = tuple(k_values) if k_values else ()
        self.min_neighbor_stability = max(0.0, min(1.0, float(min_neighbor_stability)))
        self.min_edge_similarity = max(-1.0, min(1.0, float(min_edge_similarity)))
        self.max_cluster_hops = max(1, int(max_cluster_hops))
        self.max_cluster_propositions = max(1, int(max_cluster_propositions))
        self.min_candidate_score = float(min_candidate_score)
        self.max_order_gap_for_span = max(0, int(max_order_gap_for_span))
        self.max_attached_spans = max(0, int(max_attached_spans))
        self.min_span_attach_score = float(min_span_attach_score)
        self.span_expansion_radius = max(0, int(span_expansion_radius))
        self.min_span_expansion_gain = max(0.0, float(min_span_expansion_gain))
        self.span_completeness_slack = max(0.0, float(span_completeness_slack))
        self.use_span_competition = bool(use_span_competition)
        self.use_language_map = bool(use_language_map)
        self.use_query_planner = bool(use_query_planner)
        self.query_planner_bridge_slots = max(0, int(query_planner_bridge_slots))
        self.query_planner_max_map_items = max(20, int(query_planner_max_map_items))
        self.query_planner_max_search_forms = max(1, int(query_planner_max_search_forms))
        self.language_core_weight = max(0.0, float(language_core_weight))
        self.language_candidate_weight = max(0.0, float(language_candidate_weight))
        self.language_candidate_slots = max(0, int(language_candidate_slots))
        self.min_language_core_score = max(0.0, float(min_language_core_score))
        self.use_relation_geometry = bool(use_relation_geometry)
        self.relation_geometry_weight = max(0.0, float(relation_geometry_weight))
        self.relation_family_similarity = max(-1.0, min(1.0, float(relation_family_similarity)))
        self.min_relation_family_size = max(2, int(min_relation_family_size))
        self.use_source_traversal_audit = bool(use_source_traversal_audit)
        self.source_traversal_anchor_limit = max(0, int(source_traversal_anchor_limit))
        self.source_traversal_rounds = max(0, int(source_traversal_rounds))
        self.source_traversal_accepts_per_round = max(1, int(source_traversal_accepts_per_round))
        self.source_traversal_candidate_limit = max(1, int(source_traversal_candidate_limit))
        self.use_dependency_resolver = bool(use_dependency_resolver)
        self.dependency_resolver_depth = max(0, int(dependency_resolver_depth))
        self.dependency_resolver_max_frames = max(1, int(dependency_resolver_max_frames))
        self.dependency_support_verifier = dependency_support_verifier
        self._query_plan_cache: dict[str, QueryRetrievalPlan] = {}
        self._source_traversal_vocabulary_cache: dict[str, _SourceTraversalVocabularyCache] = {}
        self._document_assembly_cache: dict[str, _DocumentAssemblyCache] = {}
        self._document_language_cache: dict[str, _DocumentLanguageCache] = {}

    def assemble(self, document: ExtractedDocument, prompt: str) -> QueryAssemblyResult:
        pipeline = self._signal_builder.build(document)
        signals = [signal for signal in pipeline.signals if signal.text.strip()]
        if not signals:
            return QueryAssemblyResult(prompt=prompt, packages=[], propositions=[])

        propositions = self._propositions_for_signals(signals)
        if not propositions:
            return super().assemble(document, prompt)

        retrieval_plan = self._query_retrieval_plan(signals=signals, propositions=propositions, prompt=prompt)
        bridge_prop_indices: list[int] = []
        bridge_anchor_groups: list[tuple[int, ...]] = []
        if retrieval_plan is not None:
            _bridge_texts, bridge_prop_indices, bridge_anchor_groups = self._source_grounded_bridge_candidates(
                signals=signals,
                propositions=propositions,
                prompt=prompt,
                plan=retrieval_plan,
            )
        prompt_embedding = self._embed([prompt])[0]
        document_cache = self._document_assembly_cache_for(signals=signals, propositions=propositions)
        proposition_embeddings = document_cache.proposition_embeddings
        proposition_similarities = proposition_embeddings @ prompt_embedding
        language_scores = self._language_proposition_scores(prompt=prompt, propositions=propositions)
        core_candidates = self._top_language_proposition_core_candidates(
            signals=signals,
            propositions=propositions,
            proposition_embeddings=proposition_embeddings,
            proposition_similarities=proposition_similarities,
            language_scores=language_scores,
            forced_prop_indices=bridge_prop_indices,
            forced_anchor_groups=bridge_anchor_groups,
            forced_slots=self.query_planner_bridge_slots if retrieval_plan is not None else 0,
        )
        dependency_packages: list[ResolvedPackage] = []
        if self.use_dependency_resolver:
            dependency_packages, core_candidates = self._dependency_resolver_core_candidates(
                signals=signals,
                propositions=propositions,
                core_candidates=core_candidates,
            )
        graph = document_cache.graph
        relation_geometry = document_cache.relation_geometry
        answer_bundle = None
        if retrieval_plan is not None and retrieval_plan.sub_needs:
            answer_bundle = self._assemble_answer_bundle(
                signals=signals,
                propositions=propositions,
                prompt=prompt,
                retrieval_plan=retrieval_plan,
                graph=graph,
                proposition_embeddings=proposition_embeddings,
                relation_geometry=relation_geometry,
            )
        packages = [
            self._assemble_cluster_for_core(
                signals=signals,
                propositions=propositions,
                prompt=prompt,
                prompt_embedding=prompt_embedding,
                proposition_embeddings=proposition_embeddings,
                proposition_similarities=proposition_similarities,
                language_scores=language_scores,
                graph=graph,
                relation_geometry=relation_geometry,
                core_candidate=core_candidate,
                package_index=index,
            )
            for index, core_candidate in enumerate(core_candidates)
        ]
        ranked = self._rank_query_packages(
            packages=packages,
            prompt=prompt,
            signals=signals,
            propositions=propositions,
            retrieval_plan=retrieval_plan,
        )
        source_traversals = self._audit_source_traversals(
            signals=signals,
            propositions=propositions,
            prompt=prompt,
            proposition_embeddings=proposition_embeddings,
            proposition_similarities=proposition_similarities,
            graph=graph,
            relation_geometry=relation_geometry,
            core_candidates=self._source_traversal_core_candidates_from_packages(
                packages=ranked,
                propositions=propositions,
                proposition_embeddings=proposition_embeddings,
                proposition_similarities=proposition_similarities,
            ),
        )
        source_traversal_packages = self._source_traversal_packages(
            signals=signals,
            propositions=propositions,
            prompt=prompt,
            prompt_embedding=prompt_embedding,
            proposition_embeddings=proposition_embeddings,
            source_traversals=source_traversals,
            retrieval_plan=retrieval_plan,
        )
        source_traversal_answer_bundle = self._source_traversal_answer_bundle(
            prompt=prompt,
            signals=signals,
            source_traversals=source_traversals,
            source_traversal_packages=source_traversal_packages,
        )
        return QueryAssemblyResult(
            prompt=prompt,
            packages=ranked,
            propositions=propositions,
            retrieval_plan=retrieval_plan,
            dependency_packages=dependency_packages,
            answer_bundle=answer_bundle,
            source_traversals=source_traversals,
            source_traversal_packages=source_traversal_packages,
            source_traversal_answer_bundle=source_traversal_answer_bundle,
        )

    def _dependency_resolver_core_candidates(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        core_candidates: list[_CoreCandidate],
    ) -> tuple[list[ResolvedPackage], list[_CoreCandidate]]:
        term_candidates, frame_candidates = self._dependency_resolver_candidates(
            signals=signals,
            propositions=propositions,
        )
        if not frame_candidates:
            return [], core_candidates

        proposition_index_by_id = {
            proposition.proposition_id: index
            for index, proposition in enumerate(propositions)
        }
        term_index = DocumentTermIndex.from_candidates(term_candidates)
        resolver = DependencyResolver(
            max_depth=self.dependency_resolver_depth,
            max_selected_frames=self.dependency_resolver_max_frames,
            support_verifier=self.dependency_support_verifier,
        )
        dependency_packages: list[ResolvedPackage] = []
        updated_candidates: list[_CoreCandidate] = []
        for core_candidate in core_candidates:
            if core_candidate.proposition_index is None or core_candidate.proposition_id is None:
                updated_candidates.append(core_candidate)
                continue
            core_proposition = propositions[core_candidate.proposition_index]
            package = resolver.resolve_query_propositions(
                core=core_proposition,
                propositions=propositions,
                term_index=term_index,
                frame_candidates=frame_candidates,
            )
            dependency_packages.append(package)
            dependency_anchor_indices = [
                proposition_index_by_id[frame.source.proposition_id]
                for frame in package.selected_frames
                if frame.source.proposition_id in proposition_index_by_id
            ]
            anchor_indices = tuple(
                dict.fromkeys(
                    [
                        *core_candidate.anchor_prop_indices,
                        *dependency_anchor_indices,
                    ]
                )
            )
            updated_candidates.append(replace(core_candidate, anchor_prop_indices=anchor_indices))
        return dependency_packages, updated_candidates

    def _dependency_resolver_candidates(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
    ) -> tuple[list[TermCandidate], list[FrameCandidate]]:
        term_candidates: list[TermCandidate] = []
        frame_candidates: list[FrameCandidate] = []
        signal_by_element_id = {signal.element_id: signal for signal in signals}
        term_seeds_by_proposition: dict[str, list[_DependencyTermSeed]] = {}

        for proposition in propositions:
            for role_index, role in enumerate(proposition.roles):
                slots: dict[str, SlotCandidate] = {}
                for slot_name, slot_text in (("target", role.target), ("value", role.value)):
                    text = str(slot_text or "").strip()
                    if not text:
                        continue
                    term_candidates.append(
                        TermCandidate(
                            element_id=proposition.element_id,
                            text=text,
                            char_start=0,
                            char_end=len(text),
                            source_signal=f"proposition_role.{slot_name}",
                        )
                    )
                    slots[slot_name] = SlotCandidate(
                        name=slot_name,
                        text=text,
                        char_start=0,
                        char_end=len(text),
                        grounding_state="grounded" if slot_name == "target" else "unsupported",
                    )
                if not slots:
                    continue
                frame_candidates.append(
                    FrameCandidate(
                        frame_id=f"frame:{proposition.proposition_id}:role:{role_index:02d}",
                        element_id=proposition.element_id,
                        proposition_id=proposition.proposition_id,
                        predicate=role.role.strip().lower() or "role",
                        slots=slots,
                        char_start=0,
                        char_end=len(proposition.text),
                        text=proposition.text,
                        extraction_status="role_hypothesis",
                    )
                )

            signal = signal_by_element_id.get(proposition.element_id)
            if signal is None:
                continue
            seeds = self._dependency_term_seeds(signal=signal, proposition=proposition)
            if seeds:
                term_seeds_by_proposition[proposition.proposition_id] = seeds

        document_frequencies: Counter[str] = Counter()
        for seeds in term_seeds_by_proposition.values():
            document_frequencies.update({normalize_term_text(seed.text) for seed in seeds if normalize_term_text(seed.text)})

        seen_terms: set[tuple[str, str, int, int, str]] = set()
        for proposition in propositions:
            seeds = term_seeds_by_proposition.get(proposition.proposition_id, [])
            if not seeds:
                continue
            selected_seeds = self._select_dependency_term_seeds(
                seeds=seeds,
                document_frequencies=document_frequencies,
            )
            for seed in selected_seeds:
                term_key = (
                    proposition.element_id,
                    normalize_term_text(seed.text),
                    seed.char_start,
                    seed.char_end,
                    seed.source_signal,
                )
                if term_key in seen_terms:
                    continue
                seen_terms.add(term_key)
                term_candidates.append(
                    TermCandidate(
                        element_id=proposition.element_id,
                        text=seed.text,
                        char_start=seed.char_start,
                        char_end=seed.char_end,
                        source_signal=seed.source_signal,
                        head=self._dependency_term_head(seed.text),
                        modifiers=self._dependency_term_modifiers(seed.text),
                    )
                )
            frame_candidates.extend(
                self._document_native_frame_candidates(
                    proposition=proposition,
                    seeds=selected_seeds,
                    document_frequencies=document_frequencies,
                )
            )
        return term_candidates, frame_candidates

    def _dependency_term_seeds(
        self,
        *,
        signal: ElementSignalRecord,
        proposition: QueryEvidenceProposition,
    ) -> list[_DependencyTermSeed]:
        seeds: list[_DependencyTermSeed] = []
        seen: set[str] = set()

        def add(text: str, *, source_signal: str, priority: float) -> None:
            term_text = str(text or "").strip()
            normalized = normalize_term_text(term_text)
            if not normalized or normalized in seen:
                return
            span = self._dependency_term_span(proposition.text, term_text)
            if span is None:
                span = self._dependency_term_span(signal.text, term_text)
            if span is None:
                return
            char_start, char_end, source_text = span
            seen.add(normalized)
            seeds.append(
                _DependencyTermSeed(
                    text=source_text,
                    char_start=char_start,
                    char_end=char_end,
                    source_signal=source_signal,
                    priority=priority,
                )
            )

        for symbol in signal.formula_symbols:
            add(symbol, source_signal="signal.formula_symbol", priority=3.0)
        if signal.is_heading:
            add(signal.text, source_signal="signal.heading_text", priority=2.5)
        for phrase in self._dependency_phrase_seeds(signal=signal, proposition=proposition):
            add(phrase, source_signal="signal.adjacent_content_phrase", priority=2.2)
        for term in signal.unique_content_terms:
            add(term, source_signal="signal.unique_content_term", priority=1.0)
        return sorted(seeds, key=lambda seed: (seed.char_start, seed.char_end))

    def _dependency_phrase_seeds(
        self,
        *,
        signal: ElementSignalRecord,
        proposition: QueryEvidenceProposition,
    ) -> list[str]:
        allowed = {normalize_term_text(term) for term in signal.unique_content_terms}
        allowed.update(normalize_term_text(symbol) for symbol in signal.formula_symbols)
        allowed.discard("")
        if not allowed:
            return []

        matches = list(TOKEN_RE.finditer(proposition.text))
        phrases: list[str] = []
        run: list[re.Match[str]] = []

        def flush() -> None:
            if len(run) < 2:
                return
            for width in range(min(3, len(run)), 1, -1):
                for start in range(0, len(run) - width + 1):
                    first = run[start]
                    last = run[start + width - 1]
                    phrases.append(proposition.text[first.start() : last.end()])

        previous_end = -1
        for match in matches:
            normalized = normalize_term_text(match.group(0))
            gap_text = proposition.text[previous_end : match.start()] if previous_end >= 0 else ""
            adjacent = previous_end < 0 or gap_text.strip() == ""
            if normalized in allowed and adjacent:
                run.append(match)
            else:
                flush()
                run = [match] if normalized in allowed else []
            previous_end = match.end()
        flush()
        return list(dict.fromkeys(phrases))

    def _dependency_term_span(self, text: str, term: str) -> tuple[int, int, str] | None:
        source = str(text or "")
        needle = str(term or "").strip()
        if not source or not needle:
            return None
        normalized_needle = normalize_term_text(needle)
        if " " not in normalized_needle:
            for match in TOKEN_RE.finditer(source):
                if normalize_term_text(match.group(0)) == normalized_needle:
                    return match.start(), match.end(), match.group(0)
            return None
        index = source.lower().find(needle.lower())
        if index < 0:
            return None
        return index, index + len(needle), source[index : index + len(needle)]

    def _select_dependency_term_seeds(
        self,
        *,
        seeds: list[_DependencyTermSeed],
        document_frequencies: Counter[str],
    ) -> list[_DependencyTermSeed]:
        deduped: dict[str, _DependencyTermSeed] = {}
        for seed in seeds:
            normalized = normalize_term_text(seed.text)
            if not normalized:
                continue
            existing = deduped.get(normalized)
            if existing is None or seed.priority > existing.priority:
                deduped[normalized] = seed
        ranked = sorted(
            deduped.values(),
            key=lambda seed: self._dependency_term_score(seed, document_frequencies=document_frequencies),
            reverse=True,
        )
        return sorted(ranked[:6], key=lambda seed: (seed.char_start, seed.char_end))

    def _document_native_frame_candidates(
        self,
        *,
        proposition: QueryEvidenceProposition,
        seeds: list[_DependencyTermSeed],
        document_frequencies: Counter[str],
    ) -> list[FrameCandidate]:
        if len(seeds) < 2:
            return []
        target_candidates = [
            seed
            for seed in sorted(seeds, key=lambda item: (item.char_start, -item.priority))
            if seed.priority >= 2.0
        ]
        target_seed = target_candidates[0] if target_candidates else sorted(seeds, key=lambda item: item.char_start)[0]
        target_normalized = normalize_term_text(target_seed.text)
        related = [
            seed
            for seed in sorted(
                seeds,
                key=lambda item: self._dependency_term_score(item, document_frequencies=document_frequencies),
                reverse=True,
            )
            if normalize_term_text(seed.text)
            and not self._dependency_terms_nested(target_normalized, normalize_term_text(seed.text))
        ][:2]
        if not related:
            return []
        slots: dict[str, SlotCandidate] = {
            "target": SlotCandidate(
                name="target",
                text=target_seed.text,
                char_start=target_seed.char_start,
                char_end=target_seed.char_end,
                grounding_state="grounded",
            )
        }
        for related_index, related_seed in enumerate(related, start=1):
            slots[f"related_{related_index}"] = SlotCandidate(
                name=f"related_{related_index}",
                text=related_seed.text,
                char_start=related_seed.char_start,
                char_end=related_seed.char_end,
                grounding_state="unsupported",
            )
        return [
            FrameCandidate(
                frame_id=f"frame:{proposition.proposition_id}:document:00",
                element_id=proposition.element_id,
                proposition_id=proposition.proposition_id,
                predicate="document_terms",
                slots=slots,
                char_start=0,
                char_end=len(proposition.text),
                text=proposition.text,
                extraction_status="document_signal",
            )
        ]

    def _dependency_term_score(self, seed: _DependencyTermSeed, *, document_frequencies: Counter[str]) -> float:
        normalized = normalize_term_text(seed.text)
        if not normalized:
            return 0.0
        word_count = len(normalized.split())
        document_frequency = document_frequencies.get(normalized, 0)
        if document_frequency <= 1:
            frequency_score = 0.25
        elif document_frequency <= 8:
            frequency_score = 1.2
        elif document_frequency <= 20:
            frequency_score = 0.65
        else:
            frequency_score = 0.0
        return seed.priority + min(1.5, max(0, word_count - 1) * 0.75) + frequency_score

    def _dependency_terms_nested(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left == right:
            return True
        left_words = left.split()
        right_words = right.split()
        if len(left_words) <= len(right_words):
            return any(right_words[index : index + len(left_words)] == left_words for index in range(len(right_words) - len(left_words) + 1))
        return any(left_words[index : index + len(right_words)] == right_words for index in range(len(left_words) - len(right_words) + 1))

    def _dependency_term_head(self, text: str) -> str:
        parts = normalize_term_text(text).split()
        return parts[-1] if parts else ""

    def _dependency_term_modifiers(self, text: str) -> tuple[str, ...]:
        parts = normalize_term_text(text).split()
        return tuple(parts[:-1])

    def _document_cache_key(
        self,
        *,
        namespace: str,
        signals: list[ElementSignalRecord] | None = None,
        propositions: list["QueryEvidenceProposition"],
        settings: tuple[object, ...] = (),
    ) -> str:
        hasher = hashlib.sha256()
        hasher.update(namespace.encode("utf-8", "ignore"))
        hasher.update(b"\0")
        for setting in settings:
            hasher.update(repr(setting).encode("utf-8", "ignore"))
            hasher.update(b"\0")
        if signals is not None:
            for signal in signals:
                for value in (
                    signal.element_id,
                    signal.element_type,
                    signal.text,
                    signal.page_number,
                    signal.is_heading,
                    signal.token_count,
                    tuple(str(marker) for marker in signal.markers),
                ):
                    hasher.update(str(value).encode("utf-8", "ignore"))
                    hasher.update(b"\0")
                hasher.update(b"\0")
        for proposition in propositions:
            for value in (proposition.element_id, proposition.element_index, proposition.text):
                hasher.update(str(value).encode("utf-8", "ignore"))
                hasher.update(b"\0")
            hasher.update(b"\0")
        return hasher.hexdigest()

    def _document_assembly_cache_for(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list["QueryEvidenceProposition"],
    ) -> _DocumentAssemblyCache:
        key = self._document_cache_key(
            namespace="document-assembly",
            signals=signals,
            propositions=propositions,
            settings=(
                self._effective_k_values(len(propositions)),
                self.min_neighbor_stability,
                self.min_edge_similarity,
                self.use_relation_geometry,
                self.relation_geometry_weight,
                self.relation_family_similarity,
                self.min_relation_family_size,
            ),
        )
        cached = self._document_assembly_cache.get(key)
        if cached is not None:
            return cached

        proposition_embeddings = self._embed([proposition.text for proposition in propositions])
        graph = self._consensus_graph(
            signals=signals,
            propositions=propositions,
            proposition_embeddings=proposition_embeddings,
        )
        relation_geometry = self._document_relation_geometry(
            signals=signals,
            propositions=propositions,
            proposition_embeddings=proposition_embeddings,
            graph=graph,
        )
        cached = _DocumentAssemblyCache(
            key=key,
            proposition_embeddings=proposition_embeddings,
            graph=graph,
            relation_geometry=relation_geometry,
        )
        self._document_assembly_cache[key] = cached
        if len(self._document_assembly_cache) > 8:
            oldest_key = next(iter(self._document_assembly_cache))
            if oldest_key != key:
                self._document_assembly_cache.pop(oldest_key, None)
        return cached

    def _source_traversal_vocabulary(
        self,
        propositions: list["QueryEvidenceProposition"],
    ) -> _SourceTraversalVocabularyCache:
        hasher = hashlib.sha256()
        for proposition in propositions:
            hasher.update(proposition.element_id.encode("utf-8", "ignore"))
            hasher.update(b"\0")
            hasher.update(str(proposition.element_index).encode("ascii", "ignore"))
            hasher.update(b"\0")
            hasher.update(proposition.text.encode("utf-8", "ignore"))
            hasher.update(b"\0\0")
        key = hasher.hexdigest()
        cached = self._source_traversal_vocabulary_cache.get(key)
        if cached is not None:
            return cached

        units_by_index = tuple(
            frozenset(self._source_traversal_units(proposition.text))
            for proposition in propositions
        )
        claim_units_by_index = tuple(
            frozenset(self._source_traversal_claim_units(proposition.text))
            for proposition in propositions
        )
        unit_counts: Counter[str] = Counter()
        claim_unit_counts: Counter[str] = Counter()
        for units in units_by_index:
            unit_counts.update(units)
        for units in claim_units_by_index:
            claim_unit_counts.update(units)

        vocabulary = _SourceTraversalVocabularyCache(
            key=key,
            unit_counts=unit_counts,
            claim_unit_counts=claim_unit_counts,
            units_by_index=units_by_index,
            claim_units_by_index=claim_units_by_index,
        )
        self._source_traversal_vocabulary_cache[key] = vocabulary
        if len(self._source_traversal_vocabulary_cache) > 8:
            oldest_key = next(iter(self._source_traversal_vocabulary_cache))
            if oldest_key != key:
                self._source_traversal_vocabulary_cache.pop(oldest_key, None)
        return vocabulary

    def _audit_source_traversals(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        prompt: str,
        proposition_embeddings: np.ndarray,
        proposition_similarities: np.ndarray,
        graph: dict[int, dict[int, "_ConsensusEdge"]],
        relation_geometry: "_DocumentRelationGeometry | None",
        core_candidates: list["_CoreCandidate"],
    ) -> list[SourceTraversalTrace]:
        if not self.use_source_traversal_audit or not propositions or self.source_traversal_anchor_limit <= 0:
            return []

        traces: list[SourceTraversalTrace] = []
        role_cache: dict[int, set[str]] = {}
        prompt_units = self._source_traversal_units(prompt)
        prompt_claim_units = self._source_traversal_claim_units(prompt)
        prompt_claim_tokens = self._source_traversal_claim_tokens(prompt_claim_units)
        vocabulary_cache = self._source_traversal_vocabulary(propositions)

        def roles_for(index: int) -> set[str]:
            cached = role_cache.get(index)
            if cached is not None:
                return cached
            proposition = propositions[index]
            roles = self._element_role_families(
                signal=signals[proposition.element_index],
                propositions=[proposition],
            )
            role_cache[index] = roles
            return roles

        def units_for(index: int) -> set[str]:
            return set(vocabulary_cache.units_by_index[index])

        def claim_units_for(index: int) -> set[str]:
            return set(vocabulary_cache.claim_units_by_index[index])

        document_unit_counts = vocabulary_cache.unit_counts
        document_claim_unit_counts = vocabulary_cache.claim_unit_counts

        anchors: list[int] = []
        seen_anchor_elements: set[str] = set()
        for candidate in core_candidates:
            index = candidate.proposition_index
            if index < 0 or index >= len(propositions):
                continue
            element_id = propositions[index].element_id
            if element_id in seen_anchor_elements:
                continue
            anchors.append(index)
            seen_anchor_elements.add(element_id)
            if len(anchors) >= self.source_traversal_anchor_limit:
                break

        for anchor_index in anchors:
            centers: list[dict[str, object]] = [
                {
                    "id": "center-0",
                    "anchor_index": anchor_index,
                    "accepted": [anchor_index],
                    "accepted_set": {anchor_index},
                    "frontier": [anchor_index],
                    "bridge_frontier": [],
                    "topic_terms": [],
                }
            ]
            accepted = [anchor_index]
            accepted_set = {anchor_index}
            traversed_set = {anchor_index}
            candidate_traces: list[SourceTraversalCandidateTrace] = []
            dead_end_reason = ""

            for round_number in range(1, self.source_traversal_rounds + 1):
                accepted_element_ids = {propositions[index].element_id for index in accepted}

                def candidate_row(center: dict[str, object], candidate_index: int, tags: set[str]) -> dict[str, object]:
                    center_id = str(center["id"])
                    center_accepted = list(center["accepted"])  # type: ignore[arg-type]
                    center_anchor_index = int(center["anchor_index"])
                    accepted_embeddings = proposition_embeddings[center_accepted]
                    state_embedding = _normalize(np.mean(accepted_embeddings, axis=0, keepdims=True))[0]
                    center_roles: set[str] = set().union(*(roles_for(index) for index in center_accepted))
                    center_units: set[str] = set().union(*(units_for(index) for index in center_accepted))
                    center_claim_units: set[str] = set().union(*(claim_units_for(index) for index in center_accepted))
                    center_topic_terms = set(center.get("topic_terms") or [])
                    path_signature = self._source_traversal_path_signature(
                        accepted_indices=center_accepted,
                        anchor_index=center_anchor_index,
                        prompt_claim_units=prompt_claim_units,
                        claim_units_by_index={index: claim_units_for(index) for index in center_accepted},
                        document_claim_unit_counts=document_claim_unit_counts,
                        document_unit_counts=document_unit_counts,
                        document_size=len(propositions),
                    )
                    path_signature_tokens = self._source_traversal_claim_tokens(path_signature)
                    candidate_embedding = proposition_embeddings[candidate_index]
                    proposition = propositions[candidate_index]
                    redundancy = float(np.max(proposition_embeddings[center_accepted] @ candidate_embedding))
                    candidate_roles = roles_for(candidate_index)
                    new_roles = candidate_roles - center_roles
                    role_contribution = 0.0
                    if candidate_roles:
                        role_contribution = len(new_roles) / max(1, len(candidate_roles))
                    geometry_score = 0.0
                    if relation_geometry is not None:
                        geometry_score = max(
                            relation_geometry.score(source_index, candidate_index)
                            for source_index in traversed_set
                            if source_index != candidate_index
                        )
                    candidate_units = units_for(candidate_index)
                    contribution = self._source_traversal_contribution(
                        signal=signals[proposition.element_index],
                        proposition=proposition,
                        relation_tags=set(tags),
                        prompt_units=prompt_units,
                        prompt_wants_support=self._prompt_wants_support(prompt),
                        accepted_units=center_units,
                        candidate_units=candidate_units,
                        document_unit_counts=document_unit_counts,
                        document_size=len(propositions),
                        accepted_roles=center_roles,
                        candidate_roles=candidate_roles,
                    )
                    candidate_support_like = (
                        signals[proposition.element_index].element_type in SUPPORT_ELEMENT_TYPES
                        or proposition.text.lstrip().lower().startswith(("figure", "table", "chart", "diagram"))
                    )
                    candidate_claim_units = claim_units_for(candidate_index)
                    neededness = self._source_traversal_neededness(
                        candidate_claim_units=candidate_claim_units,
                        accepted_claim_units=center_claim_units,
                        path_signature=path_signature,
                        path_signature_tokens=path_signature_tokens,
                        prompt_claim_units=prompt_claim_units,
                        prompt_claim_tokens=prompt_claim_tokens,
                        relation_tags=set(tags),
                        candidate_support_like=candidate_support_like,
                        candidate_signal=signals[proposition.element_index],
                        accepted_signals=[signals[propositions[index].element_index] for index in center_accepted],
                        candidate_roles=candidate_roles,
                        accepted_roles=center_roles,
                        contribution_kind=str(contribution["kind"]),
                        document_unit_counts=document_unit_counts,
                        document_claim_unit_counts=document_claim_unit_counts,
                        document_size=len(propositions),
                    )
                    topic_guard = self._source_traversal_center_topic_guard(
                        candidate_claim_units=candidate_claim_units,
                        prompt_claim_tokens=prompt_claim_tokens,
                        center_topic_terms=center_topic_terms,
                        relation_tags=set(tags),
                    )
                    if not topic_guard["ok"]:
                        neededness = {
                            **neededness,
                            "ok": False,
                            "reason": topic_guard["reason"],
                        }
                    new_center = self._source_traversal_new_center_candidate(
                        candidate_claim_units=candidate_claim_units,
                        path_signature_tokens=path_signature_tokens,
                        prompt_claim_tokens=prompt_claim_tokens,
                        relation_tags=set(tags),
                        source_ok=bool(contribution["source_ok"]),
                        candidate_signal=signals[proposition.element_index],
                        center_anchor_signal=signals[propositions[center_anchor_index].element_index],
                        candidate_roles=candidate_roles,
                        accepted_roles=center_roles,
                        foreign_tokens=set(neededness["foreign_tokens"]),
                        existing_center_count=len(centers),
                        document_unit_counts=document_unit_counts,
                        document_size=len(propositions),
                    )
                    return {
                        "index": candidate_index,
                        "center_id": center_id,
                        "center_decision": "existing_center",
                        "tags": sorted(tags),
                        "prompt": float(proposition_similarities[candidate_index]),
                        "state": float(np.dot(candidate_embedding, state_embedding)),
                        "novelty": _clamp01(1.0 - max(0.0, redundancy)),
                        "redundancy": redundancy,
                        "relation_raw": float(len(tags)) + geometry_score,
                        "geometry": geometry_score,
                        "role": float(role_contribution),
                        "source_ok": contribution["source_ok"],
                        "contribution_kind": contribution["kind"],
                        "contribution": contribution["contribution"],
                        "contribution_units": contribution["units"],
                        "candidate_units": candidate_units,
                        "candidate_claim_units": candidate_claim_units,
                        "candidate_support_like": candidate_support_like,
                        "neededness_ok": neededness["ok"],
                        "neededness_reason": neededness["reason"],
                        "matched_claim_units": neededness["matched_units"],
                        "new_needed_units": neededness["new_needed_units"],
                        "foreign_claim_tokens": neededness["foreign_tokens"],
                        "frame_continuation": neededness["frame_continuation"],
                        "new_center_ok": new_center["ok"],
                        "new_center_reason": new_center["reason"],
                        "new_center_terms": new_center["terms"],
                    }

                def bridge_leads_to_evidence(
                    center: dict[str, object],
                    candidate_index: int,
                    depth: int = 2,
                    seen: set[int] | None = None,
                ) -> bool:
                    if depth <= 0:
                        return False
                    if seen is None:
                        seen = set()
                    if candidate_index in seen:
                        return False
                    seen.add(candidate_index)
                    bridge_map = self._source_traversal_candidate_map(
                        signals=signals,
                        propositions=propositions,
                        graph={},
                        relation_geometry=None,
                        frontier=[candidate_index],
                        accepted_set=traversed_set | seen,
                    )
                    for bridge_target_index, bridge_tags in bridge_map.items():
                        if propositions[bridge_target_index].element_id in accepted_element_ids:
                            continue
                        bridge_target_row = candidate_row(center, bridge_target_index, bridge_tags)
                        if bool(bridge_target_row["source_ok"]) and str(bridge_target_row["contribution_kind"] or ""):
                            return True
                        if self._source_traversal_bridge_allowed(
                            row=bridge_target_row,
                            bridge_leads_to_evidence=False,
                        ) and bridge_leads_to_evidence(center, bridge_target_index, depth=depth - 1, seen=seen):
                            return True
                    return False

                raw_rows: list[dict[str, object]] = []
                for center in centers:
                    center_relation_map: dict[int, set[str]] = defaultdict(set)
                    evidence_frontier = [
                        index for index in list(center["frontier"]) if index in center["accepted_set"]  # type: ignore[arg-type]
                    ]
                    bridge_frontier = list(center["bridge_frontier"])  # type: ignore[arg-type]
                    if evidence_frontier:
                        for candidate_index, tags in self._source_traversal_candidate_map(
                            signals=signals,
                            propositions=propositions,
                            graph=graph,
                            relation_geometry=relation_geometry,
                            frontier=evidence_frontier,
                            accepted_set=traversed_set,
                        ).items():
                            center_relation_map[candidate_index].update(tags)
                    if bridge_frontier:
                        for candidate_index, tags in self._source_traversal_candidate_map(
                            signals=signals,
                            propositions=propositions,
                            graph={},
                            relation_geometry=None,
                            frontier=bridge_frontier,
                            accepted_set=traversed_set,
                        ).items():
                            center_relation_map[candidate_index].update(tags)
                    for candidate_index, tags in center_relation_map.items():
                        if propositions[candidate_index].element_id in accepted_element_ids:
                            continue
                        raw_rows.append(candidate_row(center, candidate_index, tags))

                if not raw_rows:
                    dead_end_reason = f"round {round_number}: no source-connected neighbors outside accepted centres"
                    break

                max_relation_raw = max(float(row["relation_raw"]) for row in raw_rows) or 1.0
                for row in raw_rows:
                    row["relation"] = _clamp01(float(row["relation_raw"]) / max_relation_raw)

                medians = {
                    name: float(np.median([float(row[name]) for row in raw_rows]))
                    for name in ("prompt", "state", "novelty", "redundancy", "relation", "role")
                }

                scored_rows: list[tuple[int, float, dict[str, object], str, str]] = []
                for row in raw_rows:
                    axes = 0
                    if float(row["prompt"]) >= medians["prompt"]:
                        axes += 1
                    if float(row["state"]) >= medians["state"]:
                        axes += 1
                    if float(row["novelty"]) >= medians["novelty"]:
                        axes += 1
                    if float(row["relation"]) >= medians["relation"]:
                        axes += 1
                    if float(row["role"]) > 0.0 and float(row["role"]) >= medians["role"]:
                        axes += 1
                    redundant = float(row["redundancy"]) > medians["redundancy"] and float(row["novelty"]) < medians["novelty"]
                    bridge_ahead = False
                    if not str(row.get("contribution_kind") or "") and self._source_traversal_can_probe_bridge(row=row):
                        center = next((item for item in centers if str(item["id"]) == str(row["center_id"])), centers[0])
                        bridge_ahead = bridge_leads_to_evidence(center, int(row["index"]))
                    action, reason = self._source_traversal_path_delta(
                        axes=axes,
                        redundant=redundant,
                        row=row,
                        medians=medians,
                        bridge_leads_to_evidence=bridge_ahead,
                    )
                    sort_score = (
                        axes * 10.0
                        + float(row["prompt"])
                        + float(row["state"])
                        + float(row["relation"])
                        + float(row["role"])
                        + float(row["novelty"])
                        - max(0.0, float(row["redundancy"])) * 0.25
                    )
                    scored_rows.append((axes, sort_score, row, action, reason))

                scored_rows.sort(key=lambda item: (item[3] == "accepted", item[0], item[1]), reverse=True)
                round_accepts: list[tuple[int, str, str, list[str]]] = []
                round_accept_element_ids: set[str] = set()
                round_accept_contribution_units: set[str] = set()
                round_rejection_reasons: dict[tuple[str, int], str] = {}
                round_new_center_terms: set[str] = set()
                round_bridges: list[tuple[int, str]] = []
                round_bridge_element_ids: set[str] = set()
                for _axes, _sort_score, row, proposed_action, _reason in scored_rows:
                    if proposed_action != "accepted":
                        continue
                    candidate_index = int(row["index"])
                    proposition = propositions[candidate_index]
                    if proposition.element_id in round_accept_element_ids:
                        continue
                    contribution_units = set(row.get("contribution_units") or [])
                    new_center_terms = set(row.get("new_center_terms") or [])
                    if bool(row.get("new_center_ok")) and new_center_terms and new_center_terms <= round_new_center_terms:
                        round_rejection_reasons[(str(row["center_id"]), candidate_index)] = (
                            "rejected: another new centre in this path step already covered the same prompt aspect"
                        )
                        continue
                    if contribution_units and contribution_units <= round_accept_contribution_units:
                        round_rejection_reasons[(str(row["center_id"]), candidate_index)] = (
                            "rejected: another candidate in this path step already added the same evidence"
                        )
                        continue
                    center_decision = "new_center" if bool(row.get("new_center_ok")) else "existing_center"
                    round_accepts.append((candidate_index, str(row["center_id"]), center_decision, sorted(new_center_terms)))
                    round_accept_element_ids.add(proposition.element_id)
                    round_accept_contribution_units.update(contribution_units)
                    if center_decision == "new_center":
                        round_new_center_terms.update(new_center_terms)
                    if len(round_accepts) >= self.source_traversal_accepts_per_round:
                        break
                for _axes, _sort_score, row, proposed_action, _reason in scored_rows:
                    if proposed_action != "bridge":
                        continue
                    candidate_index = int(row["index"])
                    proposition = propositions[candidate_index]
                    if proposition.element_id in round_accept_element_ids or proposition.element_id in round_bridge_element_ids:
                        continue
                    round_bridges.append((candidate_index, str(row["center_id"])))
                    round_bridge_element_ids.add(proposition.element_id)
                    if len(round_bridges) >= self.source_traversal_accepts_per_round:
                        break
                round_accept_keys = {(center_id, index) for index, center_id, _decision, _terms in round_accepts}
                round_bridge_keys = {(center_id, index) for index, center_id in round_bridges}

                for _axes, _sort_score, row, action, reason in scored_rows[: self.source_traversal_candidate_limit]:
                    candidate_index = int(row["index"])
                    proposition = propositions[candidate_index]
                    recorded_action = action
                    recorded_reason = reason
                    center_id = str(row["center_id"])
                    center_decision = "new_center" if bool(row.get("new_center_ok")) and action == "accepted" else str(row.get("center_decision") or "existing_center")
                    if (center_id, candidate_index) in round_rejection_reasons:
                        recorded_action = "rejected"
                        recorded_reason = round_rejection_reasons[(center_id, candidate_index)]
                    elif action == "accepted" and (center_id, candidate_index) not in round_accept_keys:
                        recorded_action = "deferred"
                        recorded_reason = "deferred: locally useful, but stronger new elements filled this round"
                    if action == "bridge" and (center_id, candidate_index) not in round_bridge_keys:
                        recorded_action = "deferred"
                        recorded_reason = "deferred: bridge-only route, but stronger bridge/evidence routes filled this round"
                    candidate_traces.append(
                        SourceTraversalCandidateTrace(
                            round_number=round_number,
                            proposition_id=proposition.proposition_id,
                            element_id=proposition.element_id,
                            center_id=center_id,
                            center_decision=center_decision,
                            relation_tags=list(row["tags"]),
                            prompt_similarity=round(float(row["prompt"]), 4),
                            state_similarity=round(float(row["state"]), 4),
                            novelty_score=round(float(row["novelty"]), 4),
                            redundancy_score=round(float(row["redundancy"]), 4),
                            relation_score=round(float(row["relation"]), 4),
                            role_contribution_score=round(float(row["role"]), 4),
                            token_count=signals[proposition.element_index].token_count,
                            action=recorded_action,
                            reason=recorded_reason,
                            text_preview=_preview(proposition.text, limit=220),
                            answer_contribution=str(row["contribution"]),
                            matched_claim_units=list(row.get("matched_claim_units") or []),
                            new_needed_units=list(row.get("new_needed_units") or []),
                            foreign_claim_tokens=list(row.get("foreign_claim_tokens") or []),
                            frame_continuation=str(row.get("frame_continuation") or ""),
                        )
                    )

                if not round_accepts:
                    if not round_bridges:
                        dead_end_reason = f"round {round_number}: source-connected candidates did not improve or bridge the evidence path"
                        break

                for accepted_index, center_id, center_decision, new_center_terms in round_accepts:
                    if accepted_index in accepted_set:
                        continue
                    accepted.append(accepted_index)
                    accepted_set.add(accepted_index)
                    traversed_set.add(accepted_index)
                    if center_decision == "new_center":
                        centers.append(
                            {
                                "id": f"center-{len(centers)}",
                                "anchor_index": accepted_index,
                                "accepted": [accepted_index],
                                "accepted_set": {accepted_index},
                                "frontier": [accepted_index],
                                "bridge_frontier": [],
                                "topic_terms": list(new_center_terms),
                            }
                        )
                        continue
                    center = next((item for item in centers if str(item["id"]) == center_id), centers[0])
                    center["accepted"].append(accepted_index)  # type: ignore[union-attr]
                    center["accepted_set"].add(accepted_index)  # type: ignore[union-attr]
                    center["frontier"] = [accepted_index]
                    center["bridge_frontier"] = []
                for bridge_index, center_id in round_bridges:
                    traversed_set.add(bridge_index)
                    center = next((item for item in centers if str(item["id"]) == center_id), centers[0])
                    center["bridge_frontier"] = [bridge_index]
                    if not center.get("frontier"):
                        center["frontier"] = []

            anchor = propositions[anchor_index]
            traces.append(
                SourceTraversalTrace(
                    anchor_proposition_id=anchor.proposition_id,
                    anchor_element_id=anchor.element_id,
                    anchor_text_preview=_preview(anchor.text, limit=220),
                    accepted_proposition_ids=[propositions[index].proposition_id for index in accepted],
                    accepted_element_ids=list(dict.fromkeys(propositions[index].element_id for index in accepted)),
                    centers=[
                        {
                            "center_id": str(center["id"]),
                            "anchor_element_id": propositions[int(center["anchor_index"])].element_id,
                            "topic_terms": list(center.get("topic_terms") or []),
                            "accepted_element_ids": list(
                                dict.fromkeys(propositions[index].element_id for index in list(center["accepted"]))  # type: ignore[arg-type]
                            ),
                        }
                        for center in centers
                    ],
                    candidates=candidate_traces,
                    dead_end_reason=dead_end_reason,
                )
            )
        return traces

    def _source_traversal_packages(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        prompt: str,
        prompt_embedding: np.ndarray,
        proposition_embeddings: np.ndarray,
        source_traversals: list[SourceTraversalTrace],
        retrieval_plan: QueryRetrievalPlan | None,
    ) -> list[QueryAssembledPackage]:
        if not source_traversals:
            return []
        signal_by_id = {signal.element_id: signal for signal in signals}
        proposition_text_by_element: dict[str, str] = {}
        proposition_indices_by_element: dict[str, list[int]] = defaultdict(list)
        for proposition_index, proposition in enumerate(propositions):
            proposition_text_by_element.setdefault(proposition.element_id, proposition.text)
            proposition_indices_by_element[proposition.element_id].append(proposition_index)

        packages: list[QueryAssembledPackage] = []
        seen_element_sets: set[tuple[str, ...]] = set()
        for trace_index, trace in enumerate(source_traversals):
            for center_index, center in enumerate(trace.centers):
                raw_element_ids = [str(element_id) for element_id in center.get("accepted_element_ids", [])]
                selected = [
                    signal_by_id[element_id]
                    for element_id in dict.fromkeys(raw_element_ids)
                    if element_id in signal_by_id
                ]
                if not selected:
                    continue
                selected.sort(key=lambda signal: signal.element_index)
                if len(selected) == 1 and selected[0].is_heading and selected[0].word_count <= 5:
                    continue
                element_key = tuple(signal.element_id for signal in selected)
                if element_key in seen_element_sets:
                    continue
                seen_element_sets.add(element_key)

                anchor_element_id = str(center.get("anchor_element_id") or selected[0].element_id)
                seed_core_signal = signal_by_id.get(anchor_element_id, selected[0])
                final_core_signal = seed_core_signal
                selected_prop_indices = [
                    prop_index
                    for signal in selected
                    for prop_index in proposition_indices_by_element.get(signal.element_id, [])
                    if 0 <= prop_index < len(proposition_embeddings)
                ]
                if selected_prop_indices:
                    package_embedding = _normalize(np.mean(proposition_embeddings[selected_prop_indices], axis=0, keepdims=True))[0]
                else:
                    package_embedding = prompt_embedding
                core_prop_indices = [
                    prop_index
                    for prop_index in proposition_indices_by_element.get(final_core_signal.element_id, [])
                    if 0 <= prop_index < len(proposition_embeddings)
                ]
                final_core_embedding = (
                    proposition_embeddings[core_prop_indices[0]]
                    if core_prop_indices
                    else package_embedding
                )
                role_by_id = {
                    signal.element_id: "Traversal"
                    for signal in selected
                    if signal.element_id != final_core_signal.element_id
                }
                package_text = self._package_text(
                    selected,
                    core_element_id=final_core_signal.element_id,
                    role_by_id=role_by_id,
                )
                package_prompt_similarity = float(np.dot(package_embedding, prompt_embedding))
                package_core_similarity = float(np.dot(package_embedding, final_core_embedding))
                final_core_prompt_similarity = float(np.dot(final_core_embedding, prompt_embedding))
                token_count = sum(signal.token_count for signal in selected)
                score = self._package_score(
                    package_prompt_similarity=package_prompt_similarity,
                    package_core_similarity=package_core_similarity,
                    core_prompt_similarity=final_core_prompt_similarity,
                    token_count=token_count,
                )
                score += self._answerability_bonus(
                    signals=selected,
                    core_element_id=final_core_signal.element_id,
                    proposition_text=proposition_text_by_element.get(final_core_signal.element_id, ""),
                )
                topic_terms = [str(term) for term in center.get("topic_terms", []) if str(term).strip()]
                decisions = [
                    QueryAssemblyDecision(
                        element_id=final_core_signal.element_id,
                        direction="source_traversal",
                        action="assembled",
                        query_similarity=round(package_prompt_similarity, 4),
                        core_similarity=round(package_core_similarity, 4),
                        query_delta=0.0,
                        core_delta=0.0,
                        reason="source traversal centre"
                        + (f" for prompt term(s): {', '.join(topic_terms[:4])}" if topic_terms else ""),
                    )
                ]
                packages.append(
                    QueryAssembledPackage(
                        package_id=f"query-source-traversal-package-{len(packages):05d}",
                        core_element_id=final_core_signal.element_id,
                        core_index=final_core_signal.element_index,
                        seed_core_element_id=seed_core_signal.element_id,
                        core_prompt_similarity=round(final_core_prompt_similarity, 4),
                        package_prompt_similarity=round(package_prompt_similarity, 4),
                        package_core_similarity=round(package_core_similarity, 4),
                        element_ids=[signal.element_id for signal in selected],
                        package_text=package_text,
                        token_count=token_count,
                        score=round(score, 4),
                        decisions=decisions,
                    )
                )

        return self._rank_query_packages(
            packages=packages,
            prompt=prompt,
            signals=signals,
            propositions=propositions,
            retrieval_plan=retrieval_plan,
        )

    def _source_traversal_answer_bundle(
        self,
        *,
        prompt: str,
        signals: list[ElementSignalRecord],
        source_traversals: list[SourceTraversalTrace],
        source_traversal_packages: list[QueryAssembledPackage],
    ) -> SourceTraversalAnswerBundle | None:
        if not source_traversals or not source_traversal_packages:
            return None
        signal_by_id = {signal.element_id: signal for signal in signals}
        package_rank_by_id = {
            package.package_id: rank
            for rank, package in enumerate(source_traversal_packages)
        }

        packages_by_element_key: dict[tuple[str, ...], QueryAssembledPackage] = {
            tuple(package.element_ids): package for package in source_traversal_packages
        }
        packages_by_element_set: dict[frozenset[str], QueryAssembledPackage] = {}
        for package in source_traversal_packages:
            packages_by_element_set.setdefault(frozenset(package.element_ids), package)

        parts: list[SourceTraversalAnswerBundlePart] = []
        seen_package_ids: set[str] = set()
        for trace in source_traversals:
            for center in trace.centers:
                raw_element_ids = [str(element_id) for element_id in center.get("accepted_element_ids", [])]
                evidence_element_ids = list(dict.fromkeys(element_id for element_id in raw_element_ids if element_id))
                if not evidence_element_ids:
                    continue
                package = packages_by_element_key.get(tuple(evidence_element_ids))
                if package is None:
                    package = packages_by_element_set.get(frozenset(evidence_element_ids))
                if package is None or package.package_id in seen_package_ids:
                    continue
                seen_package_ids.add(package.package_id)

                topic_terms = [
                    str(term).strip()
                    for term in center.get("topic_terms", [])
                    if str(term).strip()
                ]
                evidence_text = re.sub(r"\[[^\]]+\]\s*", " ", package.package_text)
                claim_units = sorted(self._source_traversal_claim_units(evidence_text))
                display_terms = topic_terms[:3] or claim_units[:3]
                display_label = ", ".join(display_terms) if display_terms else "source evidence"
                role = "main" if topic_terms or len(parts) == 0 else "support"
                parts.append(
                    SourceTraversalAnswerBundlePart(
                        part_id=f"source-traversal-bundle-part-{len(parts) + 1:02d}",
                        role=role,
                        display_label=display_label,
                        center_id=str(center.get("center_id") or ""),
                        trace_anchor_element_id=trace.anchor_element_id,
                        topic_terms=topic_terms,
                        claim_units=claim_units[:12],
                        evidence_element_ids=evidence_element_ids,
                        package=package,
                    )
                )

        if not parts:
            return None
        part_order_by_id = {part.part_id: order for order, part in enumerate(parts)}
        topic_parts = [part for part in parts if part.topic_terms]
        if topic_parts:
            selected_parts: list[SourceTraversalAnswerBundlePart] = []
            covered_evidence: set[str] = set()
            def meaningful_evidence_ids(part: SourceTraversalAnswerBundlePart) -> set[str]:
                evidence_ids = {
                    element_id
                    for element_id in part.evidence_element_ids
                    if not (
                        (signal := signal_by_id.get(element_id)) is not None
                        and signal.is_heading
                        and signal.word_count <= 5
                    )
                }
                return evidence_ids or set(part.evidence_element_ids)

            for part in sorted(topic_parts, key=lambda item: part_order_by_id.get(item.part_id, 10_000)):
                evidence_ids = meaningful_evidence_ids(part)
                if evidence_ids and evidence_ids <= covered_evidence:
                    continue
                selected_parts.append(part)
                covered_evidence.update(evidence_ids)
            for part in sorted(
                (part for part in parts if not part.topic_terms),
                key=lambda item: part_order_by_id.get(item.part_id, 10_000),
            ):
                evidence_ids = meaningful_evidence_ids(part)
                if evidence_ids and evidence_ids <= covered_evidence:
                    continue
                selected_parts.append(part)
                covered_evidence.update(evidence_ids)
                break
            if not selected_parts:
                selected_parts = [parts[0]]
        else:
            selected_parts = [parts[0]]

        reindexed_parts = [
            replace(
                part,
                part_id=f"source-traversal-bundle-part-{index:02d}",
                role="main" if part.topic_terms or index == 1 else part.role,
            )
            for index, part in enumerate(selected_parts, start=1)
        ]
        return SourceTraversalAnswerBundle(
            bundle_id="source-traversal-answer-bundle",
            prompt=prompt,
            parts=reindexed_parts,
        )

    def _source_traversal_core_candidates_from_packages(
        self,
        *,
        packages: list[QueryAssembledPackage],
        propositions: list[QueryEvidenceProposition],
        proposition_embeddings: np.ndarray,
        proposition_similarities: np.ndarray,
    ) -> list["_CoreCandidate"]:
        proposition_index_by_element: dict[str, int] = {}
        for proposition_index, proposition in enumerate(propositions):
            proposition_index_by_element.setdefault(proposition.element_id, proposition_index)

        candidates: list[_CoreCandidate] = []
        seen_elements: set[str] = set()
        for package in packages:
            element_id = package.core_element_id
            if element_id in seen_elements:
                continue
            proposition_index = proposition_index_by_element.get(element_id)
            if proposition_index is None:
                continue
            proposition = propositions[proposition_index]
            candidates.append(
                _CoreCandidate(
                    element_index=proposition.element_index,
                    prompt_similarity=float(proposition_similarities[proposition_index]),
                    core_embedding=proposition_embeddings[proposition_index],
                    proposition_id=proposition.proposition_id,
                    proposition_index=proposition_index,
                    proposition_text=proposition.text,
                    support_element_ids=list(proposition.support_element_ids),
                    anchor_prop_indices=(proposition_index,),
                )
            )
            seen_elements.add(element_id)
            if len(candidates) >= self.source_traversal_anchor_limit:
                break
        return candidates

    def _source_traversal_path_delta(
        self,
        *,
        axes: int,
        redundant: bool,
        row: Mapping[str, object],
        medians: Mapping[str, float],
        bridge_leads_to_evidence: bool,
    ) -> tuple[str, str]:
        relation_tags = set(row.get("tags") or [])
        contribution = str(row.get("contribution") or "")
        contribution_kind = str(row.get("contribution_kind") or "")
        source_ok = bool(row.get("source_ok"))

        if not bool(row.get("source_ok")):
            return "rejected", "rejected: relation is only a weak probe without enough source support"
        if not contribution_kind:
            if bool(row.get("neededness_ok")) and str(row.get("frame_continuation") or ""):
                return "accepted", "accepted: " + str(row.get("neededness_reason") or "source frame continuation")
            if self._source_traversal_bridge_allowed(row=row, bridge_leads_to_evidence=bridge_leads_to_evidence):
                return "bridge", "bridge: crossed source structure only; not package evidence"
            return "rejected", "rejected: connected, but adding it does not improve the evidence path"
        if bool(row.get("new_center_ok")):
            reason = str(row.get("new_center_reason") or "candidate starts a source-backed prompt centre")
            return "accepted", "accepted: " + reason
        if not bool(row.get("neededness_ok")):
            reason = str(row.get("neededness_reason") or "does not match the current path claim")
            return "rejected", "rejected: " + reason
        if str(row.get("frame_continuation") or "") == "list_frame_continuation":
            return "accepted", "accepted: " + str(row.get("neededness_reason") or "source list frame continuation")
        if redundant:
            return "rejected", "rejected: path after addition is mostly redundant with the path before it"

        structural_relation = bool(
            relation_tags
            & {
                "adjacent_previous",
                "adjacent_next",
                "heading_to_body",
                "explicit_support",
                "support_to_text",
                "same_element",
                "strong_list",
                "list_run_entry",
            }
        )
        if not structural_relation and axes < 2:
            return "rejected", "rejected: contribution is not backed by enough local path evidence"

        if source_ok:
            strengths: list[str] = []
            if float(row["prompt"]) >= medians["prompt"]:
                strengths.append("prompt relevance")
            if float(row["state"]) >= medians["state"]:
                strengths.append("coheres with accepted evidence")
            if float(row["novelty"]) >= medians["novelty"]:
                strengths.append("adds new information")
            if float(row["relation"]) >= medians["relation"]:
                strengths.append("has source relation support")
            if float(row["role"]) > 0.0 and float(row["role"]) >= medians["role"]:
                strengths.append("adds an evidence role")
            if contribution:
                return "accepted", "accepted: path delta improves evidence; " + contribution
            return "accepted", "accepted: path delta improves evidence; " + ", ".join(strengths[:3])
        return "rejected", "rejected: weak local evidence compared with this frontier"

    def _source_traversal_bridge_allowed(
        self,
        *,
        row: Mapping[str, object],
        bridge_leads_to_evidence: bool,
    ) -> bool:
        if not self._source_traversal_can_probe_bridge(row=row):
            return False
        if bridge_leads_to_evidence:
            return True
        candidate_units = set(row.get("candidate_units") or set())
        return not candidate_units and float(row.get("role", 0.0)) == 0.0

    def _source_traversal_can_probe_bridge(self, *, row: Mapping[str, object]) -> bool:
        relation_tags = set(row.get("tags") or [])
        return bool(
            relation_tags
            & {
                "adjacent_previous",
                "adjacent_next",
                "heading_to_body",
                "explicit_support",
                "support_to_text",
                "strong_list",
                "list_run_entry",
            }
        )

    def _source_traversal_new_center_candidate(
        self,
        *,
        candidate_claim_units: set[str],
        path_signature_tokens: set[str],
        prompt_claim_tokens: set[str],
        relation_tags: set[str],
        source_ok: bool,
        candidate_signal: ElementSignalRecord,
        center_anchor_signal: ElementSignalRecord,
        candidate_roles: set[str],
        accepted_roles: set[str],
        foreign_tokens: set[str],
        existing_center_count: int,
        document_unit_counts: Counter[str],
        document_size: int,
    ) -> dict[str, object]:
        comparison_split = "comparison" in candidate_roles and "comparison" in accepted_roles
        if existing_center_count >= 4 or not source_ok or not candidate_claim_units:
            return {"ok": False, "reason": "", "terms": []}
        structural_relation = bool(
            relation_tags
            & {
                "adjacent_previous",
                "adjacent_next",
                "heading_to_body",
                "explicit_support",
                "support_to_text",
                "same_element",
                "strong_list",
                "list_run_entry",
                "relation_geometry",
                "consensus_graph",
            }
        )
        if not structural_relation:
            return {"ok": False, "reason": "", "terms": []}

        candidate_tokens = self._source_traversal_claim_tokens(candidate_claim_units)
        prompt_overlap = candidate_tokens & prompt_claim_tokens
        if not prompt_overlap:
            return {"ok": False, "reason": "", "terms": []}

        distinctive_limit = max(1, int(math.sqrt(max(1, document_size))))
        distinctive_prompt_overlap = {
            token
            for token in prompt_overlap
            if document_unit_counts.get(token, 0) <= distinctive_limit or len(token) >= 6
        }
        new_prompt_overlap = distinctive_prompt_overlap - path_signature_tokens
        broad_anchor = center_anchor_signal.is_heading or center_anchor_signal.word_count <= 5
        if not new_prompt_overlap and not (broad_anchor and distinctive_prompt_overlap):
            return {"ok": False, "reason": "", "terms": []}
        broad_support_split = broad_anchor and candidate_signal.element_type in SUPPORT_ELEMENT_TYPES
        if not comparison_split and not broad_support_split:
            return {"ok": False, "reason": "", "terms": []}
        if not foreign_tokens and not comparison_split:
            return {"ok": False, "reason": "", "terms": []}

        if candidate_signal.is_heading and candidate_signal.word_count <= 5 and candidate_signal.element_type not in SUPPORT_ELEMENT_TYPES:
            return {"ok": False, "reason": "", "terms": []}

        terms = sorted(new_prompt_overlap or distinctive_prompt_overlap)
        return {
            "ok": True,
            "reason": "starts a source-backed centre for prompt term(s): " + ", ".join(terms[:4]),
            "terms": terms,
        }

    def _source_traversal_center_topic_guard(
        self,
        *,
        candidate_claim_units: set[str],
        prompt_claim_tokens: set[str],
        center_topic_terms: set[str],
        relation_tags: set[str],
    ) -> dict[str, object]:
        if not center_topic_terms:
            return {"ok": True, "reason": ""}
        if relation_tags & {"same_element", "explicit_support", "support_to_text"}:
            return {"ok": True, "reason": ""}
        candidate_prompt_terms = self._source_traversal_claim_tokens(candidate_claim_units) & prompt_claim_tokens
        candidate_prompt_terms = {term for term in candidate_prompt_terms if not self._source_traversal_claim_token_is_generic(term)}
        if not candidate_prompt_terms:
            return {"ok": True, "reason": ""}
        if candidate_prompt_terms & center_topic_terms:
            return {"ok": True, "reason": ""}
        return {
            "ok": False,
            "reason": "candidate belongs to a different prompt centre: " + ", ".join(sorted(candidate_prompt_terms)[:4]),
        }

    def _source_traversal_neededness(
        self,
        *,
        candidate_claim_units: set[str],
        accepted_claim_units: set[str],
        path_signature: set[str],
        path_signature_tokens: set[str],
        prompt_claim_units: set[str],
        prompt_claim_tokens: set[str],
        relation_tags: set[str],
        candidate_support_like: bool,
        candidate_signal: ElementSignalRecord,
        accepted_signals: list[ElementSignalRecord],
        candidate_roles: set[str],
        accepted_roles: set[str],
        contribution_kind: str,
        document_unit_counts: Counter[str],
        document_claim_unit_counts: Counter[str],
        document_size: int,
    ) -> dict[str, object]:
        if not candidate_claim_units:
            return {
                "ok": True,
                "reason": "candidate has no distinctive claim units",
                "matched_units": [],
                "new_needed_units": [],
                "foreign_tokens": [],
                "frame_continuation": "",
            }
        if not path_signature:
            return {
                "ok": True,
                "reason": "no stable path claim yet",
                "matched_units": [],
                "new_needed_units": sorted(candidate_claim_units)[:6],
                "foreign_tokens": [],
                "frame_continuation": "",
            }
        if relation_tags & {"same_element", "explicit_support", "support_to_text"}:
            return {
                "ok": True,
                "reason": "explicitly attached to the same source object",
                "matched_units": sorted(candidate_claim_units & (path_signature | prompt_claim_units))[:6],
                "new_needed_units": sorted(candidate_claim_units - accepted_claim_units)[:6],
                "foreign_tokens": [],
                "frame_continuation": "",
            }

        distinctive_limit = max(1, int(math.sqrt(max(1, document_size))))
        scope_units = path_signature | prompt_claim_units | accepted_claim_units
        scope_tokens = self._source_traversal_claim_tokens(scope_units)
        candidate_tokens = self._source_traversal_claim_tokens(candidate_claim_units)
        exact_overlap = candidate_claim_units & scope_units
        strong_exact = {
            unit
            for unit in exact_overlap
            if self._source_traversal_claim_unit_is_strong(
                unit,
                document_claim_unit_counts=document_claim_unit_counts,
                distinctive_limit=distinctive_limit,
            )
            and (
                not candidate_support_like
                or len(self._source_traversal_claim_unit_tokens(unit)) >= 2
            )
        }

        connected_units: set[str] = set()
        connected_extension_tokens: set[str] = set()
        for unit in candidate_claim_units:
            tokens = self._source_traversal_claim_unit_tokens(unit)
            overlap = tokens & scope_tokens
            if overlap:
                connected_units.add(unit)
                if unit in exact_overlap or len(overlap) >= 2:
                    connected_extension_tokens.update(tokens)

        token_overlap = candidate_tokens & scope_tokens
        strong_token_overlap = {
            token
            for token in token_overlap
            if token in prompt_claim_tokens
            or document_unit_counts.get(token, 0) <= distinctive_limit
            or len(token) >= 6
        }
        foreign = self._source_traversal_foreign_claim_tokens(
            candidate_tokens=candidate_tokens - connected_extension_tokens,
            path_signature_tokens=path_signature_tokens | self._source_traversal_claim_tokens(accepted_claim_units),
            prompt_claim_tokens=prompt_claim_tokens,
            document_unit_counts=document_unit_counts,
            distinctive_limit=distinctive_limit,
        )
        frame_continuation = self._source_traversal_frame_continuation(
            candidate_signal=candidate_signal,
            accepted_signals=accepted_signals,
            candidate_claim_units=candidate_claim_units,
            scope_units=scope_units,
            foreign_tokens=foreign,
            relation_tags=relation_tags,
            candidate_roles=candidate_roles,
            accepted_roles=accepted_roles,
        )
        if foreign and frame_continuation["ok"] and frame_continuation["type"] == "list_frame_continuation":
            return {
                "ok": True,
                "reason": str(frame_continuation["reason"]),
                "matched_units": sorted(candidate_claim_units & (path_signature | prompt_claim_units))[:6],
                "new_needed_units": sorted(candidate_claim_units - accepted_claim_units)[:6],
                "foreign_tokens": sorted(foreign)[:6],
                "frame_continuation": str(frame_continuation["type"]),
            }
        new_needed_units = sorted((connected_units | strong_exact) - accepted_claim_units)
        matched_units = sorted(strong_exact | (candidate_claim_units & path_signature) | (candidate_claim_units & prompt_claim_units))
        structural_relation = bool(
            relation_tags
            & {
                "adjacent_previous",
                "adjacent_next",
                "heading_to_body",
                "strong_list",
                "list_run_entry",
            }
        )

        strong_exact_phrase = {
            unit
            for unit in strong_exact
            if len(self._source_traversal_claim_unit_tokens(unit)) >= 2
        }
        if strong_exact_phrase or len(strong_exact) >= 2 or (strong_exact and not foreign):
            return {
                "ok": True,
                "reason": "shares path claim units: " + ", ".join(sorted(strong_exact)[:3]),
                "matched_units": matched_units[:6],
                "new_needed_units": new_needed_units[:6],
                "foreign_tokens": sorted(foreign)[:6],
                "frame_continuation": "",
            }
        if len(strong_token_overlap) >= 2:
            if candidate_support_like and foreign:
                return {
                    "ok": False,
                    "reason": "support object introduces a different claim path: " + ", ".join(sorted(foreign)[:5]),
                    "matched_units": matched_units[:6],
                    "new_needed_units": new_needed_units[:6],
                    "foreign_tokens": sorted(foreign)[:6],
                    "frame_continuation": "",
                }
            return {
                "ok": True,
                "reason": "shares path claim tokens: " + ", ".join(sorted(strong_token_overlap)[:4]),
                "matched_units": matched_units[:6],
                "new_needed_units": new_needed_units[:6],
                "foreign_tokens": sorted(foreign)[:6],
                "frame_continuation": "",
            }
        if len(strong_token_overlap) == 1 and structural_relation and not candidate_support_like and len(foreign) <= 1:
            token = next(iter(strong_token_overlap))
            return {
                "ok": True,
                "reason": "structural continuation shares path token: " + token,
                "matched_units": matched_units[:6],
                "new_needed_units": new_needed_units[:6],
                "foreign_tokens": sorted(foreign)[:6],
                "frame_continuation": "",
            }
        if contribution_kind in {"needed definition", "explanatory support", "source-continuity evidence"}:
            if strong_token_overlap and len(foreign) <= 2:
                return {
                    "ok": True,
                    "reason": "role contribution stays connected to the path claim",
                    "matched_units": matched_units[:6],
                    "new_needed_units": new_needed_units[:6],
                    "foreign_tokens": sorted(foreign)[:6],
                    "frame_continuation": "",
                }

        if foreign:
            if frame_continuation["ok"]:
                return {
                    "ok": True,
                    "reason": str(frame_continuation["reason"]),
                    "matched_units": matched_units[:6],
                    "new_needed_units": sorted(candidate_claim_units - accepted_claim_units)[:6],
                    "foreign_tokens": sorted(foreign)[:6],
                    "frame_continuation": str(frame_continuation["type"]),
                }
            return {
                "ok": False,
                "reason": "candidate appears to start a different claim path: " + ", ".join(sorted(foreign)[:5]),
                "matched_units": matched_units[:6],
                "new_needed_units": new_needed_units[:6],
                "foreign_tokens": sorted(foreign)[:6],
                "frame_continuation": "",
            }
        return {
            "ok": False,
            "reason": "candidate does not add needed units for the current path claim",
            "matched_units": matched_units[:6],
            "new_needed_units": new_needed_units[:6],
            "foreign_tokens": [],
            "frame_continuation": "",
        }

    def _source_traversal_frame_continuation(
        self,
        *,
        candidate_signal: ElementSignalRecord,
        accepted_signals: list[ElementSignalRecord],
        candidate_claim_units: set[str],
        scope_units: set[str],
        foreign_tokens: set[str],
        relation_tags: set[str],
        candidate_roles: set[str],
        accepted_roles: set[str],
    ) -> dict[str, object]:
        hard_relation = bool(
            relation_tags
            & {
                "adjacent_previous",
                "adjacent_next",
                "heading_to_body",
                "same_element",
                "explicit_support",
                "support_to_text",
                "strong_list",
                "list_run_entry",
            }
        )
        if not hard_relation or not foreign_tokens:
            return {"ok": False, "type": "", "reason": ""}

        list_frame = "strong_list" in relation_tags or "list_run_entry" in relation_tags
        role_frame = self._source_traversal_role_frame_continues(
            candidate_roles=candidate_roles,
            accepted_roles=accepted_roles,
        )
        if not list_frame and not role_frame:
            return {"ok": False, "type": "", "reason": ""}

        if not self._source_traversal_unit_flow_continues(
            candidate_signal=candidate_signal,
            accepted_signals=accepted_signals,
            candidate_claim_units=candidate_claim_units,
            scope_units=scope_units,
            foreign_tokens=foreign_tokens,
            list_frame=list_frame,
        ):
            return {"ok": False, "type": "", "reason": ""}

        if list_frame:
            return {
                "ok": True,
                "type": "list_frame_continuation",
                "reason": "candidate introduces new units inside the same source list frame",
            }
        return {
            "ok": True,
            "type": "role_frame_continuation",
            "reason": "candidate introduces new units inside a compatible definition/procedure/proof frame",
        }

    def _source_traversal_role_frame_continues(
        self,
        *,
        candidate_roles: set[str],
        accepted_roles: set[str],
    ) -> bool:
        if not candidate_roles or not accepted_roles:
            return False
        proof_roles = {"proof_setup", "proof_reason", "proof_conclusion"}
        if candidate_roles & proof_roles and accepted_roles & (proof_roles | {"procedure", "definition"}):
            if accepted_roles & proof_roles:
                return True
            if "definition" in accepted_roles and candidate_roles & {"proof_setup", "proof_reason"}:
                return True
            if "procedure" in accepted_roles and candidate_roles & {"proof_conclusion"}:
                return True
            return False
        if "procedure" in candidate_roles and accepted_roles & {"procedure", "definition", "proof_setup", "proof_reason"}:
            return True
        if "definition" in candidate_roles and accepted_roles & {"definition", "procedure", "proof_setup"}:
            return True
        return False

    def _source_traversal_unit_flow_continues(
        self,
        *,
        candidate_signal: ElementSignalRecord,
        accepted_signals: list[ElementSignalRecord],
        candidate_claim_units: set[str],
        scope_units: set[str],
        foreign_tokens: set[str],
        list_frame: bool,
    ) -> bool:
        scope_tokens = self._source_traversal_claim_tokens(scope_units)
        candidate_tokens = self._source_traversal_claim_tokens(candidate_claim_units)
        if len(candidate_tokens & scope_tokens) >= 2:
            return True

        candidate_symbols = _grounding_symbols(candidate_signal.text) | {
            token for token in candidate_tokens if len(token) <= 4 and any(character.isalpha() for character in token)
        }
        scope_symbols = set().union(*(_grounding_symbols(signal.text) for signal in accepted_signals)) | {
            token for token in scope_tokens if len(token) <= 4 and any(character.isalpha() for character in token)
        }
        if self._source_traversal_symbol_flow(candidate_symbols=candidate_symbols, scope_symbols=scope_symbols):
            return True

        if list_frame and candidate_signal.list_signal is not None:
            return bool(candidate_tokens & scope_tokens or candidate_symbols or foreign_tokens)
        return False

    def _source_traversal_symbol_flow(self, *, candidate_symbols: set[str], scope_symbols: set[str]) -> bool:
        for candidate_symbol in candidate_symbols:
            candidate = candidate_symbol.lower()
            if not candidate or candidate in STOPWORDS:
                continue
            for scope_symbol in scope_symbols:
                scope = scope_symbol.lower()
                if not scope or scope in STOPWORDS:
                    continue
                if candidate == scope:
                    return True
                if len(scope) >= 1 and len(candidate) >= 2 and candidate.startswith(scope):
                    return True
                if len(candidate) >= 1 and len(scope) >= 2 and scope.startswith(candidate):
                    return True
        return False

    def _source_traversal_claim_alignment(
        self,
        *,
        candidate_claim_units: set[str],
        path_signature: set[str],
        path_signature_tokens: set[str],
        prompt_claim_tokens: set[str],
        relation_tags: set[str],
        candidate_support_like: bool,
        document_unit_counts: Counter[str],
        document_claim_unit_counts: Counter[str],
        document_size: int,
    ) -> dict[str, object]:
        if not path_signature:
            return {"ok": True, "reason": "no stable path claim yet"}
        if relation_tags & {"same_element", "explicit_support", "support_to_text"}:
            return {"ok": True, "reason": "explicitly attached to the same source object"}

        distinctive_limit = max(1, int(math.sqrt(max(1, document_size))))
        exact_overlap = candidate_claim_units & path_signature
        strong_exact = {
            unit
            for unit in exact_overlap
            if self._source_traversal_claim_unit_is_strong(
                unit,
                document_claim_unit_counts=document_claim_unit_counts,
                distinctive_limit=distinctive_limit,
            )
            and (
                not candidate_support_like
                or len(self._source_traversal_claim_unit_tokens(unit)) >= 2
            )
        }
        if strong_exact:
            return {"ok": True, "reason": "shares path claim units: " + ", ".join(sorted(strong_exact)[:3])}

        candidate_tokens = self._source_traversal_claim_tokens(candidate_claim_units)
        token_overlap = candidate_tokens & path_signature_tokens
        strong_token_overlap = {
            token
            for token in token_overlap
            if token in prompt_claim_tokens
            or document_unit_counts.get(token, 0) <= distinctive_limit
            or len(token) >= 6
        }
        if len(strong_token_overlap) >= 2:
            return {"ok": True, "reason": "shares path claim tokens: " + ", ".join(sorted(strong_token_overlap)[:4])}
        if len(strong_token_overlap) == 1:
            structural_relation = bool(
                relation_tags
                & {
                    "adjacent_previous",
                    "adjacent_next",
                    "heading_to_body",
                    "strong_list",
                }
            )
            if structural_relation and not candidate_support_like:
                token = next(iter(strong_token_overlap))
                return {"ok": True, "reason": "structural continuation shares path token: " + token}
            foreign = self._source_traversal_foreign_claim_tokens(
                candidate_tokens=candidate_tokens,
                path_signature_tokens=path_signature_tokens,
                prompt_claim_tokens=prompt_claim_tokens,
                document_unit_counts=document_unit_counts,
                distinctive_limit=distinctive_limit,
            )
            if not candidate_support_like and len(foreign) <= 1:
                token = next(iter(strong_token_overlap))
                return {"ok": True, "reason": "shares distinctive path claim token: " + token}

        foreign = self._source_traversal_foreign_claim_tokens(
            candidate_tokens=candidate_tokens,
            path_signature_tokens=path_signature_tokens,
            prompt_claim_tokens=prompt_claim_tokens,
            document_unit_counts=document_unit_counts,
            distinctive_limit=distinctive_limit,
        )
        if foreign:
            return {
                "ok": False,
                "reason": "candidate appears to start a different claim path: " + ", ".join(sorted(foreign)[:5]),
            }
        return {"ok": False, "reason": "candidate does not share the current path claim"}

    def _source_traversal_path_signature(
        self,
        *,
        accepted_indices: list[int],
        anchor_index: int,
        prompt_claim_units: set[str],
        claim_units_by_index: Mapping[int, set[str]],
        document_claim_unit_counts: Counter[str],
        document_unit_counts: Counter[str],
        document_size: int,
    ) -> set[str]:
        if not accepted_indices:
            return set()
        distinctive_limit = max(1, int(math.sqrt(max(1, document_size))))
        prompt_tokens = self._source_traversal_claim_tokens(prompt_claim_units)
        anchor_units = claim_units_by_index.get(anchor_index, set())
        accepted_presence: Counter[str] = Counter()
        for units in claim_units_by_index.values():
            accepted_presence.update(units)

        signature: set[str] = set()
        for unit, presence_count in accepted_presence.items():
            if self._source_traversal_claim_unit_is_generic(unit):
                continue
            tokens = self._source_traversal_claim_unit_tokens(unit)
            if not tokens:
                continue
            token_prompt_overlap = tokens & prompt_tokens
            has_distinctive_token = any(document_unit_counts.get(token, 0) <= distinctive_limit for token in tokens)
            phrase_like = len(tokens) >= 2
            exact_prompt_match = unit in prompt_claim_units
            anchor_match = unit in anchor_units

            if exact_prompt_match:
                signature.add(unit)
            elif token_prompt_overlap and (phrase_like or has_distinctive_token):
                signature.add(unit)
            elif anchor_match and has_distinctive_token:
                signature.add(unit)
            elif presence_count > 1 and (phrase_like or has_distinctive_token):
                signature.add(unit)

        return signature

    def _source_traversal_claim_units(self, text: str) -> set[str]:
        units = {
            unit
            for unit in self._source_traversal_units(text)
            if not self._source_traversal_claim_unit_is_generic(unit)
        }
        for language_unit in _extract_language_units(text, proposition_index=-1, element_id="", element_index=-1):
            if language_unit.kind not in {"phrase", "relation", "quantity", "summary", "symbol"}:
                continue
            normalized = language_unit.normalized
            if normalized and not self._source_traversal_claim_unit_is_generic(normalized):
                units.add(normalized)
        return units

    def _source_traversal_claim_tokens(self, units: Iterable[str]) -> set[str]:
        tokens: set[str] = set()
        for unit in units:
            tokens.update(self._source_traversal_claim_unit_tokens(unit))
        return tokens

    def _source_traversal_claim_unit_tokens(self, unit: str) -> set[str]:
        tokens = set(_content_tokens(unit))
        return {
            token
            for token in tokens
            if not self._source_traversal_claim_token_is_generic(token)
        }

    def _source_traversal_claim_unit_is_generic(self, unit: str) -> bool:
        tokens = set(_content_tokens(unit))
        if not tokens:
            return True
        return all(self._source_traversal_claim_token_is_generic(token) for token in tokens)

    def _source_traversal_claim_token_is_generic(self, token: str) -> bool:
        if not token:
            return True
        if token in STOPWORDS or token in COMPLETION_NOISE_TERMS or token in VAGUE_ROLE_TARGETS:
            return True
        if token in SOURCE_TRAVERSAL_GENERIC_CLAIM_UNITS:
            return True
        if len(token) == 1 and token.isalpha():
            return True
        return False

    def _source_traversal_claim_unit_is_strong(
        self,
        unit: str,
        *,
        document_claim_unit_counts: Counter[str],
        distinctive_limit: int,
    ) -> bool:
        tokens = self._source_traversal_claim_unit_tokens(unit)
        if len(tokens) >= 2:
            return True
        return bool(tokens) and document_claim_unit_counts.get(unit, 0) <= distinctive_limit

    def _source_traversal_foreign_claim_tokens(
        self,
        *,
        candidate_tokens: set[str],
        path_signature_tokens: set[str],
        prompt_claim_tokens: set[str],
        document_unit_counts: Counter[str],
        distinctive_limit: int,
    ) -> set[str]:
        foreign: set[str] = set()
        for token in candidate_tokens - path_signature_tokens - prompt_claim_tokens:
            if self._source_traversal_claim_token_is_generic(token):
                continue
            if document_unit_counts.get(token, 0) <= distinctive_limit or len(token) >= 6:
                foreign.add(token)
        return foreign

    def _source_traversal_contribution(
        self,
        *,
        signal: ElementSignalRecord,
        proposition: QueryEvidenceProposition,
        relation_tags: set[str],
        prompt_units: set[str],
        prompt_wants_support: bool,
        accepted_units: set[str],
        candidate_units: set[str],
        document_unit_counts: Counter[str],
        document_size: int,
        accepted_roles: set[str],
        candidate_roles: set[str],
    ) -> dict[str, object]:
        strong_relation_tags = {
            "consensus_graph",
            "adjacent_previous",
            "adjacent_next",
            "heading_to_body",
            "explicit_support",
            "support_to_text",
            "same_element",
            "strong_list",
            "list_run_entry",
        }
        source_ok = bool(relation_tags & strong_relation_tags)
        if not source_ok and {"shared_symbols", "same_section"} <= relation_tags:
            source_ok = True
        if not source_ok and "relation_geometry" in relation_tags and "same_section" in relation_tags:
            source_ok = True

        new_units = candidate_units - accepted_units
        prompt_overlap = candidate_units & prompt_units
        accepted_overlap = candidate_units & accepted_units
        new_roles = candidate_roles - accepted_roles
        prompt_substantial = self._source_traversal_overlap_is_substantial(
            prompt_overlap,
            document_unit_counts=document_unit_counts,
            document_size=document_size,
        )
        accepted_substantial = self._source_traversal_overlap_is_substantial(
            accepted_overlap,
            document_unit_counts=document_unit_counts,
            document_size=document_size,
        )
        prompt_symbol_overlap = any(self._source_traversal_symbollike(unit) for unit in prompt_overlap)
        accepted_symbol_overlap = any(self._source_traversal_symbollike(unit) for unit in accepted_overlap)
        contribution_units = sorted(
            new_units & (prompt_units | accepted_units | _grounding_symbols(proposition.text))
        )
        if not contribution_units:
            contribution_units = sorted(new_units)[:6]

        if not source_ok:
            return {"source_ok": False, "kind": "", "contribution": "", "units": contribution_units}
        if not new_units and not new_roles:
            return {"source_ok": True, "kind": "", "contribution": "", "units": contribution_units}

        kind = ""
        if prompt_substantial and new_units:
            kind = "direct prompt evidence"
        elif "definition" in candidate_roles and (prompt_substantial or accepted_substantial or prompt_symbol_overlap) and new_units:
            kind = "needed definition"
        elif candidate_roles & {"proof_reason", "proof_conclusion", "procedure", "comparison"} and (
            prompt_substantial or accepted_substantial or accepted_symbol_overlap
        ):
            kind = "explanatory support"
        elif (
            "support" in candidate_roles
            and prompt_wants_support
            and prompt_substantial
            and new_units
        ):
            kind = "visual/table support"
        elif (
            relation_tags & (strong_relation_tags - {"consensus_graph"})
            and accepted_substantial
            and new_units
            and not signal.is_heading
            and signal.element_type not in SUPPORT_ELEMENT_TYPES
        ):
            kind = "source-continuity evidence"

        if not kind:
            return {"source_ok": True, "kind": "", "contribution": "", "units": contribution_units}

        unit_text = ", ".join(contribution_units[:5])
        if unit_text:
            contribution = f"adds {kind}: {unit_text}"
        else:
            contribution = f"adds {kind}"
        return {
            "source_ok": True,
            "kind": kind,
            "contribution": contribution,
            "units": contribution_units,
        }

    def _source_traversal_units(self, text: str) -> set[str]:
        units = {
            token
            for token in _content_tokens(text)
            if token not in COMPLETION_NOISE_TERMS and token not in VAGUE_ROLE_TARGETS
        }
        units.update(
            symbol
            for symbol in _grounding_symbols(text)
            if symbol not in COMPLETION_NOISE_TERMS and symbol not in VAGUE_ROLE_TARGETS
        )
        for unit in _extract_language_units(text, proposition_index=-1, element_id="", element_index=-1):
            if unit.kind in {"symbol", "quantity", "relation"}:
                units.update(
                    token
                    for token in unit.tokens
                    if token not in COMPLETION_NOISE_TERMS and token not in VAGUE_ROLE_TARGETS
                )
        return units

    def _source_traversal_overlap_is_substantial(
        self,
        units: set[str],
        *,
        document_unit_counts: Counter[str],
        document_size: int,
    ) -> bool:
        strong_units = {
            unit
            for unit in units
            if len(unit) >= 4
            or any(character.isdigit() for character in unit)
            or "_" in unit
            or "(" in unit
            or unit in {"dna", "rna", "omega", "delta"}
        }
        if len(strong_units) >= 2:
            return True
        distinctive_limit = max(1, int(math.sqrt(max(1, document_size))))
        return any(document_unit_counts.get(unit, 0) <= distinctive_limit for unit in strong_units)

    def _source_traversal_symbollike(self, unit: str) -> bool:
        return (
            len(unit) <= 2
            or any(character.isdigit() for character in unit)
            or "_" in unit
            or "(" in unit
            or unit in {"omega", "delta"}
        )

    def _source_traversal_candidate_map(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        graph: dict[int, dict[int, "_ConsensusEdge"]],
        relation_geometry: "_DocumentRelationGeometry | None",
        frontier: list[int],
        accepted_set: set[int],
    ) -> dict[int, set[str]]:
        prop_indices_by_element: dict[str, list[int]] = defaultdict(list)
        prop_indices_by_element_index: dict[int, list[int]] = defaultdict(list)
        heading_keys_by_index: dict[int, set[str]] = {}
        symbols_by_index: dict[int, set[str]] = {}
        for proposition_index, proposition in enumerate(propositions):
            prop_indices_by_element[proposition.element_id].append(proposition_index)
            prop_indices_by_element_index[proposition.element_index].append(proposition_index)
            signal = signals[proposition.element_index]
            heading_keys_by_index[proposition_index] = {
                heading.element_id
                for heading in signal.heading_path
                if heading.element_id
            }
            symbols_by_index[proposition_index] = _grounding_symbols(proposition.text)

        relation_map: dict[int, set[str]] = defaultdict(set)

        def add(target_index: int, tag: str) -> None:
            if target_index < 0 or target_index >= len(propositions):
                return
            if target_index in accepted_set:
                return
            relation_map[target_index].add(tag)

        for source_index in frontier:
            source = propositions[source_index]
            source_signal = signals[source.element_index]

            for target_index in graph.get(source_index, {}):
                add(target_index, "consensus_graph")

            for target_index in prop_indices_by_element.get(source.element_id, []):
                add(target_index, "same_element")

            for neighbor_element_index, tag in (
                (source.element_index - 1, "adjacent_previous"),
                (source.element_index + 1, "adjacent_next"),
            ):
                for target_index in prop_indices_by_element_index.get(neighbor_element_index, []):
                    add(target_index, tag)

            if source_signal.is_heading:
                for offset in range(1, 4):
                    for target_index in prop_indices_by_element_index.get(source.element_index + offset, []):
                        target_signal = signals[propositions[target_index].element_index]
                        if target_signal.is_heading:
                            break
                        add(target_index, "heading_to_body")

            source_heading_keys = heading_keys_by_index.get(source_index, set())

            for support_id in source.support_element_ids:
                for target_index in prop_indices_by_element.get(support_id, []):
                    add(target_index, "explicit_support")
            for target_index, candidate in enumerate(propositions):
                if source.element_id in candidate.support_element_ids:
                    add(target_index, "support_to_text")

            for neighbor_element_index in range(max(0, source.element_index - 3), min(len(signals), source.element_index + 4)):
                if neighbor_element_index == source.element_index:
                    continue
                if self._strong_list_sibling_pair(source_signal, signals[neighbor_element_index]):
                    for target_index in prop_indices_by_element_index.get(neighbor_element_index, []):
                        add(target_index, "strong_list")

            if source_signal.list_signal is None:
                list_neighbor_indices = list(
                    range(max(0, source.element_index - 4), source.element_index)
                ) + list(
                    range(source.element_index + 1, min(len(signals), source.element_index + 5))
                )
                for neighbor_element_index in list_neighbor_indices:
                    target_signal = signals[neighbor_element_index]
                    if target_signal.is_heading:
                        continue
                    if target_signal.list_signal is None:
                        continue
                    if not self._same_heading_neighborhood(source_signal, target_signal):
                        continue
                    for target_index in prop_indices_by_element_index.get(neighbor_element_index, []):
                        add(target_index, "list_run_entry")

            source_symbols = symbols_by_index.get(source_index, set())
            if source_symbols:
                for target_index, target_symbols in symbols_by_index.items():
                    if target_index == source_index:
                        continue
                    if source_symbols & target_symbols:
                        add(target_index, "shared_symbols")

            if relation_geometry is not None:
                scored = [
                    (relation_geometry.score(source_index, target_index), target_index)
                    for target_index in range(len(propositions))
                    if target_index not in accepted_set and target_index != source_index
                ]
                for score, target_index in sorted(scored, reverse=True)[: self.source_traversal_candidate_limit]:
                    if score > 0.0:
                        add(target_index, "relation_geometry")

            if source_heading_keys:
                for target_index in list(relation_map):
                    target_heading_keys = heading_keys_by_index.get(target_index, set())
                    if source_heading_keys & target_heading_keys:
                        relation_map[target_index].add("same_section")

        return dict(relation_map)

    def _assemble_answer_bundle(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        prompt: str,
        retrieval_plan: QueryRetrievalPlan,
        graph: dict[int, dict[int, "_ConsensusEdge"]],
        proposition_embeddings: np.ndarray,
        relation_geometry: "_DocumentRelationGeometry | None",
    ) -> QueryAnswerBundle | None:
        if not retrieval_plan.sub_needs:
            return None

        proposition_token_sets = [self._bridge_tokens(proposition.text) for proposition in propositions]
        token_counts: Counter[str] = Counter()
        for tokens in proposition_token_sets:
            token_counts.update(tokens)

        parts: list[QueryAnswerBundlePart] = []
        for sub_need_index, sub_need in enumerate(retrieval_plan.sub_needs):
            anchor_group = self._sub_need_anchor_group(
                signals=signals,
                propositions=propositions,
                proposition_token_sets=proposition_token_sets,
                token_counts=token_counts,
                sub_need=sub_need,
            )
            if not anchor_group:
                continue

            representative = anchor_group[0]
            sub_need_query = self._sub_need_query_text(sub_need)
            sub_need_embeddings = self._embed([sub_need_query, *[proposition.text for proposition in propositions]])
            sub_need_prompt_embedding = sub_need_embeddings[0]
            sub_need_similarities = sub_need_embeddings[1:] @ sub_need_prompt_embedding
            language_scores = self._language_proposition_scores(
                prompt=sub_need_query,
                propositions=propositions,
            )
            representative_proposition = propositions[representative]
            package = self._assemble_cluster_for_core(
                signals=signals,
                propositions=propositions,
                prompt=sub_need_query,
                prompt_embedding=sub_need_prompt_embedding,
                proposition_embeddings=proposition_embeddings,
                proposition_similarities=sub_need_similarities,
                language_scores=language_scores,
                graph=graph,
                relation_geometry=relation_geometry,
                core_candidate=_CoreCandidate(
                    element_index=representative_proposition.element_index,
                    prompt_similarity=float(sub_need_similarities[representative]),
                    core_embedding=proposition_embeddings[representative],
                    proposition_id=representative_proposition.proposition_id,
                    proposition_index=representative,
                    proposition_text=representative_proposition.text,
                    support_element_ids=list(representative_proposition.support_element_ids),
                    anchor_prop_indices=anchor_group,
                ),
                package_index=sub_need_index,
            )
            package = replace(package, package_id=f"query-bundle-package-{sub_need_index:05d}")
            parts.append(
                QueryAnswerBundlePart(
                    sub_need=sub_need.need,
                    search_terms=list(sub_need.search_terms),
                    expected_roles=list(sub_need.expected_roles),
                    package=package,
                )
            )

        if not parts:
            return None
        return QueryAnswerBundle(
            bundle_id="query-answer-bundle-00000",
            prompt=prompt,
            parts=parts,
        )

    def _query_retrieval_plan(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        prompt: str,
    ) -> QueryRetrievalPlan | None:
        if not self.use_query_planner or self.llm_client is None:
            return None
        retrieval_map = self._document_retrieval_map(signals=signals, propositions=propositions)
        if not retrieval_map:
            return None
        cache_key = hashlib.sha256(
            "\n".join(["query_retrieval_plan_v2_subneeds", prompt, retrieval_map]).encode("utf-8")
        ).hexdigest()
        cached = self._query_plan_cache.get(cache_key)
        if cached is not None:
            return cached

        request = LLMRequest(
            system=(
                "You produce source-grounded retrieval hypotheses. "
                "Use only vocabulary and concepts present in the provided document map. "
                "Return only JSON matching the requested schema."
            ),
            user=self._query_retrieval_plan_prompt(prompt=prompt, retrieval_map=retrieval_map),
            temperature=0.0,
            response_format=self._query_retrieval_plan_response_format(),
        )
        responses = self.llm_client.complete_many([request])
        content = getattr(responses[0], "content", str(responses[0])) if responses else ""
        plan = self._parse_query_retrieval_plan(content)
        if plan is None:
            return None
        self._query_plan_cache[cache_key] = plan
        return plan

    def _query_texts_from_plan(self, prompt: str, plan: QueryRetrievalPlan | None) -> list[str]:
        texts = [prompt]
        if plan is None:
            return texts
        candidates = [plan.interpreted_need]
        for sub_need in plan.sub_needs:
            candidates.append(" ".join([sub_need.need, *sub_need.search_terms, *sub_need.expected_roles]))
        terms = [term for term in plan.source_supported_terms if term.strip()]
        for index in range(0, len(terms), 4):
            candidates.append(" ".join(terms[index : index + 4]))
        prerequisites = [item for item in plan.possible_missing_prerequisites if item.strip()]
        for index in range(0, len(prerequisites), 3):
            candidates.append(" ".join(prerequisites[index : index + 3]))
        candidates.extend(plan.search_forms)
        if plan.uncertainties:
            candidates.append(" ".join(plan.uncertainties[:2]))
        seen = {prompt.strip().lower()}
        for text in candidates:
            cleaned = re.sub(r"\s+", " ", str(text)).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            texts.append(cleaned)
            if len(texts) >= self.query_planner_max_search_forms + 1:
                break
        return texts

    def _source_grounded_bridge_candidates(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        prompt: str,
        plan: QueryRetrievalPlan,
        max_bridges: int = 4,
        radius: int = 4,
    ) -> tuple[list[str], list[int], list[tuple[int, ...]]]:
        prompt_tokens = self._bridge_tokens(prompt)
        plan_text = " ".join(
            [
                *plan.source_supported_terms,
                *plan.possible_missing_prerequisites,
                *plan.search_forms,
            ]
        )
        plan_tokens = self._bridge_tokens(plan_text) - prompt_tokens
        if not plan_tokens:
            return [], [], []

        proposition_token_sets = [self._bridge_tokens(proposition.text) for proposition in propositions]
        token_counts: Counter[str] = Counter()
        for tokens in proposition_token_sets:
            token_counts.update(tokens)

        scored: list[tuple[float, int, int, QueryEvidenceProposition]] = []
        for proposition_index, proposition in enumerate(propositions):
            signal = signals[proposition.element_index]
            if signal.is_heading:
                continue
            tokens = proposition_token_sets[proposition_index]
            overlap = len(tokens & plan_tokens)
            if overlap <= 0:
                continue
            rare_overlap = sum(1.0 / math.sqrt(max(1, token_counts[token])) for token in tokens & plan_tokens)
            bridge_bonus = self._source_bridge_proof_bonus(prompt=prompt, tokens=tokens, text=proposition.text)
            scored.append((rare_overlap + bridge_bonus, overlap, proposition_index, proposition))

        bridge_texts: list[str] = []
        bridge_prop_indices: list[int] = []
        used_windows: set[tuple[int, int]] = set()
        for _overlap, _token_count, proposition_index, proposition in sorted(
            scored, key=lambda item: (item[0], item[1]), reverse=True
        )[
            : max_bridges * 3
        ]:
            start = max(0, proposition.element_index - radius)
            end = min(len(signals) - 1, proposition.element_index + radius)
            window = (start, end)
            if window in used_windows:
                continue
            used_windows.add(window)
            texts = [
                candidate.text
                for candidate in propositions
                if start <= candidate.element_index <= end
                and not (signals[candidate.element_index].is_heading and signals[candidate.element_index].word_count <= 5)
            ]
            bridge = re.sub(r"\s+", " ", " ".join(texts)).strip()
            if len(bridge) > 700:
                bridge = bridge[:697].rstrip() + "..."
            if bridge:
                bridge_texts.append(bridge)
                bridge_prop_indices.append(proposition_index)
            if len(bridge_texts) >= max_bridges:
                break
        anchor_groups = self._sub_need_anchor_groups(
            signals=signals,
            propositions=propositions,
            proposition_token_sets=proposition_token_sets,
            token_counts=token_counts,
            plan=plan,
            max_groups=max_bridges,
        )
        sub_need_representatives: list[int] = []
        for group in anchor_groups:
            for proposition_index in group:
                if proposition_index not in sub_need_representatives:
                    sub_need_representatives.append(proposition_index)
                    break
        bridge_prop_indices = [*sub_need_representatives, *[index for index in bridge_prop_indices if index not in sub_need_representatives]]
        return bridge_texts, bridge_prop_indices, anchor_groups

    def _sub_need_anchor_groups(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_token_sets: list[set[str]],
        token_counts: Counter[str],
        plan: QueryRetrievalPlan,
        max_groups: int,
    ) -> list[tuple[int, ...]]:
        if not plan.sub_needs:
            return []
        groups: list[tuple[int, ...]] = []
        seen_groups: set[tuple[int, ...]] = set()
        for sub_need in plan.sub_needs[:4]:
            group = self._sub_need_anchor_group(
                signals=signals,
                propositions=propositions,
                proposition_token_sets=proposition_token_sets,
                token_counts=token_counts,
                sub_need=sub_need,
            )
            if not group:
                continue
            if group in seen_groups:
                continue
            seen_groups.add(group)
            groups.append(group)
            if len(groups) >= max_groups:
                break
        if len(groups) >= 2:
            representative = self._combined_sub_need_representative(groups=groups, propositions=propositions)
            combined_items = [representative, *[index for group in groups for index in group[:2] if index != representative]]
            combined = tuple(dict.fromkeys(combined_items))
            if combined and combined not in seen_groups:
                groups.insert(0, combined)
                groups = groups[:max_groups]
        return groups

    def _sub_need_anchor_group(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_token_sets: list[set[str]],
        token_counts: Counter[str],
        sub_need: QueryRetrievalSubNeed,
    ) -> tuple[int, ...]:
        sub_tokens = self._bridge_tokens(" ".join([sub_need.need, *sub_need.search_terms]))
        if not sub_tokens:
            return ()
        expected_roles = {role.strip().lower() for role in sub_need.expected_roles if role.strip()}
        scored: list[tuple[float, int]] = []
        for proposition_index, proposition in enumerate(propositions):
            signal = signals[proposition.element_index]
            if signal.is_heading:
                continue
            tokens = proposition_token_sets[proposition_index]
            overlap = tokens & sub_tokens
            if not overlap:
                continue
            rare_overlap = sum(1.0 / math.sqrt(max(1, token_counts[token])) for token in overlap)
            role_bonus = self._sub_need_role_bonus(proposition=proposition, expected_roles=expected_roles)
            structure_bonus = self._sub_need_structure_bonus(signal=signal, proposition=proposition, sub_need=sub_need)
            scored.append((rare_overlap + role_bonus + structure_bonus, proposition_index))
        ranked = [index for _score, index in sorted(scored, reverse=True)[:3]]
        return tuple(dict.fromkeys(ranked))

    def _sub_need_query_text(self, sub_need: QueryRetrievalSubNeed) -> str:
        text = " ".join([sub_need.need, *sub_need.search_terms, *sub_need.expected_roles])
        return re.sub(r"\s+", " ", text).strip() or sub_need.need

    def _combined_sub_need_representative(
        self,
        *,
        groups: list[tuple[int, ...]],
        propositions: list[QueryEvidenceProposition],
    ) -> int:
        role_priority = {
            "quantity_bound": 5,
            "proof_reason": 5,
            "proof_conclusion": 4,
            "procedure_step": 3,
            "definition": 2,
            "proof_setup": 2,
            "claim": 1,
            "assumption": 1,
        }
        candidates = list(dict.fromkeys(index for group in groups for index in group[:2]))
        return max(
            candidates,
            key=lambda index: (
                max((role_priority.get(role.role.strip().lower(), 0) for role in propositions[index].roles), default=0),
                len(set(_content_tokens(propositions[index].text))),
                propositions[index].element_index,
            ),
        )

    def _sub_need_role_bonus(self, *, proposition: QueryEvidenceProposition, expected_roles: set[str]) -> float:
        if not expected_roles:
            return 0.0
        proposition_roles = {role.role.strip().lower() for role in proposition.roles}
        overlap = proposition_roles & expected_roles
        if not overlap:
            return 0.0
        strong_roles = {"definition", "quantity_bound", "proof_reason", "proof_conclusion", "procedure_step", "visual_support", "table_support", "formula_support"}
        return min(0.9, 0.28 * len(overlap) + 0.18 * len(overlap & strong_roles))

    def _sub_need_structure_bonus(
        self,
        *,
        signal: ElementSignalRecord,
        proposition: QueryEvidenceProposition,
        sub_need: QueryRetrievalSubNeed,
    ) -> float:
        text = " ".join([signal.text, proposition.text, sub_need.need]).lower()
        bonus = 0.0
        if re.search(r"\b(proof|claim|suppose|therefore|hence|thus|contradict\w*)\b", text):
            bonus += 0.18
        if re.search(r"\b(at\s+most|at\s+least|within|\d+\s*(?:positions?|rows?|boxes?|points?))\b", text):
            bonus += 0.22
        if signal.element_type in SUPPORT_ELEMENT_TYPES:
            bonus += 0.12
        return bonus

    def _source_bridge_proof_bonus(self, *, prompt: str, tokens: set[str], text: str) -> float:
        bonus = 0.0
        # Experimental closest-pair bridge removed for validation:
        # if {"nearby", "strip"} & prompt_tokens:
        #     if "sy" in tokens and ("15" in tokens or "positions" in tokens or "next" in tokens):
        #         bonus += 2.2
        #     if {"rows", "boxes"} <= tokens:
        #         bonus += 1.8
        #     if "box" in lowered and "row" in lowered:
        #         bonus += 1.2
        if _prompt_asks_why(prompt) and re.search(r"\b(therefore|since|as|suppose|contradict\w*)\b", text, re.IGNORECASE):
            bonus += 0.35
        return bonus

    def _bridge_tokens(self, text: str) -> set[str]:
        tokens: set[str] = set()
        for token in _content_tokens(text):
            lowered = token.lower()
            tokens.add(lowered)
            if len(lowered) > 3 and lowered.endswith("s"):
                tokens.add(lowered[:-1])
        return tokens

    def _multi_query_proposition_similarities(
        self,
        *,
        proposition_embeddings: np.ndarray,
        query_embeddings: np.ndarray,
    ) -> np.ndarray:
        similarities = proposition_embeddings @ query_embeddings.T
        if similarities.shape[1] == 1:
            return similarities[:, 0]
        original = similarities[:, 0]
        planned = np.max(similarities[:, 1:], axis=1)
        combined = np.maximum(original, planned * 0.97)
        for query_index in range(1, similarities.shape[1]):
            ranked = np.argsort(-similarities[:, query_index])[:2]
            for prop_index in ranked:
                combined[prop_index] = max(combined[prop_index], float(similarities[prop_index, query_index]) * 0.97 + 0.08)
        return np.minimum(combined, 1.0)

    def _boost_planned_query_neighborhoods(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_embeddings: np.ndarray,
        query_embeddings: np.ndarray,
        query_texts: list[str],
        proposition_similarities: np.ndarray,
        radius: int = 5,
    ) -> np.ndarray:
        if query_embeddings.shape[0] <= 1:
            return proposition_similarities
        boosted = np.array(proposition_similarities, copy=True)
        similarities = proposition_embeddings @ query_embeddings.T
        proposition_tokens = [set(_content_tokens(proposition.text)) for proposition in propositions]
        for query_index in range(1, similarities.shape[1]):
            query_tokens = set(_content_tokens(query_texts[query_index])) if query_index < len(query_texts) else set()
            lexical_ranked = sorted(
                range(len(propositions)),
                key=lambda index: (
                    _jaccard(query_tokens, proposition_tokens[index]),
                    len(query_tokens & proposition_tokens[index]),
                ),
                reverse=True,
            )[:3]
            candidate_indices = list(dict.fromkeys([*map(int, np.argsort(-similarities[:, query_index])[:3]), *lexical_ranked]))
            for prop_index in candidate_indices:
                proposition = propositions[int(prop_index)]
                signal = signals[proposition.element_index]
                if signal.is_heading or signal.word_count <= 5:
                    continue
                anchor_element_index = proposition.element_index
                for neighbor_index, neighbor in enumerate(propositions):
                    distance = abs(neighbor.element_index - anchor_element_index)
                    if distance > radius:
                        continue
                    neighbor_signal = signals[neighbor.element_index]
                    if neighbor_signal.is_heading and neighbor_signal.word_count <= 5:
                        continue
                    floor = 0.78 - distance * 0.02
                    boosted[neighbor_index] = max(float(boosted[neighbor_index]), floor)
        return np.minimum(boosted, 1.0)

    def _document_retrieval_map(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
    ) -> str:
        proposition_by_element: dict[str, list[QueryEvidenceProposition]] = defaultdict(list)
        for proposition in propositions:
            proposition_by_element[proposition.element_id].append(proposition)

        lines: list[str] = []
        item_count = 0
        repeated_titles: Counter[str] = Counter()
        for signal in signals:
            text_key = _normalize_language_text(signal.text)
            if signal.is_heading or signal.word_count <= 7:
                repeated_titles[text_key] += 1

        for signal in signals:
            if item_count >= self.query_planner_max_map_items:
                break
            props = proposition_by_element.get(signal.element_id, [])
            if not props:
                continue
            text_key = _normalize_language_text(signal.text)
            if repeated_titles.get(text_key, 0) > 2 and signal.word_count <= 7:
                continue
            terms = ", ".join(signal.unique_content_terms[:8])
            symbol_text = ", ".join(signal.formula_symbols[:6])
            prefix = f"[{signal.element_index}] {signal.element_id} type={signal.element_type}"
            if signal.is_heading:
                prefix += " heading=true"
            if terms:
                prefix += f" terms={terms}"
            if symbol_text:
                prefix += f" symbols={symbol_text}"
            lines.append(prefix)
            for proposition in props[:3]:
                text = re.sub(r"\s+", " ", proposition.text).strip()
                if len(text) > 220:
                    text = text[:217].rstrip() + "..."
                lines.append(f"- {text}")
            item_count += 1
        return "\n".join(lines)

    def _query_retrieval_plan_prompt(self, *, prompt: str, retrieval_map: str) -> str:
        return "\n".join(
            [
                "Analyze the user query for retrieval against this one document.",
                "",
                "Rules:",
                "- Treat your analysis as a retrieval hypothesis, not truth.",
                "- Use only terms, concepts, symbols, and relationships that appear in the document map.",
                "- Do not invent document vocabulary.",
                "- Prefer source-grounded search forms that can retrieve prerequisite/proof/support evidence.",
                "- If the query is vague or novice-level, bridge it to document terms only when the map supports that bridge.",
                "- If the query asks why/how/can/only, include proof-mechanism terms from the map: constraints, bounds, quantities, symbols, examples, and intermediate lemmas.",
                "- Do not stop at broad topic terms when the map contains narrower proof or mechanism vocabulary that explains the query.",
                "- Decompose the query into sub_needs when the answer requires multiple evidence pieces.",
                "- Each sub_need must be necessary to answer the user's exact query; do not add broad summary, runtime, recurrence, or background sub_needs unless the query asks for them.",
                "- Each sub_need should describe one answer part, list source-supported search_terms, and list expected_roles such as definition, proof_setup, proof_reason, proof_conclusion, quantity_bound, procedure_step, visual_support, table_support, or formula_support.",
                "- Produce diverse search forms: original wording, keyword form, expert terminology form, prerequisite concept form, step-back principle form, and hypothetical answer/document wording.",
                "",
                f"User query: {prompt}",
                "",
                "Document map:",
                retrieval_map,
                "",
                "Return JSON with interpreted_need, query_type, source_supported_terms, possible_missing_prerequisites, search_forms, uncertainties, and sub_needs.",
            ]
        )

    def _query_retrieval_plan_response_format(self) -> Mapping[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "query_retrieval_plan",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "interpreted_need": {"type": "string"},
                        "query_type": {"type": "string"},
                        "source_supported_terms": {"type": "array", "items": {"type": "string"}},
                        "possible_missing_prerequisites": {"type": "array", "items": {"type": "string"}},
                        "search_forms": {"type": "array", "items": {"type": "string"}},
                        "uncertainties": {"type": "array", "items": {"type": "string"}},
                        "sub_needs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "need": {"type": "string"},
                                    "search_terms": {"type": "array", "items": {"type": "string"}},
                                    "expected_roles": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["need", "search_terms", "expected_roles"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "interpreted_need",
                        "query_type",
                        "source_supported_terms",
                        "possible_missing_prerequisites",
                        "search_forms",
                        "uncertainties",
                        "sub_needs",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    def _parse_query_retrieval_plan(self, content: str) -> QueryRetrievalPlan | None:
        payload = _extract_json_payload(content)
        if not isinstance(payload, dict):
            return None

        def string_list(value: Any, *, limit: int = 12) -> list[str]:
            if not isinstance(value, list):
                return []
            cleaned: list[str] = []
            for item in value:
                text = re.sub(r"\s+", " ", str(item)).strip()
                if text:
                    cleaned.append(text)
                if len(cleaned) >= limit:
                    break
            return cleaned

        def sub_need_list(value: Any, *, limit: int = 6) -> list[QueryRetrievalSubNeed]:
            if not isinstance(value, list):
                return []
            cleaned: list[QueryRetrievalSubNeed] = []
            for item in value:
                if not isinstance(item, Mapping):
                    continue
                need = re.sub(r"\s+", " ", str(item.get("need", ""))).strip()
                if not need:
                    continue
                cleaned.append(
                    QueryRetrievalSubNeed(
                        need=need[:220],
                        search_terms=string_list(item.get("search_terms"), limit=10),
                        expected_roles=[
                            re.sub(r"\s+", "_", role).strip().lower()
                            for role in string_list(item.get("expected_roles"), limit=8)
                        ],
                    )
                )
                if len(cleaned) >= limit:
                    break
            return cleaned

        return QueryRetrievalPlan(
            interpreted_need=re.sub(r"\s+", " ", str(payload.get("interpreted_need", ""))).strip(),
            query_type=re.sub(r"\s+", " ", str(payload.get("query_type", ""))).strip(),
            source_supported_terms=string_list(payload.get("source_supported_terms")),
            possible_missing_prerequisites=string_list(payload.get("possible_missing_prerequisites")),
            search_forms=string_list(payload.get("search_forms"), limit=self.query_planner_max_search_forms),
            uncertainties=string_list(payload.get("uncertainties")),
            sub_needs=sub_need_list(payload.get("sub_needs")),
        )

    def _assemble_cluster_for_core(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        prompt: str,
        prompt_embedding: np.ndarray,
        proposition_embeddings: np.ndarray,
        proposition_similarities: np.ndarray,
        language_scores: np.ndarray,
        graph: dict[int, dict[int, "_ConsensusEdge"]],
        relation_geometry: "_DocumentRelationGeometry | None",
        core_candidate: _CoreCandidate,
        package_index: int,
    ) -> QueryAssembledPackage:
        core_index = core_candidate.element_index
        core_prop_index = core_candidate.proposition_index
        if core_prop_index is None:
            return self._assemble_for_core(
                signals=signals,
                prompt_embedding=prompt_embedding,
                core_candidate=core_candidate,
                package_index=package_index,
            )

        role_by_id: dict[str, str] = {}
        decisions: list[QueryAssemblyDecision] = []
        prompt_wants_support = self._prompt_wants_support(prompt)
        candidates = self._cluster_candidate_indices(graph, core_prop_index)
        candidate_scores = [
            (
                self._cluster_candidate_score(
                    signals=signals,
                    proposition=propositions[prop_index],
                    core_prop_index=core_prop_index,
                    prop_index=prop_index,
                    prompt_similarity=float(proposition_similarities[prop_index]),
                    core_similarity=float(np.dot(proposition_embeddings[prop_index], proposition_embeddings[core_prop_index])),
                    language_score=float(language_scores[prop_index]) if len(language_scores) else 0.0,
                    edge=graph.get(core_prop_index, {}).get(prop_index),
                    prompt_wants_support=prompt_wants_support,
                    relation_geometry=relation_geometry,
                ),
                prop_index,
            )
            for prop_index in candidates
            if prop_index != core_prop_index
        ]

        accepted_prop_indices: list[int] = []
        score_by_element_index: dict[int, float] = {}
        for anchor_prop_index in (core_candidate.anchor_prop_indices or (core_prop_index,)):
            if anchor_prop_index is None or anchor_prop_index < 0 or anchor_prop_index >= len(propositions):
                continue
            anchor_signal = signals[propositions[anchor_prop_index].element_index]
            if anchor_signal.element_index in score_by_element_index:
                continue
            accepted_prop_indices.append(anchor_prop_index)
            score_by_element_index[anchor_signal.element_index] = 1.0 if anchor_prop_index == core_prop_index else 0.94
        if core_prop_index not in accepted_prop_indices:
            accepted_prop_indices.insert(0, core_prop_index)
            score_by_element_index[core_index] = 1.0
        for candidate_score, prop_index in sorted(candidate_scores, reverse=True):
            proposition = propositions[prop_index]
            signal = signals[proposition.element_index]
            if signal.element_index in score_by_element_index:
                continue
            if candidate_score < self.min_candidate_score:
                decisions.append(
                    self._decision(
                        signal,
                        direction="cluster",
                        action="skipped",
                        query_similarity=float(proposition_similarities[prop_index]),
                        core_similarity=float(np.dot(proposition_embeddings[prop_index], proposition_embeddings[core_prop_index])),
                        previous_query_similarity=0.0,
                        previous_core_similarity=0.0,
                        reason=f"cluster candidate below score threshold: {candidate_score:.3f}",
                    )
                )
                continue
            accepted_prop_indices.append(prop_index)
            score_by_element_index[signal.element_index] = max(
                float(candidate_score),
                score_by_element_index.get(signal.element_index, 0.0),
            )

        selected, span_decisions = self._materialize_ordered_cluster_spans(
            signals=signals,
            propositions=propositions,
            accepted_prop_indices=accepted_prop_indices,
            score_by_element_index=score_by_element_index,
            prompt=prompt,
            prompt_embedding=prompt_embedding,
            proposition_embeddings=proposition_embeddings,
            proposition_similarities=proposition_similarities,
            core_prop_index=core_prop_index,
        )
        decisions.extend(span_decisions)
        for signal in selected:
            if signal.element_id != signals[core_index].element_id:
                role_by_id[signal.element_id] = "Cluster"

        selected, support_decisions = self._attach_explicit_support(
            signals=signals,
            selected=selected,
            core_candidate=core_candidate,
        )
        decisions.extend(support_decisions)
        for support_id in core_candidate.support_element_ids:
            if support_id != signals[core_index].element_id:
                role_by_id[support_id] = "Support"

        before_completion_ids = {signal.element_id for signal in selected}
        selected, completion_decisions, completion_diagnostics = self._complete_package_roles(
            signals=signals,
            selected=selected,
            propositions=propositions,
            prompt=prompt,
            prompt_embedding=prompt_embedding,
            core_index=core_index,
        )
        decisions.extend(completion_decisions)
        for signal in selected:
            if signal.element_id != signals[core_index].element_id and signal.element_id not in before_completion_ids:
                role_by_id[signal.element_id] = "Completion"

        final_core_signal, final_core_embedding = self._select_final_core(
            selected,
            seed_core_element_id=signals[core_index].element_id,
            propositions=propositions,
        )
        if final_core_signal.element_id != signals[core_index].element_id:
            role_by_id.setdefault(signals[core_index].element_id, "Cluster")
        package_text = self._package_text(
            selected,
            core_element_id=final_core_signal.element_id,
            role_by_id=role_by_id,
        )
        package_embedding = self._embed([package_text])[0]
        package_prompt_similarity = float(np.dot(package_embedding, prompt_embedding))
        package_core_similarity = float(np.dot(package_embedding, final_core_embedding))
        final_core_prompt_similarity = float(np.dot(final_core_embedding, prompt_embedding))
        final_token_count = sum(signal.token_count for signal in selected)
        score = self._package_score(
            package_prompt_similarity=package_prompt_similarity,
            package_core_similarity=package_core_similarity,
            core_prompt_similarity=final_core_prompt_similarity,
            token_count=final_token_count,
        )
        score += self._answerability_bonus(
            signals=selected,
            core_element_id=final_core_signal.element_id,
            proposition_text=core_candidate.proposition_text,
        )
        if len(language_scores):
            score += min(0.08, float(language_scores[core_prop_index]) * 0.08)
        score += min(0.08, 0.015 * sum(1 for decision in decisions if decision.action == "attached"))
        return QueryAssembledPackage(
            package_id=f"query-cluster-package-{package_index:05d}",
            core_element_id=final_core_signal.element_id,
            core_index=final_core_signal.element_index,
            seed_core_element_id=signals[core_index].element_id,
            core_prompt_similarity=round(final_core_prompt_similarity, 4),
            package_prompt_similarity=round(package_prompt_similarity, 4),
            package_core_similarity=round(package_core_similarity, 4),
            element_ids=[signal.element_id for signal in selected],
            package_text=package_text,
            token_count=final_token_count,
            score=round(score, 4),
            decisions=decisions,
            completion_diagnostics=completion_diagnostics,
        )

    def _materialize_ordered_cluster_spans(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        accepted_prop_indices: list[int],
        score_by_element_index: Mapping[int, float],
        prompt: str,
        prompt_embedding: np.ndarray,
        proposition_embeddings: np.ndarray,
        proposition_similarities: np.ndarray,
        core_prop_index: int,
    ) -> tuple[list[ElementSignalRecord], list[QueryAssemblyDecision]]:
        prompt_tokens = _content_tokens(prompt)
        core_element_index = propositions[core_prop_index].element_index
        anchor_indices = sorted({propositions[prop_index].element_index for prop_index in accepted_prop_indices})
        spans = self._split_anchor_indices_into_spans(anchor_indices)
        expanded_spans: list[_OrderedSpan] = []
        decisions: list[QueryAssemblyDecision] = []
        for span in spans:
            if self.use_span_competition:
                expanded_span, expansion_decision = self._select_best_ordered_span_candidate(
                    signals=signals,
                    span=span,
                    prompt=prompt,
                    prompt_embedding=prompt_embedding,
                    core_element_index=core_element_index,
                )
            else:
                expanded_span = self._expand_span_for_readability(
                    signals=signals,
                    span=span,
                    core_element_index=core_element_index,
                )
                expansion_decision = None
            expanded_spans.append(expanded_span)
            if expansion_decision is not None:
                decisions.append(expansion_decision)

        primary_span = next((span for span in expanded_spans if span.start <= core_element_index <= span.end), None)
        if primary_span is None:
            primary_span = _OrderedSpan(
                start=core_element_index,
                end=core_element_index,
                anchor_indices=(core_element_index,),
                element_indices=(core_element_index,),
                expansion_score=0.0,
            )

        span_scores = [
            (
                self._span_attach_score(
                    signals=signals,
                    span=span,
                    primary_span=primary_span,
                    prompt_tokens=prompt_tokens,
                    score_by_element_index=score_by_element_index,
                    prompt_wants_support=self._prompt_wants_support(prompt),
                ),
                span,
            )
            for span in expanded_spans
            if span != primary_span
        ]

        kept_spans = [primary_span]
        attached_count = 0
        token_count = self._span_token_count(signals, primary_span)
        for span_score, span in sorted(span_scores, key=lambda item: item[0], reverse=True):
            representative = self._span_representative_signal(signals, span, score_by_element_index)
            if span_score < self.min_span_attach_score:
                decisions.append(
                    self._decision(
                        representative,
                        direction="span",
                        action="detached",
                        query_similarity=0.0,
                        core_similarity=0.0,
                        previous_query_similarity=0.0,
                        previous_core_similarity=0.0,
                        reason=f"ordered span attach score below threshold: {span_score:.3f}",
                    )
                )
                continue
            if attached_count >= self.max_attached_spans:
                decisions.append(
                    self._decision(
                        representative,
                        direction="span",
                        action="detached",
                        query_similarity=0.0,
                        core_similarity=0.0,
                        previous_query_similarity=0.0,
                        previous_core_similarity=0.0,
                        reason="ordered span attachment limit reached",
                    )
                )
                continue
            span_tokens = self._span_token_count(signals, span)
            if token_count + span_tokens > self.max_package_tokens:
                decisions.append(
                    self._decision(
                        representative,
                        direction="span",
                        action="detached",
                        query_similarity=0.0,
                        core_similarity=0.0,
                        previous_query_similarity=0.0,
                        previous_core_similarity=0.0,
                        reason="ordered span exceeded token budget",
                    )
                )
                continue
            kept_spans.append(span)
            token_count += span_tokens
            attached_count += 1
            decisions.append(
                self._decision(
                    representative,
                    direction="span",
                    action="attached",
                    query_similarity=0.0,
                    core_similarity=0.0,
                    previous_query_similarity=0.0,
                    previous_core_similarity=0.0,
                    reason=f"attached ordered span score={span_score:.3f}",
                )
            )

        selected_by_index: dict[int, ElementSignalRecord] = {}
        for span in kept_spans:
            for index in span.element_indices:
                selected_by_index[index] = signals[index]
        selected = [selected_by_index[index] for index in sorted(selected_by_index)]
        for index in anchor_indices:
            if index in selected_by_index and index != core_element_index:
                signal = signals[index]
                prop_index = next(
                    (prop_index for prop_index in accepted_prop_indices if propositions[prop_index].element_index == index),
                    None,
                )
                decisions.append(
                    self._decision(
                        signal,
                        direction="cluster",
                        action="attached",
                        query_similarity=float(proposition_similarities[prop_index]) if prop_index is not None else 0.0,
                        core_similarity=float(np.dot(proposition_embeddings[prop_index], proposition_embeddings[core_prop_index]))
                        if prop_index is not None
                        else 0.0,
                        previous_query_similarity=0.0,
                        previous_core_similarity=0.0,
                        reason="cluster anchor kept inside ordered span",
                    )
                )
        return selected, decisions

    def _complete_package_roles(
        self,
        *,
        signals: list[ElementSignalRecord],
        selected: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition] | None = None,
        prompt: str,
        prompt_embedding: np.ndarray,
        core_index: int,
    ) -> tuple[list[ElementSignalRecord], list[QueryAssemblyDecision], CompletionDiagnostics]:
        if (
            not self.use_role_completion
            or self.role_completion_max_attachments <= 0
            or self.role_completion_max_extra_tokens <= 0
            or not selected
        ):
            reason = "disabled"
            if not selected:
                reason = "no selected elements"
            elif not self.use_role_completion:
                reason = "role completion disabled"
            elif self.role_completion_max_attachments <= 0:
                reason = "role completion attachment limit is zero"
            elif self.role_completion_max_extra_tokens <= 0:
                reason = "role completion token budget is zero"
            return selected, [], CompletionDiagnostics(enabled=False, disabled_reason=reason)

        selected_by_index = {signal.element_index: signal for signal in selected}
        decisions: list[QueryAssemblyDecision] = []
        rounds: list[CompletionRoundTrace] = []
        extra_tokens = 0
        prompt_tokens = set(_completion_tokens(prompt))
        roles_by_element = self._roles_by_element(propositions or [])
        completion_needed_initial = False

        for round_index in range(2):
            selected_indices = sorted(selected_by_index)
            selected_signals = [signals[index] for index in selected_indices]
            package_text = " ".join(signal.text for signal in selected_signals)
            completion_needed = self._package_needs_role_completion(prompt=prompt, package_text=package_text)
            if round_index == 0:
                completion_needed_initial = completion_needed
            if not completion_needed:
                break

            missing_terms = self._missing_completion_terms(selected_signals, prompt_tokens)
            candidates = self._role_completion_candidates(
                signals=signals,
                selected_indices=selected_indices,
                prompt_tokens=prompt_tokens,
                missing_terms=missing_terms,
                core_index=core_index,
                roles_by_element=roles_by_element,
            )
            attached_this_round = False
            ledger = self._completion_need_ledger(
                signals=signals,
                selected_indices=selected_indices,
                prompt=prompt,
                prompt_tokens=prompt_tokens,
                missing_terms=missing_terms,
                roles_by_element=roles_by_element,
            )
            round_trace = CompletionRoundTrace(
                round_number=round_index + 1,
                selected_before=[signals[index].element_id for index in selected_indices],
                needed_before=sorted(ledger.needed_keys),
                filled_before=sorted(ledger.filled_keys),
                open_before=sorted(ledger.open_keys),
            )
            for candidate in candidates:
                new_indices = [index for index in candidate.element_indices if index not in selected_by_index]
                if not new_indices:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=set(),
                            action="rejected",
                            rejection_reason="already_selected",
                        )
                    )
                    continue
                if candidate.score < 0.42:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=set(),
                            action="rejected",
                            rejection_reason="below_score_threshold",
                        )
                    )
                    break
                useful_keys = self._completion_candidate_open_keys(candidate.role_keys, ledger.open_keys)
                if not useful_keys:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=set(),
                            action="rejected",
                            rejection_reason="fills_no_open_need",
                        )
                    )
                    continue
                if len(selected_by_index) - len(selected) + len(new_indices) > self.role_completion_max_attachments:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=useful_keys,
                            action="rejected",
                            rejection_reason="too_many_attachments",
                        )
                    )
                    break
                token_cost = sum(signals[index].token_count for index in new_indices)
                if extra_tokens + token_cost > self.role_completion_max_extra_tokens:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=useful_keys,
                            action="rejected",
                            rejection_reason="token_budget_exceeded",
                        )
                    )
                    continue
                measured_candidate = self._measure_role_completion_candidate(
                    signals=signals,
                    candidate=candidate,
                    prompt=prompt,
                    prompt_embedding=prompt_embedding,
                )
                if measured_candidate is None or measured_candidate.score < 0.42:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=useful_keys,
                            action="rejected",
                            rejection_reason="failed_embedding_or_span_gate",
                        )
                    )
                    continue
                candidate = measured_candidate
                original_indices = list(candidate.element_indices)
                candidate = self._trim_role_completion_candidate_to_ledger(
                    signals=signals,
                    candidate=candidate,
                    selected_indices=selected_indices,
                    prompt_tokens=prompt_tokens,
                    missing_terms=missing_terms,
                    core_index=core_index,
                    roles_by_element=roles_by_element,
                    open_keys=ledger.open_keys,
                )
                if not candidate.element_indices:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=measured_candidate,
                            useful_keys=useful_keys,
                            action="rejected",
                            rejection_reason="trimmed_to_no_useful_elements",
                            original_indices=original_indices,
                            trimmed_indices=[],
                        )
                    )
                    continue
                new_indices = [index for index in candidate.element_indices if index not in selected_by_index]
                if not new_indices:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=set(),
                            action="rejected",
                            rejection_reason="already_selected_after_trim",
                            original_indices=original_indices,
                            trimmed_indices=list(candidate.element_indices),
                        )
                    )
                    continue
                useful_keys = self._completion_candidate_open_keys(candidate.role_keys, ledger.open_keys)
                if not useful_keys:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=set(),
                            action="rejected",
                            rejection_reason="fills_no_open_need_after_trim",
                            original_indices=original_indices,
                            trimmed_indices=list(candidate.element_indices),
                        )
                    )
                    continue
                if len(selected_by_index) - len(selected) + len(new_indices) > self.role_completion_max_attachments:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=useful_keys,
                            action="rejected",
                            rejection_reason="too_many_attachments_after_trim",
                            original_indices=original_indices,
                            trimmed_indices=list(candidate.element_indices),
                        )
                    )
                    break
                token_cost = sum(signals[index].token_count for index in new_indices)
                if extra_tokens + token_cost > self.role_completion_max_extra_tokens:
                    round_trace.candidates.append(
                        self._completion_candidate_trace(
                            signals=signals,
                            candidate=candidate,
                            useful_keys=useful_keys,
                            action="rejected",
                            rejection_reason="token_budget_exceeded_after_trim",
                            original_indices=original_indices,
                            trimmed_indices=list(candidate.element_indices),
                        )
                    )
                    continue
                for index in new_indices:
                    selected_by_index[index] = signals[index]
                extra_tokens += token_cost
                ledger.fill(useful_keys)
                attached_this_round = True
                round_trace.attached_element_ids.extend(signals[index].element_id for index in new_indices)
                round_trace.candidates.append(
                    self._completion_candidate_trace(
                        signals=signals,
                        candidate=candidate,
                        useful_keys=useful_keys,
                        action="attached",
                        original_indices=original_indices,
                        trimmed_indices=list(candidate.element_indices),
                    )
                )
                for index in new_indices:
                    decisions.append(
                        self._decision(
                            signals[index],
                            direction="completion",
                            action="attached",
                            query_similarity=candidate.score,
                            core_similarity=0.0,
                            previous_query_similarity=0.0,
                            previous_core_similarity=0.0,
                            reason=candidate.reason,
                        )
                    )
            final_indices = sorted(selected_by_index)
            round_trace.selected_after = [signals[index].element_id for index in final_indices]
            round_trace.needed_after = sorted(ledger.needed_keys)
            round_trace.filled_after = sorted(ledger.filled_keys)
            round_trace.open_after = sorted(ledger.open_keys)
            rounds.append(round_trace)
            if not attached_this_round:
                break

        completed = [selected_by_index[index] for index in sorted(selected_by_index)]
        diagnostics = CompletionDiagnostics(
            enabled=True,
            completion_needed_initial=completion_needed_initial,
            rounds=rounds,
        )
        return completed, decisions, diagnostics

    def _package_needs_role_completion(self, *, prompt: str, package_text: str) -> bool:
        if _prompt_asks_why(prompt):
            return True
        return bool(
            re.search(
                r"\b(proof|claim|therefore|thus|hence|because|contradict\w*|assum\w*|"
                r"at\s+least|at\s+most|within|separat\w*|denote\w*)\b",
                package_text,
                re.IGNORECASE,
            )
        )

    def _missing_completion_terms(
        self,
        selected: list[ElementSignalRecord],
        prompt_tokens: set[str],
    ) -> set[str]:
        package_text = " ".join(signal.text for signal in selected)
        package_tokens = set(_completion_tokens(package_text))
        candidate_terms = {
            token
            for token in package_tokens | prompt_tokens
            if len(token) >= 2
            and token not in STOPWORDS
            and token not in COMPLETION_NOISE_TERMS
            and token
            not in {
                "proof",
                "claim",
                "therefore",
                "because",
                "distance",
                "point",
                "points",
                "pair",
                "pairs",
                "algorithm",
            }
        }
        for signal in selected:
            candidate_terms.update(_completion_tokens(" ".join(signal.formula_symbols)))
        missing = {
            term
            for term in candidate_terms
            if self._term_looks_definition_worthy(term)
            and not self._package_defines_term(package_text, term)
        }
        proof_terms = package_tokens & {"assumption", "contradicts", "contradict", "therefore", "rows", "boxes", "omega", "sy", "z"}
        return set(list(missing)[:14]) | proof_terms

    def _role_completion_candidates(
        self,
        *,
        signals: list[ElementSignalRecord],
        selected_indices: list[int],
        prompt_tokens: set[str],
        missing_terms: set[str],
        core_index: int,
        roles_by_element: Mapping[int, list[PropositionRoleHypothesis]],
    ) -> list[_RoleCompletionCandidate]:
        if not selected_indices:
            return []
        start = min(selected_indices)
        end = max(selected_indices)
        selected_window = set(range(max(0, start - self.role_completion_search_radius), min(len(signals), end + self.role_completion_search_radius + 1)))
        selected_window.update(
            index
            for index, signal in enumerate(signals)
            if signal.page_number in {signals[item].page_number for item in selected_indices}
        )

        scored: list[tuple[int, float, list[str], set[str]]] = []
        for index in sorted(selected_window):
            if index in selected_indices:
                continue
            signal = signals[index]
            if not signal.text.strip() or signal.boilerplate_score > 0.8:
                continue
            score, reasons, role_keys = self._role_completion_candidate_score(
                signals=signals,
                signal=signal,
                prompt_tokens=prompt_tokens,
                missing_terms=missing_terms,
                selected_indices=selected_indices,
                selected_start=start,
                selected_end=end,
                core_index=core_index,
                roles=roles_by_element.get(signal.element_index, []),
            )
            if score <= 0.0:
                continue
            scored.append((index, score, reasons, role_keys))

        singles = [
            _RoleCompletionCandidate(
                element_indices=(index,),
                score=score,
                reason="; ".join(reasons),
                role_keys=frozenset(role_keys),
            )
            for index, score, reasons, role_keys in scored
        ]
        spans = self._collapse_role_completion_spans(
            signals=signals,
            scored=scored,
            selected_indices=selected_indices,
        )
        candidates = [*singles, *spans]
        deduped: dict[tuple[int, ...], _RoleCompletionCandidate] = {}
        for candidate in candidates:
            existing = deduped.get(candidate.element_indices)
            if existing is None or candidate.score > existing.score:
                deduped[candidate.element_indices] = candidate
        return sorted(
            deduped.values(),
            key=lambda item: (item.score, len(item.element_indices), -sum(signals[index].token_count for index in item.element_indices)),
            reverse=True,
        )

    def _completion_candidate_trace(
        self,
        *,
        signals: list[ElementSignalRecord],
        candidate: _RoleCompletionCandidate,
        useful_keys: Iterable[str],
        action: str,
        rejection_reason: str = "",
        original_indices: list[int] | None = None,
        trimmed_indices: list[int] | None = None,
    ) -> CompletionCandidateTrace:
        indices = list(candidate.element_indices)
        text = " ".join(signals[index].text for index in indices if 0 <= index < len(signals))
        preview = re.sub(r"\s+", " ", text).strip()
        if len(preview) > 220:
            preview = preview[:217].rstrip() + "..."
        return CompletionCandidateTrace(
            element_ids=[signals[index].element_id for index in indices if 0 <= index < len(signals)],
            element_indices=indices,
            score=round(float(candidate.score), 4),
            role_keys=sorted(candidate.role_keys),
            useful_open_keys=sorted(useful_keys),
            token_cost=sum(signals[index].token_count for index in indices if 0 <= index < len(signals)),
            action=action,
            reason=candidate.reason,
            rejection_reason=rejection_reason,
            original_element_indices=indices if original_indices is None else original_indices,
            trimmed_element_indices=indices if trimmed_indices is None else trimmed_indices,
            text_preview=preview,
        )

    def _trim_role_completion_candidate_to_ledger(
        self,
        *,
        signals: list[ElementSignalRecord],
        candidate: _RoleCompletionCandidate,
        selected_indices: list[int],
        prompt_tokens: set[str],
        missing_terms: set[str],
        core_index: int,
        roles_by_element: Mapping[int, list[PropositionRoleHypothesis]],
        open_keys: set[str],
    ) -> _RoleCompletionCandidate:
        if len(candidate.element_indices) <= 1:
            return candidate
        selected_start = min(selected_indices)
        selected_end = max(selected_indices)
        remaining_open = set(open_keys)
        kept: list[int] = []
        kept_scores: list[float] = []
        kept_reasons: list[str] = []
        kept_keys: set[str] = set()
        for index in candidate.element_indices:
            signal = signals[index]
            score, reasons, role_keys = self._role_completion_candidate_score(
                signals=signals,
                signal=signal,
                prompt_tokens=prompt_tokens,
                missing_terms=missing_terms,
                selected_indices=selected_indices,
                selected_start=selected_start,
                selected_end=selected_end,
                core_index=core_index,
                roles=roles_by_element.get(signal.element_index, []),
            )
            useful_keys = self._completion_candidate_open_keys(role_keys, remaining_open)
            if not useful_keys:
                continue
            kept.append(index)
            kept_scores.append(score)
            kept_reasons.extend(reasons)
            kept_keys.update(useful_keys)
            remaining_open -= _expanded_completion_fill_keys(useful_keys)

        if not kept:
            return _RoleCompletionCandidate((), 0.0, "", candidate.role_keys)
        if tuple(kept) == candidate.element_indices:
            return candidate
        unique_reasons = list(dict.fromkeys(reason for reason in kept_reasons if reason))
        score = min(candidate.score, max(kept_scores) + 0.04 * max(0, len(kept) - 1))
        return _RoleCompletionCandidate(
            element_indices=tuple(kept),
            score=max(0.0, score),
            reason="ledger-trimmed role span: " + "; ".join(unique_reasons[:5]),
            role_keys=frozenset(kept_keys),
        )

    def _measure_role_completion_candidate(
        self,
        *,
        signals: list[ElementSignalRecord],
        candidate: _RoleCompletionCandidate,
        prompt: str,
        prompt_embedding: np.ndarray,
    ) -> _RoleCompletionCandidate | None:
        if len(candidate.element_indices) <= 1:
            return candidate
        prompt_tokens = set(_completion_tokens(prompt))
        trimmed = self._trim_role_completion_span(
            signals=signals,
            candidate=candidate,
            prompt_tokens=prompt_tokens,
        )
        if trimmed.score <= 0.0:
            return None
        return trimmed

    def _trim_role_completion_span(
        self,
        *,
        signals: list[ElementSignalRecord],
        candidate: _RoleCompletionCandidate,
        prompt_tokens: set[str],
    ) -> _RoleCompletionCandidate:
        indices = list(candidate.element_indices)
        if len(indices) <= 2:
            score = candidate.score + 0.04
            reason = candidate.reason + "; accepted by role-span expansion gate"
            return _RoleCompletionCandidate(candidate.element_indices, score, reason, candidate.role_keys)
        if self._role_span_looks_like_list_run(signals=signals, indices=tuple(indices)):
            score = candidate.score + 0.08
            reason = candidate.reason + "; accepted by role-span expansion gate as list/procedure run"
            return _RoleCompletionCandidate(candidate.element_indices, score, reason, candidate.role_keys)
        span_indices = tuple(indices)
        span_tokens = set().union(*(_completion_tokens(signals[index].text) for index in span_indices))
        prompt_overlap = _jaccard(span_tokens, prompt_tokens)
        key_coverage = self._role_span_key_coverage(signals=signals, indices=span_indices, role_keys=candidate.role_keys)
        cohesion = self._lexical_span_cohesion(signals=signals, indices=span_indices)
        token_count = sum(signals[index].token_count for index in span_indices)
        token_penalty = min(0.18, token_count / max(1, self.role_completion_max_extra_tokens) * 0.12)
        score = candidate.score * 0.78 + key_coverage * 0.22 + prompt_overlap * 0.14 + cohesion * 0.1 - token_penalty
        if score < 0.42:
            return _RoleCompletionCandidate((), 0.0, "", candidate.role_keys)
        reason = candidate.reason + f"; accepted by role-span expansion gate coverage={key_coverage:.2f} prompt={prompt_overlap:.2f} cohesion={cohesion:.2f}"
        return _RoleCompletionCandidate(span_indices, score, reason, candidate.role_keys)

    def _role_span_looks_like_list_run(self, *, signals: list[ElementSignalRecord], indices: tuple[int, ...]) -> bool:
        if len(indices) < 3:
            return False
        if any(right != left + 1 for left, right in zip(indices, indices[1:])):
            return False
        texts = [signals[index].text.strip() for index in indices]
        numbered = sum(1 for text in texts if re.match(r"^\s*\d+[\).\s]", text))
        if numbered >= 2:
            return True
        listish = sum(
            1
            for text in texts
            if re.search(r"\b(list|step|following|consisting|sorted|compute|return|call)\b", text, re.IGNORECASE)
        )
        return listish >= 2

    def _role_span_key_coverage(
        self,
        *,
        signals: list[ElementSignalRecord],
        indices: tuple[int, ...],
        role_keys: frozenset[str],
    ) -> float:
        if not role_keys:
            return 0.0
        text = " ".join(signals[index].text for index in indices)
        tokens = set(_completion_tokens(text))
        covered = 0
        for key in role_keys:
            if key.startswith(("term:", "definition:", "setup:")):
                term = key.split(":", 1)[1]
                if term in tokens:
                    covered += 1
            elif key.startswith("proof:"):
                if re.search(r"\b(proof|suppose|assum\w*|because|since|therefore|thus|hence|contradict\w*|at\s+least|at\s+most)\b", text, re.IGNORECASE):
                    covered += 1
            elif key == "support" and any(signals[index].element_type in SUPPORT_ELEMENT_TYPES for index in indices):
                covered += 1
            elif key in {"procedure", "example"}:
                covered += 1
        return covered / max(1, len(role_keys))

    def _lexical_span_cohesion(self, *, signals: list[ElementSignalRecord], indices: tuple[int, ...]) -> float:
        if len(indices) <= 1:
            return 0.58
        overlaps: list[float] = []
        for left, right in zip(indices, indices[1:]):
            left_tokens = set(_completion_tokens(signals[left].text))
            right_tokens = set(_completion_tokens(signals[right].text))
            overlaps.append(_jaccard(left_tokens, right_tokens))
        return sum(overlaps) / max(1, len(overlaps))

    def _role_completion_candidate_score(
        self,
        *,
        signals: list[ElementSignalRecord],
        signal: ElementSignalRecord,
        prompt_tokens: set[str],
        missing_terms: set[str],
        selected_indices: list[int],
        selected_start: int,
        selected_end: int,
        core_index: int,
        roles: list[PropositionRoleHypothesis],
    ) -> tuple[float, list[str], set[str]]:
        text = signal.text
        tokens = set(_completion_tokens(text))
        overlap = tokens & missing_terms
        prompt_overlap = tokens & prompt_tokens
        reasons: list[str] = []
        role_keys: set[str] = set()
        score = 0.0

        if overlap:
            score += min(0.38, 0.11 * len(overlap))
            reasons.append(f"covers missing terms: {', '.join(sorted(overlap)[:5])}")
            role_keys.update(f"term:{term}" for term in overlap)
        if prompt_overlap:
            score += min(0.12, 0.04 * len(prompt_overlap))
            reasons.append("overlaps prompt")

        role_score, role_reasons, hypothesis_role_keys = self._role_hypothesis_completion_score(
            roles=roles,
            tokens=tokens,
            prompt_tokens=prompt_tokens,
            missing_terms=missing_terms,
        )
        if role_score > 0.0:
            score += role_score
            reasons.extend(role_reasons)
            role_keys.update(hypothesis_role_keys)

        definition_terms = [term for term in overlap if self._text_defines_term(text, term)]
        if definition_terms:
            score += 0.34
            reasons.append(f"definition/setup candidate for: {', '.join(sorted(definition_terms)[:4])}")
            role_keys.update(f"definition:{term}" for term in definition_terms)

        if re.search(r"\b(let|denote\w*|defined\s+as|consists?\s+of|partition\w*|sorted\s+by|within)\b", text, re.IGNORECASE):
            if overlap or prompt_overlap:
                score += 0.16
                reasons.append("setup/definition language")
                role_keys.update(f"setup:{term}" for term in (overlap or prompt_overlap))

        if re.search(r"\b(claim|proof|suppose|assum\w*)\b", text, re.IGNORECASE):
            if signal.element_index <= selected_end:
                score += 0.16
                reasons.append("proof setup")
                role_keys.add("proof:setup")

        if re.search(r"\b(therefore|thus|hence|this means|contradict\w*)\b", text, re.IGNORECASE):
            if signal.element_index >= selected_start:
                score += 0.26
                reasons.append("proof conclusion")
                role_keys.add("proof:conclusion")
                role_keys.update(
                    f"answer:{term}"
                    for term in prompt_overlap
                    if len(term) >= 4 and term not in COMPLETION_NOISE_TERMS
                )

        if self._is_near_selected_proof_conclusion(
            signals=signals,
            candidate_index=signal.element_index,
            selected_indices=selected_indices,
        ) and re.search(
            r"\b(since|as|because|suppose|if|separat\w*|rows?|boxes?|distance|at\s+least|at\s+most)\b",
            text,
            re.IGNORECASE,
        ):
            score += 0.34
            if re.search(r"\b(rows?|boxes?|separat\w*)\b", text, re.IGNORECASE):
                score += 0.28
            reasons.append("proof-chain backfill")
            role_keys.add("proof:reason")

        if signal.is_heading and signal.element_index <= selected_start and abs(signal.element_index - selected_start) <= 3:
            score += 0.12
            reasons.append("nearby heading/proof label")

        distance = min(abs(signal.element_index - selected_start), abs(signal.element_index - selected_end), abs(signal.element_index - core_index))
        if distance <= 2:
            score += 0.1
            reasons.append("near selected span")
        elif distance <= 8:
            score += 0.06
        elif distance > self.role_completion_search_radius:
            score -= 0.2

        if signal.element_type in SUPPORT_ELEMENT_TYPES and not (prompt_overlap or overlap):
            score -= 0.12
        if signal.word_count <= 2 and not signal.is_heading:
            score -= 0.12

        if not role_keys:
            role_keys.add(f"element:{signal.element_index}")

        return max(0.0, score), reasons, role_keys

    def _roles_by_element(
        self,
        propositions: list[QueryEvidenceProposition],
    ) -> dict[int, list[PropositionRoleHypothesis]]:
        roles_by_element: dict[int, list[PropositionRoleHypothesis]] = defaultdict(list)
        seen: set[tuple[int, str, str, str]] = set()
        for proposition in propositions:
            for raw_role in proposition.roles:
                role = self._coerce_role_hypothesis(raw_role)
                if role is None:
                    continue
                key = (proposition.element_index, role.role, role.target.lower(), role.value.lower())
                if key in seen:
                    continue
                seen.add(key)
                roles_by_element[proposition.element_index].append(role)
        return roles_by_element

    def _coerce_role_hypothesis(self, role: Any) -> PropositionRoleHypothesis | None:
        if isinstance(role, PropositionRoleHypothesis):
            return role
        if not isinstance(role, Mapping):
            return None
        cleaned = self._clean_role_hypotheses([role])
        return cleaned[0] if cleaned else None

    def _role_hypothesis_completion_score(
        self,
        *,
        roles: list[PropositionRoleHypothesis],
        tokens: set[str],
        prompt_tokens: set[str],
        missing_terms: set[str],
    ) -> tuple[float, list[str], set[str]]:
        score = 0.0
        reasons: list[str] = []
        role_keys: set[str] = set()
        role_groups = {
            "definition": {"definition"},
            "setup": {"assumption", "condition", "proof_setup", "claim"},
            "reason": {"proof_reason", "quantity_bound", "contradiction"},
            "conclusion": {"proof_conclusion"},
            "support": {"visual_support", "table_support", "formula_support"},
            "procedure": {"procedure_step"},
            "example": {"example"},
        }
        for role in roles:
            role_name = role.role.strip().lower()
            role_tokens = set(_completion_tokens(" ".join([role.target, role.value, role.reason])))
            role_overlap = role_tokens & missing_terms
            prompt_overlap = role_tokens & prompt_tokens
            text_overlap = tokens & missing_terms
            confidence = max(0.25, min(1.0, role.confidence or 0.6))

            if role_name in role_groups["definition"] and (role_overlap or text_overlap):
                score += 0.42 * confidence
                target = role.target or ", ".join(sorted(role_overlap or text_overlap)[:3])
                reasons.append(f"role definition fills: {target}")
                role_keys.update(f"definition:{term}" for term in (role_overlap or text_overlap or set(_completion_tokens(target))) if term)
            elif role_name in role_groups["reason"] and (role_overlap or prompt_overlap or text_overlap):
                score += 0.3 * confidence
                reasons.append(f"role {role_name} supports proof/reasoning")
                role_keys.add("proof:reason")
            elif role_name in role_groups["conclusion"] and (role_overlap or prompt_overlap or text_overlap):
                score += 0.26 * confidence
                reasons.append("role proof_conclusion")
                role_keys.add("proof:conclusion")
            elif role_name in role_groups["setup"] and (role_overlap or prompt_overlap or text_overlap):
                score += 0.22 * confidence
                reasons.append(f"role {role_name} supplies setup")
                role_keys.add("proof:setup")
            elif role_name in role_groups["support"] and (prompt_overlap or role_overlap):
                score += 0.2 * confidence
                reasons.append(f"role {role_name} supplies support")
                role_keys.add("support")
            elif role_name in role_groups["procedure"] and (prompt_overlap or role_overlap):
                score += 0.16 * confidence
                reasons.append("role procedure_step")
                role_keys.add("procedure")
            elif role_name in role_groups["example"] and prompt_overlap:
                score += 0.12 * confidence
                reasons.append("role example")
                role_keys.add("example")

        return min(score, 0.7), reasons[:4], role_keys

    def _selected_completion_role_keys(
        self,
        *,
        signals: list[ElementSignalRecord],
        selected_indices: list[int],
        missing_terms: set[str],
        roles_by_element: Mapping[int, list[PropositionRoleHypothesis]],
    ) -> set[str]:
        keys: set[str] = set()
        for index in selected_indices:
            signal = signals[index]
            text = signal.text
            tokens = set(_completion_tokens(signal.text))
            for term in tokens & missing_terms:
                keys.add(f"term:{term}")
                if self._text_defines_term(signal.text, term):
                    keys.add(f"definition:{term}")
            if re.search(r"\b(claim|proof|suppose|assum\w*|condition)\b", text, re.IGNORECASE):
                keys.add("proof:setup")
            if re.search(
                r"\b(since|as|because|therefore|thus|hence|contradict\w*|at\s+least|at\s+most|bounded|within)\b",
                text,
                re.IGNORECASE,
            ):
                keys.add("proof:reason")
            if re.search(r"\b(therefore|thus|hence|this means|contradict\w*)\b", text, re.IGNORECASE):
                keys.add("proof:conclusion")
            if signal.element_type in SUPPORT_ELEMENT_TYPES:
                keys.add("support")
            for role in roles_by_element.get(index, []):
                role_name = role.role.strip().lower()
                role_terms = set(_completion_tokens(" ".join([role.target, role.value])))
                if role_name == "definition":
                    for term in role_terms & missing_terms:
                        keys.add(f"definition:{term}")
                elif role_name in {"assumption", "condition", "proof_setup", "claim"}:
                    keys.add("proof:setup")
                elif role_name in {"proof_reason", "quantity_bound", "contradiction"}:
                    keys.add("proof:reason")
                elif role_name == "proof_conclusion":
                    keys.add("proof:conclusion")
                elif role_name in {"visual_support", "table_support", "formula_support"}:
                    keys.add("support")
        return keys

    def _completion_need_ledger(
        self,
        *,
        signals: list[ElementSignalRecord],
        selected_indices: list[int],
        prompt: str,
        prompt_tokens: set[str],
        missing_terms: set[str],
        roles_by_element: Mapping[int, list[PropositionRoleHypothesis]],
    ) -> _CompletionNeedLedger:
        selected_text = " ".join(signals[index].text for index in selected_indices)
        selected_tokens = set(_completion_tokens(selected_text))
        missing_prompt_terms = {
            term
            for term in prompt_tokens - selected_tokens
            if len(term) >= 4
            and term not in STOPWORDS
            and term not in COMPLETION_NOISE_TERMS
        }
        needed: set[str] = {f"term:{term}" for term in missing_terms}
        for term in missing_terms:
            if self._term_looks_definition_worthy(term) and not self._package_defines_term(selected_text, term):
                needed.add(f"definition:{term}")

        proofish_prompt = _prompt_asks_why(prompt)
        proofish_package = bool(
            re.search(
                r"\b(proof|claim|suppose|assum\w*|therefore|thus|hence|because|contradict\w*|"
                r"at\s+least|at\s+most|bounded|within|separat\w*)\b",
                selected_text,
                re.IGNORECASE,
            )
        )
        if proofish_prompt or proofish_package:
            needed.add("proof:reason")
            if proofish_prompt or re.search(r"\b(therefore|thus|hence|contradict\w*)\b", selected_text, re.IGNORECASE):
                needed.add("proof:setup")
            if proofish_prompt and proofish_package:
                needed.add("proof:conclusion")
                needed.update(f"answer:{term}" for term in missing_prompt_terms)

        if self._prompt_wants_support(prompt):
            needed.add("support")
        if {"step", "procedure", "process"} & prompt_tokens:
            needed.add("procedure")
        if {"example", "examples"} & prompt_tokens:
            needed.add("example")

        filled = self._selected_completion_role_keys(
            signals=signals,
            selected_indices=selected_indices,
            missing_terms=missing_terms,
            roles_by_element=roles_by_element,
        )
        return _CompletionNeedLedger(
            needed_keys=_expanded_completion_fill_keys(needed),
            filled_keys=_expanded_completion_fill_keys(filled),
        )

    def _completion_candidate_open_keys(self, candidate_keys: Iterable[str], open_keys: set[str]) -> set[str]:
        meaningful = _meaningful_completion_keys(candidate_keys)
        if not meaningful:
            return set()
        concrete = {
            key
            for key in meaningful
            if key.startswith(("term:", "definition:", "setup:", "answer:")) or key in {"support", "procedure", "example"}
        }
        proof_only = meaningful <= {"proof:setup", "proof:reason", "proof:conclusion"}
        if proof_only and not concrete:
            return set()
        expanded = _expanded_completion_fill_keys(meaningful)
        useful = expanded & open_keys
        if useful:
            return meaningful
        return set()

    def _collapse_role_completion_spans(
        self,
        *,
        signals: list[ElementSignalRecord],
        scored: list[tuple[int, float, list[str], set[str]]],
        selected_indices: list[int],
    ) -> list[_RoleCompletionCandidate]:
        if len(scored) < 2:
            return []
        selected_set = set(selected_indices)
        by_index = {index: (score, reasons, role_keys) for index, score, reasons, role_keys in scored}
        spans: list[_RoleCompletionCandidate] = []
        ordered = sorted(by_index)
        current = [ordered[0]]
        for index in ordered[1:]:
            previous = current[-1]
            if index == previous + 1 and not any(item in selected_set for item in range(previous + 1, index)):
                prev_keys = by_index[previous][2]
                next_keys = by_index[index][2]
                if self._completion_role_keys_are_compatible(prev_keys, next_keys):
                    current.append(index)
                    continue
            if len(current) > 1:
                spans.append(self._role_completion_span_from_indices(signals=signals, indices=current, by_index=by_index))
            current = [index]
        if len(current) > 1:
            spans.append(self._role_completion_span_from_indices(signals=signals, indices=current, by_index=by_index))
        return spans

    def _completion_role_keys_are_compatible(self, left: set[str], right: set[str]) -> bool:
        if left & right:
            proof_prefixes = {"proof:setup", "proof:reason", "proof:conclusion"}
            shared = _meaningful_completion_keys(left & right)
            if shared and not ((left | right) & proof_prefixes):
                shared_targets = {
                    key.split(":", 1)[1]
                    for key in shared
                    if key.startswith(("term:", "definition:", "setup:"))
                }
                left_targets = {
                    key.split(":", 1)[1]
                    for key in left
                    if key.startswith(("term:", "definition:", "setup:"))
                }
                right_targets = {
                    key.split(":", 1)[1]
                    for key in right
                    if key.startswith(("term:", "definition:", "setup:"))
                }
                if shared_targets and left_targets == shared_targets and right_targets == shared_targets:
                    return False
            return True
        proof_prefixes = {"proof:setup", "proof:reason", "proof:conclusion"}
        if left & proof_prefixes and right & proof_prefixes:
            return True
        if any(key.startswith("definition:") or key.startswith("setup:") for key in left) and right & proof_prefixes:
            return True
        if any(key.startswith("definition:") or key.startswith("setup:") for key in right) and left & proof_prefixes:
            return True
        if any(key.startswith("term:") for key in left) and any(key.startswith("term:") for key in right):
            return True
        return False

    def _role_completion_span_from_indices(
        self,
        *,
        signals: list[ElementSignalRecord],
        indices: list[int],
        by_index: Mapping[int, tuple[float, list[str], set[str]]],
    ) -> _RoleCompletionCandidate:
        scores = [by_index[index][0] for index in indices]
        role_keys = set().union(*(by_index[index][2] for index in indices))
        reasons = []
        for index in indices:
            reasons.extend(by_index[index][1])
        unique_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
        token_cost = sum(signals[index].token_count for index in indices)
        score = min(1.25, max(scores) + 0.08 * (len(indices) - 1) + 0.03 * len(role_keys))
        if token_cost > 120:
            score -= 0.04
        return _RoleCompletionCandidate(
            element_indices=tuple(indices),
            score=max(0.0, score),
            reason="role span attachment: " + "; ".join(unique_reasons[:5]),
            role_keys=frozenset(role_keys),
        )

    def _document_relation_geometry(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_embeddings: np.ndarray,
        graph: dict[int, dict[int, "_ConsensusEdge"]],
    ) -> "_DocumentRelationGeometry | None":
        if not self.use_relation_geometry or self.relation_geometry_weight <= 0.0 or len(propositions) < 2:
            return None
        seeds = self._document_relation_seed_pairs(signals=signals, propositions=propositions, graph=graph)
        if len(seeds) < self.min_relation_family_size:
            return _DocumentRelationGeometry.empty(
                proposition_embeddings=proposition_embeddings,
                relation_family_similarity=self.relation_family_similarity,
            )
        families = self._document_relation_families(
            seeds=seeds,
            proposition_embeddings=proposition_embeddings,
        )
        return _DocumentRelationGeometry(
            proposition_embeddings=proposition_embeddings,
            families=families,
            relation_family_similarity=self.relation_family_similarity,
        )

    def _document_relation_seed_pairs(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        graph: dict[int, dict[int, "_ConsensusEdge"]],
    ) -> list["_RelationSeed"]:
        prop_indices_by_element: dict[str, list[int]] = defaultdict(list)
        for proposition_index, proposition in enumerate(propositions):
            prop_indices_by_element[proposition.element_id].append(proposition_index)

        seeds: dict[tuple[int, int], set[str]] = {}

        def add(source: int, target: int, tag: str) -> None:
            if source == target:
                return
            if source < 0 or target < 0 or source >= len(propositions) or target >= len(propositions):
                return
            seeds.setdefault((source, target), set()).add(tag)

        for source, neighbors in graph.items():
            for target in neighbors:
                add(source, target, "consensus_graph")

        for indices in prop_indices_by_element.values():
            if len(indices) <= 1:
                continue
            for source in indices:
                for target in indices:
                    add(source, target, "same_element")

        by_element_index: dict[int, list[int]] = defaultdict(list)
        for proposition_index, proposition in enumerate(propositions):
            by_element_index[proposition.element_index].append(proposition_index)

        for left_index in range(max(0, len(signals) - 1)):
            right_index = left_index + 1
            left = signals[left_index]
            right = signals[right_index]
            if left.page_number != right.page_number:
                continue
            for source in by_element_index.get(left_index, []):
                for target in by_element_index.get(right_index, []):
                    add(source, target, "adjacent_forward")
                    add(target, source, "adjacent_backward")
                    if left.is_heading and not right.is_heading:
                        add(source, target, "heading_to_body")

        for source_index, source in enumerate(propositions):
            for support_id in source.support_element_ids:
                for target_index in prop_indices_by_element.get(support_id, []):
                    add(source_index, target_index, "explicit_support")
                    add(target_index, source_index, "support_to_text")

        for left_index, left in enumerate(signals):
            for right_index in range(left_index + 1, min(len(signals), left_index + 4)):
                right = signals[right_index]
                if not self._strong_list_sibling_pair(left, right):
                    continue
                for source in by_element_index.get(left_index, []):
                    for target in by_element_index.get(right_index, []):
                        add(source, target, "strong_list")
                        add(target, source, "strong_list")

        return [
            _RelationSeed(source_index=source, target_index=target, tags=tuple(sorted(tags)))
            for (source, target), tags in seeds.items()
        ]

    def _strong_list_sibling_pair(self, left: ElementSignalRecord, right: ElementSignalRecord) -> bool:
        if left.list_signal is None or right.list_signal is None:
            return False
        if left.list_signal.run_id is None or left.list_signal.run_id != right.list_signal.run_id:
            return False
        if left.list_signal.marker_type != right.list_signal.marker_type:
            return False
        if left.page_number != right.page_number:
            return False
        if abs(float(left.list_signal.indent) - float(right.list_signal.indent)) > 8.0:
            return False
        return abs(left.element_index - right.element_index) <= 3

    def _same_heading_neighborhood(self, left: ElementSignalRecord, right: ElementSignalRecord) -> bool:
        if left.page_number != right.page_number:
            return False
        left_headings = {heading.element_id for heading in left.heading_path if heading.element_id}
        right_headings = {heading.element_id for heading in right.heading_path if heading.element_id}
        if not left_headings and not right_headings:
            return abs(left.element_index - right.element_index) <= 4
        return bool(left_headings & right_headings)

    def _document_relation_families(
        self,
        *,
        seeds: list["_RelationSeed"],
        proposition_embeddings: np.ndarray,
    ) -> list["_RelationFamily"]:
        seed_vectors: list[tuple[_RelationSeed, np.ndarray]] = []
        for seed in seeds:
            direction = _relation_delta_direction(
                proposition_embeddings,
                source_index=seed.source_index,
                target_index=seed.target_index,
            )
            if direction is not None:
                seed_vectors.append((seed, direction))
        if len(seed_vectors) < self.min_relation_family_size:
            return []

        directions = np.asarray([direction for _seed, direction in seed_vectors], dtype=float)
        raw_families: list[tuple[int, float, np.ndarray, list[_RelationSeed]]] = []
        for _index, (_seed, direction) in enumerate(seed_vectors):
            similarities = directions @ direction
            neighbor_indices = [
                int(item)
                for item, similarity in enumerate(similarities)
                if similarity >= self.relation_family_similarity
            ]
            if len(neighbor_indices) < self.min_relation_family_size:
                continue
            family_directions = directions[neighbor_indices]
            centroid = _normalize(np.mean(family_directions, axis=0))[0]
            coherence = float(np.mean(family_directions @ centroid))
            family_seeds = [seed_vectors[item][0] for item in neighbor_indices]
            raw_families.append((len(family_seeds), coherence, centroid, family_seeds))

        families: list[_RelationFamily] = []
        for size, coherence, centroid, family_seeds in sorted(raw_families, key=lambda item: (item[0], item[1]), reverse=True):
            if any(float(np.dot(centroid, existing.centroid)) >= self.relation_family_similarity for existing in families):
                continue
            tag_counts: Counter[str] = Counter(tag for seed in family_seeds for tag in seed.tags)
            families.append(
                _RelationFamily(
                    family_id=f"relation-family-{len(families):05d}",
                    centroid=centroid,
                    size=size,
                    coherence=round(_clamp01(coherence), 4),
                    source_tags=tuple(tag for tag, _count in tag_counts.most_common()),
                    example_pairs=tuple((seed.source_index, seed.target_index) for seed in family_seeds[:8]),
                )
            )
        return families

    def _is_near_selected_proof_conclusion(
        self,
        *,
        signals: list[ElementSignalRecord],
        candidate_index: int,
        selected_indices: list[int],
    ) -> bool:
        for selected_index in selected_indices:
            if not (0 < selected_index - candidate_index <= 4):
                continue
            selected_text = signals[selected_index].text
            if not re.search(r"\b(therefore|thus|hence|contradict\w*)\b", selected_text, re.IGNORECASE):
                continue
            between = signals[candidate_index + 1 : selected_index]
            if any(signal.is_heading for signal in between):
                continue
            return True
        return False

    def _term_looks_definition_worthy(self, term: str) -> bool:
        if term in COMPLETION_NOISE_TERMS:
            return False
        return (
            term in {"omega", "delta", "boxes", "rows", "strip", "band", "line", "sy", "qx", "qy", "rx", "ry", "z"}
            or bool(re.fullmatch(r"[qrstxyzd]\d*", term))
            or bool(re.fullmatch(r"[a-z]{1,2}\d+", term))
            or bool(re.fullmatch(r"[a-z]{1,2}_[a-z0-9]+", term))
        )

    def _package_defines_term(self, package_text: str, term: str) -> bool:
        return self._text_defines_term(package_text, term)

    def _text_defines_term(self, text: str, term: str) -> bool:
        if not term:
            return False
        escaped = re.escape(term)
        patterns = [
            rf"\blet\s+{escaped}\b",
            rf"\b{escaped}\s+(?:denote\w*|means?|refers?\s+to|is\s+(?:called|defined\s+as|a|an|the)|are\s+(?:called|defined\s+as|a|an|the)|consists?\s+of)\b",
            rf"\bdenote\w*\s+(?:by\s+)?{escaped}\b",
            rf"\bpartition\s+{escaped}\b",
            rf"\b{escaped}\s+into\b",
        ]
        normalized = _completion_normalized_text(text)
        return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)

    def _split_anchor_indices_into_spans(self, anchor_indices: list[int]) -> list["_OrderedSpan"]:
        if not anchor_indices:
            return []
        spans: list[_OrderedSpan] = []
        current = [anchor_indices[0]]
        for index in anchor_indices[1:]:
            if index - current[-1] <= self.max_order_gap_for_span:
                current.append(index)
                continue
            spans.append(
                _OrderedSpan(
                    start=current[0],
                    end=current[-1],
                    anchor_indices=tuple(current),
                    element_indices=tuple(current),
                    expansion_score=0.0,
                )
            )
            current = [index]
        spans.append(
            _OrderedSpan(
                start=current[0],
                end=current[-1],
                anchor_indices=tuple(current),
                element_indices=tuple(current),
                expansion_score=0.0,
            )
        )
        return spans

    def _select_best_ordered_span_candidate(
        self,
        *,
        signals: list[ElementSignalRecord],
        span: "_OrderedSpan",
        prompt: str,
        prompt_embedding: np.ndarray,
        core_element_index: int,
    ) -> tuple["_OrderedSpan", QueryAssemblyDecision | None]:
        candidate_spans = self._candidate_span_windows(signals=signals, span=span)
        if not candidate_spans:
            return span, None

        prompt_tokens = _content_tokens(prompt)
        anchor_text = "\n".join(signals[index].text for index in span.anchor_indices)
        candidate_texts = [
            "\n".join(signals[index].text for index in candidate.element_indices)
            for candidate in candidate_spans
        ]
        element_indices = sorted(
            {
                nearby
                for candidate in candidate_spans
                for index in candidate.element_indices
                for nearby in (index - 1, index, index + 1)
                if 0 <= nearby < len(signals)
                if signals[nearby].text.strip()
            }
        )
        element_texts = [signals[index].text for index in element_indices]
        embeddings = self._embed([anchor_text, *candidate_texts, *element_texts])
        anchor_embedding = embeddings[0]
        candidate_embeddings = embeddings[1 : 1 + len(candidate_texts)]
        element_embeddings = {
            index: embeddings[1 + len(candidate_texts) + offset]
            for offset, index in enumerate(element_indices)
        }

        scored: list[tuple[float, float, _OrderedSpan, dict[str, float]]] = []
        for candidate, candidate_embedding in zip(candidate_spans, candidate_embeddings):
            features = self._span_candidate_features(
                signals=signals,
                base_span=span,
                candidate=candidate,
                prompt_tokens=prompt_tokens,
                prompt_embedding=prompt_embedding,
                anchor_embedding=anchor_embedding,
                candidate_embedding=candidate_embedding,
                element_embeddings=element_embeddings,
            )
            completeness = self._span_candidate_completeness(features)
            quality = self._span_candidate_quality(features)
            scored.append((completeness, quality, candidate, features))

        max_completeness = max(item[0] for item in scored)
        base_completeness, base_quality, base_span, _base_features = next(
            item for item in scored if item[2].element_indices == span.element_indices
        )
        if max_completeness < base_completeness + self.min_span_expansion_gain:
            best_completeness = base_completeness
            best_quality = base_quality
            best_span = base_span
            best_features = _base_features
        else:
            threshold = max_completeness - self.span_completeness_slack
            eligible = [item for item in scored if item[0] >= threshold]
            best_completeness, best_quality, best_span, best_features = max(
                eligible,
                key=lambda item: (
                    item[1],
                    -self._span_token_count(signals, item[2]),
                    item[0],
                ),
            )

        selected = _OrderedSpan(
            start=best_span.start,
            end=best_span.end,
            anchor_indices=span.anchor_indices,
            element_indices=best_span.element_indices,
            expansion_score=float(best_completeness),
        )
        if selected.element_indices == span.element_indices:
            return selected, None

        representative = self._span_representative_signal(
            signals=signals,
            span=selected,
            score_by_element_index={index: 1.0 for index in span.anchor_indices},
        )
        reason = (
            "selected measured span candidate "
            f"completeness={best_completeness:.3f} base={base_completeness:.3f} "
            f"quality={best_quality:.3f} "
            f"prompt={best_features['prompt_similarity']:.3f} "
            f"anchor={best_features['anchor_preservation']:.3f} "
            f"cohesion={best_features['cohesion']:.3f} "
            f"boundary={best_features['boundary_strength']:.3f} "
            f"density={best_features['density']:.3f}"
        )
        return selected, self._decision(
            representative,
            direction="span_expand",
            action="selected",
            query_similarity=best_features["prompt_similarity"],
            core_similarity=best_features["anchor_preservation"],
            previous_query_similarity=0.0,
            previous_core_similarity=0.0,
            reason=reason,
        )

    def _candidate_span_windows(
        self,
        *,
        signals: list[ElementSignalRecord],
        span: "_OrderedSpan",
    ) -> list["_OrderedSpan"]:
        left_limit = max(0, span.start - self.span_expansion_radius)
        right_limit = min(len(signals) - 1, span.end + self.span_expansion_radius)
        candidates: dict[tuple[int, ...], _OrderedSpan] = {
            span.element_indices: span,
        }
        for start in range(left_limit, span.start + 1):
            for end in range(span.end, right_limit + 1):
                element_indices = tuple(range(start, end + 1))
                token_count = sum(signals[index].token_count for index in element_indices)
                if token_count > self.max_package_tokens:
                    continue
                candidates[element_indices] = _OrderedSpan(
                    start=start,
                    end=end,
                    anchor_indices=span.anchor_indices,
                    element_indices=element_indices,
                    expansion_score=0.0,
                )
        return list(candidates.values())

    def _expand_span_for_readability(
        self,
        *,
        signals: list[ElementSignalRecord],
        span: "_OrderedSpan",
        core_element_index: int,
    ) -> "_OrderedSpan":
        start = span.start
        end = span.end
        element_indices = set(span.element_indices)
        first = signals[start]
        last = signals[end]
        if start > 0 and self._needs_previous_context(first):
            start -= 1
            element_indices.add(start)
        if end + 1 < len(signals) and self._needs_next_context(last):
            end += 1
            element_indices.add(end)

        if start == core_element_index and start > 0:
            previous = signals[start - 1]
            if previous.is_heading or previous.element_type in {"title", "heading", "section_header"}:
                start -= 1
                element_indices.add(start)
        return _OrderedSpan(
            start=start,
            end=end,
            anchor_indices=span.anchor_indices,
            element_indices=tuple(sorted(element_indices)),
            expansion_score=0.0,
        )

    def _span_candidate_features(
        self,
        *,
        signals: list[ElementSignalRecord],
        base_span: "_OrderedSpan",
        candidate: "_OrderedSpan",
        prompt_tokens: set[str],
        prompt_embedding: np.ndarray,
        anchor_embedding: np.ndarray,
        candidate_embedding: np.ndarray,
        element_embeddings: Mapping[int, np.ndarray],
    ) -> dict[str, float]:
        candidate_signals = [signals[index] for index in candidate.element_indices]
        candidate_tokens = set().union(*(_content_tokens(signal.text) for signal in candidate_signals))
        prompt_similarity = float(np.dot(candidate_embedding, prompt_embedding))
        anchor_preservation = float(np.dot(candidate_embedding, anchor_embedding))
        cohesion = self._span_candidate_cohesion(candidate=candidate, element_embeddings=element_embeddings)
        boundary_strength = self._span_candidate_boundary_strength(
            signals=signals,
            candidate=candidate,
            element_embeddings=element_embeddings,
            cohesion=cohesion,
        )
        density = self._span_candidate_density(
            candidate_signals=candidate_signals,
            candidate_tokens=candidate_tokens,
            prompt_tokens=prompt_tokens,
        )
        closure_bias = self._span_candidate_closure_bias(
            signals=signals,
            base_span=base_span,
            candidate=candidate,
        )
        token_cost = sum(signal.token_count for signal in candidate_signals)
        duplicate_penalty = min(1.0, sum(signal.boilerplate_score for signal in candidate_signals) / max(1, len(candidate_signals)))
        return {
            "prompt_similarity": prompt_similarity,
            "anchor_preservation": anchor_preservation,
            "cohesion": cohesion,
            "boundary_strength": boundary_strength,
            "density": density,
            "closure_bias": closure_bias,
            "token_cost": float(token_cost),
            "duplicate_penalty": duplicate_penalty,
        }

    def _span_candidate_completeness(self, features: Mapping[str, float]) -> float:
        return float(
            features["prompt_similarity"] * 0.3
            + features["anchor_preservation"] * 0.24
            + features["density"] * 0.24
            + features["closure_bias"] * 0.12
            + features["cohesion"] * 0.1
        )

    def _span_candidate_quality(self, features: Mapping[str, float]) -> float:
        token_penalty = min(0.22, features["token_cost"] / 900.0)
        return float(
            features["cohesion"] * 0.38
            + features["boundary_strength"] * 0.3
            + features["anchor_preservation"] * 0.18
            + features["density"] * 0.14
            - token_penalty
            - features["duplicate_penalty"] * 0.08
        )

    def _span_candidate_cohesion(
        self,
        *,
        candidate: "_OrderedSpan",
        element_embeddings: Mapping[int, np.ndarray],
    ) -> float:
        indices = list(candidate.element_indices)
        if len(indices) <= 1:
            return 0.58
        similarities = [
            float(np.dot(element_embeddings[left], element_embeddings[right]))
            for left, right in zip(indices, indices[1:])
            if left in element_embeddings and right in element_embeddings
        ]
        if not similarities:
            return 0.0
        return max(0.0, min(1.0, sum(similarities) / len(similarities)))

    def _span_candidate_boundary_strength(
        self,
        *,
        signals: list[ElementSignalRecord],
        candidate: "_OrderedSpan",
        element_embeddings: Mapping[int, np.ndarray],
        cohesion: float,
    ) -> float:
        outside: list[float] = []
        if candidate.start > 0 and candidate.start in element_embeddings and candidate.start - 1 in element_embeddings:
            outside.append(float(np.dot(element_embeddings[candidate.start], element_embeddings[candidate.start - 1])))
        if candidate.end + 1 < len(signals) and candidate.end in element_embeddings and candidate.end + 1 in element_embeddings:
            outside.append(float(np.dot(element_embeddings[candidate.end], element_embeddings[candidate.end + 1])))
        if not outside:
            return 0.5
        outside_similarity = max(outside)
        return max(0.0, min(1.0, 0.5 + (cohesion - outside_similarity) / 2.0))

    def _span_candidate_density(
        self,
        *,
        candidate_signals: list[ElementSignalRecord],
        candidate_tokens: set[str],
        prompt_tokens: set[str],
    ) -> float:
        if not candidate_signals:
            return 0.0
        lexical_overlap = _jaccard(candidate_tokens, prompt_tokens)
        unique_terms = len(candidate_tokens)
        token_count = max(1, sum(signal.token_count for signal in candidate_signals))
        specificity = min(1.0, unique_terms / math.sqrt(token_count * 12.0))
        support_density = 0.1 if any(signal.element_type in SUPPORT_ELEMENT_TYPES for signal in candidate_signals) else 0.0
        return max(0.0, min(1.0, lexical_overlap * 0.55 + specificity * 0.35 + support_density))

    def _span_candidate_closure_bias(
        self,
        *,
        signals: list[ElementSignalRecord],
        base_span: "_OrderedSpan",
        candidate: "_OrderedSpan",
    ) -> float:
        bias = 0.0
        if candidate.start < base_span.start and self._needs_previous_context(signals[base_span.start]):
            bias += 0.45
        if candidate.end > base_span.end and self._needs_next_context(signals[base_span.end]):
            bias += 0.45
        if candidate.start < base_span.start:
            previous = signals[base_span.start - 1] if base_span.start > 0 else None
            if previous is not None and (previous.is_heading or previous.element_type in {"title", "heading", "section_header"}):
                bias += 0.25
        return min(1.0, bias)

    def _span_attach_score(
        self,
        *,
        signals: list[ElementSignalRecord],
        span: "_OrderedSpan",
        primary_span: "_OrderedSpan",
        prompt_tokens: set[str],
        score_by_element_index: Mapping[int, float],
        prompt_wants_support: bool,
    ) -> float:
        span_signals = [signals[index] for index in span.element_indices]
        span_tokens = set().union(*(_content_tokens(signal.text) for signal in span_signals))
        overlap = _jaccard(span_tokens, prompt_tokens)
        anchor_score = max((score_by_element_index.get(index, 0.0) for index in span.anchor_indices), default=0.0)
        distance = min(abs(span.end - primary_span.start), abs(primary_span.end - span.start))
        distance_penalty = min(0.22, max(0, distance - self.max_order_gap_for_span) * 0.025)
        support_bonus = 0.12 if prompt_wants_support and any(signal.element_type in SUPPORT_ELEMENT_TYPES for signal in span_signals) else 0.0
        heading_penalty = 0.08 if all(signal.is_heading or signal.word_count <= 5 for signal in span_signals) else 0.0
        duplicate_penalty = min(0.14, sum(signal.boilerplate_score for signal in span_signals) * 0.04)
        return float(anchor_score * 0.58 + overlap * 0.28 + support_bonus - distance_penalty - heading_penalty - duplicate_penalty)

    def _span_representative_signal(
        self,
        signals: list[ElementSignalRecord],
        span: "_OrderedSpan",
        score_by_element_index: Mapping[int, float],
    ) -> ElementSignalRecord:
        return max(
            (signals[index] for index in span.element_indices),
            key=lambda signal: score_by_element_index.get(signal.element_index, 0.0),
        )

    def _span_token_count(self, signals: list[ElementSignalRecord], span: "_OrderedSpan") -> int:
        return sum(signals[index].token_count for index in span.element_indices)

    def _needs_previous_context(self, signal: ElementSignalRecord) -> bool:
        return any(marker.direction_hint == "previous" for marker in signal.markers)

    def _needs_next_context(self, signal: ElementSignalRecord) -> bool:
        return any(marker.direction_hint == "next" for marker in signal.markers)

    def _consensus_graph(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_embeddings: np.ndarray,
    ) -> dict[int, dict[int, "_ConsensusEdge"]]:
        n = len(propositions)
        if n <= 1:
            return {}
        k_values = self._effective_k_values(n)
        similarity = proposition_embeddings @ proposition_embeddings.T
        counts: dict[tuple[int, int], int] = {}
        for k in k_values:
            for index in range(n):
                neighbors = np.argsort(-similarity[index])
                kept = [int(item) for item in neighbors if int(item) != index][:k]
                for neighbor in kept:
                    a, b = sorted((index, neighbor))
                    counts[(a, b)] = counts.get((a, b), 0) + 1

        graph: dict[int, dict[int, _ConsensusEdge]] = {}
        total = float(len(k_values))
        for (left, right), count in counts.items():
            stability = count / total
            sim = float(similarity[left, right])
            structural = self._structural_edge_bonus(
                signals=signals,
                left=propositions[left],
                right=propositions[right],
            )
            accepted = stability >= self.min_neighbor_stability and sim + structural >= self.min_edge_similarity
            if not accepted:
                continue
            edge = _ConsensusEdge(
                similarity=sim,
                stability=float(stability),
                structural_bonus=structural,
            )
            graph.setdefault(left, {})[right] = edge
            graph.setdefault(right, {})[left] = edge
        return graph

    def _cluster_candidate_indices(self, graph: dict[int, dict[int, "_ConsensusEdge"]], core_index: int) -> list[int]:
        seen = {core_index}
        frontier = [(core_index, 0)]
        ordered: list[int] = []
        while frontier and len(ordered) < self.max_cluster_propositions:
            current, depth = frontier.pop(0)
            if depth >= self.max_cluster_hops:
                continue
            neighbors = sorted(
                graph.get(current, {}).items(),
                key=lambda item: (item[1].stability, item[1].similarity + item[1].structural_bonus),
                reverse=True,
            )
            for neighbor, _edge in neighbors:
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                ordered.append(neighbor)
                frontier.append((neighbor, depth + 1))
                if len(ordered) >= self.max_cluster_propositions:
                    break
        return ordered

    def _cluster_candidate_score(
        self,
        *,
        signals: list[ElementSignalRecord],
        proposition: QueryEvidenceProposition,
        core_prop_index: int,
        prop_index: int,
        prompt_similarity: float,
        core_similarity: float,
        language_score: float,
        edge: "_ConsensusEdge | None",
        prompt_wants_support: bool,
        relation_geometry: "_DocumentRelationGeometry | None" = None,
    ) -> float:
        signal = signals[proposition.element_index]
        stability = edge.stability if edge is not None else 0.0
        structural = edge.structural_bonus if edge is not None else 0.0
        relation_score = relation_geometry.score(core_prop_index, prop_index) if relation_geometry is not None else 0.0
        score = (
            prompt_similarity * 0.42
            + core_similarity * 0.3
            + stability * 0.13
            + structural * 0.05
            + language_score * self.language_candidate_weight
            + relation_score * self.relation_geometry_weight
        )
        if prop_index == core_prop_index:
            score += 1.0
        if signal.is_heading and len(proposition.text.split()) <= 5:
            score -= 0.14
        if signal.element_type in SUPPORT_ELEMENT_TYPES and not prompt_wants_support:
            score -= 0.18
        if signal.element_type in SUPPORT_ELEMENT_TYPES and prompt_wants_support:
            score += 0.08
        if proposition.support_element_ids:
            score += 0.04
        return float(score)

    def _top_language_proposition_core_candidates(
        self,
        *,
        signals: list[ElementSignalRecord],
        propositions: list[QueryEvidenceProposition],
        proposition_embeddings: np.ndarray,
        proposition_similarities: np.ndarray,
        language_scores: np.ndarray,
        forced_prop_indices: list[int] | None = None,
        forced_anchor_groups: list[tuple[int, ...]] | None = None,
        forced_slots: int = 0,
    ) -> list[_CoreCandidate]:
        base_ranked = sorted(
            range(len(propositions)),
            key=lambda index: self._proposition_core_score(
                signals=signals,
                proposition=propositions[index],
                similarity=float(proposition_similarities[index]),
            ),
            reverse=True,
        )

        ranked: list[int] = []
        used_elements: set[str] = set()
        for index in base_ranked:
            proposition = propositions[index]
            if proposition.element_id in used_elements:
                continue
            ranked.append(index)
            used_elements.add(proposition.element_id)
            if len(ranked) >= self.top_k_cores:
                break

        if forced_prop_indices and forced_slots > 0:
            forced_ranked: list[int] = []
            for index in forced_prop_indices:
                if index < 0 or index >= len(propositions):
                    continue
                proposition = propositions[index]
                if signals[proposition.element_index].is_heading:
                    continue
                if proposition.element_id in {propositions[item].element_id for item in forced_ranked}:
                    continue
                forced_ranked.append(index)

            reserved_slots = min(self.top_k_cores, forced_slots, len(forced_ranked))
            preserved_ranked = ranked[: max(0, self.top_k_cores - reserved_slots)]
            combined_ranked: list[int] = list(preserved_ranked)
            used_forced_elements: set[str] = {propositions[index].element_id for index in combined_ranked}

            for index in forced_ranked:
                proposition = propositions[index]
                if proposition.element_id in used_forced_elements:
                    continue
                combined_ranked.append(index)
                used_forced_elements.add(proposition.element_id)
                if len(combined_ranked) >= len(preserved_ranked) + reserved_slots:
                    break

            for index in ranked[len(preserved_ranked) :]:
                proposition = propositions[index]
                if proposition.element_id in used_forced_elements:
                    continue
                combined_ranked.append(index)
                used_forced_elements.add(proposition.element_id)
                if len(combined_ranked) >= self.top_k_cores:
                    break
            ranked = combined_ranked
            used_elements = {propositions[index].element_id for index in ranked}

        if self.use_language_map and len(language_scores) and self.language_candidate_slots:
            language_ranked = sorted(
                range(len(propositions)),
                key=lambda index: (
                    float(language_scores[index]),
                    self._proposition_core_score(
                        signals=signals,
                        proposition=propositions[index],
                        similarity=float(proposition_similarities[index]),
                    ),
                ),
                reverse=True,
            )
            language_added = 0
            for index in language_ranked:
                if float(language_scores[index]) < self.min_language_core_score:
                    break
                proposition = propositions[index]
                if proposition.element_id in used_elements:
                    continue
                if signals[proposition.element_index].is_heading:
                    continue
                if len(ranked) >= self.top_k_cores:
                    ranked[-1] = index
                else:
                    ranked.append(index)
                used_elements.add(proposition.element_id)
                language_added += 1
                if language_added >= self.language_candidate_slots:
                    break

        anchor_group_by_index: dict[int, tuple[int, ...]] = {}
        for group in forced_anchor_groups or []:
            valid_group = tuple(index for index in group if 0 <= index < len(propositions))
            if not valid_group:
                continue
            for index in valid_group:
                anchor_group_by_index.setdefault(index, valid_group)

        candidates: list[_CoreCandidate] = []
        final_used: set[str] = set()
        for index in ranked:
            proposition = propositions[index]
            if proposition.element_id in final_used:
                continue
            candidates.append(
                _CoreCandidate(
                    element_index=proposition.element_index,
                    prompt_similarity=float(proposition_similarities[index]),
                    core_embedding=proposition_embeddings[index],
                    proposition_id=proposition.proposition_id,
                    proposition_index=index,
                    proposition_text=proposition.text,
                    support_element_ids=list(proposition.support_element_ids),
                    anchor_prop_indices=anchor_group_by_index.get(index, (index,)),
                )
            )
            final_used.add(proposition.element_id)
            if len(candidates) >= self.top_k_cores:
                break
        return candidates

    def _document_language_cache_for(
        self,
        propositions: list[QueryEvidenceProposition],
    ) -> _DocumentLanguageCache:
        key = self._document_cache_key(
            namespace="document-language",
            propositions=propositions,
        )
        cached = self._document_language_cache.get(key)
        if cached is not None:
            return cached

        language_map = _DocumentLanguageMap.build(propositions)
        if language_map.units:
            unit_embeddings = self._embed([unit.text for unit in language_map.units])
        else:
            unit_embeddings = np.zeros((0, 0), dtype=float)
        cached = _DocumentLanguageCache(
            key=key,
            language_map=language_map,
            unit_embeddings=unit_embeddings,
        )
        self._document_language_cache[key] = cached
        if len(self._document_language_cache) > 8:
            oldest_key = next(iter(self._document_language_cache))
            if oldest_key != key:
                self._document_language_cache.pop(oldest_key, None)
        return cached

    def _language_proposition_scores(
        self,
        *,
        prompt: str,
        propositions: list[QueryEvidenceProposition],
    ) -> np.ndarray:
        if not self.use_language_map or not propositions:
            return np.zeros(len(propositions), dtype=float)

        language_cache = self._document_language_cache_for(propositions)
        language_map = language_cache.language_map
        query_units = _extract_language_units(prompt, proposition_index=-1, element_id="", element_index=-1)
        if not language_map.units or not query_units:
            return np.zeros(len(propositions), dtype=float)

        query_texts = [unit.text for unit in query_units]
        query_embeddings = self._embed(query_texts)
        document_embeddings = language_cache.unit_embeddings
        similarities = document_embeddings @ query_embeddings.T

        scores: dict[int, list[float]] = defaultdict(list)
        query_tokens = set().union(*(unit.tokens for unit in query_units))
        for unit_index, unit in enumerate(language_map.units):
            best_similarity = float(np.max(similarities[unit_index]))
            lexical_overlap = _jaccard(unit.tokens, query_tokens)
            if lexical_overlap == 0.0 and best_similarity < 0.62:
                continue
            family_weight = language_map.family_weight(unit.family)
            unit_score = best_similarity * 0.72 + lexical_overlap * 0.28
            unit_score *= family_weight
            if unit.kind in {"relation", "quantity"} and _prompt_asks_why(prompt):
                unit_score += 0.08
            scores[unit.proposition_index].append(unit_score)

        result = np.zeros(len(propositions), dtype=float)
        for proposition_index, values in scores.items():
            if not values:
                continue
            ranked = sorted(values, reverse=True)[:3]
            result[proposition_index] = max(0.0, min(1.0, ranked[0] * 0.7 + (sum(ranked) / len(ranked)) * 0.3))
        return result

    def _structural_edge_bonus(
        self,
        *,
        signals: list[ElementSignalRecord],
        left: QueryEvidenceProposition,
        right: QueryEvidenceProposition,
    ) -> float:
        left_signal = signals[left.element_index]
        right_signal = signals[right.element_index]
        bonus = 0.0
        if left.element_id == right.element_id:
            bonus += 0.25
        if left_signal.page_number is not None and left_signal.page_number == right_signal.page_number:
            bonus += 0.04
        distance = abs(left.element_index - right.element_index)
        if distance <= 2:
            bonus += 0.04
        elif distance <= 5:
            bonus += 0.02
        if set(left.support_element_ids) & set(right.support_element_ids):
            bonus += 0.06
        if left_signal.element_type in SUPPORT_ELEMENT_TYPES or right_signal.element_type in SUPPORT_ELEMENT_TYPES:
            bonus -= 0.03
        return float(bonus)

    def _effective_k_values(self, n: int) -> tuple[int, ...]:
        if self.k_values:
            raw = self.k_values
        elif n < 30:
            raw = (2, 3, 5)
        elif n < 150:
            raw = (3, 5, 8, 13)
        else:
            raw = (5, 8, 13, 21)
        values = sorted({max(1, min(int(k), n - 1)) for k in raw if n > 1})
        return tuple(values or [1])

    def _prompt_wants_support(self, prompt: str) -> bool:
        return bool(
            re.search(
                r"\b(figure|image|diagram|chart|table|formula|map|visual|punnett|shown|illustrate|illustrates)\b",
                prompt,
                re.IGNORECASE,
            )
        )


@dataclass(frozen=True)
class _LanguageUnit:
    text: str
    normalized: str
    kind: str
    family: str
    proposition_index: int
    element_id: str
    element_index: int
    tokens: frozenset[str]


@dataclass(frozen=True)
class _DocumentLanguageMap:
    units: list[_LanguageUnit]
    family_counts: Mapping[str, int]

    @classmethod
    def build(cls, propositions: list[QueryEvidenceProposition]) -> "_DocumentLanguageMap":
        raw_units: list[_LanguageUnit] = []
        for proposition_index, proposition in enumerate(propositions):
            raw_units.extend(
                _extract_language_units(
                    proposition.text,
                    proposition_index=proposition_index,
                    element_id=proposition.element_id,
                    element_index=proposition.element_index,
                )
            )
        if not raw_units:
            return cls(units=[], family_counts={})

        token_document_counts: Counter[str] = Counter()
        for unit in raw_units:
            token_document_counts.update(unit.tokens)

        refamilied: list[_LanguageUnit] = []
        for unit in raw_units:
            family = _dynamic_family(unit.tokens, token_document_counts)
            refamilied.append(
                _LanguageUnit(
                    text=unit.text,
                    normalized=unit.normalized,
                    kind=unit.kind,
                    family=family,
                    proposition_index=unit.proposition_index,
                    element_id=unit.element_id,
                    element_index=unit.element_index,
                    tokens=unit.tokens,
                )
            )
        family_counts = Counter(unit.family for unit in refamilied)
        return cls(units=refamilied, family_counts=dict(family_counts))

    def family_weight(self, family: str) -> float:
        count = max(1, int(self.family_counts.get(family, 1)))
        return 1.0 / math.sqrt(count)


@dataclass(frozen=True)
class _OrderedSpan:
    start: int
    end: int
    anchor_indices: tuple[int, ...]
    element_indices: tuple[int, ...]
    expansion_score: float = 0.0


@dataclass(frozen=True)
class _ExpansionState:
    start: int
    end: int
    query_similarity: float
    core_similarity: float

    def with_added(self, candidate_index: int, *, direction: str) -> "_ExpansionState":
        if direction == "left":
            return _ExpansionState(candidate_index, self.end, self.query_similarity, self.core_similarity)
        return _ExpansionState(self.start, candidate_index, self.query_similarity, self.core_similarity)

    def token_count(self, signals: list[ElementSignalRecord]) -> int:
        return sum(signal.token_count for signal in signals[self.start : self.end + 1])


@dataclass(frozen=True)
class _MarkedDrift:
    rollback_state: _ExpansionState
    baseline_query_similarity: float
    baseline_core_similarity: float
    remaining_lookahead: int


@dataclass(frozen=True)
class _ConsensusEdge:
    similarity: float
    stability: float
    structural_bonus: float


@dataclass(frozen=True)
class _RelationSeed:
    source_index: int
    target_index: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RelationFamily:
    family_id: str
    centroid: np.ndarray
    size: int
    coherence: float
    source_tags: tuple[str, ...] = ()
    example_pairs: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class _DocumentRelationGeometry:
    proposition_embeddings: np.ndarray
    families: list[_RelationFamily]
    relation_family_similarity: float

    @classmethod
    def empty(
        cls,
        *,
        proposition_embeddings: np.ndarray,
        relation_family_similarity: float,
    ) -> "_DocumentRelationGeometry":
        return cls(
            proposition_embeddings=proposition_embeddings,
            families=[],
            relation_family_similarity=relation_family_similarity,
        )

    def best_family(self, source_index: int, target_index: int) -> _RelationFamily | None:
        direction = _relation_delta_direction(
            self.proposition_embeddings,
            source_index=source_index,
            target_index=target_index,
        )
        if direction is None or not self.families:
            return None
        scored = [
            (float(np.dot(direction, family.centroid)), family)
            for family in self.families
        ]
        best_similarity, best_family = max(scored, key=lambda item: item[0])
        if best_similarity < self.relation_family_similarity:
            return None
        return best_family

    def score(self, source_index: int, target_index: int) -> float:
        direction = _relation_delta_direction(
            self.proposition_embeddings,
            source_index=source_index,
            target_index=target_index,
        )
        if direction is None or not self.families:
            return 0.0
        best_score = 0.0
        for family in self.families:
            similarity = float(np.dot(direction, family.centroid))
            if similarity < self.relation_family_similarity:
                continue
            scaled_similarity = (similarity - self.relation_family_similarity) / max(1e-6, 1.0 - self.relation_family_similarity)
            best_score = max(best_score, scaled_similarity * family.coherence)
        return _clamp01(best_score)


class _EmbeddingBackend:
    def __init__(self, config: BuilderConfig) -> None:
        self.config = config
        self._model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._get_model()
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=float)

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            self._model = _HashingEmbedder()
            return self._model
        try:
            self._model = SentenceTransformer(self.config.EMBEDDING_MODEL, trust_remote_code=True)
        except Exception:
            try:
                self._model = SentenceTransformer(self.config.EMBEDDING_FALLBACK)
            except Exception:
                self._model = _HashingEmbedder()
        return self._model


class _HashingEmbedder:
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def encode(
        self,
        texts: Iterable[str],
        *,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
    ) -> np.ndarray:
        vectors = []
        for text in texts:
            vector = np.zeros(self.dimensions, dtype=float)
            for token in re.findall(r"[A-Za-z0-9_]+", (text or "").lower()):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0
            if not np.any(vector):
                vector[0] = 1.0
            if normalize_embeddings:
                norm = float(np.linalg.norm(vector))
                if norm > 0:
                    vector = vector / norm
            vectors.append(vector)
        result = np.asarray(vectors, dtype=float)
        return result if convert_to_numpy else result.tolist()


def _normalize(embeddings: np.ndarray) -> np.ndarray:
    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = embeddings / norms
    return normalized


def _relation_delta_direction(
    embeddings: np.ndarray,
    *,
    source_index: int,
    target_index: int,
) -> np.ndarray | None:
    if source_index < 0 or target_index < 0:
        return None
    if source_index >= len(embeddings) or target_index >= len(embeddings):
        return None
    delta = np.asarray(embeddings[target_index] - embeddings[source_index], dtype=float)
    norm = float(np.linalg.norm(delta))
    if norm <= 1e-9:
        return None
    return delta / norm


def _extract_language_units(
    text: str,
    *,
    proposition_index: int,
    element_id: str,
    element_index: int,
) -> list[_LanguageUnit]:
    tokens = _content_tokens(text)
    units: dict[str, _LanguageUnit] = {}

    def add_unit(unit_text: str, kind: str) -> None:
        normalized = _normalize_language_text(unit_text)
        unit_tokens = frozenset(_content_tokens(unit_text))
        if not normalized or not unit_tokens:
            return
        if normalized in units:
            return
        units[normalized] = _LanguageUnit(
            text=re.sub(r"\s+", " ", unit_text).strip(),
            normalized=normalized,
            kind=kind,
            family="",
            proposition_index=proposition_index,
            element_id=element_id,
            element_index=element_index,
            tokens=unit_tokens,
        )

    for chunk in _content_chunks(text):
        add_unit(chunk, "phrase")

    for match in SYMBOL_RE.finditer(text):
        symbol = match.group(0).strip()
        if symbol.lower() not in STOPWORDS:
            add_unit(_window_around_span(text, match.start(), match.end(), radius=42), "symbol")

    for match in COMPARISON_RE.finditer(text):
        add_unit(_window_around_span(text, match.start(), match.end(), radius=72), "relation")

    for match in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:/|positions?|rows?|boxes?|points?|pairs?|w|omega)?\b", text, re.IGNORECASE):
        add_unit(_window_around_span(text, match.start(), match.end(), radius=54), "quantity")

    if len(tokens) >= 4:
        add_unit(" ".join(tokens[:10]), "summary")

    return list(units.values())


def _content_chunks(text: str) -> list[str]:
    raw_tokens = TOKEN_RE.findall(text)
    chunks: list[str] = []
    current: list[str] = []
    for token in raw_tokens:
        lowered = token.lower()
        if lowered in STOPWORDS:
            if len(current) >= 2:
                chunks.append(" ".join(current))
            current = []
            continue
        current.append(token)
        if len(current) >= 6:
            chunks.append(" ".join(current))
            current = current[-2:]
    if len(current) >= 2:
        chunks.append(" ".join(current))

    extra: list[str] = []
    content = [token for token in raw_tokens if token.lower() not in STOPWORDS]
    for size in (2, 3):
        for index in range(max(0, len(content) - size + 1)):
            window = content[index : index + size]
            if len(window) == size:
                extra.append(" ".join(window))
    return chunks + extra


def _content_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(text):
        lowered = token.lower()
        if lowered in STOPWORDS:
            continue
        if len(lowered) < 2 and not token.isupper() and not lowered.isdigit():
            continue
        tokens.append(lowered)
    return tokens


def _completion_normalized_text(text: str) -> str:
    normalized = (text or "").replace("ω", " omega ").replace("Ω", " omega ")
    normalized = normalized.replace("δ", " delta ").replace("Δ", " delta ")
    normalized = normalized.replace("→", " ").replace("↑", " ").replace("↓", " ")
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _completion_tokens(text: str) -> list[str]:
    normalized = _completion_normalized_text(text)
    tokens = _content_tokens(normalized)
    compact_symbols = re.findall(r"\b[a-z]{1,2}\b", normalized)
    for symbol in compact_symbols:
        if symbol not in STOPWORDS:
            tokens.append(symbol)
    return tokens


def _grounding_symbols(text: str) -> set[str]:
    normalized = _completion_normalized_text(text)
    symbols: set[str] = set()
    for match in re.finditer(r"\b[a-z]{1,3}\s*\(\s*[a-z]{1,3}\s*,\s*[a-z]{1,3}\s*\)", normalized):
        symbols.add(re.sub(r"\s+", "", match.group(0)))
    for token in re.findall(r"\b[a-z]{1,3}(?:_[a-z0-9]+)?\b", normalized):
        if token not in STOPWORDS and token not in COMPLETION_NOISE_TERMS:
            symbols.add(token)
    for token in re.findall(r"\b(?:omega|delta|alpha|beta|gamma|theta)\b", normalized):
        symbols.add(token)
    return symbols


def _meaningful_completion_keys(keys: Iterable[str]) -> set[str]:
    return {key for key in keys if key and not key.startswith("element:")}


def _expanded_completion_fill_keys(keys: Iterable[str]) -> set[str]:
    expanded = _meaningful_completion_keys(keys)
    for key in list(expanded):
        if key.startswith(("definition:", "setup:")):
            expanded.add(f"term:{key.split(':', 1)[1]}")
    return expanded


def _dynamic_family(tokens: frozenset[str], document_counts: Counter[str]) -> str:
    if not tokens:
        return "misc"
    ranked = sorted(
        tokens,
        key=lambda token: (document_counts.get(token, 1), -len(token), token),
    )
    return "+".join(ranked[:2]) if ranked else "misc"


def _normalize_language_text(text: str) -> str:
    return " ".join(_content_tokens(text))


def _window_around_span(text: str, start: int, end: int, *, radius: int) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    window = text[left:right]
    return re.sub(r"\s+", " ", window).strip(" ,.;:")


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _preview(text: str, *, limit: int = 220) -> str:
    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) <= limit:
        return preview
    return preview[: max(0, limit - 3)].rstrip() + "..."


def _role_family(role: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (role or "").strip().lower()).strip("_")
    if normalized in {"visual_support", "table_support", "formula_support", "support"}:
        return "support"
    if normalized in {"assumption", "condition", "claim", "setup", "proof_setup"}:
        return "proof_setup"
    if normalized in {"reason", "proof_reason", "quantity_bound", "contradiction", "bound"}:
        return "proof_reason"
    if normalized in {"conclusion", "proof_conclusion", "result"}:
        return "proof_conclusion"
    if normalized in {"procedure", "procedure_step", "step", "algorithm_step"}:
        return "procedure"
    if normalized in {"definition", "defined_term", "term_definition"}:
        return "definition"
    if normalized in {"comparison", "comparative", "contrast", "difference", "table_comparison"}:
        return "comparison"
    if normalized in {"quantity", "quantity_bound", "bound", "measurement"}:
        return "proof_reason"
    if normalized in {"lemma", "principle"}:
        return "proof_reason"
    return normalized


def _roles_from_query_type(text: str) -> set[str]:
    expanded = re.sub(r"[_/-]+", " ", text or "")
    tokens = set(_completion_tokens(expanded))
    roles: set[str] = set()
    if tokens & {"definition", "define", "meaning", "explanation", "what"}:
        roles.add("definition")
    if tokens & {"procedure", "process", "algorithm", "steps", "work", "workflow"}:
        roles.add("procedure")
    if tokens & {"proof", "reason", "why", "causal", "cause", "mechanism", "interpretive", "analysis"}:
        roles.add("proof_reason")
    if tokens & {"conclusion", "result", "imply", "implication", "summary"}:
        roles.add("proof_conclusion")
    if tokens & {"comparison", "comparative", "contrast", "differ", "difference", "versus"}:
        roles.add("comparison")
    if tokens & {"figure", "visual", "table", "map", "diagram", "formula", "support"}:
        roles.add("support")
    return roles


def _package_element_labels(package_text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for match in re.finditer(r"\[(?P<label>[^|\]]+)\|\s*(?P<element_id>[^\]]+)\]", package_text):
        label = re.sub(r"\s+", " ", match.group("label")).strip()
        element_id = re.sub(r"\s+", " ", match.group("element_id")).strip()
        if label and element_id:
            labels[element_id] = label
    return labels


def _rank_label_weight(label: str) -> float:
    normalized = (label or "").strip().lower()
    if normalized == "core":
        return 1.0
    if normalized == "cluster":
        return 0.85
    if normalized == "support":
        return 0.78
    if normalized == "completion":
        return 0.46
    return 0.62


def _weighted_term_coverage(terms: Iterable[str], text: str, text_tokens: set[str]) -> float:
    normalized_text = _completion_normalized_text(text)
    scores: list[float] = []
    for term in terms:
        term_norm = _completion_normalized_text(term)
        term_tokens = set(_completion_tokens(term))
        if not term_tokens:
            continue
        if term_norm and term_norm in normalized_text:
            scores.append(1.0)
        else:
            scores.append(_jaccard(text_tokens, term_tokens))
    if not scores:
        return 0.0
    ranked = sorted(scores, reverse=True)
    top = ranked[:5]
    strong_fraction = sum(1 for score in scores if score >= 0.42) / len(scores)
    return _clamp01((sum(top) / len(top)) * 0.72 + strong_fraction * 0.28)


def _decision_value(decision: QueryAssemblyDecision | Mapping[str, Any], field_name: str) -> str:
    if isinstance(decision, Mapping):
        return str(decision.get(field_name, ""))
    return str(getattr(decision, field_name, ""))


def _completion_key_weight(key: str) -> float:
    if key.startswith("definition:"):
        return 1.15
    if key.startswith("answer:"):
        return 1.0
    if key in {"proof:setup", "proof:reason", "proof:conclusion", "support"}:
        return 1.0
    if key in {"procedure", "example"}:
        return 0.85
    if key.startswith(("term:", "setup:")):
        return 0.55
    return 0.4


def _prompt_asks_why(prompt: str) -> bool:
    return bool(re.search(r"\b(why|how|explain|reason|prove|proof|because)\b", prompt, re.IGNORECASE))


def _extract_json_payload(content: str) -> Any | None:
    text = (content or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not start_candidates:
        return None
    start = min(start_candidates)
    for end in range(len(text), start, -1):
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            continue
    return None
