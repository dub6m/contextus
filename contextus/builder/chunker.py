from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from statistics import mean, pstdev
from typing import Any, Iterable
import hashlib
import json
import math
import os
import re
import threading

import numpy as np

from contextus.ingestion.models import ExtractedDocument, ExtractedElement
from contextus.llm import LLMClient

from .config import BuilderConfig
from .preprocessor import ElementPreprocessor


@dataclass
class BoundaryElementView:
    """Stable view of one extracted element for boundary analysis."""

    element_id: str
    element_type: str
    page_number: int
    order: int
    bbox: tuple[float, float, float, float]
    confidence: float | None
    text: str
    raw_text: str
    source: str
    asset_path: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BoundarySignals:
    """Cheap first-pass evidence attached to one candidate boundary."""

    page_gap: int
    order_gap: int
    left_confidence: float | None
    right_confidence: float | None
    adjacent_embedding_similarity: float
    type_prior: float
    left_heading_like_score: float
    right_heading_like_score: float
    heading_like_score: float
    left_caption_or_artifact_score: float
    right_caption_or_artifact_score: float
    caption_or_artifact_score: float
    left_formula_or_table_score: float
    right_formula_or_table_score: float
    formula_or_table_score: float
    left_admin_front_matter_score: float
    right_admin_front_matter_score: float
    admin_front_matter_score: float
    text_continuation_score: float
    hard_rule_flags: dict[str, bool] = field(default_factory=dict)


@dataclass
class BoundaryPreliminaryDecision:
    """Tier 0 read of a boundary candidate before semantic refinement."""

    decision: str
    split_probability: float
    confidence: float
    tier_used: str = "0"
    reasons: list[str] = field(default_factory=list)
    hard_rule_flags: dict[str, bool] = field(default_factory=dict)


@dataclass
class BoundaryCandidate:
    """Adjacent element boundary plus local context for later scoring."""

    boundary_id: str
    boundary_index: int
    left: BoundaryElementView
    right: BoundaryElementView
    left_context: list[BoundaryElementView] = field(default_factory=list)
    right_context: list[BoundaryElementView] = field(default_factory=list)
    same_page: bool = False
    page_gap: int = 0
    order_gap: int = 0
    signals: BoundarySignals | None = None
    preliminary_decision: BoundaryPreliminaryDecision | None = None

    @property
    def left_element_id(self) -> str:
        return self.left.element_id

    @property
    def right_element_id(self) -> str:
        return self.right.element_id


@dataclass
class TentativeBlock:
    """Manageable document region created from preliminary boundary decisions."""

    block_id: str
    block_index: int
    elements: list[BoundaryElementView]
    start_element_index: int
    end_element_index: int
    start_boundary: BoundaryCandidate | None = None
    end_boundary: BoundaryCandidate | None = None
    internal_boundaries: list[BoundaryCandidate] = field(default_factory=list)
    stability: str = "ambiguous"
    reason_summary: str = ""

    @property
    def element_ids(self) -> list[str]:
        return [element.element_id for element in self.elements]

    @property
    def boundary_ids(self) -> list[str]:
        return [boundary.boundary_id for boundary in self.internal_boundaries]


@dataclass
class ActiveConcept:
    """Current concept accumulator used while refining one tentative block."""

    start_element_index: int
    end_element_index: int
    elements: list[BoundaryElementView]
    concept_summary: str
    evidence_types: dict[str, int] = field(default_factory=dict)
    open_threads: list[str] = field(default_factory=list)

    @property
    def element_ids(self) -> list[str]:
        return [element.element_id for element in self.elements]


@dataclass
class ConceptProbeDecision:
    """Semantic decision for one candidate boundary during active refinement."""

    boundary_id: str
    decision: str
    confidence: float
    source: str
    reasons: list[str] = field(default_factory=list)
    needs_more_context: bool = False
    context_request: dict[str, Any] = field(default_factory=dict)
    context_expansions: int = 0
    prompt_context_window: int = 0


@dataclass
class ChunkRepairDecision:
    """Local Step 6 repair action applied after active chunk refinement."""

    action: str
    confidence: float
    source: str
    reasons: list[str] = field(default_factory=list)
    affected_element_ids: list[str] = field(default_factory=list)
    source_group_id: str | None = None
    target_group_id: str | None = None


@dataclass
class _LocalAuditDecision:
    """Parsed LLM recommendation for one suspicious local chunk window."""

    action: str
    confidence: float
    reason: str
    element_ids: list[str] = field(default_factory=list)


@dataclass
class _BlockSegmentationDecision:
    """Parsed LLM segmentation for one tentative block."""

    split_start_element_ids: list[str]
    confidence: float
    reason: str


@dataclass
class _LocalAuditJob:
    """One Step 6 audit request selected for a non-overlapping round."""

    index: int
    risk_flags: list[str]
    signature: tuple[tuple[str, ...], tuple[str, ...]]
    prompt: str


@dataclass
class RefinedChunkGroup:
    """Concept-sized group produced by refining a tentative block."""

    group_id: str
    group_index: int
    source_block_id: str
    elements: list[BoundaryElementView]
    start_element_index: int
    end_element_index: int
    internal_boundaries: list[BoundaryCandidate] = field(default_factory=list)
    probe_decisions: list[ConceptProbeDecision] = field(default_factory=list)
    repair_decisions: list[ChunkRepairDecision] = field(default_factory=list)
    stability: str = "ambiguous"
    reason_summary: str = ""
    search_strategy: str = "sequential"

    @property
    def element_ids(self) -> list[str]:
        return [element.element_id for element in self.elements]

    @property
    def boundary_ids(self) -> list[str]:
        return [boundary.boundary_id for boundary in self.internal_boundaries]


@dataclass
class BoundaryDecision:
    """Decision record for one adjacent boundary in the document."""

    left_element_id: str
    right_element_id: str
    tier_used: str
    decision: str
    confidence: float
    notes: str


@dataclass
class ProbeOutcome:
    """Internal probe result used during anchor-guided boundary search."""

    verdict: str
    confidence: float
    tier_used: str
    notes: str
    llm_calls_used: int = 0


@dataclass
class _RepairGroupState:
    """Mutable group state used while Step 6 shifts whole elements locally."""

    source_group_ids: list[str]
    source_block_ids: list[str]
    elements: list[BoundaryElementView]
    internal_boundaries: list[BoundaryCandidate]
    probe_decisions: list[ConceptProbeDecision]
    repair_decisions: list[ChunkRepairDecision]
    stability: str
    reason_summary: str
    split_piece_index: int | None = None


class _HashingEmbedder:
    """Offline-safe lexical embedder used when sentence-transformers models are unavailable."""

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def encode(
        self,
        texts: list[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
    ) -> np.ndarray:
        vectors: list[np.ndarray] = []
        for text in texts:
            vector = np.zeros(self.dimensions, dtype=float)
            for token in self._tokens(text):
                index = self._token_index(token)
                vector[index] += 1.0
            if not np.any(vector):
                vector[0] = 1.0
            if normalize_embeddings:
                norm = float(np.linalg.norm(vector))
                if norm > 0.0:
                    vector = vector / norm
            vectors.append(vector)
        result = np.asarray(vectors, dtype=float)
        return result if convert_to_numpy else result.tolist()

    def _token_index(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % self.dimensions

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9_]+", (text or "").lower())


class _LexicalCrossEncoder:
    """Offline-safe lexical overlap scorer with a cross-encoder-like predict API."""

    def predict(self, pairs: list[tuple[str, str]]) -> np.ndarray:
        scores: list[float] = []
        for left_text, right_text in pairs:
            left_tokens = set(re.findall(r"[A-Za-z0-9_]+", (left_text or "").lower()))
            right_tokens = set(re.findall(r"[A-Za-z0-9_]+", (right_text or "").lower()))
            union = left_tokens | right_tokens
            overlap = (len(left_tokens & right_tokens) / len(union)) if union else 0.0
            probability = min(0.95, max(0.05, 0.1 + (0.8 * overlap)))
            scores.append(math.log(probability / (1.0 - probability)))
        return np.asarray(scores, dtype=float)


class DocumentChunker:
    """Partitions a document into contiguous concept-sized element groups."""

    DEFAULT_TYPE_PRIORS: dict[tuple[str, str], float] = {
        ("text", "text"): 0.7,
        ("text", "formula"): 0.8,
        ("formula", "text"): 0.8,
        ("text", "table"): 0.6,
        ("table", "text"): 0.5,
        ("text", "figure"): 0.6,
        ("figure", "text"): 0.4,
        ("title", "*"): 0.0,
        ("*", "title"): 0.0,
        ("formula", "formula"): 0.5,
        ("figure", "figure"): 0.3,
        ("table", "table"): 0.3,
    }

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        config: BuilderConfig | None = None,
        preprocessor: ElementPreprocessor | None = None,
        type_priors: dict[tuple[str, str], float] | None = None,
    ) -> None:
        """Create a chunker with cached model handles and empty decision logs."""
        self.llm_client = llm_client
        self.config = config or BuilderConfig()
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.type_priors = dict(self.DEFAULT_TYPE_PRIORS)
        if type_priors:
            self.type_priors.update(type_priors)
        self.boundary_candidates: list[BoundaryCandidate] = []
        self.tentative_blocks: list[TentativeBlock] = []
        self.refined_groups: list[RefinedChunkGroup] = []
        self.repair_decisions: list[ChunkRepairDecision] = []
        self.boundary_log: list[BoundaryDecision] = []
        self._embedder = None
        self._cross_encoder = None
        self._refinement_response_cache: dict[str, str] = {}
        self._refinement_response_cache_lock = threading.Lock()
        self._llm_calls_lock = threading.Lock()
        self.llm_calls = 0
        self.recoverable_errors: list[str] = []

    def chunk(self, document: ExtractedDocument) -> list[list[ExtractedElement]]:
        """Chunk the document into contiguous groups in global reading order."""
        elements = self._sorted_elements(document)
        self.boundary_candidates = []
        self.tentative_blocks = []
        self.refined_groups = []
        self.repair_decisions = []
        self.boundary_log = []
        self.llm_calls = 0
        self.recoverable_errors = []
        if not elements:
            return []
        if len(elements) == 1:
            text = self.preprocessor.to_text(elements[0])
            self.tentative_blocks = self._single_tentative_block(document.id, elements[0], text)
            self.refined_groups = self._build_refined_groups(
                document_id=document.id,
                tentative_blocks=self.tentative_blocks,
                allow_llm=False,
            )
            self.refined_groups = self._repair_refined_groups(
                document_id=document.id,
                groups=self.refined_groups,
            )
            return [[elements[0]]]

        texts = [self.preprocessor.to_text(element) for element in elements]
        adjacent_similarities, similarity_mean, similarity_std = self._compute_similarity_stats(texts)
        self.boundary_candidates = self._build_boundary_candidates(
            document_id=document.id,
            elements=elements,
            texts=texts,
            context_window=self.config.BOUNDARY_CONTEXT_WINDOW,
            adjacent_similarities=adjacent_similarities,
        )
        self.tentative_blocks = self._build_tentative_blocks(document.id, self.boundary_candidates)
        self.refined_groups = self._build_refined_groups(
            document_id=document.id,
            tentative_blocks=self.tentative_blocks,
            allow_llm=False,
        )
        self.refined_groups = self._repair_refined_groups(
            document_id=document.id,
            groups=self.refined_groups,
        )
        threshold = similarity_mean - (similarity_std * self.config.DEPTH_SCORE_SENSITIVITY)
        merge_priors = self._compute_merge_priors(elements, adjacent_similarities, threshold, similarity_std)

        blocks = self._build_blocks(elements)
        chunks: list[list[ExtractedElement]] = []
        for start, end, trailing_decision in blocks:
            if start <= end:
                block_chunks = self._resolve_block(
                    elements=elements,
                    texts=texts,
                    adjacent_similarities=adjacent_similarities,
                    merge_priors=merge_priors,
                    threshold=threshold,
                    sigma=similarity_std,
                    start=start,
                    end=end,
                )
                chunks.extend(block_chunks)
            if trailing_decision is not None:
                self.boundary_log.append(trailing_decision)
        return chunks

    def _sorted_elements(self, document: ExtractedDocument) -> list[ExtractedElement]:
        elements = [element for page in document.pages for element in page.elements]
        return sorted(elements, key=lambda item: (item.page_number, item.order))

    def build_boundary_candidates(
        self,
        document: ExtractedDocument,
        *,
        context_window: int | None = None,
    ) -> list[BoundaryCandidate]:
        """Return the full adjacent-boundary ledger for a document."""
        elements = self._sorted_elements(document)
        if len(elements) < 2:
            return []
        texts = [self.preprocessor.to_text(element) for element in elements]
        adjacent_similarities, _, _ = self._compute_similarity_stats(texts)
        return self._build_boundary_candidates(
            document_id=document.id,
            elements=elements,
            texts=texts,
            context_window=self.config.BOUNDARY_CONTEXT_WINDOW if context_window is None else context_window,
            adjacent_similarities=adjacent_similarities,
        )

    def build_tentative_blocks(
        self,
        document: ExtractedDocument,
        *,
        context_window: int | None = None,
    ) -> list[TentativeBlock]:
        """Return tentative blocks formed by high-confidence preliminary boundaries."""
        elements = self._sorted_elements(document)
        if not elements:
            return []
        texts = [self.preprocessor.to_text(element) for element in elements]
        if len(elements) == 1:
            return self._single_tentative_block(document.id, elements[0], texts[0])
        adjacent_similarities, _, _ = self._compute_similarity_stats(texts)
        candidates = self._build_boundary_candidates(
            document_id=document.id,
            elements=elements,
            texts=texts,
            context_window=self.config.BOUNDARY_CONTEXT_WINDOW if context_window is None else context_window,
            adjacent_similarities=adjacent_similarities,
        )
        return self._build_tentative_blocks(document.id, candidates)

    def build_refined_groups(
        self,
        document: ExtractedDocument,
        *,
        context_window: int | None = None,
        allow_llm: bool = True,
        refinement_strategy: str | None = None,
    ) -> list[RefinedChunkGroup]:
        """Return concept-sized groups refined within tentative blocks."""
        tentative_blocks = self.build_tentative_blocks(document, context_window=context_window)
        return self._build_refined_groups(
            document_id=document.id,
            tentative_blocks=tentative_blocks,
            allow_llm=allow_llm,
            refinement_strategy=refinement_strategy or self.config.STEP5_REFINEMENT_STRATEGY,
        )

    def build_repaired_groups(
        self,
        document: ExtractedDocument,
        *,
        context_window: int | None = None,
        allow_llm: bool = True,
        refinement_strategy: str | None = None,
    ) -> list[RefinedChunkGroup]:
        """Return Step 6 repaired groups after active refinement."""
        elements = self._sorted_elements(document)
        self.boundary_candidates = []
        self.tentative_blocks = []
        self.refined_groups = []
        self.repair_decisions = []
        self.llm_calls = 0
        self.recoverable_errors = []
        if not elements:
            return []
        texts = [self.preprocessor.to_text(element) for element in elements]
        if len(elements) == 1:
            self.tentative_blocks = self._single_tentative_block(document.id, elements[0], texts[0])
        else:
            adjacent_similarities, _, _ = self._compute_similarity_stats(texts)
            self.boundary_candidates = self._build_boundary_candidates(
                document_id=document.id,
                elements=elements,
                texts=texts,
                context_window=self.config.BOUNDARY_CONTEXT_WINDOW if context_window is None else context_window,
                adjacent_similarities=adjacent_similarities,
            )
            self.tentative_blocks = self._build_tentative_blocks(document.id, self.boundary_candidates)
        refined_groups = self._build_refined_groups(
            document_id=document.id,
            tentative_blocks=self.tentative_blocks,
            allow_llm=allow_llm,
            refinement_strategy=refinement_strategy or self.config.STEP5_REFINEMENT_STRATEGY,
        )
        repaired_groups = self._repair_refined_groups(
            document_id=document.id,
            groups=refined_groups,
        )
        if allow_llm:
            repaired_groups = self._llm_audit_repaired_groups(
                document_id=document.id,
                groups=repaired_groups,
            )
        self.refined_groups = repaired_groups
        return self.refined_groups

    def _single_tentative_block(
        self,
        document_id: str,
        element: ExtractedElement,
        text: str,
    ) -> list[TentativeBlock]:
        return [
            TentativeBlock(
                block_id=f"{document_id}::block::00000",
                block_index=0,
                elements=[self._element_view(element, text)],
                start_element_index=0,
                end_element_index=0,
                stability="locked",
                reason_summary="single element document",
            )
        ]

    def _build_boundary_candidates(
        self,
        *,
        document_id: str,
        elements: list[ExtractedElement],
        texts: list[str],
        context_window: int,
        adjacent_similarities: list[float] | None = None,
    ) -> list[BoundaryCandidate]:
        window = max(0, int(context_window))
        views = [self._element_view(element, texts[index]) for index, element in enumerate(elements)]
        candidates: list[BoundaryCandidate] = []
        similarities = adjacent_similarities or []
        for index in range(len(views) - 1):
            left = views[index]
            right = views[index + 1]
            page_gap = right.page_number - left.page_number
            order_gap = right.order - left.order
            similarity = similarities[index] if index < len(similarities) else 0.0
            signals = self._boundary_signals(left, right, page_gap, order_gap, similarity)
            candidates.append(
                BoundaryCandidate(
                    boundary_id=f"{document_id}::boundary::{index:05d}",
                    boundary_index=index,
                    left=left,
                    right=right,
                    left_context=views[max(0, index - window):index],
                    right_context=views[index + 2:index + 2 + window],
                    same_page=left.page_number == right.page_number,
                    page_gap=page_gap,
                    order_gap=order_gap,
                    signals=signals,
                    preliminary_decision=self._preliminary_decision(signals),
                )
            )
        return candidates

    def _build_tentative_blocks(
        self,
        document_id: str,
        candidates: list[BoundaryCandidate],
    ) -> list[TentativeBlock]:
        if not candidates:
            return []
        element_views = [candidates[0].left] + [candidate.right for candidate in candidates]
        blocks: list[TentativeBlock] = []
        start_element_index = 0
        start_boundary: BoundaryCandidate | None = None
        for candidate in candidates:
            if not self._is_tentative_block_divider(candidate):
                continue
            end_element_index = candidate.boundary_index
            blocks.append(
                self._make_tentative_block(
                    document_id=document_id,
                    block_index=len(blocks),
                    elements=element_views,
                    candidates=candidates,
                    start_element_index=start_element_index,
                    end_element_index=end_element_index,
                    start_boundary=start_boundary,
                    end_boundary=candidate,
                )
            )
            start_element_index = candidate.boundary_index + 1
            start_boundary = candidate
        blocks.append(
            self._make_tentative_block(
                document_id=document_id,
                block_index=len(blocks),
                elements=element_views,
                candidates=candidates,
                start_element_index=start_element_index,
                end_element_index=len(element_views) - 1,
                start_boundary=start_boundary,
                end_boundary=None,
            )
        )
        return blocks

    def _make_tentative_block(
        self,
        *,
        document_id: str,
        block_index: int,
        elements: list[BoundaryElementView],
        candidates: list[BoundaryCandidate],
        start_element_index: int,
        end_element_index: int,
        start_boundary: BoundaryCandidate | None,
        end_boundary: BoundaryCandidate | None,
    ) -> TentativeBlock:
        internal_boundaries = [
            candidate
            for candidate in candidates
            if start_element_index <= candidate.boundary_index < end_element_index
        ]
        stability = self._tentative_block_stability(internal_boundaries)
        reason_summary = self._tentative_block_reason_summary(
            internal_boundaries=internal_boundaries,
            start_boundary=start_boundary,
            end_boundary=end_boundary,
            stability=stability,
        )
        return TentativeBlock(
            block_id=f"{document_id}::block::{block_index:05d}",
            block_index=block_index,
            elements=elements[start_element_index:end_element_index + 1],
            start_element_index=start_element_index,
            end_element_index=end_element_index,
            start_boundary=start_boundary,
            end_boundary=end_boundary,
            internal_boundaries=internal_boundaries,
            stability=stability,
            reason_summary=reason_summary,
        )

    def _is_tentative_block_divider(self, candidate: BoundaryCandidate) -> bool:
        decision = candidate.preliminary_decision
        return (
            decision is not None
            and decision.decision == "split"
            and decision.confidence >= self.config.TENTATIVE_BLOCK_SPLIT_CONFIDENCE
        )

    def _tentative_block_stability(self, internal_boundaries: list[BoundaryCandidate]) -> str:
        if not internal_boundaries:
            return "locked"
        decisions = [boundary.preliminary_decision for boundary in internal_boundaries]
        if any(decision is None or decision.decision == "unknown" for decision in decisions):
            return "ambiguous"
        if any(
            decision.decision == "split" and decision.confidence < self.config.TENTATIVE_BLOCK_SPLIT_CONFIDENCE
            for decision in decisions
            if decision is not None
        ):
            return "ambiguous"
        if all(
            decision is not None
            and decision.decision == "continue"
            and decision.confidence >= self.config.TENTATIVE_BLOCK_CONTINUE_CONFIDENCE
            for decision in decisions
        ):
            return "likely_good"
        return "ambiguous"

    def _tentative_block_reason_summary(
        self,
        *,
        internal_boundaries: list[BoundaryCandidate],
        start_boundary: BoundaryCandidate | None,
        end_boundary: BoundaryCandidate | None,
        stability: str,
    ) -> str:
        parts = [f"stability={stability}", f"internal_boundaries={len(internal_boundaries)}"]
        unknown_count = sum(
            1
            for boundary in internal_boundaries
            if boundary.preliminary_decision is None or boundary.preliminary_decision.decision == "unknown"
        )
        continue_count = sum(
            1
            for boundary in internal_boundaries
            if boundary.preliminary_decision is not None and boundary.preliminary_decision.decision == "continue"
        )
        if continue_count:
            parts.append(f"continues={continue_count}")
        if unknown_count:
            parts.append(f"unknown={unknown_count}")
        if start_boundary is not None and start_boundary.preliminary_decision is not None:
            reason = "; ".join(start_boundary.preliminary_decision.reasons[:2])
            parts.append(f"starts_after={start_boundary.boundary_id} ({reason})")
        if end_boundary is not None and end_boundary.preliminary_decision is not None:
            reason = "; ".join(end_boundary.preliminary_decision.reasons[:2])
            parts.append(f"ends_at={end_boundary.boundary_id} ({reason})")
        return "; ".join(parts)

    def _build_refined_groups(
        self,
        *,
        document_id: str,
        tentative_blocks: list[TentativeBlock],
        allow_llm: bool,
        refinement_strategy: str | None = None,
    ) -> list[RefinedChunkGroup]:
        refinement_strategy = self._normalize_refinement_strategy(
            refinement_strategy or self.config.STEP5_REFINEMENT_STRATEGY
        )
        if (
            allow_llm
            and self.llm_client is not None
            and len(tentative_blocks) > 1
            and int(self.config.MAX_LLM_CALLS_PER_BOUNDARY) > 0
            and refinement_strategy != "semantic_walk"
        ):
            return self._build_refined_groups_concurrently(
                document_id=document_id,
                tentative_blocks=tentative_blocks,
                allow_llm=allow_llm,
                refinement_strategy=refinement_strategy,
            )
        groups: list[RefinedChunkGroup] = []
        for block in tentative_blocks:
            groups.extend(
                self._refine_tentative_block_with_strategy(
                    document_id=document_id,
                    block=block,
                    first_group_index=len(groups),
                    allow_llm=allow_llm,
                    refinement_strategy=refinement_strategy,
                )
            )
        return groups

    def _normalize_refinement_strategy(self, refinement_strategy: str) -> str:
        strategy = (refinement_strategy or "galloping").strip().lower()
        if strategy in {"semantic", "semantic_walk", "level4"}:
            return "semantic_walk"
        if strategy not in {"galloping", "block", "semantic_walk"}:
            raise ValueError(f"Unknown refinement strategy: {refinement_strategy}")
        return strategy

    def _build_refined_groups_concurrently(
        self,
        *,
        document_id: str,
        tentative_blocks: list[TentativeBlock],
        allow_llm: bool,
        refinement_strategy: str,
    ) -> list[RefinedChunkGroup]:
        max_workers = min(
            len(tentative_blocks),
            max(1, int(os.environ.get("CONTEXTUS_LLM_CONCURRENCY", "4"))),
        )
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="contextus-step5") as executor:
            futures = [
                executor.submit(
                    self._refine_tentative_block_with_strategy,
                    document_id=document_id,
                    block=block,
                    first_group_index=0,
                    allow_llm=allow_llm,
                    refinement_strategy=refinement_strategy,
                )
                for block in tentative_blocks
            ]
            block_groups = [future.result() for future in futures]

        groups = [group for result in block_groups for group in result]
        for group_index, group in enumerate(groups):
            group.group_index = group_index
            group.group_id = f"{document_id}::group::{group_index:05d}"
        return groups

    def _refine_tentative_block_with_strategy(
        self,
        *,
        document_id: str,
        block: TentativeBlock,
        first_group_index: int,
        allow_llm: bool,
        refinement_strategy: str,
    ) -> list[RefinedChunkGroup]:
        if refinement_strategy == "block":
            return self._refine_tentative_block_by_segmentation(
                document_id=document_id,
                block=block,
                first_group_index=first_group_index,
                allow_llm=allow_llm,
            )
        if refinement_strategy == "semantic_walk":
            return self._refine_tentative_block_by_semantic_walk(
                document_id=document_id,
                block=block,
                first_group_index=first_group_index,
            )
        return self._refine_tentative_block(
            document_id=document_id,
            block=block,
            first_group_index=first_group_index,
            allow_llm=allow_llm,
        )

    def _refine_tentative_block(
        self,
        *,
        document_id: str,
        block: TentativeBlock,
        first_group_index: int,
        allow_llm: bool,
    ) -> list[RefinedChunkGroup]:
        if not block.elements:
            return []
        if not block.internal_boundaries:
            return [
                self._make_refined_group(
                    document_id=document_id,
                    block=block,
                    group_index=first_group_index,
                    start_offset=0,
                    end_offset=len(block.elements) - 1,
                    probe_decisions=[],
                )
            ]

        groups: list[RefinedChunkGroup] = []
        group_start_offset = 0
        current_decisions: list[ConceptProbeDecision] = []
        for boundary in block.internal_boundaries:
            active_end_offset = boundary.boundary_index - block.start_element_index
            if active_end_offset < group_start_offset:
                continue
            probe_decision = self._refine_concept_boundary(
                block=block,
                boundary=boundary,
                group_start_offset=group_start_offset,
                active_end_offset=active_end_offset,
                allow_llm=allow_llm,
            )
            current_decisions.append(probe_decision)
            if probe_decision.decision in {"split", "unsure"}:
                groups.append(
                    self._make_refined_group(
                        document_id=document_id,
                        block=block,
                        group_index=first_group_index + len(groups),
                        start_offset=group_start_offset,
                        end_offset=active_end_offset,
                        probe_decisions=current_decisions,
                    )
                )
                group_start_offset = active_end_offset + 1
                current_decisions = []

        if group_start_offset < len(block.elements):
            groups.append(
                self._make_refined_group(
                    document_id=document_id,
                    block=block,
                    group_index=first_group_index + len(groups),
                    start_offset=group_start_offset,
                    end_offset=len(block.elements) - 1,
                    probe_decisions=current_decisions,
                )
            )
        return groups

    def _refine_tentative_block_by_segmentation(
        self,
        *,
        document_id: str,
        block: TentativeBlock,
        first_group_index: int,
        allow_llm: bool,
    ) -> list[RefinedChunkGroup]:
        if not block.elements:
            return []
        if not block.internal_boundaries:
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_trivial",
                reason="block_segmentation skipped; no internal boundaries",
            )
        if not allow_llm or self.llm_client is None or int(self.config.MAX_LLM_CALLS_PER_BOUNDARY) <= 0:
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_unavailable",
                reason="block_segmentation unavailable; LLM refinement disabled",
            )
        if len(block.elements) > max(1, int(self.config.BLOCK_SEGMENTATION_MAX_ELEMENTS)):
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_skipped",
                reason=f"block_segmentation skipped; element_count={len(block.elements)} exceeds configured cap",
            )
        total_chars = sum(len(element.text or "") for element in block.elements)
        if total_chars > max(1, int(self.config.BLOCK_SEGMENTATION_MAX_CHARS)):
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_skipped",
                reason=f"block_segmentation skipped; char_count={total_chars} exceeds configured cap",
            )

        prompt = self._block_segmentation_prompt(block)
        try:
            response = self.llm_client.complete(
                system=(
                    "You decide multiple adjacent extracted document boundaries at once. "
                    "Return only one compact JSON object."
                ),
                user=prompt,
                temperature=0.0,
                response_format=self._block_segmentation_response_format(),
            )
        except Exception as exc:  # pragma: no cover - defensive around external model clients
            self.recoverable_errors.append(f"Block segmentation call failed: {exc}")
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_error",
                reason=f"block_segmentation failed; {exc}",
            )

        self._record_llm_call()
        decision = self._parse_block_segmentation_response(
            getattr(response, "content", str(response)),
            block=block,
        )
        if decision.confidence < self.config.BLOCK_SEGMENTATION_CONFIDENCE_THRESHOLD:
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_rejected",
                reason=(
                    f"block_segmentation rejected; confidence={decision.confidence:.2f}; "
                    f"split_starts={','.join(decision.split_start_element_ids) or 'none'}; "
                    f"{decision.reason}"
                ).strip(),
            )
        split_offsets = self._validated_block_split_offsets(block, decision.split_start_element_ids)
        if split_offsets is None:
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="block_segmentation_rejected",
                reason=(
                    f"block_segmentation rejected; invalid split_start_element_ids="
                    f"{','.join(decision.split_start_element_ids) or 'none'}; {decision.reason}"
                ).strip(),
            )

        boundaries = [0, *split_offsets, len(block.elements)]
        groups: list[RefinedChunkGroup] = []
        for piece_index in range(len(boundaries) - 1):
            group = self._make_refined_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index + piece_index,
                start_offset=boundaries[piece_index],
                end_offset=boundaries[piece_index + 1] - 1,
                probe_decisions=[],
            )
            group.search_strategy = "block_segmentation"
            group.reason_summary = (
                f"block_segmentation confidence={decision.confidence:.2f}; "
                f"split_starts={','.join(decision.split_start_element_ids) or 'none'}; "
                f"{decision.reason}"
            ).strip()
            groups.append(group)
        return groups

    def _refine_tentative_block_by_semantic_walk(
        self,
        *,
        document_id: str,
        block: TentativeBlock,
        first_group_index: int,
    ) -> list[RefinedChunkGroup]:
        if not block.elements:
            return []
        if not block.internal_boundaries:
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="semantic_walk_trivial",
                reason="semantic_walk skipped; no internal boundaries",
            )

        distances = self._semantic_walk_distances(block.elements)
        eligible_boundary_offsets = {
            boundary.boundary_index - block.start_element_index
            for boundary in block.internal_boundaries
        }
        if len(distances) < max(1, int(self.config.SEMANTIC_WALK_MIN_BOUNDARIES)):
            split_offsets: list[int] = []
            threshold = None
        else:
            threshold = float(
                np.percentile(
                    distances,
                    max(0.0, min(100.0, float(self.config.SEMANTIC_WALK_BREAKPOINT_PERCENTILE))),
                )
            )
            min_distance = max(0.0, float(self.config.SEMANTIC_WALK_MIN_DISTANCE))
            split_offsets = [
                distance_index + 1
                for distance_index, distance in enumerate(distances)
                if (
                    distance_index in eligible_boundary_offsets
                    and distance > threshold
                    and distance >= min_distance
                )
            ]

        if not split_offsets:
            reason = "semantic_walk found no breakpoint outliers"
            if threshold is not None:
                reason = f"{reason}; threshold={threshold:.3f}"
            return self._make_single_block_segmentation_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index,
                search_strategy="semantic_walk",
                reason=reason,
            )

        boundaries = [0, *split_offsets, len(block.elements)]
        groups: list[RefinedChunkGroup] = []
        threshold_note = f"{threshold:.3f}" if threshold is not None else "n/a"
        split_start_ids = [block.elements[offset].element_id for offset in split_offsets]
        for piece_index in range(len(boundaries) - 1):
            group = self._make_refined_group(
                document_id=document_id,
                block=block,
                group_index=first_group_index + piece_index,
                start_offset=boundaries[piece_index],
                end_offset=boundaries[piece_index + 1] - 1,
                probe_decisions=[],
            )
            group.search_strategy = "semantic_walk"
            group.reason_summary = (
                f"semantic_walk threshold={threshold_note}; "
                f"split_starts={','.join(split_start_ids)}"
            )
            groups.append(group)
        return groups

    def _semantic_walk_distances(self, elements: list[BoundaryElementView]) -> list[float]:
        combined_texts = self._semantic_walk_combined_texts(elements)
        if len(combined_texts) < 2:
            return []
        embeddings = self._embed_texts(combined_texts)
        distances: list[float] = []
        for index in range(len(embeddings) - 1):
            similarity = float(np.dot(embeddings[index], embeddings[index + 1]))
            distances.append(max(0.0, min(2.0, 1.0 - similarity)))
        return distances

    def _semantic_walk_combined_texts(self, elements: list[BoundaryElementView]) -> list[str]:
        buffer_size = max(0, int(self.config.SEMANTIC_WALK_BUFFER_SIZE))
        combined_texts: list[str] = []
        for index in range(len(elements)):
            start = max(0, index - buffer_size)
            end = min(len(elements), index + buffer_size + 1)
            combined_texts.append(
                "\n".join(
                    self._normalized_text(element.text)
                    for element in elements[start:end]
                    if self._normalized_text(element.text)
                )
            )
        return combined_texts

    def _make_single_block_segmentation_group(
        self,
        *,
        document_id: str,
        block: TentativeBlock,
        group_index: int,
        search_strategy: str,
        reason: str,
    ) -> list[RefinedChunkGroup]:
        group = self._make_refined_group(
            document_id=document_id,
            block=block,
            group_index=group_index,
            start_offset=0,
            end_offset=len(block.elements) - 1,
            probe_decisions=[],
        )
        group.search_strategy = search_strategy
        group.reason_summary = reason
        return [group]

    def _validated_block_split_offsets(
        self,
        block: TentativeBlock,
        split_start_element_ids: list[str],
    ) -> list[int] | None:
        offset_by_id = {element.element_id: offset for offset, element in enumerate(block.elements)}
        split_offsets: list[int] = []
        for element_id in split_start_element_ids:
            if element_id not in offset_by_id:
                return None
            offset = offset_by_id[element_id]
            if offset <= 0:
                return None
            split_offsets.append(offset)
        if split_offsets != sorted(split_offsets) or len(set(split_offsets)) != len(split_offsets):
            return None
        return split_offsets

    def _make_refined_group(
        self,
        *,
        document_id: str,
        block: TentativeBlock,
        group_index: int,
        start_offset: int,
        end_offset: int,
        probe_decisions: list[ConceptProbeDecision],
    ) -> RefinedChunkGroup:
        start_element_index = block.start_element_index + start_offset
        end_element_index = block.start_element_index + end_offset
        internal_boundaries = [
            boundary
            for boundary in block.internal_boundaries
            if start_element_index <= boundary.boundary_index < end_element_index
        ]
        decisions = list(probe_decisions)
        stability = self._refined_group_stability(internal_boundaries, decisions, block.stability)
        return RefinedChunkGroup(
            group_id=f"{document_id}::group::{group_index:05d}",
            group_index=group_index,
            source_block_id=block.block_id,
            elements=block.elements[start_offset:end_offset + 1],
            start_element_index=start_element_index,
            end_element_index=end_element_index,
            internal_boundaries=internal_boundaries,
            probe_decisions=decisions,
            stability=stability,
            reason_summary=self._refined_group_reason_summary(stability, internal_boundaries, decisions),
        )

    def _refined_group_stability(
        self,
        internal_boundaries: list[BoundaryCandidate],
        probe_decisions: list[ConceptProbeDecision],
        block_stability: str,
    ) -> str:
        if not internal_boundaries:
            return "locked" if block_stability == "locked" else "likely_good"
        if any(decision.decision == "unsure" or decision.source == "fallback" for decision in probe_decisions):
            return "ambiguous"
        if all(
            decision.decision == "continue"
            and decision.confidence >= self.config.ACTIVE_REFINEMENT_CONTINUE_CONFIDENCE
            for decision in probe_decisions
        ):
            return "likely_good"
        return "ambiguous"

    def _refined_group_reason_summary(
        self,
        stability: str,
        internal_boundaries: list[BoundaryCandidate],
        probe_decisions: list[ConceptProbeDecision],
    ) -> str:
        parts = [f"stability={stability}", f"internal_boundaries={len(internal_boundaries)}"]
        if probe_decisions:
            decisions = {decision.decision for decision in probe_decisions}
            sources = {decision.source for decision in probe_decisions}
            parts.append(f"decisions={','.join(sorted(decisions))}")
            parts.append(f"sources={','.join(sorted(sources))}")
        return "; ".join(parts)

    def _record_llm_call(self) -> None:
        with self._llm_calls_lock:
            self.llm_calls += 1

    def _repair_refined_groups(
        self,
        *,
        document_id: str,
        groups: list[RefinedChunkGroup],
    ) -> list[RefinedChunkGroup]:
        if not groups:
            return []
        self.repair_decisions = []
        states = self._repair_states_from_groups(groups)
        index_by_element_id = self._element_index_map(groups)
        boundary_by_index = self._boundary_index_map(groups)

        index = 0
        while index < len(states):
            if not states[index].elements:
                del states[index]
                continue
            if self._is_support_only_group(states[index]):
                if index > 0 and self._group_text_owns_support(states[index - 1].elements, states[index].elements):
                    self._merge_group_into_previous(
                        states,
                        index,
                        action="merge_orphan_support_with_previous",
                        confidence=0.88,
                        reason="previous chunk text explicitly owns the support-only chunk",
                    )
                    index = max(0, index - 1)
                    continue
                if index + 1 < len(states) and self._starts_with_heading(states[index + 1]):
                    self._merge_group_into_next(
                        states,
                        index,
                        action="merge_orphan_support_with_next",
                        confidence=0.86,
                        reason="support-only chunk appears immediately before a title-led chunk",
                    )
                    index = max(0, index - 1)
                    continue
                if index > 0:
                    self._merge_group_into_previous(
                        states,
                        index,
                        action="merge_orphan_support_with_previous",
                        confidence=0.82,
                        reason="support-only chunk has no local text of its own",
                    )
                    index = max(0, index - 1)
                    continue
                if index + 1 < len(states):
                    self._merge_group_into_next(
                        states,
                        index,
                        action="merge_orphan_support_with_next",
                        confidence=0.78,
                        reason="support-only chunk starts the document region",
                    )
                    index = max(0, index - 1)
                    continue
            if (
                index + 1 < len(states)
                and self._is_repaired_scaffold_group(states[index])
                and self._has_substantive_body_text(states[index + 1].elements)
            ):
                self._merge_group_into_next(
                    states,
                    index,
                    action="merge_repaired_scaffold_with_body",
                    confidence=0.86,
                    reason="a repaired heading/support scaffold should travel with the nearby body text",
                )
                index = max(0, index - 1)
                continue
            if index + 1 < len(states) and self._is_heading_scaffold_group(states[index]):
                self._merge_group_into_next(
                    states,
                    index,
                    action="merge_heading_with_next",
                    confidence=0.9,
                    reason="heading scaffold should travel with the body it introduces",
                )
                index = max(0, index - 1)
                continue
            if index + 1 < len(states) and self._is_bridge_text_group(states[index]):
                self._merge_group_into_next(
                    states,
                    index,
                    action="merge_bridge_text_with_next",
                    confidence=0.84,
                    reason="short bridge text points to following material",
                )
                index = max(0, index - 1)
                continue
            if index > 0 and self._is_dangling_text_group(states[index]):
                self._merge_group_into_previous(
                    states,
                    index,
                    action="merge_dangling_text_with_previous",
                    confidence=0.8,
                    reason="short text chunk appears to continue a previous thought",
                )
                index = max(0, index - 1)
                continue
            index += 1

        return [
            self._make_repaired_group(
                document_id=document_id,
                group_index=group_index,
                state=state,
                index_by_element_id=index_by_element_id,
                boundary_by_index=boundary_by_index,
            )
            for group_index, state in enumerate(states)
            if state.elements
        ]

    def _repair_states_from_groups(self, groups: list[RefinedChunkGroup]) -> list[_RepairGroupState]:
        return [
            _RepairGroupState(
                source_group_ids=[group.group_id],
                source_block_ids=[group.source_block_id],
                elements=list(group.elements),
                internal_boundaries=list(group.internal_boundaries),
                probe_decisions=list(group.probe_decisions),
                repair_decisions=list(group.repair_decisions),
                stability=group.stability,
                reason_summary=group.reason_summary,
            )
            for group in groups
        ]

    def _llm_audit_repaired_groups(
        self,
        *,
        document_id: str,
        groups: list[RefinedChunkGroup],
    ) -> list[RefinedChunkGroup]:
        if not groups or self.llm_client is None or int(self.config.LOCAL_AUDIT_MAX_CALLS) <= 0:
            return groups

        states = self._repair_states_from_groups(groups)
        index_by_element_id = self._element_index_map(groups)
        boundary_by_index = self._boundary_index_map(groups)
        audited_signatures: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        audit_calls = 0
        max_calls = max(0, int(self.config.LOCAL_AUDIT_MAX_CALLS))

        while audit_calls < max_calls:
            states[:] = [state for state in states if state.elements]
            jobs = self._select_local_audit_round_jobs(
                states=states,
                audited_signatures=audited_signatures,
                remaining_calls=max_calls - audit_calls,
            )
            if not jobs:
                break

            for job in jobs:
                audited_signatures.add(job.signature)
            responses = self._run_local_audit_jobs(jobs)
            audit_calls += len(jobs)

            for job, content in sorted(responses, key=lambda item: item[0].index, reverse=True):
                if content is None or job.index >= len(states):
                    continue
                decision = self._parse_local_audit_response(content)
                if decision.confidence < self.config.LOCAL_AUDIT_CONFIDENCE_THRESHOLD:
                    continue
                if decision.action == "needs_wider_review" and audit_calls < max_calls:
                    expanded_decision = self._run_expanded_local_audit(
                        states=states,
                        index=job.index,
                        risk_flags=job.risk_flags,
                        reason=decision.reason,
                    )
                    audit_calls += 1
                    if (
                        expanded_decision is not None
                        and expanded_decision.confidence >= self.config.LOCAL_AUDIT_CONFIDENCE_THRESHOLD
                    ):
                        decision = expanded_decision
                    if decision.confidence < self.config.LOCAL_AUDIT_CONFIDENCE_THRESHOLD:
                        continue
                self._apply_local_audit_decision(states, job.index, decision)

        return [
            self._make_repaired_group(
                document_id=document_id,
                group_index=group_index,
                state=state,
                index_by_element_id=index_by_element_id,
                boundary_by_index=boundary_by_index,
            )
            for group_index, state in enumerate(states)
            if state.elements
        ]

    def _select_local_audit_round_jobs(
        self,
        *,
        states: list[_RepairGroupState],
        audited_signatures: set[tuple[tuple[str, ...], tuple[str, ...]]],
        remaining_calls: int,
    ) -> list[_LocalAuditJob]:
        jobs: list[_LocalAuditJob] = []
        blocked_indices: set[int] = set()
        for index in self._local_audit_scan_order(states):
            if len(jobs) >= remaining_calls:
                break
            state = states[index]
            if not state.elements:
                continue
            window = set(range(max(0, index - 1), min(len(states), index + 2)))
            if window & blocked_indices:
                continue
            risk_flags = self._local_audit_risk_flags(states, index)
            signature = (
                tuple(element.element_id for element in state.elements),
                tuple(risk_flags),
            )
            if not risk_flags or signature in audited_signatures:
                continue
            jobs.append(
                _LocalAuditJob(
                    index=index,
                    risk_flags=risk_flags,
                    signature=signature,
                    prompt=self._local_audit_prompt(states, index, risk_flags),
                )
            )
            blocked_indices.update(window)
        return jobs

    def _local_audit_scan_order(self, states: list[_RepairGroupState]) -> list[int]:
        fresh_split_indices = [
            index
            for index, state in enumerate(states)
            if self._is_fresh_split_edge_piece(state)
        ]
        normal_indices = [
            index
            for index in range(len(states))
            if index not in set(fresh_split_indices)
        ]
        return fresh_split_indices + normal_indices

    def _run_local_audit_jobs(self, jobs: list[_LocalAuditJob]) -> list[tuple[_LocalAuditJob, str | None]]:
        system = (
            "You audit local document chunks for ingestion quality. "
            "Return only one compact JSON object."
        )
        response_format = self._local_audit_response_format()
        if hasattr(self.llm_client, "submit"):
            futures = [
                (
                    job,
                    self.llm_client.submit(
                        system=system,
                        user=job.prompt,
                        temperature=0.0,
                        response_format=response_format,
                    ),
                )
                for job in jobs
            ]
            results: list[tuple[_LocalAuditJob, str | None]] = []
            for job, future in futures:
                try:
                    response = future.result()
                except Exception as exc:  # pragma: no cover - defensive around external model clients
                    self.recoverable_errors.append(f"Local chunk audit call failed: {exc}")
                    results.append((job, None))
                    continue
                self._record_llm_call()
                results.append((job, getattr(response, "content", str(response))))
            return results

        results = []
        for job in jobs:
            try:
                response = self.llm_client.complete(
                    system=system,
                    user=job.prompt,
                    temperature=0.0,
                    response_format=response_format,
                )
            except Exception as exc:  # pragma: no cover - defensive around external model clients
                self.recoverable_errors.append(f"Local chunk audit call failed: {exc}")
                results.append((job, None))
                continue
            self._record_llm_call()
            results.append((job, getattr(response, "content", str(response))))
        return results

    def _run_expanded_local_audit(
        self,
        *,
        states: list[_RepairGroupState],
        index: int,
        risk_flags: list[str],
        reason: str,
    ) -> _LocalAuditDecision | None:
        if index >= len(states) or not states[index].elements:
            return None
        base_edge_count = max(1, int(self.config.LOCAL_AUDIT_EDGE_ELEMENTS))
        expanded_edge_count = max(
            base_edge_count + 1,
            int(self.config.CONTEXT_EXPANSION_MAX_ELEMENTS),
        )
        prompt = self._local_audit_prompt(
            states,
            index,
            risk_flags,
            edge_count=expanded_edge_count,
            review_note=(
                "This is an expanded second-pass review because the first local audit "
                f"requested wider context: {reason or 'no reason provided'}"
            ),
        )
        job = _LocalAuditJob(
            index=index,
            risk_flags=risk_flags,
            signature=(
                tuple(element.element_id for element in states[index].elements),
                tuple([*risk_flags, "expanded_context_review"]),
            ),
            prompt=prompt,
        )
        responses = self._run_local_audit_jobs([job])
        content = responses[0][1] if responses else None
        if content is None:
            return None
        return self._parse_local_audit_response(content)

    def _local_audit_risk_flags(self, states: list[_RepairGroupState], index: int) -> list[str]:
        state = states[index]
        if not state.elements:
            return []

        flags: list[str] = []
        heading_count = sum(1 for element in state.elements if self._is_heading_element(element))
        next_state = states[index + 1] if index + 1 < len(states) else None

        if self._is_support_only_group(state):
            flags.append("support_only_chunk")
        if len(state.elements) == 1 and self._is_heading_element(state.elements[0]):
            flags.append("heading_only_chunk")
        if len(state.elements) == 1 and state.elements[0].element_type == "text":
            flags.append("singleton_text_chunk")
        if heading_count > 1:
            flags.append("multiple_headings_in_chunk")
        if heading_count and not self._has_substantive_body_text(state.elements):
            flags.append("heading_without_body_text")
        if self._is_dangling_text_group(state):
            flags.append("dangling_short_text")
        if self._is_bridge_text_group(state):
            flags.append("bridge_text_only")
        if (
            next_state is not None
            and state.elements
            and self._is_support_element(state.elements[-1])
            and self._starts_with_heading(next_state)
        ):
            flags.append("trailing_support_before_next_heading")
        if self._is_visual_edge_support_candidate(states, index):
            flags.append("visual_edge_support_candidate")
        if self._is_mixed_visual_support_candidate(states, index):
            flags.append("mixed_visual_support_candidate")
        if self._is_possible_internal_split_candidate(state):
            flags.append("possible_internal_split")
        return flags

    def _local_audit_prompt(
        self,
        states: list[_RepairGroupState],
        index: int,
        risk_flags: list[str],
        *,
        edge_count: int | None = None,
        review_note: str = "",
    ) -> str:
        edge_count = max(1, int(self.config.LOCAL_AUDIT_EDGE_ELEMENTS) if edge_count is None else edge_count)
        previous_elements = states[index - 1].elements[-edge_count:] if index > 0 else []
        current_elements = states[index].elements
        next_elements = states[index + 1].elements[:edge_count] if index + 1 < len(states) else []

        risk_lines = [f"- {flag.replace('_', ' ')}" for flag in risk_flags]
        review_note_lines = [review_note, ""] if review_note else []
        action_lines = [
            "- keep: the current chunk is acceptable.",
            "- move_current_prefix_to_previous: the first one or more current elements belong at the end of the previous chunk.",
            "- move_current_suffix_to_next: the final one or more current elements belong at the start of the next chunk.",
            "- pull_next_prefix_to_current: the first one or more next elements belong at the end of the current chunk.",
            "- split_current: the current chunk contains 2 or 3 independent small knowledge units and should be split internally.",
            "- needs_wider_review: this local view is insufficient for a safe decision.",
        ]

        return "\n".join(
            [
                "You are auditing one proposed document chunk before it becomes input for a knowledge-building system.",
                "",
                *review_note_lines,
                "The system turns chunks into small knowledge units.",
                "A useful small knowledge unit should let a later model write one clear concept, claim, definition, procedure step, example, relationship, or support/evidence item without inventing missing context.",
                "A good chunk usually has one main idea or object, is complete enough to understand locally, and keeps figures, tables, formulas, captions, or examples with the text they support.",
                "Do not punish a chunk just because it is short, visual-heavy, title+figure, title+phrase, or has a repeated slide/page title.",
                "A single text-element chunk can be valid if it is a complete standalone definition, claim, theorem, fact, example, or procedure step; otherwise merge it with the smallest coherent neighboring context.",
                "Only repair when the chunk is incomplete, mixed, orphaned, or has edge elements owned by a neighbor.",
                "Same broad topic is not enough reason to move or merge elements.",
                "A single trailing figure, table, or image can still be misplaced if it clearly supports the next chunk more than the current one.",
                "Move elements only when the boundary is misplaced and one side cannot become a useful small knowledge unit without the moved edge element(s).",
                "Avoid orphan headings, orphan support, dangling sentence fragments, and unrelated topics packed together.",
                "Prefer keeping neighboring substantive chunks separate unless the current chunk is orphan-like or the edge element clearly belongs across the boundary.",
                "Do not move edge elements if doing so leaves the current chunk heading-only, support-only, or otherwise orphaned.",
                "If the only coherent edge repair would move every element in the current chunk, choose that only when the current chunk has no independent knowledge-unit use and clearly belongs with its neighbor.",
                "",
                "Decision priority:",
                "1. If content appears missing or damaged, choose needs_wider_review unless the missing piece is clearly visible in the previous or next edge.",
                "2. If the issue is only wrong ownership of edge elements, move the smallest correct prefix or suffix.",
                "3. If the current chunk is complete but contains multiple independent knowledge units, choose split_current with at most two split points.",
                "4. If the chunk is oddly shaped but still understandable as a small knowledge unit or support/evidence item, choose keep.",
                "5. If a repair would create a heading-only, support-only, or dangling orphan, choose keep or needs_wider_review.",
                "",
                "Risk flags:",
                self._join_prompt_lines(risk_lines),
                "",
                "Previous chunk tail:",
                self._join_prompt_lines(self._element_audit_lines(previous_elements, prefix="P")),
                "",
                "Current chunk under review:",
                self._join_prompt_lines(self._element_audit_lines(current_elements, prefix="C")),
                "",
                "Next chunk head:",
                self._join_prompt_lines(self._element_audit_lines(next_elements, prefix="N")),
                "",
                "Allowed actions:",
                "\n".join(action_lines),
                "",
                "For move_current_prefix_to_previous, element_ids must be the exact ids of a contiguous prefix of the current chunk, in order.",
                "For move_current_suffix_to_next, element_ids must be the exact ids of a contiguous suffix of the current chunk, in order.",
                "For pull_next_prefix_to_current, element_ids must be the exact ids of a contiguous prefix of the next chunk, in order.",
                "For split_current, element_ids must be 1 or 2 exact current-chunk ids where a new piece should start; never include the first current element id.",
                "split_current can create at most 3 pieces. If more pieces are needed, choose needs_wider_review.",
                "Using every current element id is a full merge; do this only when the current chunk has no independent graph use.",
                "For keep and needs_wider_review, set element_ids to an empty list.",
                "",
                "Return a JSON object matching the provided schema.",
            ]
        )

    def _element_audit_lines(self, elements: list[BoundaryElementView], *, prefix: str) -> list[str]:
        lines: list[str] = []
        for offset, element in enumerate(elements, start=1):
            text = self._normalized_text(element.text)
            if len(text) > 700:
                text = text[:697].rstrip() + "..."
            lines.append(
                f"{prefix}{offset}. [id={element.element_id}, {element.element_type}, "
                f"page {element.page_number}] {text}"
            )
        return lines

    def _parse_local_audit_response(self, content: str) -> _LocalAuditDecision:
        payload = self._extract_json_object(content)
        if not isinstance(payload, dict):
            return _LocalAuditDecision(
                action="keep",
                confidence=0.0,
                reason="LLM did not return a JSON object",
                element_ids=[],
            )
        action = str(payload.get("action", "keep")).strip().lower()
        allowed_actions = {
            "keep",
            "move_current_prefix_to_previous",
            "move_current_suffix_to_next",
            "pull_next_prefix_to_current",
            "split_current",
            "needs_wider_review",
        }
        if action not in allowed_actions:
            action = "keep"
        try:
            confidence = self._clamp_score(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = str(payload.get("reason", "")).strip()
        raw_element_ids = payload.get("element_ids", [])
        if isinstance(raw_element_ids, str):
            element_ids = [raw_element_ids.strip()] if raw_element_ids.strip() else []
        elif isinstance(raw_element_ids, list):
            element_ids = [str(element_id).strip() for element_id in raw_element_ids if str(element_id).strip()]
        else:
            raw_element_id = str(payload.get("element_id", "")).strip()
            element_ids = [raw_element_id] if raw_element_id else []
        return _LocalAuditDecision(
            action=action,
            confidence=confidence,
            reason=reason,
            element_ids=element_ids,
        )

    def _local_audit_response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "local_chunk_audit",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "keep",
                                "move_current_prefix_to_previous",
                                "move_current_suffix_to_next",
                                "pull_next_prefix_to_current",
                                "split_current",
                                "needs_wider_review",
                            ],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {"type": "string"},
                        "element_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["action", "confidence", "reason", "element_ids"],
                    "additionalProperties": False,
                },
            },
        }

    def _apply_local_audit_decision(
        self,
        states: list[_RepairGroupState],
        index: int,
        decision: _LocalAuditDecision,
    ) -> int | None:
        reason = decision.reason or "LLM local audit requested this repair"
        if decision.action in {"keep", "needs_wider_review"}:
            if decision.action == "needs_wider_review":
                self.recoverable_errors.append(f"Local audit requested wider review at repaired group {index}")
            return None
        if decision.action == "move_current_prefix_to_previous":
            if not self._move_current_prefix_to_previous(
                states,
                index,
                element_ids=decision.element_ids,
                confidence=decision.confidence,
                reason=reason,
            ):
                return None
            return index - 1
        if decision.action == "move_current_suffix_to_next":
            if not self._move_current_suffix_to_next(
                states,
                index,
                element_ids=decision.element_ids,
                confidence=decision.confidence,
                reason=reason,
            ):
                return None
            return index - 1
        if decision.action == "pull_next_prefix_to_current":
            if not self._pull_next_prefix_to_current(
                states,
                index,
                element_ids=decision.element_ids,
                confidence=decision.confidence,
                reason=reason,
            ):
                return None
            return index - 1
        if decision.action == "split_current":
            if not self._split_current_group(
                states,
                index,
                split_before_element_ids=decision.element_ids,
                confidence=decision.confidence,
                reason=reason,
            ):
                return None
            return index + len(decision.element_ids)
        return None

    def _element_index_map(self, groups: list[RefinedChunkGroup]) -> dict[str, int]:
        index_by_element_id: dict[str, int] = {}
        for group in groups:
            for offset, element in enumerate(group.elements):
                index_by_element_id.setdefault(element.element_id, group.start_element_index + offset)
        return index_by_element_id

    def _boundary_index_map(self, groups: list[RefinedChunkGroup]) -> dict[int, BoundaryCandidate]:
        boundary_by_index: dict[int, BoundaryCandidate] = {
            boundary.boundary_index: boundary
            for boundary in self.boundary_candidates
        }
        for block in self.tentative_blocks:
            for boundary in [block.start_boundary, block.end_boundary, *block.internal_boundaries]:
                if boundary is not None:
                    boundary_by_index.setdefault(boundary.boundary_index, boundary)
        for group in groups:
            for boundary in group.internal_boundaries:
                boundary_by_index.setdefault(boundary.boundary_index, boundary)
        return boundary_by_index

    def _make_repaired_group(
        self,
        *,
        document_id: str,
        group_index: int,
        state: _RepairGroupState,
        index_by_element_id: dict[str, int],
        boundary_by_index: dict[int, BoundaryCandidate],
    ) -> RefinedChunkGroup:
        element_indices = [
            index_by_element_id[element.element_id]
            for element in state.elements
            if element.element_id in index_by_element_id
        ]
        start_element_index = min(element_indices) if element_indices else group_index
        end_element_index = max(element_indices) if element_indices else group_index
        internal_boundaries = [
            boundary
            for boundary_index, boundary in sorted(boundary_by_index.items())
            if start_element_index <= boundary_index < end_element_index
        ]
        repairs = list(state.repair_decisions)
        stability = "repaired" if repairs else state.stability
        return RefinedChunkGroup(
            group_id=f"{document_id}::repaired_group::{group_index:05d}",
            group_index=group_index,
            source_block_id="+".join(self._unique_ordered(state.source_block_ids)),
            elements=list(state.elements),
            start_element_index=start_element_index,
            end_element_index=end_element_index,
            internal_boundaries=internal_boundaries,
            probe_decisions=list(state.probe_decisions),
            repair_decisions=repairs,
            stability=stability,
            reason_summary=self._repaired_group_reason_summary(state, stability),
            search_strategy="sequential+repair",
        )

    def _repaired_group_reason_summary(self, state: _RepairGroupState, stability: str) -> str:
        parts = [f"stability={stability}"]
        if state.reason_summary:
            parts.append(f"base=({state.reason_summary})")
        if state.repair_decisions:
            actions = [decision.action for decision in state.repair_decisions]
            parts.append(f"repairs={','.join(actions)}")
        return "; ".join(parts)

    def _move_trailing_support_to_next_title(
        self,
        current: _RepairGroupState,
        next_group: _RepairGroupState,
    ) -> bool:
        suffix = self._trailing_support_suffix(current.elements)
        if not suffix or len(suffix) == len(current.elements) or not self._starts_with_heading(next_group):
            return False
        if not self._has_substantive_body_text(next_group.elements):
            return False
        owner_elements = current.elements[:-len(suffix)]
        if not self._has_substantive_body_text(owner_elements):
            return False
        if self._group_text_owns_support(owner_elements, suffix):
            return False
        if not self._support_points_to_next_heading(owner_elements, suffix, next_group):
            return False
        moved_ids = [element.element_id for element in suffix]
        decision = ChunkRepairDecision(
            action="move_trailing_support_to_next",
            confidence=0.82,
            source="heuristic",
            reasons=["trailing support appears immediately before a title-led next chunk"],
            affected_element_ids=moved_ids,
            source_group_id=current.source_group_ids[-1] if current.source_group_ids else None,
            target_group_id=next_group.source_group_ids[0] if next_group.source_group_ids else None,
        )
        current.elements = current.elements[:-len(suffix)]
        next_group.elements = suffix + next_group.elements
        next_group.source_group_ids = self._unique_ordered(current.source_group_ids + next_group.source_group_ids)
        next_group.source_block_ids = self._unique_ordered(current.source_block_ids + next_group.source_block_ids)
        next_group.probe_decisions = current.probe_decisions + next_group.probe_decisions
        next_group.internal_boundaries = self._unique_boundaries(current.internal_boundaries + next_group.internal_boundaries)
        next_group.repair_decisions = next_group.repair_decisions + [decision]
        current.stability = "repaired"
        next_group.stability = "repaired"
        self.repair_decisions.append(decision)
        return True

    def _merge_group_into_next(
        self,
        states: list[_RepairGroupState],
        index: int,
        *,
        action: str,
        confidence: float,
        reason: str,
        source: str = "heuristic",
    ) -> None:
        current = states[index]
        target = states[index + 1]
        decision = ChunkRepairDecision(
            action=action,
            confidence=confidence,
            source=source,
            reasons=[reason],
            affected_element_ids=[element.element_id for element in current.elements],
            source_group_id=current.source_group_ids[-1] if current.source_group_ids else None,
            target_group_id=target.source_group_ids[0] if target.source_group_ids else None,
        )
        target.elements = current.elements + target.elements
        target.source_group_ids = self._unique_ordered(current.source_group_ids + target.source_group_ids)
        target.source_block_ids = self._unique_ordered(current.source_block_ids + target.source_block_ids)
        target.internal_boundaries = self._unique_boundaries(current.internal_boundaries + target.internal_boundaries)
        target.probe_decisions = current.probe_decisions + target.probe_decisions
        target.repair_decisions = current.repair_decisions + [decision] + target.repair_decisions
        target.stability = "repaired"
        self.repair_decisions.append(decision)
        del states[index]

    def _merge_group_into_previous(
        self,
        states: list[_RepairGroupState],
        index: int,
        *,
        action: str,
        confidence: float,
        reason: str,
        source: str = "heuristic",
    ) -> None:
        current = states[index]
        target = states[index - 1]
        decision = ChunkRepairDecision(
            action=action,
            confidence=confidence,
            source=source,
            reasons=[reason],
            affected_element_ids=[element.element_id for element in current.elements],
            source_group_id=current.source_group_ids[0] if current.source_group_ids else None,
            target_group_id=target.source_group_ids[-1] if target.source_group_ids else None,
        )
        target.elements.extend(current.elements)
        target.source_group_ids = self._unique_ordered(target.source_group_ids + current.source_group_ids)
        target.source_block_ids = self._unique_ordered(target.source_block_ids + current.source_block_ids)
        target.internal_boundaries = self._unique_boundaries(target.internal_boundaries + current.internal_boundaries)
        target.probe_decisions.extend(current.probe_decisions)
        target.repair_decisions.extend(current.repair_decisions + [decision])
        target.stability = "repaired"
        self.repair_decisions.append(decision)
        del states[index]

    def _move_current_prefix_to_previous(
        self,
        states: list[_RepairGroupState],
        index: int,
        *,
        element_ids: list[str],
        confidence: float,
        reason: str,
    ) -> bool:
        if index <= 0 or not states[index].elements or not element_ids:
            return False
        current = states[index]
        target = states[index - 1]
        if not self._element_ids_are_prefix(current.elements, element_ids):
            return False

        moved = current.elements[:len(element_ids)]
        current.elements = current.elements[len(element_ids):]
        decision = ChunkRepairDecision(
            action="move_current_prefix_to_previous",
            confidence=confidence,
            source="llm",
            reasons=[reason],
            affected_element_ids=[element.element_id for element in moved],
            source_group_id=current.source_group_ids[0] if current.source_group_ids else None,
            target_group_id=target.source_group_ids[-1] if target.source_group_ids else None,
        )
        target.elements.extend(moved)
        target.source_group_ids = self._unique_ordered(target.source_group_ids + current.source_group_ids)
        target.source_block_ids = self._unique_ordered(target.source_block_ids + current.source_block_ids)
        target.internal_boundaries = self._unique_boundaries(target.internal_boundaries + current.internal_boundaries)
        target.probe_decisions.extend(current.probe_decisions)
        target.repair_decisions.append(decision)
        target.stability = "repaired"
        current.stability = "repaired"
        self.repair_decisions.append(decision)
        if not current.elements:
            target.repair_decisions.extend(current.repair_decisions)
            del states[index]
        return True

    def _move_current_suffix_to_next(
        self,
        states: list[_RepairGroupState],
        index: int,
        *,
        element_ids: list[str],
        confidence: float,
        reason: str,
    ) -> bool:
        if index + 1 >= len(states) or not states[index].elements or not element_ids:
            return False
        current = states[index]
        target = states[index + 1]
        if not self._element_ids_are_suffix(current.elements, element_ids):
            return False

        moved = current.elements[-len(element_ids):]
        if not self._can_move_current_suffix_to_next(current, moved):
            return False
        remaining = current.elements[:-len(element_ids)]
        if remaining and not self._split_piece_is_valid(remaining):
            return False
        current.elements = current.elements[:-len(element_ids)]
        decision = ChunkRepairDecision(
            action="move_current_suffix_to_next",
            confidence=confidence,
            source="llm",
            reasons=[reason],
            affected_element_ids=[element.element_id for element in moved],
            source_group_id=current.source_group_ids[-1] if current.source_group_ids else None,
            target_group_id=target.source_group_ids[0] if target.source_group_ids else None,
        )
        target.elements = moved + target.elements
        target.source_group_ids = self._unique_ordered(current.source_group_ids + target.source_group_ids)
        target.source_block_ids = self._unique_ordered(current.source_block_ids + target.source_block_ids)
        target.internal_boundaries = self._unique_boundaries(current.internal_boundaries + target.internal_boundaries)
        target.probe_decisions = current.probe_decisions + target.probe_decisions
        target.repair_decisions = target.repair_decisions + [decision]
        target.stability = "repaired"
        current.stability = "repaired"
        self.repair_decisions.append(decision)
        if not current.elements:
            target.repair_decisions = current.repair_decisions + target.repair_decisions
            del states[index]
        return True

    def _pull_next_prefix_to_current(
        self,
        states: list[_RepairGroupState],
        index: int,
        *,
        element_ids: list[str],
        confidence: float,
        reason: str,
    ) -> bool:
        if index + 1 >= len(states) or not states[index + 1].elements or not element_ids:
            return False
        current = states[index]
        source_state = states[index + 1]
        if not self._element_ids_are_prefix(source_state.elements, element_ids):
            return False

        moved = source_state.elements[:len(element_ids)]
        source_state.elements = source_state.elements[len(element_ids):]
        decision = ChunkRepairDecision(
            action="pull_next_prefix_to_current",
            confidence=confidence,
            source="llm",
            reasons=[reason],
            affected_element_ids=[element.element_id for element in moved],
            source_group_id=source_state.source_group_ids[0] if source_state.source_group_ids else None,
            target_group_id=current.source_group_ids[-1] if current.source_group_ids else None,
        )
        current.elements.extend(moved)
        current.source_group_ids = self._unique_ordered(current.source_group_ids + source_state.source_group_ids)
        current.source_block_ids = self._unique_ordered(current.source_block_ids + source_state.source_block_ids)
        current.internal_boundaries = self._unique_boundaries(current.internal_boundaries + source_state.internal_boundaries)
        current.probe_decisions.extend(source_state.probe_decisions)
        current.repair_decisions.append(decision)
        current.stability = "repaired"
        source_state.stability = "repaired"
        self.repair_decisions.append(decision)
        if not source_state.elements:
            current.repair_decisions.extend(source_state.repair_decisions)
            del states[index + 1]
        return True

    def _split_current_group(
        self,
        states: list[_RepairGroupState],
        index: int,
        *,
        split_before_element_ids: list[str],
        confidence: float,
        reason: str,
    ) -> bool:
        if not states[index].elements or not split_before_element_ids:
            return False
        if len(split_before_element_ids) > 2 or len(set(split_before_element_ids)) != len(split_before_element_ids):
            return False

        current = states[index]
        offset_by_id = {element.element_id: offset for offset, element in enumerate(current.elements)}
        split_offsets: list[int] = []
        for element_id in split_before_element_ids:
            if element_id not in offset_by_id:
                return False
            offset = offset_by_id[element_id]
            if offset <= 0:
                return False
            split_offsets.append(offset)
        if split_offsets != sorted(split_offsets) or len(set(split_offsets)) != len(split_offsets):
            return False

        boundaries = [0, *split_offsets, len(current.elements)]
        pieces = [
            current.elements[boundaries[piece_index]:boundaries[piece_index + 1]]
            for piece_index in range(len(boundaries) - 1)
        ]
        if len(pieces) > 3 or any(not self._split_piece_is_valid(piece) for piece in pieces):
            return False

        decision = ChunkRepairDecision(
            action="split_current",
            confidence=confidence,
            source="llm",
            reasons=[reason],
            affected_element_ids=[element.element_id for element in current.elements],
            source_group_id=current.source_group_ids[0] if current.source_group_ids else None,
            target_group_id=None,
        )
        new_states = [
            _RepairGroupState(
                source_group_ids=list(current.source_group_ids),
                source_block_ids=list(current.source_block_ids),
                elements=list(piece),
                internal_boundaries=list(current.internal_boundaries),
                probe_decisions=list(current.probe_decisions),
                repair_decisions=list(current.repair_decisions) + [decision],
                stability="repaired",
                reason_summary=(current.reason_summary + "; llm split_current").strip("; "),
                split_piece_index=piece_index,
            )
            for piece_index, piece in enumerate(pieces)
        ]
        states[index:index + 1] = new_states
        self.repair_decisions.append(decision)
        return True

    def _split_piece_is_valid(self, elements: list[BoundaryElementView]) -> bool:
        if not elements:
            return False
        if len(elements) == 1:
            only = elements[0]
            if self._is_heading_element(only):
                return False
            if self._is_support_element(only) or self._looks_like_caption_or_artifact(only):
                return False
            if self._normalized_type(only) == "text" and self._is_dangling_text_element(only):
                return False
        if all(self._is_support_element(element) or self._looks_like_caption_or_artifact(element) for element in elements):
            return False
        heading_count = sum(1 for element in elements if self._is_heading_element(element))
        if heading_count and not self._has_substantive_body_text(elements):
            has_visual_or_table_support = any(self._is_support_element(element) for element in elements)
            if not has_visual_or_table_support:
                return False
        return True

    def _element_ids_are_prefix(self, elements: list[BoundaryElementView], element_ids: list[str]) -> bool:
        if not element_ids or len(element_ids) > len(elements):
            return False
        return [element.element_id for element in elements[:len(element_ids)]] == element_ids

    def _element_ids_are_suffix(self, elements: list[BoundaryElementView], element_ids: list[str]) -> bool:
        if not element_ids or len(element_ids) > len(elements):
            return False
        return [element.element_id for element in elements[-len(element_ids):]] == element_ids

    def _can_move_current_suffix_to_next(
        self,
        current: _RepairGroupState,
        moved: list[BoundaryElementView],
    ) -> bool:
        if not moved:
            return False
        if self._is_pure_support_sequence(moved):
            return True
        return len(moved) == len(current.elements) and self._is_fresh_split_edge_piece(current)

    def _is_pure_support_sequence(self, elements: list[BoundaryElementView]) -> bool:
        return bool(elements) and all(
            self._is_support_element(element) or self._looks_like_caption_or_artifact(element)
            for element in elements
        )

    def _is_fresh_split_edge_piece(self, state: _RepairGroupState) -> bool:
        if state.split_piece_index is None or state.split_piece_index <= 0:
            return False
        return any(decision.action == "split_current" and decision.source == "llm" for decision in state.repair_decisions)

    def _trailing_support_suffix(self, elements: list[BoundaryElementView]) -> list[BoundaryElementView]:
        suffix: list[BoundaryElementView] = []
        for element in reversed(elements):
            if self._is_support_element(element) or self._looks_like_caption_or_artifact(element):
                suffix.append(element)
            else:
                break
        return list(reversed(suffix))

    def _is_support_only_group(self, state: _RepairGroupState) -> bool:
        return bool(state.elements) and all(
            self._is_support_element(element) or self._looks_like_caption_or_artifact(element)
            for element in state.elements
        )

    def _is_heading_scaffold_group(self, state: _RepairGroupState) -> bool:
        return len(state.elements) == 1 and self._is_heading_element(state.elements[0])

    def _is_repaired_scaffold_group(self, state: _RepairGroupState) -> bool:
        if not state.repair_decisions:
            return False
        if self._has_non_scaffold_body_text(state.elements):
            return False
        if not any(self._is_heading_element(element) for element in state.elements):
            return False
        allowed_actions = {"merge_orphan_support_with_next", "merge_bridge_text_with_next"}
        return any(decision.action in allowed_actions for decision in state.repair_decisions)

    def _has_non_scaffold_body_text(self, elements: list[BoundaryElementView]) -> bool:
        for element in elements:
            if self._normalized_type(element) != "text":
                continue
            if self._looks_like_caption_or_artifact(element) or self._heading_like_score(element) >= 0.82:
                continue
            if self._is_bridge_text_element(element):
                continue
            if self._tokens(element.text):
                return True
        return False

    def _starts_with_heading(self, state: _RepairGroupState) -> bool:
        if not state.elements:
            return False
        return self._is_heading_element(state.elements[0])

    def _is_bridge_text_group(self, state: _RepairGroupState) -> bool:
        if len(state.elements) != 1 or self._normalized_type(state.elements[0]) != "text":
            return False
        return self._is_bridge_text_element(state.elements[0])

    def _is_possible_internal_split_candidate(self, state: _RepairGroupState) -> bool:
        if self._is_support_only_group(state):
            return False
        split_candidate_elements = [
            element
            for element in state.elements
            if self._is_substantive_split_candidate_element(element)
        ]
        if len(split_candidate_elements) < 6:
            return False

        complete_lines = sum(
            1 for element in split_candidate_elements if self._looks_like_complete_knowledge_line(element)
        )
        topic_moves = sum(
            1 for element in split_candidate_elements[1:] if self._starts_internal_topic_move(element)
        )
        return complete_lines >= 4 or topic_moves >= 1

    def _is_substantive_split_candidate_element(self, element: BoundaryElementView) -> bool:
        if self._normalized_type(element) not in {"text", "title"}:
            return False
        if self._looks_like_caption_or_artifact(element) or self._is_bridge_text_element(element):
            return False
        return len(self._tokens(element.text)) >= 3

    def _looks_like_complete_knowledge_line(self, element: BoundaryElementView) -> bool:
        text = element.text.strip()
        tokens = self._tokens(text)
        if len(tokens) < 5:
            return False
        if text.endswith((".", "?", "!", ";")):
            return True
        return len(tokens) >= 10

    def _starts_internal_topic_move(self, element: BoundaryElementView) -> bool:
        return bool(
            re.match(
                r"^(then|next|now|similarly|finally|first|second|third|suppose|let|before|after|using|to compute|we now|the algorithm|the routine)\b",
                element.text.strip(),
                re.IGNORECASE,
            )
        )

    def _is_mixed_visual_support_candidate(self, states: list[_RepairGroupState], index: int) -> bool:
        state = states[index]
        visual_elements = [
            element
            for element in state.elements
            if self._is_visual_support_element(element)
        ]
        if len(visual_elements) < 2:
            return False

        next_state = states[index + 1] if index + 1 < len(states) else None
        trailing_visual = state.elements[-1] if self._is_visual_support_element(state.elements[-1]) else None
        if trailing_visual is not None and next_state is not None:
            trailing_tokens = self._visual_subject_tokens(trailing_visual)
            current_tokens = self._group_subject_tokens(state.elements[:-1])
            next_tokens = self._group_subject_tokens(next_state.elements[:3])
            if trailing_tokens and (trailing_tokens & next_tokens) and len(trailing_tokens & next_tokens) > len(trailing_tokens & current_tokens):
                return True

        token_sets = [
            tokens
            for tokens in (self._visual_subject_tokens(element) for element in visual_elements)
            if len(tokens) >= 2
        ]
        for left_index, left_tokens in enumerate(token_sets):
            for right_tokens in token_sets[left_index + 1:]:
                union = left_tokens | right_tokens
                if not union:
                    continue
                overlap_ratio = len(left_tokens & right_tokens) / len(union)
                if overlap_ratio <= 0.08:
                    return True
        return False

    def _is_visual_edge_support_candidate(self, states: list[_RepairGroupState], index: int) -> bool:
        state = states[index]
        if len(state.elements) < 2 or self._is_support_only_group(state):
            return False

        next_state = states[index + 1] if index + 1 < len(states) else None
        if next_state is None or not next_state.elements:
            return False

        trailing_suffix = self._trailing_support_suffix(state.elements)
        if len(trailing_suffix) != 1:
            return False
        trailing_visual = trailing_suffix[0]
        if not self._is_visual_support_element(trailing_visual):
            return False

        current_owner = state.elements[:-1]
        if not current_owner or not self._split_piece_is_valid(current_owner):
            return False
        if not self._has_substantive_body_text(next_state.elements):
            return False

        trailing_tokens = self._visual_subject_tokens(trailing_visual)
        current_tokens = self._group_subject_tokens(current_owner)
        next_tokens = self._group_subject_tokens(next_state.elements[:3])
        if len(trailing_tokens) < 2 or not next_tokens:
            return False

        next_overlap = len(trailing_tokens & next_tokens)
        current_overlap = len(trailing_tokens & current_tokens)
        return next_overlap >= 1 and next_overlap > current_overlap

    def _is_visual_support_element(self, element: BoundaryElementView) -> bool:
        return self._normalized_type(element) in {
            "figure",
            "image",
            "diagram",
            "chart",
            "table",
        }

    def _group_subject_tokens(self, elements: list[BoundaryElementView]) -> set[str]:
        tokens: set[str] = set()
        for element in elements:
            if self._is_visual_support_element(element):
                tokens |= self._visual_subject_tokens(element)
            elif not self._looks_like_caption_or_artifact(element):
                tokens |= self._meaningful_tokens(element.text)
        return tokens - self._generic_visual_tokens()

    def _visual_subject_tokens(self, element: BoundaryElementView) -> set[str]:
        return self._meaningful_tokens(element.text) - self._generic_visual_tokens()

    def _generic_visual_tokens(self) -> set[str]:
        return {
            "annotated",
            "annotation",
            "area",
            "arrow",
            "background",
            "black",
            "blue",
            "border",
            "bottom",
            "box",
            "chart",
            "color",
            "colored",
            "column",
            "contains",
            "depicting",
            "depicts",
            "diagram",
            "figure",
            "grid",
            "green",
            "illustration",
            "image",
            "include",
            "includes",
            "labeled",
            "label",
            "labels",
            "large",
            "left",
            "line",
            "panel",
            "red",
            "right",
            "row",
            "schematic",
            "showing",
            "shows",
            "side",
            "small",
            "table",
            "text",
            "top",
            "vertical",
            "white",
        }

    def _is_bridge_text_element(self, element: BoundaryElementView) -> bool:
        text = element.text.strip()
        if len(self._tokens(text)) > 30:
            return False
        return bool(
            re.search(
                r"\b(next|following|below|above|figure|fig\.|table|formula|diagram|slide|shown|illustrat(?:e|es|ed|ing))\b",
                text,
                re.IGNORECASE,
            )
        )

    def _is_heading_element(self, element: BoundaryElementView) -> bool:
        return self._normalized_type(element) == "title" or self._heading_like_score(element) >= 0.82

    def _is_dangling_text_group(self, state: _RepairGroupState) -> bool:
        if len(state.elements) != 1 or self._normalized_type(state.elements[0]) != "text":
            return False
        return self._is_dangling_text_element(state.elements[0])

    def _is_dangling_text_element(self, element: BoundaryElementView) -> bool:
        text = element.text.strip()
        tokens = self._tokens(text)
        if not tokens or len(tokens) > 24:
            return False
        if re.match(r"^(and|but|or|so|therefore|thus|hence|however|because|which|where|this|these|those|it)\b", text, re.IGNORECASE):
            return True
        if text and text[0].islower():
            return True
        return not text.endswith((".", "?", "!", ":", ";"))

    def _is_support_element(self, element: BoundaryElementView) -> bool:
        return self._normalized_type(element) in {
            "caption",
            "figure",
            "formula",
            "image",
            "diagram",
            "chart",
            "table",
            "table_footnote",
        }

    def _looks_like_caption_or_artifact(self, element: BoundaryElementView) -> bool:
        return self._caption_or_artifact_score(element) >= 0.82

    def _has_substantive_body_text(self, elements: list[BoundaryElementView]) -> bool:
        for element in elements:
            if self._normalized_type(element) != "text":
                continue
            if self._looks_like_caption_or_artifact(element) or self._heading_like_score(element) >= 0.82:
                continue
            if self._tokens(element.text):
                return True
        return False

    def _group_text_owns_support(
        self,
        owner_elements: list[BoundaryElementView],
        support_elements: list[BoundaryElementView],
    ) -> bool:
        if not owner_elements or not support_elements:
            return False
        owner_text = " ".join(element.text for element in owner_elements).lower()
        support_types = {self._normalized_type(element) for element in support_elements}
        if "formula" in support_types and (owner_text.rstrip().endswith(":") or re.search(r"\b(equation|formula|recurrence|expression|equals?)\b", owner_text)):
            return True
        if {"figure", "image", "diagram", "chart"} & support_types and re.search(r"\b(figure|fig\.|diagram|image|shown|illustrat(?:e|es|ed|ing)|below|above)\b", owner_text):
            return True
        if "table" in support_types and re.search(r"\b(table|shown|below|above)\b", owner_text):
            return True
        return False

    def _support_points_to_next_heading(
        self,
        owner_elements: list[BoundaryElementView],
        support_elements: list[BoundaryElementView],
        next_group: _RepairGroupState,
    ) -> bool:
        next_heading_tokens = self._meaningful_tokens(
            " ".join(element.text for element in next_group.elements[:3] if self._is_heading_element(element))
        )
        if not next_heading_tokens:
            return False
        support_tokens = self._meaningful_tokens(" ".join(element.text for element in support_elements))
        owner_tokens = self._meaningful_tokens(" ".join(element.text for element in owner_elements))
        next_overlap = support_tokens & next_heading_tokens
        if not next_overlap:
            return False
        owner_overlap = support_tokens & owner_tokens
        return bool(next_overlap - owner_overlap)

    def _meaningful_tokens(self, text: str) -> set[str]:
        stop_words = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "by",
            "for",
            "from",
            "in",
            "into",
            "is",
            "of",
            "on",
            "or",
            "the",
            "to",
            "with",
        }
        return {
            token
            for token in self._tokens(text)
            if len(token) > 2 and token not in stop_words
        }

    def _unique_ordered(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            unique.append(value)
        return unique

    def _unique_boundaries(self, boundaries: list[BoundaryCandidate]) -> list[BoundaryCandidate]:
        seen: set[str] = set()
        unique: list[BoundaryCandidate] = []
        for boundary in sorted(boundaries, key=lambda item: item.boundary_index):
            if boundary.boundary_id in seen:
                continue
            seen.add(boundary.boundary_id)
            unique.append(boundary)
        return unique

    def _refine_concept_boundary(
        self,
        *,
        block: TentativeBlock,
        boundary: BoundaryCandidate,
        group_start_offset: int,
        active_end_offset: int,
        allow_llm: bool,
    ) -> ConceptProbeDecision:
        preliminary = boundary.preliminary_decision
        if (
            preliminary is not None
            and preliminary.decision == "continue"
            and preliminary.confidence >= self.config.ACTIVE_REFINEMENT_CONTINUE_CONFIDENCE
        ):
            return ConceptProbeDecision(
                boundary_id=boundary.boundary_id,
                decision="continue",
                confidence=preliminary.confidence,
                source="tier0",
                reasons=list(preliminary.reasons),
                prompt_context_window=0,
            )
        if (
            preliminary is not None
            and preliminary.decision == "split"
            and preliminary.confidence >= self.config.ACTIVE_REFINEMENT_SPLIT_CONFIDENCE
        ):
            return ConceptProbeDecision(
                boundary_id=boundary.boundary_id,
                decision="split",
                confidence=preliminary.confidence,
                source="tier0",
                reasons=list(preliminary.reasons),
                prompt_context_window=0,
            )
        if (
            allow_llm
            and self.llm_client is not None
            and int(self.config.MAX_LLM_CALLS_PER_BOUNDARY) > 0
        ):
            return self._llm_refine_concept_boundary(
                block=block,
                boundary=boundary,
                group_start_offset=group_start_offset,
                active_end_offset=active_end_offset,
            )
        if preliminary is not None and preliminary.decision in {"continue", "split"}:
            return ConceptProbeDecision(
                boundary_id=boundary.boundary_id,
                decision=preliminary.decision,
                confidence=preliminary.confidence,
                source="tier0_low_confidence",
                reasons=list(preliminary.reasons),
                prompt_context_window=0,
            )
        return ConceptProbeDecision(
            boundary_id=boundary.boundary_id,
            decision="split",
            confidence=0.5,
            source="fallback",
            reasons=["LLM refinement unavailable for ambiguous boundary; conservative split"],
            prompt_context_window=0,
        )

    def _llm_refine_concept_boundary(
        self,
        *,
        block: TentativeBlock,
        boundary: BoundaryCandidate,
        group_start_offset: int,
        active_end_offset: int,
    ) -> ConceptProbeDecision:
        max_calls = max(1, int(self.config.MAX_LLM_CALLS_PER_BOUNDARY))
        max_expansions = min(max(0, int(self.config.CONTEXT_EXPANSION_MAX_REQUESTS)), max_calls - 1)
        max_elements = max(0, int(self.config.CONTEXT_EXPANSION_MAX_ELEMENTS))
        base_window = max(0, int(self.config.ACTIVE_REFINEMENT_CONTEXT_WINDOW))
        left_expand = 0
        right_expand = 0
        context_request: dict[str, Any] = {}
        expansions = 0

        while True:
            active_concept = self._active_concept(
                block=block,
                start_offset=group_start_offset,
                end_offset=active_end_offset,
            )
            prompt = self._refinement_prompt(
                block=block,
                boundary=boundary,
                active_concept=active_concept,
                active_end_offset=active_end_offset,
                base_window=base_window,
                left_expand=left_expand,
                right_expand=right_expand,
                expansions=expansions,
                max_expansions=max_expansions,
                previous_context_request=context_request,
            )
            cache_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            with self._refinement_response_cache_lock:
                content = self._refinement_response_cache.get(cache_key)
            if content is None:
                response = self.llm_client.complete(
                    system=(
                        "You decide whether adjacent extracted document elements belong to the "
                        "same concept. Return only one compact JSON object."
                    ),
                    user=prompt,
                    temperature=0.0,
                    response_format=self._refinement_response_format(),
                )
                self._record_llm_call()
                content = getattr(response, "content", str(response))
                with self._refinement_response_cache_lock:
                    self._refinement_response_cache[cache_key] = content
            decision = self._parse_refinement_response(
                boundary_id=boundary.boundary_id,
                content=content,
                context_expansions=expansions,
                prompt_context_window=base_window + max(left_expand, right_expand),
            )
            if not decision.needs_more_context or expansions >= max_expansions:
                return decision

            context_request = decision.context_request
            requested_left = self._safe_context_request_count(context_request.get("expand_left_elements"), base_window)
            requested_right = self._safe_context_request_count(context_request.get("expand_right_elements"), base_window)
            left_expand = min(max_elements, max(left_expand, requested_left))
            right_expand = min(max_elements, max(right_expand, requested_right))
            if left_expand == 0 and right_expand == 0:
                return decision
            expansions += 1

    def _refinement_response_format(self) -> dict[str, Any]:
        max_elements = max(0, int(self.config.CONTEXT_EXPANSION_MAX_ELEMENTS))
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "concept_boundary_refinement",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "decision": {
                            "type": "string",
                            "enum": ["continue", "split", "unsure"],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reasons": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "needs_more_context": {"type": "boolean"},
                        "context_request": {
                            "type": "object",
                            "properties": {
                                "expand_left_elements": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": max_elements,
                                },
                                "expand_right_elements": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": max_elements,
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["expand_left_elements", "expand_right_elements", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "required": [
                        "decision",
                        "confidence",
                        "reasons",
                        "needs_more_context",
                        "context_request",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    def _block_segmentation_prompt(self, block: TentativeBlock) -> str:
        lines = self._block_segmentation_element_lines(block.elements)
        boundary_lines = self._block_segmentation_boundary_lines(block)
        return "\n".join(
            [
                "You are deciding multiple adjacent document boundaries at once.",
                "",
                "A good chunk contains one atomic, self-contained idea. It includes necessary support, but it does not collect every related nearby point.",
                "",
                "For each boundary, decide whether the right element should continue the current chunk on its left or start a new chunk.",
                "",
                "Choose CONTINUE if the right element completes, explains, illustrates, or directly supports the chunk being built.",
                "Choose SPLIT if the right element starts a distinct idea, step, claim, proof, example, section, slide topic, or subtopic, even when related to the same broad subject.",
                "",
                "Process boundaries in order. Maintain the current chunk mentally. A SPLIT starts a new current chunk at the right element.",
                "",
                "Important:",
                "- Do not make every meaningful sentence its own chunk.",
                "- Consider the chunk that would exist from the previous split up to this boundary.",
                "- Consecutive short text elements often belong together when they form one setup, explanation, proof move, or algorithm phase.",
                "- Headings usually continue with the body they introduce.",
                "- Formulas, figures, tables, and captions usually continue with their owner text.",
                "",
                "Elements in this tentative block:",
                self._join_prompt_lines(lines),
                "",
                "Boundaries to decide:",
                self._join_prompt_lines(boundary_lines),
                "",
                "Return one decision object for every boundary pair, in the same order as the boundary list.",
                "For each decision, copy the exact left_element_id and right_element_id from the boundary pair.",
                "Use CONTINUE when the right element belongs in the current chunk.",
                "Use SPLIT when the right element should start a new chunk.",
                "Give a short reason for each boundary decision.",
                "",
                "Return a JSON object matching the provided schema.",
            ]
        )

    def _block_segmentation_element_lines(self, elements: list[BoundaryElementView]) -> list[str]:
        lines: list[str] = []
        for offset, element in enumerate(elements):
            text = self._normalized_text(element.text)
            if len(text) > 700:
                text = text[:697].rstrip() + "..."
            lines.append(
                f"{self._alpha_label(offset)}. [id={element.element_id}, "
                f"{element.element_type}, page {element.page_number}] {text}"
            )
        return lines

    def _block_segmentation_boundary_lines(self, block: TentativeBlock) -> list[str]:
        lines: list[str] = []
        for boundary in block.internal_boundaries:
            left_label = self._alpha_label(boundary.boundary_index - block.start_element_index)
            right_label = self._alpha_label(boundary.boundary_index - block.start_element_index + 1)
            lines.append(
                f"- {boundary.boundary_id}: {left_label} | {right_label} "
                f"({boundary.left.element_id} -> {boundary.right.element_id})"
            )
        return lines

    def _block_segmentation_response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "block_concept_segmentation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "decisions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "left_element_id": {"type": "string"},
                                    "right_element_id": {"type": "string"},
                                    "decision": {
                                        "type": "string",
                                        "enum": ["continue", "split"],
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "reason": {"type": "string"},
                                },
                                "required": [
                                    "left_element_id",
                                    "right_element_id",
                                    "decision",
                                    "confidence",
                                    "reason",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["decisions", "confidence", "reason"],
                    "additionalProperties": False,
                },
            },
        }

    def _parse_block_segmentation_response(
        self,
        content: str,
        *,
        block: TentativeBlock,
    ) -> _BlockSegmentationDecision:
        payload = self._extract_json_object(content)
        if not isinstance(payload, dict):
            return _BlockSegmentationDecision(
                split_start_element_ids=[],
                confidence=0.0,
                reason="LLM did not return a JSON object",
            )
        boundary_decisions = self._parse_block_boundary_decisions(payload.get("decisions", []))
        right_element_by_pair = {
            (boundary.left_element_id, boundary.right_element_id): boundary.right_element_id
            for boundary in block.internal_boundaries
        }
        expected_pairs = [
            (boundary.left_element_id, boundary.right_element_id)
            for boundary in block.internal_boundaries
        ]
        returned_pairs = [
            (left_element_id, right_element_id)
            for left_element_id, right_element_id, _decision in boundary_decisions
        ]
        unknown_pairs = [
            pair
            for pair in returned_pairs
            if pair not in right_element_by_pair
        ]
        duplicate_pairs = sorted(
            pair
            for pair in set(returned_pairs)
            if returned_pairs.count(pair) > 1
        )
        missing_pairs = [
            pair
            for pair in expected_pairs
            if pair not in returned_pairs
        ]
        if unknown_pairs or duplicate_pairs or missing_pairs:
            return _BlockSegmentationDecision(
                split_start_element_ids=[],
                confidence=0.0,
                reason=(
                    f"invalid_boundary_decisions; unknown={self._format_boundary_pairs(unknown_pairs)}; "
                    f"duplicate={self._format_boundary_pairs(duplicate_pairs)}; "
                    f"missing={self._format_boundary_pairs(missing_pairs)}"
                ),
            )
        split_pairs = [
            (left_element_id, right_element_id)
            for left_element_id, right_element_id, decision in boundary_decisions
            if decision == "split"
        ]
        continue_pairs = [
            (left_element_id, right_element_id)
            for left_element_id, right_element_id, decision in boundary_decisions
            if decision == "continue"
        ]
        split_start_element_ids = [
            right_element_by_pair[pair]
            for pair in split_pairs
        ]
        try:
            confidence = self._clamp_score(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = str(payload.get("reason", "")).strip() or (
            f"decisions continue={len(continue_pairs)} split={len(split_pairs)}"
        )
        return _BlockSegmentationDecision(
            split_start_element_ids=split_start_element_ids,
            confidence=confidence,
            reason=reason,
        )

    def _parse_block_boundary_decisions(self, raw_items: Any) -> list[tuple[str, str, str]]:
        if not isinstance(raw_items, list):
            return []
        decisions: list[tuple[str, str, str]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            left_element_id = str(item.get("left_element_id", "")).strip()
            right_element_id = str(item.get("right_element_id", "")).strip()
            decision = str(item.get("decision", "")).strip().lower()
            if left_element_id and right_element_id and decision in {"continue", "split"}:
                decisions.append((left_element_id, right_element_id, decision))
        return decisions

    def _format_boundary_pairs(self, pairs: list[tuple[str, str]]) -> str:
        if not pairs:
            return "none"
        return ",".join(f"{left}->{right}" for left, right in pairs)

    def _active_concept(
        self,
        *,
        block: TentativeBlock,
        start_offset: int,
        end_offset: int,
    ) -> ActiveConcept:
        elements = block.elements[start_offset:end_offset + 1]
        evidence_types: dict[str, int] = {}
        for element in elements:
            evidence_types[element.element_type] = evidence_types.get(element.element_type, 0) + 1
        open_threads: list[str] = []
        if elements:
            last_text = self._normalized_text(elements[-1].text)
            if last_text and not self._has_terminal_sentence(last_text):
                open_threads.append("last_element_has_open_sentence")
            if self._formula_or_table_score(elements[-1]) >= 0.8:
                open_threads.append("last_element_is_formula_or_table")
        return ActiveConcept(
            start_element_index=block.start_element_index + start_offset,
            end_element_index=block.start_element_index + end_offset,
            elements=elements,
            concept_summary=self._summarize_element_views(elements),
            evidence_types=evidence_types,
            open_threads=open_threads,
        )

    def _refinement_prompt(
        self,
        *,
        block: TentativeBlock,
        boundary: BoundaryCandidate,
        active_concept: ActiveConcept,
        active_end_offset: int,
        base_window: int,
        left_expand: int,
        right_expand: int,
        expansions: int,
        max_expansions: int,
        previous_context_request: dict[str, Any],
    ) -> str:
        next_offset = active_end_offset + 1
        active_start_offset = active_concept.start_element_index - block.start_element_index
        left_start = max(0, active_start_offset - base_window - left_expand)
        right_end = min(len(block.elements), next_offset + 1 + base_window + right_expand)
        previous_context = self._element_prompt_lines(block.elements[left_start:active_start_offset], prefix="P")
        current_lines = self._element_prompt_lines(active_concept.elements, start_index=0)
        candidate_lines = self._element_prompt_lines(
            block.elements[next_offset:next_offset + 1],
            start_index=len(active_concept.elements),
        )
        following_lines = self._element_prompt_lines(
            block.elements[next_offset + 1:right_end],
            start_index=len(active_concept.elements) + 1,
        )
        context_remaining = max(0, max_expansions - expansions)
        max_context = int(self.config.CONTEXT_EXPANSION_MAX_ELEMENTS)
        previous_request = self._context_request_note(previous_context_request)
        open_notes = self._active_concept_notes(active_concept)

        return "\n".join(
            [
                "You are deciding whether the next extracted document element should continue the current chunk or start a new chunk.",
                "",
                "A good chunk contains one atomic, self-contained idea. It includes necessary support, but it does not collect every related nearby point.",
                "",
                "Choose CONTINUE only if the candidate is needed to complete, explain, illustrate, or directly support the current chunk.",
                "Choose SPLIT if the candidate starts a distinct idea, step, claim, proof, example, section, slide topic, or subtopic, even when it is related to the same broad subject.",
                "Choose UNSURE only if this local view is genuinely insufficient; then request a bounded local expansion.",
                "",
                f"Position: {self._boundary_position_note(boundary)}",
                "",
                "Previous local context:",
                self._join_prompt_lines(previous_context),
                "",
                "Current chunk:",
                self._join_prompt_lines(current_lines),
                "",
                "Candidate next element:",
                self._join_prompt_lines(candidate_lines),
                "",
                "Following local context:",
                self._join_prompt_lines(following_lines),
                "",
                "Current chunk notes:",
                self._join_prompt_lines(open_notes),
                "",
                f"Context expansion available: {context_remaining} request(s) remain. You may request up to {max_context} more elements on either side.",
                f"Previous context request: {previous_request}",
                "",
                "Question: Should the candidate next element be included in the same chunk as the current chunk?",
                "",
                "Return a JSON object matching the provided schema. If needs_more_context is false, set both expansion counts to 0 and reason to an empty string.",
            ]
        )

    def _parse_refinement_response(
        self,
        *,
        boundary_id: str,
        content: str,
        context_expansions: int,
        prompt_context_window: int,
    ) -> ConceptProbeDecision:
        payload = self._extract_json_object(content)
        if not isinstance(payload, dict):
            return ConceptProbeDecision(
                boundary_id=boundary_id,
                decision="unsure",
                confidence=0.0,
                source="llm_parse_error",
                reasons=["LLM did not return a JSON object"],
                context_expansions=context_expansions,
                prompt_context_window=prompt_context_window,
            )
        decision = str(payload.get("decision", "unsure")).strip().lower()
        if decision not in {"continue", "split", "unsure"}:
            decision = "unsure"
        reasons = payload.get("reasons", [])
        if isinstance(reasons, str):
            reasons = [reasons]
        if not isinstance(reasons, list):
            reasons = []
        context_request = payload.get("context_request", {})
        if not isinstance(context_request, dict):
            context_request = {}
        return ConceptProbeDecision(
            boundary_id=boundary_id,
            decision=decision,
            confidence=self._clamp_score(payload.get("confidence", 0.0)),
            source="llm",
            reasons=[str(reason) for reason in reasons[:5]],
            needs_more_context=bool(payload.get("needs_more_context", False)),
            context_request=context_request,
            context_expansions=context_expansions,
            prompt_context_window=prompt_context_window,
        )

    def _extract_json_object(self, content: str) -> dict[str, Any] | None:
        text = (content or "").strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match is None:
                return None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None

    def _safe_context_request_count(self, value: Any, default: int) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return max(0, int(default))

    def _summarize_element_views(self, elements: list[BoundaryElementView]) -> str:
        rows = self._element_context_rows(elements)
        if len(rows) <= 4:
            return " | ".join(rows)
        return " | ".join(rows[:2] + [f"... {len(rows) - 4} omitted ..."] + rows[-2:])

    def _element_context_rows(self, elements: list[BoundaryElementView]) -> list[str]:
        rows: list[str] = []
        for element in elements:
            text = self._normalized_text(element.text)
            if len(text) > 240:
                text = text[:237].rstrip() + "..."
            rows.append(
                f"{element.element_id} [{element.element_type}] "
                f"p{element.page_number}/o{element.order}: {text}"
            )
        return rows

    def _element_prompt_rows(self, elements: list[BoundaryElementView]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for offset, element in enumerate(elements, start=1):
            text = self._normalized_text(element.text)
            if len(text) > 700:
                text = text[:697].rstrip() + "..."
            rows.append(
                {
                    "label": f"E{offset}",
                    "type": element.element_type,
                    "page": element.page_number,
                    "text": text,
                }
            )
        return rows

    def _element_prompt_lines(
        self,
        elements: list[BoundaryElementView],
        *,
        start_index: int = 0,
        prefix: str | None = None,
    ) -> list[str]:
        lines: list[str] = []
        for offset, element in enumerate(elements):
            label = f"{prefix}{offset + 1}" if prefix is not None else self._alpha_label(start_index + offset)
            text = self._normalized_text(element.text)
            if len(text) > 700:
                text = text[:697].rstrip() + "..."
            lines.append(f"{label}. [{element.element_type}, page {element.page_number}] {text}")
        return lines

    def _alpha_label(self, index: int) -> str:
        current = max(0, int(index))
        pieces: list[str] = []
        while True:
            pieces.append(chr(ord("A") + (current % 26)))
            current = (current // 26) - 1
            if current < 0:
                break
        return "".join(reversed(pieces))

    def _join_prompt_lines(self, lines: list[str]) -> str:
        return "\n".join(lines) if lines else "(none)"

    def _active_concept_notes(self, active_concept: ActiveConcept) -> list[str]:
        notes: list[str] = []
        if active_concept.open_threads:
            if "last_element_has_open_sentence" in active_concept.open_threads:
                notes.append("- The current chunk appears to end with an unfinished sentence or open thought.")
            if "last_element_is_formula_or_table" in active_concept.open_threads:
                notes.append("- The current chunk ends with a formula or table that may need nearby explanation.")
        if active_concept.evidence_types:
            type_counts = ", ".join(
                f"{count} {element_type}" for element_type, count in sorted(active_concept.evidence_types.items())
            )
            notes.append(f"- Current chunk element types: {type_counts}.")
        return notes

    def _context_request_note(self, context_request: dict[str, Any]) -> str:
        if not context_request:
            return "none"
        return (
            f"left={context_request.get('expand_left_elements', 0)}, "
            f"right={context_request.get('expand_right_elements', 0)}, "
            f"reason={context_request.get('reason', '')}"
        )

    def _boundary_position_note(self, boundary: BoundaryCandidate) -> str:
        if boundary.page_gap == 0:
            return f"The candidate is adjacent to the current chunk on page {boundary.left.page_number}."
        if boundary.page_gap == 1:
            return (
                f"The candidate starts on the next page: current chunk ends on page "
                f"{boundary.left.page_number}, candidate is on page {boundary.right.page_number}."
            )
        return (
            f"There is a gap of {boundary.page_gap} pages between the current chunk ending on page "
            f"{boundary.left.page_number} and the candidate on page {boundary.right.page_number}."
        )

    def _boundary_context_rows(
        self,
        boundaries: list[BoundaryCandidate],
        *,
        start_element_index: int,
        end_element_index: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for boundary in boundaries:
            if not (start_element_index <= boundary.boundary_index < end_element_index):
                continue
            preliminary = boundary.preliminary_decision
            rows.append(
                {
                    "boundary_id": boundary.boundary_id,
                    "left_element_id": boundary.left_element_id,
                    "right_element_id": boundary.right_element_id,
                    "decision": preliminary.decision if preliminary is not None else None,
                    "confidence": preliminary.confidence if preliminary is not None else None,
                    "reasons": preliminary.reasons[:3] if preliminary is not None else [],
                }
            )
        return rows

    def _element_view(self, element: ExtractedElement, text: str) -> BoundaryElementView:
        return BoundaryElementView(
            element_id=element.id,
            element_type=element.type,
            page_number=element.page_number,
            order=element.order,
            bbox=element.bbox,
            confidence=element.confidence,
            text=text,
            raw_text=element.raw_text,
            source=element.source,
            asset_path=element.asset_path,
            metadata=dict(element.metadata),
        )

    def _boundary_signals(
        self,
        left: BoundaryElementView,
        right: BoundaryElementView,
        page_gap: int,
        order_gap: int,
        adjacent_similarity: float,
    ) -> BoundarySignals:
        type_prior = self._lookup_prior(left.element_type, right.element_type)
        left_heading = self._heading_like_score(left)
        right_heading = self._heading_like_score(right)
        left_artifact = self._caption_or_artifact_score(left)
        right_artifact = self._caption_or_artifact_score(right)
        left_formula_table = self._formula_or_table_score(left)
        right_formula_table = self._formula_or_table_score(right)
        left_admin = self._admin_front_matter_score(left)
        right_admin = self._admin_front_matter_score(right)
        return BoundarySignals(
            page_gap=page_gap,
            order_gap=order_gap,
            left_confidence=left.confidence,
            right_confidence=right.confidence,
            adjacent_embedding_similarity=max(-1.0, min(1.0, float(adjacent_similarity))),
            type_prior=type_prior,
            left_heading_like_score=left_heading,
            right_heading_like_score=right_heading,
            heading_like_score=max(left_heading, right_heading),
            left_caption_or_artifact_score=left_artifact,
            right_caption_or_artifact_score=right_artifact,
            caption_or_artifact_score=max(left_artifact, right_artifact),
            left_formula_or_table_score=left_formula_table,
            right_formula_or_table_score=right_formula_table,
            formula_or_table_score=max(left_formula_table, right_formula_table),
            left_admin_front_matter_score=left_admin,
            right_admin_front_matter_score=right_admin,
            admin_front_matter_score=max(left_admin, right_admin),
            text_continuation_score=self._text_continuation_score(left, right),
            hard_rule_flags=self._hard_rule_flags(left, right, page_gap, type_prior),
        )

    def _preliminary_decision(self, signals: BoundarySignals) -> BoundaryPreliminaryDecision:
        flags = signals.hard_rule_flags
        if flags.get("right_is_title"):
            return self._make_preliminary_decision(
                decision="split",
                split_probability=0.98,
                confidence=0.96,
                signals=signals,
                reasons=["right element is a title"],
            )
        if flags.get("left_low_confidence") or flags.get("right_low_confidence"):
            return self._make_preliminary_decision(
                decision="split",
                split_probability=0.9,
                confidence=0.88,
                signals=signals,
                reasons=["low-confidence extraction near boundary"],
            )
        if flags.get("type_prior_forces_split"):
            return self._make_preliminary_decision(
                decision="split",
                split_probability=0.94,
                confidence=0.9,
                signals=signals,
                reasons=["type prior strongly favors split"],
            )
        if flags.get("type_prior_free_merge"):
            return self._make_preliminary_decision(
                decision="continue",
                split_probability=0.06,
                confidence=0.9,
                signals=signals,
                reasons=["type prior strongly favors continuation"],
            )
        if flags.get("same_table_continuation"):
            return self._make_preliminary_decision(
                decision="continue",
                split_probability=0.12,
                confidence=0.84,
                signals=signals,
                reasons=["adjacent table elements on same page"],
            )

        split_score = 0.2
        continue_score = 0.2
        reasons: list[str] = []
        similarity = max(0.0, min(1.0, signals.adjacent_embedding_similarity))

        continue_score += signals.type_prior * 0.35
        split_score += (1.0 - signals.type_prior) * 0.25
        if signals.type_prior >= 0.7:
            reasons.append("type prior leans continue")
        elif signals.type_prior <= 0.35:
            reasons.append("type prior leans split")

        continue_score += similarity * 0.2
        split_score += (1.0 - similarity) * 0.18
        if similarity >= 0.72:
            reasons.append("high adjacent similarity")
        elif similarity <= 0.28:
            reasons.append("low adjacent similarity")

        continue_score += signals.text_continuation_score * 0.25
        if signals.text_continuation_score >= 0.65:
            reasons.append("right text appears to continue left text")

        split_score += signals.right_heading_like_score * 0.3
        if signals.right_heading_like_score >= 0.72:
            reasons.append("right side looks like a heading")

        split_score += signals.admin_front_matter_score * 0.16
        if signals.admin_front_matter_score >= 0.72:
            reasons.append("admin or front-matter signal present")

        if signals.formula_or_table_score >= 0.8 and signals.text_continuation_score >= 0.55:
            continue_score += 0.16
            reasons.append("formula/table appears attached to nearby explanation")
        elif signals.formula_or_table_score >= 0.8:
            continue_score += 0.06
            reasons.append("formula/table boundary needs context")

        if signals.caption_or_artifact_score >= 0.8 and signals.page_gap <= 1:
            continue_score += 0.08
            reasons.append("artifact/caption likely attaches locally")

        if signals.page_gap > 0:
            split_score += min(0.18, signals.page_gap * 0.08)
            reasons.append("page gap increases split risk")
        if flags.get("cross_page_gap_large"):
            split_score += 0.12
            reasons.append("large page gap")
        if flags.get("figure_without_text"):
            reasons.append("figure without text needs later repair/audit")

        split_probability = split_score / max(split_score + continue_score, 1e-6)
        margin = abs(split_probability - 0.5)
        if split_probability >= 0.72 and margin >= 0.2:
            decision = "split"
            confidence = min(0.86, 0.54 + margin)
        elif split_probability <= 0.28 and margin >= 0.2:
            decision = "continue"
            confidence = min(0.86, 0.54 + margin)
        else:
            decision = "unknown"
            confidence = max(0.2, min(0.55, 0.55 - margin))

        return self._make_preliminary_decision(
            decision=decision,
            split_probability=split_probability,
            confidence=confidence,
            signals=signals,
            reasons=reasons or ["mixed Tier 0 evidence"],
        )

    def _make_preliminary_decision(
        self,
        *,
        decision: str,
        split_probability: float,
        confidence: float,
        signals: BoundarySignals,
        reasons: list[str],
    ) -> BoundaryPreliminaryDecision:
        return BoundaryPreliminaryDecision(
            decision=decision,
            split_probability=self._clamp_score(split_probability),
            confidence=self._clamp_score(confidence),
            reasons=reasons,
            hard_rule_flags=dict(signals.hard_rule_flags),
        )

    def _heading_like_score(self, element: BoundaryElementView) -> float:
        text = self._normalized_text(element.text)
        if not text:
            return 0.0
        if self._normalized_type(element) == "title":
            return 1.0
        tokens = self._tokens(text)
        if not tokens:
            return 0.0
        score = 0.0
        if len(tokens) <= 12 and not text.endswith((".", "?", "!")):
            score = max(score, 0.45)
        if re.match(r"^(?:\d+(?:\.\d+){0,4}|[ivxlcdm]+)[.)]?\s+\S+", text, flags=re.IGNORECASE):
            score = max(score, 0.82)
        if re.match(r"^(?:chapter|section|part|appendix|principle)\b", text, flags=re.IGNORECASE):
            score = max(score, 0.82)
        alpha_chars = [char for char in text if char.isalpha()]
        uppercase_ratio = (
            sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)
            if alpha_chars
            else 0.0
        )
        if len(tokens) <= 8 and uppercase_ratio >= 0.75:
            score = max(score, 0.78)
        if len(tokens) <= 8 and text[:1].isupper() and not self._has_terminal_sentence(text):
            score = max(score, 0.62)
        if len(tokens) > 18:
            score *= 0.45
        return self._clamp_score(score)

    def _caption_or_artifact_score(self, element: BoundaryElementView) -> float:
        text = self._normalized_text(element.text)
        normalized_type = self._normalized_type(element)
        score = 0.0
        if normalized_type in {"figure", "image", "chart", "diagram", "flowchart"}:
            score = max(score, 0.85)
        if normalized_type in {"formula", "table"}:
            score = max(score, 0.65)
        if re.match(r"^(?:figure|fig\.?|table|formula|equation)\s*[\d:().-]*\b", text, flags=re.IGNORECASE):
            score = max(score, 0.88)
        if "no text content" in text.lower():
            score = max(score, 0.9)
        if element.asset_path and len(self._tokens(text)) <= 12:
            score = max(score, 0.75)
        return self._clamp_score(score)

    def _formula_or_table_score(self, element: BoundaryElementView) -> float:
        text = self._normalized_text(element.text)
        normalized_type = self._normalized_type(element)
        if normalized_type in {"formula", "table"}:
            return 1.0
        score = 0.0
        if text.lower().startswith(("formula:", "table with columns", "equation")):
            score = max(score, 0.9)
        math_chars = sum(1 for char in text if char in "=+-*/^_<>|")
        if math_chars >= 2:
            score = max(score, min(0.85, 0.35 + (math_chars / max(len(text), 1)) * 8.0))
        return self._clamp_score(score)

    def _admin_front_matter_score(self, element: BoundaryElementView) -> float:
        text = self._normalized_text(element.text)
        if not text:
            return 0.0
        lower = text.lower()
        tokens = self._tokens(text)
        apparatus_pattern = re.compile(
            r"\b(?:copyright|all rights reserved|received|accepted|published|correspondence|"
            r"author contributions?|data availability|conflicts? of interest|funding|"
            r"acknowledg(?:e)?ments?|ethics statement|open access|creative commons|licen[cs]e|"
            r"keywords?|table of contents|contents|abstract)\b",
            re.IGNORECASE,
        )
        score = 0.0
        if apparatus_pattern.search(text):
            score = max(score, 0.78)
        if lower in {
            "abstract",
            "keywords",
            "contents",
            "table of contents",
            "references",
            "acknowledgments",
            "acknowledgements",
        }:
            score = max(score, 0.92)
        if element.page_number <= 2 and score > 0.0:
            score += 0.08
        if len(tokens) > 35 and not any(marker in lower for marker in ("copyright", "creative commons", "open access")):
            score *= 0.55
        return self._clamp_score(score)

    def _text_continuation_score(self, left: BoundaryElementView, right: BoundaryElementView) -> float:
        left_text = self._normalized_text(left.text)
        right_text = self._normalized_text(right.text)
        if not left_text or not right_text:
            return 0.0
        score = 0.0
        if not self._has_terminal_sentence(left_text):
            score = max(score, 0.45)
        if left_text.endswith((",", ";", ":", "-", "and", "or")):
            score = max(score, 0.68)
        if re.search(r"\b(?:that|which|because|where|when|if|of|in|to|for|with)$", left_text, flags=re.IGNORECASE):
            score = max(score, 0.72)
        if right_text[:1].islower():
            score = max(score, 0.7)
        if re.match(r"^(?:and|or|but|which|that|therefore|however|because|whereas)\b", right_text, flags=re.IGNORECASE):
            score = max(score, 0.74)
        if self._formula_or_table_score(right) >= 0.9 and left_text.endswith((':', '=')):
            score = max(score, 0.78)
        if self._normalized_type(left) not in {"text", "title"} and self._normalized_type(right) not in {"text", "title"}:
            score *= 0.6
        return self._clamp_score(score)

    def _hard_rule_flags(
        self,
        left: BoundaryElementView,
        right: BoundaryElementView,
        page_gap: int,
        type_prior: float,
    ) -> dict[str, bool]:
        left_type = self._normalized_type(left)
        right_type = self._normalized_type(right)
        return {
            "right_is_title": right_type == "title",
            "left_low_confidence": left.confidence is not None and left.confidence < self.config.MIN_CONFIDENCE,
            "right_low_confidence": right.confidence is not None and right.confidence < self.config.MIN_CONFIDENCE,
            "type_prior_forces_split": type_prior == 0.0,
            "type_prior_free_merge": type_prior >= self.config.FREE_MERGE_PRIOR,
            "cross_page_gap_large": page_gap > 1,
            "figure_without_text": any(
                item.element_type in {"figure", "image", "chart", "diagram", "flowchart"}
                and "no text content" in item.text.lower()
                for item in (left, right)
            ),
            "same_table_continuation": left_type == "table" and right_type == "table" and page_gap == 0,
        }

    def _normalized_type(self, element: BoundaryElementView) -> str:
        return (element.element_type or "").strip().lower()

    def _normalized_text(self, text: str) -> str:
        return " ".join((text or "").split()).strip()

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9_]+", (text or "").lower())

    def _has_terminal_sentence(self, text: str) -> bool:
        return bool(re.search(r"[.!?][\"')\]]*$", (text or "").strip()))

    def _clamp_score(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _compute_similarity_stats(self, texts: list[str]) -> tuple[list[float], float, float]:
        if len(texts) < 2:
            return [], 1.0, 0.0
        embeddings = self._embed_texts(texts)
        scores = [float(np.dot(embeddings[i], embeddings[i + 1])) for i in range(len(embeddings) - 1)]
        return scores, mean(scores), pstdev(scores)

    def _embed_texts(self, texts: Iterable[str]) -> np.ndarray:
        model = self._get_embedder()
        embeddings = model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=float)

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            self._embedder = _HashingEmbedder()
            return self._embedder

        try:
            self._embedder = SentenceTransformer(self.config.EMBEDDING_MODEL, trust_remote_code=True)
        except Exception:
            try:
                self._embedder = SentenceTransformer(self.config.EMBEDDING_FALLBACK)
            except Exception:
                self._embedder = _HashingEmbedder()
        return self._embedder

    def _get_cross_encoder(self):
        if self._cross_encoder is not None:
            return self._cross_encoder
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            self._cross_encoder = _LexicalCrossEncoder()
            return self._cross_encoder
        try:
            self._cross_encoder = CrossEncoder(self.config.CROSS_ENCODER_MODEL)
        except Exception:
            self._cross_encoder = _LexicalCrossEncoder()
        return self._cross_encoder

    def _compute_merge_priors(
        self,
        elements: list[ExtractedElement],
        adjacent_similarities: list[float],
        threshold: float,
        sigma: float,
    ) -> list[float]:
        merge_priors: list[float] = []
        for index in range(len(elements) - 1):
            left = elements[index]
            right = elements[index + 1]
            base_prior = self._lookup_prior(left.type, right.type)
            if right.type == "title":
                merge_priors.append(0.0)
                continue
            if (left.confidence is not None and left.confidence < self.config.MIN_CONFIDENCE) or (
                right.confidence is not None and right.confidence < self.config.MIN_CONFIDENCE
            ):
                merge_priors.append(0.0)
                continue
            if base_prior == 0.0:
                merge_priors.append(0.0)
                continue
            sim_prob = self._similarity_to_probability(adjacent_similarities[index], threshold, sigma)
            combined = (0.6 * base_prior) + (0.4 * sim_prob)
            merge_priors.append(max(self.config.POSTERIOR_EPSILON, min(0.98, combined)))
        return merge_priors

    def _build_blocks(
        self,
        elements: list[ExtractedElement],
    ) -> list[tuple[int, int, BoundaryDecision | None]]:
        blocks: list[tuple[int, int, BoundaryDecision | None]] = []
        start = 0
        for edge_index in range(len(elements) - 1):
            decision = self._tier0_decision(elements[edge_index], elements[edge_index + 1])
            if decision is not None and decision.decision == "split":
                blocks.append((start, edge_index, decision))
                start = edge_index + 1
        blocks.append((start, len(elements) - 1, None))
        return blocks

    def _resolve_block(
        self,
        *,
        elements: list[ExtractedElement],
        texts: list[str],
        adjacent_similarities: list[float],
        merge_priors: list[float],
        threshold: float,
        sigma: float,
        start: int,
        end: int,
    ) -> list[list[ExtractedElement]]:
        chunks: list[list[ExtractedElement]] = []
        cursor = start
        while cursor <= end:
            chunk, next_cursor = self._resolve_group(
                elements=elements,
                texts=texts,
                adjacent_similarities=adjacent_similarities,
                merge_priors=merge_priors,
                threshold=threshold,
                sigma=sigma,
                start=cursor,
                end=end,
            )
            if chunks and self._should_rollback_boundary(chunks[-1], chunk, threshold, sigma):
                self._replace_last_boundary_with_merge(chunks[-1], chunk)
            else:
                chunks.append(chunk)
            cursor = next_cursor
        return chunks

    def _resolve_group(
        self,
        *,
        elements: list[ExtractedElement],
        texts: list[str],
        adjacent_similarities: list[float],
        merge_priors: list[float],
        threshold: float,
        sigma: float,
        start: int,
        end: int,
    ) -> tuple[list[ExtractedElement], int]:
        confirmed_end = self._extend_free_merges(start, end, elements)

        while confirmed_end < end and (
            (confirmed_end - start + 1) < self.config.ANCHOR_MIN_CONFIRMED
            or self._anchor_quality(elements, start, confirmed_end) < self.config.ANCHOR_WARMUP_THRESHOLD
        ):
            free_merged_end = self._extend_free_merges(confirmed_end, end, elements)
            if free_merged_end != confirmed_end:
                confirmed_end = free_merged_end
                continue
            outcome = self._probe_same_group(
                elements=elements,
                texts=texts,
                adjacent_similarities=adjacent_similarities,
                threshold=threshold,
                sigma=sigma,
                start=start,
                confirmed_end=confirmed_end,
                probe_index=confirmed_end + 1,
                block_end=end,
                llm_budget_used=0,
            )
            if outcome.verdict == "same" and outcome.confidence >= self.config.WARMUP_MERGE_THRESHOLD:
                self._append_merge_decisions(confirmed_end, confirmed_end + 1, elements, outcome)
                confirmed_end += 1
                confirmed_end = self._extend_free_merges(confirmed_end, end, elements)
                continue
            self.boundary_log.append(self._split_decision(elements, confirmed_end, outcome, "warm-up split"))
            return elements[start:confirmed_end + 1], confirmed_end + 1

        llm_budget_used = 0
        probe_steps = 0
        last_probe: ProbeOutcome | None = None
        posterior = self._initial_posterior(confirmed_end, end, merge_priors)
        while confirmed_end < end and probe_steps < self.config.MAX_PROBE_STEPS_PER_GROUP:
            free_merged_end = self._extend_free_merges(confirmed_end, end, elements)
            if free_merged_end != confirmed_end:
                confirmed_end = free_merged_end
                if confirmed_end >= end:
                    break
                posterior = self._initial_posterior(confirmed_end, end, merge_priors)
                continue

            probe_index = self._choose_probe_index(posterior, confirmed_end, end, merge_priors)
            if probe_index <= confirmed_end:
                break

            outcome = self._probe_same_group(
                elements=elements,
                texts=texts,
                adjacent_similarities=adjacent_similarities,
                threshold=threshold,
                sigma=sigma,
                start=start,
                confirmed_end=confirmed_end,
                probe_index=probe_index,
                block_end=end,
                llm_budget_used=llm_budget_used,
            )
            llm_budget_used += outcome.llm_calls_used
            last_probe = outcome
            posterior = self._update_posterior(
                posterior=posterior,
                probe_index=probe_index,
                verdict=outcome.verdict,
                reliability=max(0.55, outcome.confidence),
                confirmed_end=confirmed_end,
            )
            tail_mass = self._tail_mass(posterior, probe_index)
            if outcome.verdict == "same" and tail_mass >= self.config.POSTERIOR_MERGE_THRESHOLD:
                self._append_merge_decisions(confirmed_end, probe_index, elements, outcome)
                confirmed_end = probe_index
                confirmed_end = self._extend_free_merges(confirmed_end, end, elements)
                if confirmed_end >= end:
                    break
                posterior = self._initial_posterior(confirmed_end, end, merge_priors)
            elif posterior.get(confirmed_end, 0.0) >= self.config.POSTERIOR_COMMIT_THRESHOLD:
                break
            probe_steps += 1

        if confirmed_end < end:
            confirmed_end, llm_budget_used = self._local_recovery(
                elements=elements,
                texts=texts,
                adjacent_similarities=adjacent_similarities,
                threshold=threshold,
                sigma=sigma,
                start=start,
                confirmed_end=confirmed_end,
                block_end=end,
                llm_budget_used=llm_budget_used,
            )

        if confirmed_end < end:
            left = elements[confirmed_end]
            right = elements[confirmed_end + 1]
            if last_probe is not None and last_probe.verdict == "different":
                self.boundary_log.append(self._split_decision(elements, confirmed_end, last_probe, "search commit"))
            else:
                self.boundary_log.append(
                    BoundaryDecision(
                        left_element_id=left.id,
                        right_element_id=right.id,
                        tier_used="recovery" if probe_steps >= self.config.MAX_PROBE_STEPS_PER_GROUP else "search",
                        decision="split",
                        confidence=0.78,
                        notes="conservative split after anchor-guided search",
                    )
                )
            self.recoverable_errors.append(
                f"Unresolved boundary defaulted to split between {left.id} and {right.id}."
            )
        return elements[start:confirmed_end + 1], confirmed_end + 1

    def _extend_free_merges(self, confirmed_end: int, end: int, elements: list[ExtractedElement]) -> int:
        current = confirmed_end
        while current < end:
            decision = self._tier0_decision(elements[current], elements[current + 1])
            if decision is None or decision.decision != "merge":
                break
            self.boundary_log.append(decision)
            current += 1
        return current

    def _initial_posterior(self, confirmed_end: int, end: int, merge_priors: list[float]) -> dict[int, float]:
        log_weights: dict[int, float] = {}
        for position in range(confirmed_end, end + 1):
            log_weight = 0.0
            for edge_index in range(confirmed_end, position):
                log_weight += math.log(max(self.config.POSTERIOR_EPSILON, merge_priors[edge_index]))
            if position < end:
                boundary_prob = max(self.config.POSTERIOR_EPSILON, 1.0 - merge_priors[position])
            else:
                boundary_prob = max(self.config.POSTERIOR_EPSILON, 0.5)
            log_weight += math.log(boundary_prob)
            log_weights[position] = log_weight
        max_log = max(log_weights.values())
        weights = {position: math.exp(value - max_log) for position, value in log_weights.items()}
        total = sum(weights.values()) or 1.0
        return {position: value / total for position, value in weights.items()}

    def _choose_probe_index(
        self,
        posterior: dict[int, float],
        confirmed_end: int,
        end: int,
        merge_priors: list[float],
    ) -> int:
        candidates = [(position, prob) for position, prob in posterior.items() if position > confirmed_end]
        if not candidates:
            return confirmed_end
        max_prob = max(prob for _, prob in candidates)
        if max_prob < (1.0 / max(1, len(candidates))) * 1.2:
            boundary_weights = {position: 1.0 - merge_priors[position] for position, _ in candidates if position < end}
            if boundary_weights:
                return max(boundary_weights.items(), key=lambda item: item[1])[0]
        cumulative = 0.0
        for position, probability in sorted(candidates, key=lambda item: item[0]):
            cumulative += probability
            if cumulative >= 0.5:
                return position
        return candidates[-1][0]

    def _probe_same_group(
        self,
        *,
        elements: list[ExtractedElement],
        texts: list[str],
        adjacent_similarities: list[float],
        threshold: float,
        sigma: float,
        start: int,
        confirmed_end: int,
        probe_index: int,
        block_end: int,
        llm_budget_used: int,
    ) -> ProbeOutcome:
        anchor_summary = self._summarize_anchor(elements, texts, start, confirmed_end)
        probe_summary = self._summarize_probe(texts, probe_index, block_end)
        anchor_quality = self._anchor_quality(elements, start, confirmed_end)

        if probe_index == confirmed_end + 1 and confirmed_end < len(adjacent_similarities):
            similarity = adjacent_similarities[confirmed_end]
            similarity_note = "adjacent similarity"
        else:
            similarity = self._summary_similarity(anchor_summary, probe_summary)
            similarity_note = "anchor similarity"

        merge_margin = max(0.05, (1.0 - anchor_quality) * 0.18, sigma * 0.25)
        split_margin = max(0.05, (1.0 - anchor_quality) * 0.10, sigma * 0.15)
        if similarity >= threshold + merge_margin:
            confidence = min(0.92, 0.6 + max(0.0, similarity - threshold))
            return ProbeOutcome("same", confidence, "1a", f"{similarity_note} {similarity:.3f} exceeds merge margin")
        if similarity <= threshold - split_margin:
            confidence = min(0.92, 0.6 + max(0.0, threshold - similarity))
            return ProbeOutcome("different", confidence, "1a", f"{similarity_note} {similarity:.3f} below split margin")

        cross_score = self._score_cross_encoder(anchor_summary, probe_summary)
        if cross_score >= self.config.CROSS_ENCODER_MERGE_THRESHOLD:
            return ProbeOutcome("same", cross_score, "1b", f"cross-encoder score {cross_score:.3f} above merge threshold")
        if cross_score <= self.config.CROSS_ENCODER_SPLIT_THRESHOLD:
            return ProbeOutcome("different", 1.0 - cross_score, "1b", f"cross-encoder score {cross_score:.3f} below split threshold")

        return self._llm_probe(
            texts=texts,
            start=start,
            confirmed_end=confirmed_end,
            probe_index=probe_index,
            block_end=block_end,
            anchor_summary=anchor_summary,
            probe_summary=probe_summary,
            anchor_quality=anchor_quality,
            llm_budget_used=llm_budget_used,
        )

    def _llm_probe(
        self,
        *,
        texts: list[str],
        start: int,
        confirmed_end: int,
        probe_index: int,
        block_end: int,
        anchor_summary: str,
        probe_summary: str,
        anchor_quality: float,
        llm_budget_used: int,
    ) -> ProbeOutcome:
        if self.llm_client is None:
            return ProbeOutcome("different", 0.72, "2", "llm unavailable; conservative split")

        schedule = self._context_schedule(self.config.LLM_CONTEXT_WINDOW_SIZE)
        same_votes = 0
        different_votes = 0
        calls_used = 0
        last_valid = "DIFFERENT"
        for context_size in schedule:
            if llm_budget_used + calls_used >= self.config.MAX_LLM_CALLS_PER_BOUNDARY:
                return ProbeOutcome("different", 0.8, "2", "llm budget exhausted; conservative split", calls_used)

            left_context = texts[max(0, start - context_size):start]
            between = texts[confirmed_end + 1:probe_index]
            right_context = texts[probe_index + 1:min(len(texts), probe_index + 1 + context_size)]
            system = "You are analyzing concept boundaries in a technical document."
            user = (
                "You are analyzing a technical document to detect concept boundaries.\n\n"
                f"Context (elements before the comparison point):\n{self._join_or_placeholder(left_context)}\n\n"
                f"Element A:\n{anchor_summary}\n\n"
                f"[All elements between A and B:]\n{self._join_or_placeholder(between)}\n\n"
                f"Element B:\n{probe_summary}\n\n"
                f"Context (elements after the comparison point):\n{self._join_or_placeholder(right_context)}\n\n"
                "Do element A and element B belong to the same concept or do they represent a transition to a new concept?\n"
                "Reply with exactly one word: SAME or DIFFERENT."
            )
            response = self.llm_client.complete(system=system, user=user, temperature=0.0).content.strip().upper()
            self._record_llm_call()
            calls_used += 1
            if response not in {"SAME", "DIFFERENT"}:
                continue
            last_valid = response
            if response == "SAME":
                same_votes += 1
                if same_votes >= 2 or (anchor_quality >= self.config.ANCHOR_WARMUP_THRESHOLD and context_size >= 2):
                    confidence = min(0.92, 0.65 + 0.1 * anchor_quality + 0.08 * (context_size / max(1, self.config.LLM_CONTEXT_WINDOW_SIZE)))
                    return ProbeOutcome("same", confidence, "2", "llm confirmed same-group probe", calls_used)
            else:
                different_votes += 1
                confidence = min(0.9, 0.68 + 0.08 * (context_size / max(1, self.config.LLM_CONTEXT_WINDOW_SIZE)))
                return ProbeOutcome("different", confidence, "2", "llm confirmed boundary probe", calls_used)

        if last_valid == "SAME":
            confidence = 0.7 if anchor_quality >= self.config.ANCHOR_WARMUP_THRESHOLD else 0.62
            return ProbeOutcome("same", confidence, "2", "llm weak same-group signal at max context", calls_used)
        return ProbeOutcome("different", 0.76, "2", "llm ambiguous; conservative split", calls_used)

    def _local_recovery(
        self,
        *,
        elements: list[ExtractedElement],
        texts: list[str],
        adjacent_similarities: list[float],
        threshold: float,
        sigma: float,
        start: int,
        confirmed_end: int,
        block_end: int,
        llm_budget_used: int,
    ) -> tuple[int, int]:
        current_end = confirmed_end
        calls_used = llm_budget_used
        steps = 0
        while current_end < block_end and steps < self.config.MAX_LOCAL_RECOVERY_STEPS:
            free_merged_end = self._extend_free_merges(current_end, block_end, elements)
            if free_merged_end != current_end:
                current_end = free_merged_end
                continue
            outcome = self._probe_same_group(
                elements=elements,
                texts=texts,
                adjacent_similarities=adjacent_similarities,
                threshold=threshold,
                sigma=sigma,
                start=start,
                confirmed_end=current_end,
                probe_index=current_end + 1,
                block_end=block_end,
                llm_budget_used=calls_used,
            )
            calls_used += outcome.llm_calls_used
            if outcome.verdict == "same" and outcome.confidence >= self.config.POSTERIOR_MERGE_THRESHOLD:
                self._append_merge_decisions(current_end, current_end + 1, elements, outcome)
                current_end += 1
                steps += 1
                continue
            break
        return current_end, calls_used

    def _should_rollback_boundary(
        self,
        left_chunk: list[ExtractedElement],
        right_chunk: list[ExtractedElement],
        threshold: float,
        sigma: float,
    ) -> bool:
        if not left_chunk or not right_chunk:
            return False
        left_summary = self._summarize_chunk(left_chunk)
        right_summary = self._summarize_chunk(right_chunk)
        similarity = self._summary_similarity(left_summary, right_summary)
        if similarity >= threshold + max(0.08, sigma * 0.5):
            return True
        cross_score = self._score_cross_encoder(left_summary, right_summary)
        return cross_score >= self.config.ROLLBACK_MERGE_THRESHOLD

    def _replace_last_boundary_with_merge(
        self,
        left_chunk: list[ExtractedElement],
        right_chunk: list[ExtractedElement],
    ) -> None:
        boundary_left = left_chunk[-1].id
        boundary_right = right_chunk[0].id
        for index in range(len(self.boundary_log) - 1, -1, -1):
            entry = self.boundary_log[index]
            if entry.left_element_id == boundary_left and entry.right_element_id == boundary_right:
                self.boundary_log[index] = BoundaryDecision(
                    left_element_id=boundary_left,
                    right_element_id=boundary_right,
                    tier_used="rollback",
                    decision="merge",
                    confidence=0.88,
                    notes="local sanity check merged adjacent chunks",
                )
                break
        left_chunk.extend(right_chunk)

    def _append_merge_decisions(
        self,
        left_index: int,
        right_index: int,
        elements: list[ExtractedElement],
        outcome: ProbeOutcome,
    ) -> None:
        for edge_index in range(left_index, right_index):
            self.boundary_log.append(
                BoundaryDecision(
                    left_element_id=elements[edge_index].id,
                    right_element_id=elements[edge_index + 1].id,
                    tier_used=outcome.tier_used,
                    decision="merge",
                    confidence=max(0.0, min(1.0, outcome.confidence)),
                    notes=outcome.notes,
                )
            )

    def _split_decision(
        self,
        elements: list[ExtractedElement],
        left_index: int,
        outcome: ProbeOutcome,
        suffix: str,
    ) -> BoundaryDecision:
        return BoundaryDecision(
            left_element_id=elements[left_index].id,
            right_element_id=elements[left_index + 1].id,
            tier_used=outcome.tier_used,
            decision="split",
            confidence=max(0.0, min(1.0, outcome.confidence)),
            notes=f"{outcome.notes}; {suffix}",
        )

    def _tier0_decision(self, left: ExtractedElement, right: ExtractedElement) -> BoundaryDecision | None:
        if right.type == "title":
            return self._make_decision(left, right, "0", "split", 1.0, "title starts a new hard block")
        if (left.confidence is not None and left.confidence < self.config.MIN_CONFIDENCE) or (
            right.confidence is not None and right.confidence < self.config.MIN_CONFIDENCE
        ):
            return self._make_decision(left, right, "0", "split", 0.98, "low confidence adjacent element")

        prior = self._lookup_prior(left.type, right.type)
        if prior == 0.0:
            return self._make_decision(left, right, "0", "split", 1.0, f"type prior forces hard boundary ({left.type}->{right.type})")
        if prior >= self.config.FREE_MERGE_PRIOR:
            return self._make_decision(left, right, "0", "merge", prior, f"type prior free merge ({left.type}->{right.type})")
        return None

    def _lookup_prior(self, left_type: str, right_type: str) -> float:
        normalized = (left_type.strip().lower(), right_type.strip().lower())
        if normalized[0] == "title":
            return 0.5
        return self.type_priors.get(
            normalized,
            self.type_priors.get((normalized[0], "*"), self.type_priors.get(("*", normalized[1]), 0.5)),
        )

    def _score_cross_encoder(self, left_text: str, right_text: str) -> float:
        model = self._get_cross_encoder()
        score = model.predict([(left_text, right_text)])
        raw_score = float(np.asarray(score).reshape(-1)[0])
        return 1.0 / (1.0 + math.exp(-raw_score))

    def _summary_similarity(self, left_text: str, right_text: str) -> float:
        embeddings = self._embed_texts([left_text, right_text])
        return float(np.dot(embeddings[0], embeddings[1]))

    def _similarity_to_probability(self, similarity: float, threshold: float, sigma: float) -> float:
        scale = sigma if sigma > 0.0 else 0.1
        value = (similarity - threshold) / max(scale, 1e-6)
        return 1.0 / (1.0 + math.exp(-value))

    def _anchor_quality(self, elements: list[ExtractedElement], start: int, end: int) -> float:
        chunk = elements[start:end + 1]
        size_factor = min(1.0, len(chunk) / max(1, self.config.ANCHOR_MIN_CONFIRMED))
        type_factor = min(1.0, len({element.type for element in chunk}) / 2.0)
        confidences = [element.confidence for element in chunk if element.confidence is not None]
        confidence_factor = (sum(confidences) / len(confidences)) if confidences else 0.5
        return (0.6 * size_factor) + (0.2 * type_factor) + (0.2 * confidence_factor)

    def _summarize_anchor(
        self,
        elements: list[ExtractedElement],
        texts: list[str],
        start: int,
        end: int,
    ) -> str:
        indices = list(range(start, end + 1))
        if len(indices) <= self.config.ANCHOR_MAX_FULL_ELEMENTS:
            return "\n".join(texts[index] for index in indices)

        first = indices[:self.config.ANCHOR_EDGE_ELEMENTS]
        last = indices[-self.config.ANCHOR_EDGE_ELEMENTS:]
        diagnostic = [
            index
            for index in indices[self.config.ANCHOR_EDGE_ELEMENTS:-self.config.ANCHOR_EDGE_ELEMENTS]
            if elements[index].type not in {"text", "title"}
        ]
        selected = []
        seen = set()
        for index in first + diagnostic[:2] + last:
            if index not in seen:
                seen.add(index)
                selected.append(index)
        type_histogram: dict[str, int] = {}
        for index in indices:
            type_histogram[elements[index].type] = type_histogram.get(elements[index].type, 0) + 1
        histogram_text = ", ".join(f"{key}:{value}" for key, value in sorted(type_histogram.items()))
        middle_count = max(0, len(indices) - len(selected))
        parts = [texts[index] for index in selected]
        parts.append(f"Anchor summary: {len(indices)} confirmed elements; types = {histogram_text}; compressed middle count = {middle_count}.")
        return "\n".join(parts)

    def _summarize_probe(self, texts: list[str], probe_index: int, block_end: int) -> str:
        radius = max(0, self.config.PROBE_WINDOW_RADIUS)
        start = max(0, probe_index - radius)
        end = min(block_end, probe_index + radius)
        return "\n".join(texts[index] for index in range(start, end + 1))

    def _summarize_chunk(self, chunk: list[ExtractedElement]) -> str:
        return "\n".join(self.preprocessor.to_text(element) for element in chunk)

    def _update_posterior(
        self,
        *,
        posterior: dict[int, float],
        probe_index: int,
        verdict: str,
        reliability: float,
        confirmed_end: int,
    ) -> dict[int, float]:
        updated: dict[int, float] = {}
        low = max(0.5, min(0.99, reliability))
        high = 1.0 - low
        for position, probability in posterior.items():
            if position < confirmed_end:
                continue
            favored = position >= probe_index if verdict == "same" else position < probe_index
            updated[position] = probability * (low if favored else high)
        total = sum(updated.values())
        if total <= 0.0:
            return posterior
        return {position: value / total for position, value in updated.items()}

    def _tail_mass(self, posterior: dict[int, float], probe_index: int) -> float:
        return sum(value for position, value in posterior.items() if position >= probe_index)

    def _context_schedule(self, max_size: int) -> list[int]:
        if max_size <= 1:
            return [1]
        schedule: list[int] = []
        current = 1
        while current < max_size:
            schedule.append(current)
            current *= 2
        schedule.append(max_size)
        return schedule

    def _join_or_placeholder(self, texts: list[str]) -> str:
        return "\n".join(texts) if texts else ""

    def _make_decision(
        self,
        left: ExtractedElement,
        right: ExtractedElement,
        tier: str,
        decision: str,
        confidence: float,
        notes: str,
    ) -> BoundaryDecision:
        return BoundaryDecision(
            left_element_id=left.id,
            right_element_id=right.id,
            tier_used=tier,
            decision=decision,
            confidence=max(0.0, min(1.0, confidence)),
            notes=notes,
        )
