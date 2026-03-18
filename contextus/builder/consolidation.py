from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contextus.ingestion.models import ExtractedDocument, ExtractedElement

from .audit import ChunkAuditExporter
from .labeler import ChunkAuditLabeler
from .preprocessor import ElementPreprocessor
from .training import AttachmentDirectionResolver, ChunkActionModel


MERGE_ACTIONS = {"attach_left", "attach_right", "duplicate_drop"}
SUPPORT_ONLY_ACTIONS = {"support_only"}


@dataclass
class EvidenceChunk:
    """One source chunk attached to a canonical consolidated chunk."""

    chunk_index: int
    action: str
    confidence: float
    needs_review: bool
    used_for_node_text: bool
    elements: list[ExtractedElement]
    text: str
    source: str
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def page_numbers(self) -> list[int]:
        """Return sorted page numbers covered by this evidence chunk."""
        return sorted({element.page_number for element in self.elements})

    def element_ids(self) -> list[str]:
        """Return source element ids in stored order."""
        return [element.id for element in self.elements]


@dataclass
class ConsolidatedChunk:
    """A canonical chunk plus attached structural and duplicate evidence."""

    canonical_chunk_index: int
    segments: list[EvidenceChunk] = field(default_factory=list)

    def ordered_segments(self) -> list[EvidenceChunk]:
        """Return all segments in original document order."""
        return sorted(self.segments, key=lambda item: item.chunk_index)

    def node_text_segments(self) -> list[EvidenceChunk]:
        """Return only segments that should inform node construction text."""
        return [segment for segment in self.ordered_segments() if segment.used_for_node_text]

    def node_elements(self) -> list[ExtractedElement]:
        """Return merged node-text elements in document order."""
        elements: list[ExtractedElement] = []
        for segment in self.node_text_segments():
            elements.extend(sorted(segment.elements, key=lambda item: (item.page_number, item.order)))
        return elements

    def supporting_segments(self) -> list[EvidenceChunk]:
        """Return attached evidence not merged into the node text."""
        return [segment for segment in self.ordered_segments() if not segment.used_for_node_text]


class ChunkConsolidator:
    """Uses chunk-action predictions to consolidate chunks before node building."""

    DEFAULT_MODEL_PATH = Path("models/chunk-action-logreg.pkl")

    def __init__(
        self,
        *,
        chunk_action_model: ChunkActionModel | None = None,
        model_path: str | Path | None = None,
        audit_exporter: ChunkAuditExporter | None = None,
        preprocessor: ElementPreprocessor | None = None,
        policy_labeler: ChunkAuditLabeler | None = None,
    ) -> None:
        """Create a consolidator with optional trained-model support."""
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.audit_exporter = audit_exporter or ChunkAuditExporter(preprocessor=self.preprocessor)
        self.policy_labeler = policy_labeler or ChunkAuditLabeler()
        self.chunk_action_model = chunk_action_model or self._load_model(model_path)
        self.direction_resolver = AttachmentDirectionResolver()
        self.last_predictions: list[dict[str, Any]] = []
        self.last_action_counts: Counter[str] = Counter()
        self.last_effective_action_counts: Counter[str] = Counter()
        self.last_orphan_support_segments: list[EvidenceChunk] = []

    def consolidate(
        self,
        document: ExtractedDocument,
        chunks: list[list[ExtractedElement]],
    ) -> list[ConsolidatedChunk]:
        """Consolidate raw chunks into canonical chunks with attached evidence."""
        if not chunks:
            self.last_predictions = []
            self.last_action_counts = Counter()
            self.last_effective_action_counts = Counter()
            self.last_orphan_support_segments = []
            return []

        rows = [row.to_dict() for row in self.audit_exporter.rows_from_chunks(document, chunks)]
        predictions = [self._predict(row) for row in rows]
        effective_actions = [self._effective_action(row, prediction) for row, prediction in zip(rows, predictions)]
        self.last_orphan_support_segments = []
        if "standalone" not in effective_actions and any(action not in SUPPORT_ONLY_ACTIONS.union({"duplicate_drop"}) for action in effective_actions):
            effective_actions[0] = "standalone"
            predictions[0] = {
                **predictions[0],
                "action": "standalone",
                "rationale": "Promoted to standalone because the document would otherwise have no canonical chunk.",
            }

        canonical_indices = [index for index, action in enumerate(effective_actions) if action == "standalone"]
        bundles: dict[int, ConsolidatedChunk] = {}
        for index in canonical_indices:
            bundles[index] = ConsolidatedChunk(
                canonical_chunk_index=index,
                segments=[self._make_segment(index, chunks[index], rows[index], predictions[index], source="primary")],
            )

        for index, action in enumerate(effective_actions):
            if action == "standalone":
                continue
            target_index = self._resolve_target_index(
                action=action,
                index=index,
                canonical_indices=canonical_indices,
                bundles=bundles,
                row=rows[index],
            )
            if target_index is None:
                if action in SUPPORT_ONLY_ACTIONS.union({"duplicate_drop"}):
                    self.last_orphan_support_segments.append(
                        self._make_segment(index, chunks[index], rows[index], predictions[index], source="document_support")
                    )
                    continue
                canonical_indices.append(index)
                canonical_indices.sort()
                bundles[index] = ConsolidatedChunk(
                    canonical_chunk_index=index,
                    segments=[self._make_segment(index, chunks[index], rows[index], {**predictions[index], "action": "standalone"}, source="primary")],
                )
                continue
            segment_source = "support" if action in SUPPORT_ONLY_ACTIONS.union({"duplicate_drop"}) else "attached"
            bundles[target_index].segments.append(
                self._make_segment(index, chunks[index], rows[index], predictions[index], source=segment_source)
            )

        self.last_predictions = predictions
        self.last_action_counts = Counter(prediction["action"] for prediction in predictions)
        self.last_effective_action_counts = Counter(effective_actions)
        return [bundles[index] for index in sorted(canonical_indices)]

    def _load_model(self, model_path: str | Path | None) -> ChunkActionModel | None:
        path = Path(model_path) if model_path is not None else self.DEFAULT_MODEL_PATH
        if not path.exists():
            return None
        try:
            return ChunkActionModel.load(path)
        except Exception:
            return None

    def _predict(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.chunk_action_model is not None:
            prediction = self.chunk_action_model.predict_row(row)
            result = {
                "action": str(prediction.get("action") or "standalone"),
                "confidence": float(prediction.get("confidence") or 0.0),
                "needs_review": bool(prediction.get("needs_review")),
                "rationale": str(prediction.get("used_rule") or "model_prediction"),
                "label_source": type(self.chunk_action_model).__name__,
                "raw": prediction,
            }
        else:
            labeled = self.policy_labeler.label_row(row)
            result = {
                "action": str(labeled.get("weak_action") or "standalone"),
                "confidence": float(labeled.get("weak_confidence") or 0.0),
                "needs_review": bool(labeled.get("weak_needs_review")),
                "rationale": str(labeled.get("weak_rationale") or "policy_prediction"),
                "label_source": labeled.get("weak_label_source") or type(self.policy_labeler).__name__,
                "raw": labeled,
            }
        support_only = self.policy_labeler.support_only_decision(row)
        if support_only is not None and result["action"] != "duplicate_drop":
            return {
                "action": support_only.action,
                "confidence": max(result["confidence"], support_only.confidence),
                "needs_review": support_only.needs_review,
                "rationale": support_only.rationale,
                "label_source": type(self.policy_labeler).__name__,
                "raw": result.get("raw"),
            }
        return result

    def _effective_action(self, row: dict[str, Any], prediction: dict[str, Any]) -> str:
        action = str(prediction.get("action") or "standalone")
        if action in SUPPORT_ONLY_ACTIONS:
            return action
        if action in MERGE_ACTIONS and bool(prediction.get("needs_review")):
            if self.policy_labeler.support_only_decision(row) is not None:
                return "support_only"
            return "standalone"
        return action

    def _make_segment(
        self,
        chunk_index: int,
        chunk: list[ExtractedElement],
        row: dict[str, Any],
        prediction: dict[str, Any],
        *,
        source: str,
    ) -> EvidenceChunk:
        action = str(prediction.get("action") or "standalone")
        used_for_node_text = action not in SUPPORT_ONLY_ACTIONS.union({"duplicate_drop"})
        metadata = {
            "label_source": prediction.get("label_source"),
            "row_suggested_action": row.get("suggested_action"),
            "prediction_raw": prediction.get("raw"),
        }
        return EvidenceChunk(
            chunk_index=chunk_index,
            action=action,
            confidence=float(prediction.get("confidence") or 0.0),
            needs_review=bool(prediction.get("needs_review")),
            used_for_node_text=used_for_node_text,
            elements=list(chunk),
            text=str(row.get("chunk_text") or ""),
            source=source,
            rationale=str(prediction.get("rationale") or ""),
            metadata=metadata,
        )

    def _resolve_target_index(
        self,
        *,
        action: str,
        index: int,
        canonical_indices: list[int],
        bundles: dict[int, ConsolidatedChunk],
        row: dict[str, Any],
    ) -> int | None:
        if action == "attach_left":
            return self._nearest_canonical(canonical_indices, index=index, direction=-1) or self._nearest_canonical(canonical_indices, index=index, direction=1)
        if action == "attach_right":
            return self._nearest_canonical(canonical_indices, index=index, direction=1) or self._nearest_canonical(canonical_indices, index=index, direction=-1)
        if action == "duplicate_drop":
            earlier = [candidate for candidate in canonical_indices if candidate < index]
            if earlier:
                return self._best_duplicate_target(earlier, bundles=bundles, row=row)
            return self._nearest_canonical(canonical_indices, index=index, direction=-1) or self._nearest_canonical(canonical_indices, index=index, direction=1)
        if action == "support_only":
            return self._support_target_index(canonical_indices, index=index, row=row)
        return None

    def _support_target_index(
        self,
        canonical_indices: list[int],
        *,
        index: int,
        row: dict[str, Any],
    ) -> int | None:
        resolution = self.direction_resolver.resolve(row, allow_fallback=True)
        if resolution.action == "attach_left":
            return self._nearest_canonical(canonical_indices, index=index, direction=-1) or self._nearest_canonical(canonical_indices, index=index, direction=1)
        if resolution.action == "attach_right":
            return self._nearest_canonical(canonical_indices, index=index, direction=1) or self._nearest_canonical(canonical_indices, index=index, direction=-1)
        return self._nearest_canonical(canonical_indices, index=index, direction=1) or self._nearest_canonical(canonical_indices, index=index, direction=-1)

    def _nearest_canonical(self, canonical_indices: list[int], *, index: int, direction: int) -> int | None:
        if direction < 0:
            candidates = [candidate for candidate in canonical_indices if candidate < index]
            return candidates[-1] if candidates else None
        candidates = [candidate for candidate in canonical_indices if candidate > index]
        return candidates[0] if candidates else None

    def _best_duplicate_target(
        self,
        candidates: list[int],
        *,
        bundles: dict[int, ConsolidatedChunk],
        row: dict[str, Any],
    ) -> int:
        chunk_text = str(row.get("chunk_text") or "")
        best_index = candidates[-1]
        best_score = -1.0
        for candidate in candidates:
            primary_text = self._bundle_primary_text(bundles[candidate])
            score = self.audit_exporter._lexical_similarity(chunk_text, primary_text)
            if score > best_score:
                best_score = score
                best_index = candidate
        return best_index

    def _bundle_primary_text(self, chunk: ConsolidatedChunk) -> str:
        for segment in chunk.ordered_segments():
            if segment.source == "primary":
                return segment.text
        return chunk.ordered_segments()[0].text if chunk.segments else ""