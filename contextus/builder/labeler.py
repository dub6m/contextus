from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from concurrent.futures import ThreadPoolExecutor
import json
import re
import threading
import time

from contextus.llm import LLMClient


VALID_ACTIONS = {"standalone", "attach_left", "attach_right", "duplicate_drop", "support_only"}
POLICY_VERSION = "chunk-audit-policy-v2"
LLM_PROMPT_VERSION = "chunk-audit-label-v1"
MAX_API_RETRIES = 5
BASE_RETRY_DELAY_SECONDS = 5.0
MAX_RETRY_DELAY_SECONDS = 60.0

CLOSING_PATTERNS = (
    re.compile(r"\brespectfully submitted\b", re.IGNORECASE),
    re.compile(r"\ble tout respectueusement soumis\b", re.IGNORECASE),
    re.compile(r"\bsincerely\b", re.IGNORECASE),
    re.compile(r"\bregards\b", re.IGNORECASE),
    re.compile(r"\bsubmitted\b", re.IGNORECASE),
)

INTRODUCTORY_LABEL_PATTERNS = (
    re.compile(r"^proof\b", re.IGNORECASE),
    re.compile(r"^original signed by\b", re.IGNORECASE),
    re.compile(r"^original sign.? par\b", re.IGNORECASE),
    re.compile(r"^(?:figure|table|formula)\b", re.IGNORECASE),
)


PUBLICATION_APPARATUS_PATTERN = re.compile(
    r"\b(?:edited by|correspondence|received|accepted|published|author contributions?|data availability|conflicts? of interest|funding|acknowledg(?:e)?ments?|ethics statement|creative commons|licen[cs]e|open access)\b",
    re.IGNORECASE,
)

FRONT_MATTER_LABEL_PATTERN = re.compile(
    r"^(?:abstract|keywords|contents|table of contents|preface|prologue|chapter\s+\d+|land acknowledgement|reconnaissance territoriale|original signed by|original sign.? par)$",
    re.IGNORECASE,
)

SECTION_HEADING_PATTERN = re.compile(
    r"^(?:principle\s+\d+[:.]?.*|\d+(?:\.\d+){1,4}(?:\s+.+)?|chapter\s+\d+|section\s+\d+|part\s+[ivxlcdm]+|[ivxlcdm]+\.\s+.+)$",
    re.IGNORECASE,
)


@dataclass
class ChunkLabelDecision:
    """Weak-supervision label assigned to one chunk audit row."""

    action: str
    confidence: float
    needs_review: bool
    rationale: str

    def to_dict(self) -> dict[str, object]:
        """Serialize the decision into a JSON-safe dict."""
        return {
            "action": self.action,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "rationale": self.rationale,
        }


class ChunkAuditLabeler:
    """Applies a deterministic local policy to chunk-audit rows."""

    def __init__(self) -> None:
        """Create a local policy labeler with zero network dependencies."""
        self.llm_calls = 0

    def label_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of row augmented with local-policy label metadata."""
        decision = self._policy_decision(row)
        labeled = dict(row)
        labeled["weak_action"] = decision.action
        labeled["weak_confidence"] = decision.confidence
        labeled["weak_needs_review"] = decision.needs_review
        labeled["weak_rationale"] = decision.rationale
        labeled["weak_prompt_version"] = POLICY_VERSION
        labeled["weak_label_source"] = type(self).__name__
        return labeled

    def label_rows(self, rows: list[dict[str, Any]], *, workers: int = 1) -> list[dict[str, Any]]:
        """Label a list of chunk-audit rows."""
        return [self.label_row(row) for row in rows]

    def label_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        limit: int | None = None,
        offset: int = 0,
        workers: int = 1,
    ) -> Path:
        """Label rows from one JSONL file and write an augmented JSONL file."""
        rows = self._read_jsonl(input_path)
        selected = rows[offset:] if limit is None else rows[offset:offset + limit]
        labeled_rows = self.label_rows(selected, workers=workers)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in labeled_rows)
        path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        return path

    def _policy_decision(self, row: dict[str, Any]) -> ChunkLabelDecision:
        chunk_text = str(row.get("chunk_text") or "").strip()
        left_text = str(row.get("left_chunk_text") or "").strip()
        right_text = str(row.get("right_chunk_text") or "").strip()
        token_count = self._int(row.get("token_count"))
        content_token_count = self._int(row.get("content_token_count"))
        sentence_count = self._int(row.get("sentence_count"))
        chunk_size = self._int(row.get("chunk_size"))
        contains_non_text = bool(row.get("contains_non_text"))
        duplicate_penalty = self._score(row.get("duplicate_penalty"))
        rhetorical_penalty = self._score(row.get("rhetorical_penalty"))
        heuristic_viability = self._score(row.get("heuristic_viability"))
        heading_score = self._score(row.get("heading_score"))
        proposition_score = self._score(row.get("proposition_score"))
        admin_score = self._score(row.get("admin_score"))
        toc_score = self._score(row.get("toc_score"))
        artifact_score = self._score(row.get("artifact_score"))
        list_item_score = self._score(row.get("list_item_score"))
        docling_section_header_score = self._score(row.get("docling_section_header_score"))
        docling_apparatus_score = self._score(row.get("docling_apparatus_score"))
        docling_repeated_header_score = self._score(row.get("docling_repeated_header_score"))
        docling_caption_score = self._score(row.get("docling_caption_score"))
        docling_footnote_score = self._score(row.get("docling_footnote_score"))
        previous_substantive_distance = self._optional_int(row.get("previous_substantive_distance"))
        next_substantive_distance = self._optional_int(row.get("next_substantive_distance"))
        previous_substantive_similarity = self._score(row.get("previous_substantive_similarity"))
        next_substantive_similarity = self._score(row.get("next_substantive_similarity"))
        left_similarity = self._score(row.get("left_similarity"))
        right_similarity = self._score(row.get("right_similarity"))
        left_context_similarity = self._score(row.get("left_context_similarity"))
        right_context_similarity = self._score(row.get("right_context_similarity"))
        rhetorical_markers = [str(value).strip().lower() for value in row.get("rhetorical_markers", [])]

        prefer_right = self._prefer_right(
            previous_substantive_distance=previous_substantive_distance,
            next_substantive_distance=next_substantive_distance,
            previous_substantive_similarity=previous_substantive_similarity,
            next_substantive_similarity=next_substantive_similarity,
            left_similarity=left_similarity,
            right_similarity=right_similarity,
            left_context_similarity=left_context_similarity,
            right_context_similarity=right_context_similarity,
        )
        prefer_left = self._prefer_left(
            previous_substantive_distance=previous_substantive_distance,
            next_substantive_distance=next_substantive_distance,
            previous_substantive_similarity=previous_substantive_similarity,
            next_substantive_similarity=next_substantive_similarity,
            left_similarity=left_similarity,
            right_similarity=right_similarity,
            left_context_similarity=left_context_similarity,
            right_context_similarity=right_context_similarity,
        )

        if self._is_duplicate_drop(
            duplicate_penalty=duplicate_penalty,
            heading_score=heading_score,
            toc_score=toc_score,
            artifact_score=artifact_score,
            proposition_score=proposition_score,
        ):
            return ChunkLabelDecision(
                action="duplicate_drop",
                confidence=0.97 if duplicate_penalty >= 0.92 else 0.88,
                needs_review=False,
                rationale="Chunk appears to be a weaker repeat of material already captured earlier, so it should stay as supporting evidence rather than a separate node.",
            )

        support_only = self._support_only_decision(
            chunk_text=chunk_text,
            left_text=left_text,
            right_text=right_text,
            token_count=token_count,
            content_token_count=content_token_count,
            chunk_size=chunk_size,
            heading_score=heading_score,
            proposition_score=proposition_score,
            admin_score=admin_score,
            toc_score=toc_score,
            artifact_score=artifact_score,
            docling_section_header_score=docling_section_header_score,
            docling_apparatus_score=docling_apparatus_score,
            docling_repeated_header_score=docling_repeated_header_score,
            docling_caption_score=docling_caption_score,
            docling_footnote_score=docling_footnote_score,
            rhetorical_markers=rhetorical_markers,
        )
        if support_only is not None:
            return support_only

        if self._is_attach_left_closer(chunk_text=chunk_text):
            return ChunkLabelDecision(
                action="attach_left",
                confidence=0.96,
                needs_review=False,
                rationale="Closing or sign-off language ties this chunk structurally to the previous chunk.",
            )

        if self._is_bare_rhetorical_marker(rhetorical_markers=rhetorical_markers, token_count=token_count, chunk_size=chunk_size):
            return ChunkLabelDecision(
                action="attach_right",
                confidence=0.96,
                needs_review=False,
                rationale="Bare rhetorical marker that introduces the following content rather than standing alone.",
            )

        if self._is_introductory_label(chunk_text=chunk_text, token_count=token_count, content_token_count=content_token_count, chunk_size=chunk_size):
            return ChunkLabelDecision(
                action="attach_right",
                confidence=0.93,
                needs_review=False,
                rationale="Short structural label that mainly introduces the following material.",
            )

        if toc_score >= 0.78 and proposition_score < 0.72:
            if prefer_right and right_text:
                return ChunkLabelDecision(
                    action="attach_right",
                    confidence=0.8,
                    needs_review=True,
                    rationale="Table-of-contents-like material is structural rather than conceptual, so it should attach to nearby content instead of becoming its own node.",
                )
            if prefer_left and left_text:
                return ChunkLabelDecision(
                    action="attach_left",
                    confidence=0.8,
                    needs_review=True,
                    rationale="Table-of-contents-like material is structural rather than conceptual, so it should attach to nearby content instead of becoming its own node.",
                )

        if admin_score >= 0.8 and proposition_score < 0.72:
            if prefer_left and left_text:
                return ChunkLabelDecision(
                    action="attach_left",
                    confidence=0.82,
                    needs_review=True,
                    rationale="Administrative or front-matter content is part of the document record but not a standalone concept node.",
                )
            if prefer_right and right_text:
                return ChunkLabelDecision(
                    action="attach_right",
                    confidence=0.78,
                    needs_review=True,
                    rationale="Administrative or front-matter content is part of the document record but not a standalone concept node.",
                )

        if self._is_substantive_chunk(
            proposition_score=proposition_score,
            heuristic_viability=heuristic_viability,
            admin_score=admin_score,
            toc_score=toc_score,
            list_item_score=list_item_score,
            content_token_count=content_token_count,
            token_count=token_count,
        ):
            confidence = 0.9 if proposition_score >= 0.82 or content_token_count >= 10 or token_count >= 14 else 0.78
            return ChunkLabelDecision(
                action="standalone",
                confidence=confidence,
                needs_review=False if confidence >= 0.82 else False,
                rationale="Contains enough self-contained explanatory or factual content to keep as its own node.",
            )

        if heading_score >= 0.76 and proposition_score < 0.74:
            if prefer_right and right_text:
                return ChunkLabelDecision(
                    action="attach_right",
                    confidence=0.9 if heading_score >= 0.86 else 0.8,
                    needs_review=False if heading_score >= 0.84 else True,
                    rationale="Heading-like chunk should attach to the following substantive content instead of becoming its own node.",
                )
            if artifact_score >= 0.68 and prefer_left and left_text:
                return ChunkLabelDecision(
                    action="attach_left",
                    confidence=0.78,
                    needs_review=False,
                    rationale="Weak heading or label appears to belong with the preceding substantive material rather than stand alone.",
                )

        if list_item_score >= 0.72 and proposition_score < 0.8:
            if left_text:
                return ChunkLabelDecision(
                    action="attach_left",
                    confidence=0.82,
                    needs_review=False,
                    rationale="Shallow list item is better treated as part of its parent section unless it is clearly developed into an independent concept.",
                )
            if prefer_right and right_text:
                return ChunkLabelDecision(
                    action="attach_right",
                    confidence=0.68,
                    needs_review=True,
                    rationale="List item seems to depend on following elaboration rather than standing alone.",
                )

        if artifact_score >= 0.82 and proposition_score < 0.62:
            if prefer_left and left_text:
                return ChunkLabelDecision(
                    action="attach_left",
                    confidence=0.8,
                    needs_review=False,
                    rationale="Supporting artifact or formula fragment depends more on the preceding explanation than on standing alone.",
                )
            if prefer_right and right_text:
                return ChunkLabelDecision(
                    action="attach_right",
                    confidence=0.8,
                    needs_review=False,
                    rationale="Supporting artifact or figure label mainly introduces the following explanation.",
                )

        if prefer_right and right_text and heading_score >= proposition_score - 0.05:
            return ChunkLabelDecision(
                action="attach_right",
                confidence=0.64,
                needs_review=True,
                rationale="Borderline structural chunk leans toward the following context more than toward standing alone.",
            )

        if prefer_left and left_text:
            return ChunkLabelDecision(
                action="attach_left",
                confidence=0.64,
                needs_review=True,
                rationale="Borderline chunk appears to depend more on the previous context than on standing alone.",
            )

        if rhetorical_penalty >= 0.55 and right_text:
            return ChunkLabelDecision(
                action="attach_right",
                confidence=0.62,
                needs_review=True,
                rationale="Rhetorical chunk likely belongs with neighboring explanatory content rather than standing alone.",
            )

        return ChunkLabelDecision(
            action="standalone",
            confidence=0.55,
            needs_review=True,
            rationale="Chunk remains borderline after structural and contextual checks, so it defaults conservatively to standalone pending review.",
        )

    def support_only_decision(self, row: dict[str, Any]) -> ChunkLabelDecision | None:
        """Return a support-only override when the chunk is clearly document apparatus."""
        return self._support_only_decision(
            chunk_text=str(row.get("chunk_text") or "").strip(),
            left_text=str(row.get("left_chunk_text") or "").strip(),
            right_text=str(row.get("right_chunk_text") or "").strip(),
            token_count=self._int(row.get("token_count")),
            content_token_count=self._int(row.get("content_token_count")),
            chunk_size=self._int(row.get("chunk_size")),
            heading_score=self._score(row.get("heading_score")),
            proposition_score=self._score(row.get("proposition_score")),
            admin_score=self._score(row.get("admin_score")),
            toc_score=self._score(row.get("toc_score")),
            artifact_score=self._score(row.get("artifact_score")),
            docling_section_header_score=self._score(row.get("docling_section_header_score")),
            docling_apparatus_score=self._score(row.get("docling_apparatus_score")),
            docling_repeated_header_score=self._score(row.get("docling_repeated_header_score")),
            docling_caption_score=self._score(row.get("docling_caption_score")),
            docling_footnote_score=self._score(row.get("docling_footnote_score")),
            rhetorical_markers=[str(value).strip().lower() for value in row.get("rhetorical_markers", [])],
        )

    def _is_duplicate_drop(
        self,
        *,
        duplicate_penalty: float,
        heading_score: float,
        toc_score: float,
        artifact_score: float,
        proposition_score: float,
    ) -> bool:
        if duplicate_penalty >= 0.95:
            return True
        if duplicate_penalty >= 0.8 and max(heading_score, toc_score, artifact_score) >= 0.55:
            return True
        if duplicate_penalty >= 0.75 and proposition_score < 0.6:
            return True
        return False

    def _support_only_decision(
        self,
        *,
        chunk_text: str,
        left_text: str,
        right_text: str,
        token_count: int,
        content_token_count: int,
        chunk_size: int,
        heading_score: float,
        proposition_score: float,
        admin_score: float,
        toc_score: float,
        artifact_score: float,
        docling_section_header_score: float,
        docling_apparatus_score: float,
        docling_repeated_header_score: float,
        docling_caption_score: float,
        docling_footnote_score: float,
        rhetorical_markers: list[str],
    ) -> ChunkLabelDecision | None:
        if self._is_attach_left_closer(chunk_text=chunk_text):
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.97,
                needs_review=False,
                rationale="Closing or sign-off language should remain reachable as document evidence, not as a standalone concept node.",
            )
        if self._is_bare_rhetorical_marker(rhetorical_markers=rhetorical_markers, token_count=token_count, chunk_size=chunk_size):
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.97,
                needs_review=False,
                rationale="Bare rhetorical marker should be preserved as structural evidence rather than promoted into node text.",
            )
        if self._is_introductory_label(
            chunk_text=chunk_text,
            token_count=token_count,
            content_token_count=content_token_count,
            chunk_size=chunk_size,
        ):
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.94,
                needs_review=False,
                rationale="Short structural label should remain as supporting evidence instead of becoming concept content.",
            )
        if self._is_front_matter_label(
            chunk_text=chunk_text,
            token_count=token_count,
            content_token_count=content_token_count,
            chunk_size=chunk_size,
        ) and proposition_score < 0.72:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.92,
                needs_review=False,
                rationale="Front-matter or section-label chunk should remain structural support instead of becoming concept text.",
            )
        if toc_score >= 0.78 and proposition_score < 0.72:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.9,
                needs_review=False,
                rationale="Table-of-contents-like material is document structure, so it should be retained as support rather than promoted to a node.",
            )
        if docling_apparatus_score >= 0.72 and proposition_score < 0.82:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.94 if docling_apparatus_score >= 0.84 else 0.88,
                needs_review=False if docling_apparatus_score >= 0.84 else True,
                rationale="Docling identified this chunk as publication or editorial apparatus, so it should remain support-only evidence instead of becoming a concept node.",
            )
        if self._is_publication_apparatus(chunk_text=chunk_text, token_count=token_count):
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.92,
                needs_review=False,
                rationale="Publication-record or editorial apparatus should remain as support-only evidence instead of becoming a concept node.",
            )
        if admin_score >= 0.8 and proposition_score < 0.72:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.9 if admin_score >= 0.88 else 0.84,
                needs_review=False if admin_score >= 0.88 else True,
                rationale="Administrative or publication-record material should remain as support-only evidence instead of becoming a concept node.",
            )
        if heading_score >= 0.86 and proposition_score < 0.68 and right_text:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.86,
                needs_review=False,
                rationale="Heading-like chunk mainly organizes nearby content and should stay as support rather than node text.",
            )
        if artifact_score >= 0.84 and proposition_score < 0.58 and max(token_count, content_token_count) <= 10:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.84,
                needs_review=False,
                rationale="Artifact or figure label is useful as evidence, but too structural to promote into concept text.",
            )
        if not left_text and right_text and heading_score >= 0.72 and proposition_score < 0.6:
            return ChunkLabelDecision(
                action="support_only",
                confidence=0.8,
                needs_review=True,
                rationale="Front-matter style structural chunk should remain evidence-only unless later review shows it carries standalone conceptual content.",
            )
        return None

    def _is_publication_apparatus(self, *, chunk_text: str, token_count: int) -> bool:
        normalized = " ".join(chunk_text.split())
        if PUBLICATION_APPARATUS_PATTERN.search(normalized):
            return True
        if FRONT_MATTER_LABEL_PATTERN.match(normalized):
            return True
        if "@" in normalized:
            return True
        number_refs = len(re.findall(r"\b\d{1,2}\b", normalized))
        return token_count >= 12 and normalized.count(",") >= 8 and number_refs >= 4

    def _is_front_matter_label(self, *, chunk_text: str, token_count: int, content_token_count: int, chunk_size: int) -> bool:
        normalized = " ".join(chunk_text.split())
        if FRONT_MATTER_LABEL_PATTERN.match(normalized):
            return True
        if token_count <= 8 and content_token_count <= 6 and chunk_size <= 2 and SECTION_HEADING_PATTERN.match(normalized):
            return True
        return False

    def _is_attach_left_closer(self, *, chunk_text: str) -> bool:
        normalized = " ".join(chunk_text.split())
        return any(pattern.search(normalized) for pattern in CLOSING_PATTERNS)

    def _is_bare_rhetorical_marker(self, *, rhetorical_markers: list[str], token_count: int, chunk_size: int) -> bool:
        if not rhetorical_markers:
            return False
        return token_count <= 8 and chunk_size <= 2

    def _is_introductory_label(self, *, chunk_text: str, token_count: int, content_token_count: int, chunk_size: int) -> bool:
        normalized = " ".join(chunk_text.split())
        if any(pattern.match(normalized) for pattern in INTRODUCTORY_LABEL_PATTERNS):
            return token_count <= 10 and content_token_count <= 6
        return token_count <= 4 and chunk_size <= 2 and normalized.isupper()

    def _is_substantive_chunk(
        self,
        *,
        proposition_score: float,
        heuristic_viability: float,
        admin_score: float,
        toc_score: float,
        list_item_score: float,
        content_token_count: int,
        token_count: int,
    ) -> bool:
        if admin_score >= 0.72 or toc_score >= 0.72:
            return False
        if list_item_score >= 0.72 and proposition_score < 0.82:
            return False
        if proposition_score >= 0.78:
            return True
        if proposition_score >= 0.6 and heuristic_viability >= 0.58:
            return True
        return content_token_count >= 12 and token_count >= 14 and proposition_score >= 0.45 and heuristic_viability >= 0.52

    def _prefer_right(
        self,
        *,
        previous_substantive_distance: int | None,
        next_substantive_distance: int | None,
        previous_substantive_similarity: float,
        next_substantive_similarity: float,
        left_similarity: float,
        right_similarity: float,
        left_context_similarity: float,
        right_context_similarity: float,
    ) -> bool:
        if next_substantive_distance is None:
            return False
        if previous_substantive_distance is None:
            return True
        if next_substantive_distance < previous_substantive_distance:
            return True
        if next_substantive_similarity > previous_substantive_similarity + 0.04:
            return True
        if right_similarity > left_similarity + 0.05:
            return True
        return right_context_similarity > left_context_similarity + 0.06

    def _prefer_left(
        self,
        *,
        previous_substantive_distance: int | None,
        next_substantive_distance: int | None,
        previous_substantive_similarity: float,
        next_substantive_similarity: float,
        left_similarity: float,
        right_similarity: float,
        left_context_similarity: float,
        right_context_similarity: float,
    ) -> bool:
        if previous_substantive_distance is None:
            return False
        if next_substantive_distance is None:
            return True
        if previous_substantive_distance < next_substantive_distance:
            return True
        if previous_substantive_similarity > next_substantive_similarity + 0.04:
            return True
        if left_similarity > right_similarity + 0.05:
            return True
        return left_context_similarity > right_context_similarity + 0.06

    def _score(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.0

    def _int(self, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _optional_int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    def _read_jsonl(self, path: str | Path) -> list[dict[str, Any]]:
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


class LLMChunkAuditLabeler:
    """Applies LLM weak labels to chunk-audit rows."""

    def __init__(
        self,
        llm_client: LLMClient,
        llm_client_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        """Create a labeler backed by one LLM client."""
        self.llm_client = llm_client
        self.llm_client_factory = llm_client_factory
        self.policy_labeler = ChunkAuditLabeler()
        self.llm_calls = 0
        self._llm_calls_lock = threading.Lock()

    def label_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of row augmented with weak-label metadata."""
        decision = self._request_decision(row)
        support_only = self.policy_labeler.support_only_decision(row)
        if support_only is not None and decision.action != "duplicate_drop":
            decision = support_only
        labeled = dict(row)
        labeled["weak_action"] = decision.action
        labeled["weak_confidence"] = decision.confidence
        labeled["weak_needs_review"] = decision.needs_review
        labeled["weak_rationale"] = decision.rationale
        labeled["weak_prompt_version"] = LLM_PROMPT_VERSION
        labeled["weak_label_source"] = type(self.llm_client).__name__
        return labeled

    def label_rows(self, rows: list[dict[str, Any]], *, workers: int = 1) -> list[dict[str, Any]]:
        """Label a list of chunk-audit rows."""
        if workers <= 1:
            return [self.label_row(row) for row in rows]
        if self.llm_client_factory is None:
            raise ValueError("Parallel labeling requires an llm_client_factory.")

        labeled_rows: list[dict[str, Any] | None] = [None] * len(rows)

        def run_one(index: int, row: dict[str, Any]) -> tuple[int, dict[str, Any], int]:
            worker_labeler = LLMChunkAuditLabeler(llm_client=self.llm_client_factory())
            labeled = worker_labeler.label_row(row)
            return index, labeled, worker_labeler.llm_calls

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_one, index, row) for index, row in enumerate(rows)]
            for future in futures:
                index, labeled, llm_calls = future.result()
                labeled_rows[index] = labeled
                self._add_llm_calls(llm_calls)
        return [row for row in labeled_rows if row is not None]

    def label_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        limit: int | None = None,
        offset: int = 0,
        workers: int = 1,
    ) -> Path:
        """Label rows from one JSONL file and write an augmented JSONL file."""
        rows = self._read_jsonl(input_path)
        selected = rows[offset:] if limit is None else rows[offset:offset + limit]
        labeled_rows = self.label_rows(selected, workers=workers)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in labeled_rows)
        path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        return path

    def _request_decision(self, row: dict[str, Any]) -> ChunkLabelDecision:
        system = "You are a precise training-data labeler for knowledge-graph chunk viability."
        user = self._prompt(row)
        parse_failures = 0
        last_error = ""
        for attempt in range(MAX_API_RETRIES):
            try:
                self._add_llm_calls(1)
                response = self.llm_client.complete(system=system, user=user, temperature=0.0).content
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if self._is_retryable(exc) and attempt + 1 < MAX_API_RETRIES:
                    delay = min(BASE_RETRY_DELAY_SECONDS * (2 ** attempt), MAX_RETRY_DELAY_SECONDS)
                    time.sleep(delay)
                    continue
                return self._fallback_decision(row, f"LLM request failed: {last_error}")

            parsed = self._parse_response(response)
            if parsed is not None:
                return parsed
            parse_failures += 1
            if parse_failures >= 2:
                break
        reason = "LLM response could not be parsed as a valid label."
        if last_error:
            reason = f"{reason} Last error: {last_error}"
        return self._fallback_decision(row, reason)

    def _prompt(self, row: dict[str, Any]) -> str:
        return (
            "Label this chunk for graph-node viability.\n\n"
            "Choose exactly one action:\n"
            "- standalone\n"
            "- attach_left\n"
            "- attach_right\n"
            "- duplicate_drop\n"
            "- support_only\n\n"
            "Guidance:\n"
            "- Prefer standalone when the chunk contains self-contained explanation, definition, procedure, argument, or data that would still be worth keeping as a node by itself.\n"
            "- Do not choose attach_right merely because the chunk starts with a title. Title plus substantive explanatory content can still be standalone.\n"
            "- Prefer non-standalone when the chunk is rhetorical, duplicated, or only meaningful with neighbor context.\n"
            "- Prefer duplicate_drop for repeated weaker restatements of an earlier concept.\n"
            "- Prefer attach_right only for bare headings, proof markers, labels, setup fragments, or heading-plus-too-little-content chunks that mainly introduce the following content.\n"
            "- Prefer attach_left when the chunk clearly closes, signs off, or belongs structurally to the previous chunk.\n"
            "- Prefer support_only for document apparatus such as headings, front matter, affiliations, disclosures, acknowledgments, references, figure labels, or proof markers that should remain reachable as evidence but not become node text.\n"
            "- Mark needs_review=true when the decision is uncertain.\n\n"
            f"Chunk text:\n{row.get('chunk_text', '')}\n\n"
            f"Left neighbor:\n{row.get('left_chunk_text', '')}\n\n"
            f"Right neighbor:\n{row.get('right_chunk_text', '')}\n\n"
            "Heuristic signals:\n"
            f"- chunk_size: {row.get('chunk_size')}\n"
            f"- token_count: {row.get('token_count')}\n"
            f"- element_types: {row.get('element_types')}\n"
            f"- rhetorical_markers: {row.get('rhetorical_markers')}\n"
            f"- heuristic_viability: {row.get('heuristic_viability')}\n"
            f"- suggested_action: {row.get('suggested_action')}\n"
            f"- left_similarity: {row.get('left_similarity')}\n"
            f"- right_similarity: {row.get('right_similarity')}\n"
            f"- duplicate_penalty: {row.get('duplicate_penalty')}\n"
            f"- rhetorical_penalty: {row.get('rhetorical_penalty')}\n\n"
            "Return only valid JSON with exactly these fields:\n"
            '{"action":"...","confidence":0.0,"needs_review":false,"rationale":"..."}'
        )

    def _is_retryable(self, exc: Exception) -> bool:
        message = f"{type(exc).__name__}: {exc}".lower()
        return any(token in message for token in ("429", "rate", "queue", "connection", "timeout"))

    def _parse_response(self, text: str) -> ChunkLabelDecision | None:
        payload = self._extract_json(text)
        if payload is None:
            return None
        action = str(payload.get("action") or "").strip().lower()
        if action not in VALID_ACTIONS:
            return None
        try:
            confidence = float(payload.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        needs_review = bool(payload.get("needs_review", False))
        rationale = str(payload.get("rationale") or "").strip() or "No rationale provided."
        return ChunkLabelDecision(
            action=action,
            confidence=confidence,
            needs_review=needs_review,
            rationale=rationale,
        )

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except Exception:
            pass
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _fallback_decision(self, row: dict[str, Any], reason: str) -> ChunkLabelDecision:
        suggested = str(row.get("suggested_action") or "standalone").strip().lower()
        action = suggested if suggested in VALID_ACTIONS else "standalone"
        return ChunkLabelDecision(
            action=action,
            confidence=0.25,
            needs_review=True,
            rationale=reason,
        )

    def _read_jsonl(self, path: str | Path) -> list[dict[str, Any]]:
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _add_llm_calls(self, count: int) -> None:
        with self._llm_calls_lock:
            self.llm_calls += count




