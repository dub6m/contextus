from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable
import hashlib
import math
import re

import numpy as np

from contextus.ingestion.models import ExtractedDocument, ExtractedElement
from contextus.llm import LLMClient

from .config import BuilderConfig
from .preprocessor import ElementPreprocessor


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
        self.boundary_log: list[BoundaryDecision] = []
        self._embedder = None
        self._cross_encoder = None
        self.llm_calls = 0
        self.recoverable_errors: list[str] = []

    def chunk(self, document: ExtractedDocument) -> list[list[ExtractedElement]]:
        """Chunk the document into contiguous groups in global reading order."""
        elements = self._sorted_elements(document)
        self.boundary_log = []
        self.llm_calls = 0
        self.recoverable_errors = []
        if not elements:
            return []
        if len(elements) == 1:
            return [[elements[0]]]

        texts = [self.preprocessor.to_text(element) for element in elements]
        adjacent_similarities, similarity_mean, similarity_std = self._compute_similarity_stats(texts)
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
            self.llm_calls += 1
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
