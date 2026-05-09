from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

from contextus.ingestion.models import ExtractedDocument, ExtractedElement

from .chunker import BoundaryElementView, ChunkRepairDecision, RefinedChunkGroup
from .preprocessor import ElementPreprocessor


VISUAL_TYPES = {"figure", "image"}
SUPPORT_TYPES = {"figure", "image", "table", "formula"}
HEADING_TYPES = {"title", "heading", "section_header"}


@dataclass
class NodeCandidate:
    """Step 7 node-shaped view of one repaired chunk."""

    candidate_id: str
    candidate_index: int
    elements: list[ExtractedElement]
    text: str
    title: str
    summary: str
    source_page_numbers: list[int]
    source_element_ids: list[str]
    element_types: list[str]
    quality_flags: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class NodeCandidateBuilder:
    """Creates one node candidate per repaired chunk without assigning relationships."""

    def __init__(self, preprocessor: ElementPreprocessor | None = None) -> None:
        self.preprocessor = preprocessor or ElementPreprocessor()

    def build_candidates(
        self,
        document: ExtractedDocument,
        chunks: list[list[ExtractedElement] | RefinedChunkGroup],
    ) -> list[NodeCandidate]:
        """Return one node candidate per input chunk."""
        element_by_id = {
            element.id: element
            for page in document.pages
            for element in page.elements
        }
        candidates = [
            self._candidate_from_chunk(index=index, chunk=chunk, element_by_id=element_by_id)
            for index, chunk in enumerate(chunks)
        ]
        self._mark_repeated_titles(candidates)
        return candidates

    def _candidate_from_chunk(
        self,
        *,
        index: int,
        chunk: list[ExtractedElement] | RefinedChunkGroup,
        element_by_id: dict[str, ExtractedElement],
    ) -> NodeCandidate:
        elements = self._chunk_elements(chunk, element_by_id)
        text = self._chunk_text(elements)
        title = self._candidate_title(elements, text, index)
        summary = self._candidate_summary(text)
        metadata = self._chunk_metadata(chunk)
        metadata.update(
            {
                "candidate_index": index,
                "candidate_title": title,
                "candidate_summary": summary,
            }
        )
        return NodeCandidate(
            candidate_id=f"node-candidate-{index:05d}",
            candidate_index=index,
            elements=elements,
            text=text,
            title=title,
            summary=summary,
            source_page_numbers=sorted({element.page_number for element in elements}),
            source_element_ids=[element.id for element in elements],
            element_types=[element.type for element in elements],
            quality_flags=self._quality_flags(elements, text),
            metadata=metadata,
        )

    def _chunk_elements(
        self,
        chunk: list[ExtractedElement] | RefinedChunkGroup,
        element_by_id: dict[str, ExtractedElement],
    ) -> list[ExtractedElement]:
        if isinstance(chunk, RefinedChunkGroup):
            elements: list[ExtractedElement] = []
            for view in chunk.elements:
                element = element_by_id.get(view.element_id)
                if element is None:
                    element = self._element_from_view(view)
                elements.append(element)
            return elements
        return list(chunk)

    def _element_from_view(self, view: BoundaryElementView) -> ExtractedElement:
        return ExtractedElement(
            id=view.element_id,
            type=view.element_type,
            page_number=view.page_number,
            order=view.order,
            bbox=view.bbox,
            confidence=view.confidence,
            content=view.text,
            raw_text=view.raw_text,
            source=view.source,
            metadata=dict(view.metadata),
            asset_path=view.asset_path,
        )

    def _chunk_text(self, elements: list[ExtractedElement]) -> str:
        lines = []
        for element in elements:
            text = " ".join(self.preprocessor.to_text(element).split())
            if text:
                lines.append(text)
        return "\n".join(lines)

    def _candidate_title(self, elements: list[ExtractedElement], text: str, index: int) -> str:
        for element in elements:
            if element.type.lower() in HEADING_TYPES:
                title = " ".join(self.preprocessor.to_text(element).split())
                if title:
                    return self._limit_words(title, 10)
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        return self._limit_words(first_line, 10) or f"Chunk {index + 1}"

    def _candidate_summary(self, text: str) -> str:
        normalized = " ".join(text.split())
        if not normalized:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        summary = " ".join(sentence for sentence in sentences[:2] if sentence)
        return self._limit_words(summary or normalized, 45)

    def _quality_flags(self, elements: list[ExtractedElement], text: str) -> dict[str, bool]:
        tokens = re.findall(r"[A-Za-z0-9_]+", text)
        types = [element.type.lower() for element in elements]
        support_count = sum(1 for item in types if item in SUPPORT_TYPES)
        visual_count = sum(1 for item in types if item in VISUAL_TYPES)
        heading_count = sum(1 for item in types if item in HEADING_TYPES)
        text_count = sum(1 for item in types if item == "text")
        return {
            "empty_text": not bool(text.strip()),
            "low_information": len(tokens) < 8,
            "mostly_visual": visual_count > 0 and visual_count >= max(1, text_count),
            "support_heavy": support_count > 0 and support_count >= max(1, text_count),
            "formula_or_table_heavy": any(item in {"formula", "table"} for item in types) and support_count >= max(1, text_count),
            "multiple_headings": heading_count > 1,
            "starts_mid_sentence": self._starts_mid_sentence(text),
            "ends_mid_thought": self._ends_mid_thought(text),
            "possible_duplicate_title": False,
        }

    def _chunk_metadata(self, chunk: list[ExtractedElement] | RefinedChunkGroup) -> dict[str, Any]:
        if isinstance(chunk, RefinedChunkGroup):
            return {
                "step7_source": "repaired_group",
                "source_group_id": chunk.group_id,
                "source_block_id": chunk.source_block_id,
                "source_group_index": chunk.group_index,
                "source_stability": chunk.stability,
                "source_reason_summary": chunk.reason_summary,
                "repair_decisions": [self._repair_decision_dict(decision) for decision in chunk.repair_decisions],
                "probe_decision_count": len(chunk.probe_decisions),
            }
        return {"step7_source": "element_chunk"}

    def _repair_decision_dict(self, decision: ChunkRepairDecision) -> dict[str, Any]:
        return {
            "action": decision.action,
            "confidence": decision.confidence,
            "source": decision.source,
            "reasons": list(decision.reasons),
            "affected_element_ids": list(decision.affected_element_ids),
            "source_group_id": decision.source_group_id,
            "target_group_id": decision.target_group_id,
        }

    def _mark_repeated_titles(self, candidates: list[NodeCandidate]) -> None:
        counts: dict[str, int] = {}
        for candidate in candidates:
            key = self._normalized_title(candidate.title)
            if key:
                counts[key] = counts.get(key, 0) + 1
        for candidate in candidates:
            key = self._normalized_title(candidate.title)
            if key and counts.get(key, 0) > 1:
                candidate.quality_flags["possible_duplicate_title"] = True

    def _normalized_title(self, title: str) -> str:
        return " ".join(re.findall(r"[A-Za-z0-9_]+", title.lower()))

    def _starts_mid_sentence(self, text: str) -> bool:
        stripped = text.lstrip()
        return bool(stripped) and stripped[0].islower()

    def _ends_mid_thought(self, text: str) -> bool:
        stripped = text.rstrip()
        if not stripped:
            return False
        lowered = stripped.lower()
        dangling_endings = (
            " where",
            " in the",
            " is given in the",
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

    def _limit_words(self, text: str, limit: int) -> str:
        words = [word for word in text.split() if word]
        if len(words) <= limit:
            return " ".join(words)
        return " ".join(words[:limit])
