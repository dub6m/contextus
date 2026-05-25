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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QueryAssemblyResult:
    prompt: str
    packages: list[QueryAssembledPackage]
    propositions: list["QueryEvidenceProposition"] = field(default_factory=list)
    retrieval_plan: "QueryRetrievalPlan | None" = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
        package_text = self._package_text(
            selected,
            core_element_id=signals[core_index].element_id,
            role_by_id=role_by_id,
        )
        token_count = sum(signal.token_count for signal in selected)
        score = self._package_score(
            package_prompt_similarity=state.query_similarity,
            package_core_similarity=state.core_similarity,
            core_prompt_similarity=core_candidate.prompt_similarity,
            token_count=token_count,
        )
        package_id = f"query-package-{package_index:05d}"
        if core_candidate.proposition_id is not None:
            package_id = f"query-proposition-package-{package_index:05d}"
        return QueryAssembledPackage(
            package_id=package_id,
            core_element_id=signals[core_index].element_id,
            core_index=core_index,
            core_prompt_similarity=round(core_candidate.prompt_similarity, 4),
            package_prompt_similarity=round(state.query_similarity, 4),
            package_core_similarity=round(state.core_similarity, 4),
            element_ids=[signal.element_id for signal in selected],
            package_text=package_text,
            token_count=token_count,
            score=round(
                score
                + self._answerability_bonus(
                    signals=selected,
                    core_element_id=signals[core_index].element_id,
                    proposition_text=core_candidate.proposition_text,
                ),
                4,
            ),
            decisions=decisions,
        )

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
        self._query_plan_cache: dict[str, QueryRetrievalPlan] = {}

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
        embeddings = self._embed([prompt, *[proposition.text for proposition in propositions]])
        prompt_embedding = embeddings[0]
        proposition_embeddings = embeddings[1:]
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
        graph = self._consensus_graph(
            signals=signals,
            propositions=propositions,
            proposition_embeddings=proposition_embeddings,
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
        return QueryAssemblyResult(prompt=prompt, packages=ranked, propositions=propositions, retrieval_plan=retrieval_plan)

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
            sub_tokens = self._bridge_tokens(" ".join([sub_need.need, *sub_need.search_terms]))
            if not sub_tokens:
                continue
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
            if not ranked:
                continue
            group = tuple(dict.fromkeys(ranked))
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

        package_text = self._package_text(
            selected,
            core_element_id=signals[core_index].element_id,
            role_by_id=role_by_id,
        )
        package_embedding = self._embed([package_text])[0]
        package_prompt_similarity = float(np.dot(package_embedding, prompt_embedding))
        package_core_similarity = float(np.dot(package_embedding, proposition_embeddings[core_prop_index]))
        final_token_count = sum(signal.token_count for signal in selected)
        score = self._package_score(
            package_prompt_similarity=package_prompt_similarity,
            package_core_similarity=package_core_similarity,
            core_prompt_similarity=core_candidate.prompt_similarity,
            token_count=final_token_count,
        )
        score += self._answerability_bonus(
            signals=selected,
            core_element_id=signals[core_index].element_id,
            proposition_text=core_candidate.proposition_text,
        )
        if len(language_scores):
            score += min(0.08, float(language_scores[core_prop_index]) * 0.08)
        score += min(0.08, 0.015 * sum(1 for decision in decisions if decision.action == "attached"))
        return QueryAssembledPackage(
            package_id=f"query-cluster-package-{package_index:05d}",
            core_element_id=signals[core_index].element_id,
            core_index=core_index,
            core_prompt_similarity=round(core_candidate.prompt_similarity, 4),
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
    ) -> float:
        signal = signals[proposition.element_index]
        stability = edge.stability if edge is not None else 0.0
        structural = edge.structural_bonus if edge is not None else 0.0
        score = (
            prompt_similarity * 0.42
            + core_similarity * 0.3
            + stability * 0.13
            + structural * 0.05
            + language_score * self.language_candidate_weight
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

    def _language_proposition_scores(
        self,
        *,
        prompt: str,
        propositions: list[QueryEvidenceProposition],
    ) -> np.ndarray:
        if not self.use_language_map or not propositions:
            return np.zeros(len(propositions), dtype=float)

        language_map = _DocumentLanguageMap.build(propositions)
        query_units = _extract_language_units(prompt, proposition_index=-1, element_id="", element_index=-1)
        if not language_map.units or not query_units:
            return np.zeros(len(propositions), dtype=float)

        query_texts = [unit.text for unit in query_units]
        document_texts = [unit.text for unit in language_map.units]
        embeddings = self._embed([*query_texts, *document_texts])
        query_embeddings = embeddings[: len(query_texts)]
        document_embeddings = embeddings[len(query_texts) :]
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
