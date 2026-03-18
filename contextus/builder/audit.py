from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re

from contextus.ingestion.models import ExtractedDocument, ExtractedElement

from .chunker import DocumentChunker
from .config import BuilderConfig
from .preprocessor import ElementPreprocessor
from .structural import DoclingStructuralEnricher, StructuralEnrichmentResult


STOPWORDS = {
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
    "if",
    "in",
    "into",
    "is",
    "it",
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
    "with",
}

RHETORICAL_PATTERNS = (
    ("proof", re.compile(r"^proof\b", re.IGNORECASE)),
    ("claim", re.compile(r"^claim\s+\d+([.:]\d+)?\b", re.IGNORECASE)),
    ("example", re.compile(r"^example\b", re.IGNORECASE)),
    ("observation", re.compile(r"^observation\b", re.IGNORECASE)),
    ("remark", re.compile(r"^remark\b", re.IGNORECASE)),
    ("lemma", re.compile(r"^lemma\b", re.IGNORECASE)),
    ("theorem", re.compile(r"^theorem\b", re.IGNORECASE)),
    ("corollary", re.compile(r"^corollary\b", re.IGNORECASE)),
)

NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?:chapter\s+\d+|section\s+\d+|appendix\s+[a-z]|principle\s+\d+[:.]?.*|\d+(?:\.\d+){1,4}(?:\s+.+)?|\d+\s*\([a-z]\)\s+.+|[ivxlcdm]+\.\s+.+)$",
    re.IGNORECASE,
)
LIST_ITEM_PATTERN = re.compile(r"^(?:[-*\u2022]\s+|\d+\.\s+|[a-z]\)\s+|[ivxlcdm]+\)\s+)", re.IGNORECASE)
FIGURE_TABLE_LABEL_PATTERN = re.compile(r"^(?:figure|table|formula)\b", re.IGNORECASE)
TOC_PATTERN = re.compile(r"\b(?:table of contents|contents)\b", re.IGNORECASE)
ADMIN_PATTERN = re.compile(
    r"\b(?:copyright|all rights reserved|annual report|for the year ended|honou?rable|minister|deputy minister|legislative building|room\s+\d+|winnipeg|manitoba|rapport annuel|submitted|madam:|sir:|abstract authors?|edited by|correspondence|received|accepted|published|author contributions?|data availability|conflicts? of interest|funding|acknowledg(?:e)?ments?|ethics statement|open access|creative commons|licen[cs]e)\b",
    re.IGNORECASE,
)
VERB_PATTERN = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|do|does|did|can|could|should|would|will|may|might|must|means?|refers?|provides?|contains?|captures?|changes?|increase(?:s|d)?|decrease(?:s|d)?|improve(?:s|d)?|connect(?:s|ed)?|protect(?:s|ed)?|deliver(?:s|ed)?|make(?:s|made)?|asks?|explains?|shows?|demonstrates?|enables?|includes?|requires?|treats?|est|sont|doit|peut|améliorer|relier|protéger)\b",
    re.IGNORECASE,
)


@dataclass
class ChunkAuditRow:
    """One labeled-training candidate row derived from a chunk."""

    document_id: str
    source_name: str
    source_path: str
    chunk_index: int
    chunk_text: str
    left_chunk_text: str
    right_chunk_text: str
    left_context_text: str
    right_context_text: str
    previous_substantive_text: str
    next_substantive_text: str
    previous_substantive_distance: int | None
    next_substantive_distance: int | None
    chunk_size: int
    token_count: int
    content_token_count: int
    sentence_count: int
    element_ids: list[str]
    element_types: list[str]
    page_numbers: list[int]
    type_histogram: dict[str, int]
    contains_title: bool
    contains_non_text: bool
    singleton_chunk: bool
    left_similarity: float
    right_similarity: float
    left_context_similarity: float
    right_context_similarity: float
    previous_substantive_similarity: float
    next_substantive_similarity: float
    max_previous_similarity: float
    token_substance: float
    lexical_density: float
    type_richness: float
    left_independence: float
    right_independence: float
    novelty: float
    rhetorical_penalty: float
    duplicate_penalty: float
    heading_score: float
    proposition_score: float
    admin_score: float
    toc_score: float
    artifact_score: float
    list_item_score: float
    docling_enabled: bool
    docling_failed: bool
    docling_section_header_score: float
    docling_apparatus_score: float
    docling_repeated_header_score: float
    docling_caption_score: float
    docling_footnote_score: float
    docling_table_score: float
    docling_picture_score: float
    docling_labels: list[str]
    docling_matched_texts: list[str]
    heuristic_viability: float
    rhetorical_markers: list[str] = field(default_factory=list)
    suggested_action: str = "standalone"
    gold_action: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize the audit row into a JSONL-safe dict."""
        return asdict(self)


class ChunkAuditExporter:
    """Exports chunk-level audit rows for viability scoring and labeling."""

    CONTEXT_DEPTH = 3
    SUBSTANTIVE_SCAN_DEPTH = 4

    def __init__(
        self,
        chunker: DocumentChunker | None = None,
        preprocessor: ElementPreprocessor | None = None,
        config: BuilderConfig | None = None,
        structural_enricher: DoclingStructuralEnricher | None = None,
    ) -> None:
        """Create an exporter backed by the current chunker and preprocessor."""
        self.config = config or BuilderConfig()
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.chunker = chunker or DocumentChunker(
            llm_client=None,
            config=self.config,
            preprocessor=self.preprocessor,
        )
        self.structural_enricher = structural_enricher or DoclingStructuralEnricher(
            preprocessor=self.preprocessor,
            artifacts_path=self.config.DOCLING_ARTIFACTS_PATH,
            enabled=self.config.DOCLING_ENABLE_STRUCTURAL_ENRICHMENT,
        )

    def rows_from_document(self, document: ExtractedDocument) -> list[ChunkAuditRow]:
        """Return one audit row per chunk in document reading order."""
        chunks = self.chunker.chunk(document)
        return self.rows_from_chunks(document, chunks)

    def rows_from_chunks(
        self,
        document: ExtractedDocument,
        chunks: list[list[ExtractedElement]],
    ) -> list[ChunkAuditRow]:
        """Return audit rows for a precomputed chunk sequence."""
        chunk_texts = [self._chunk_text(chunk) for chunk in chunks]
        summaries = [self._summarize_chunk(chunk, chunk_texts[index]) for index, chunk in enumerate(chunks)]
        structural_result = self.structural_enricher.enrich(document) if self.structural_enricher is not None else StructuralEnrichmentResult(source_path=None, enabled=False, notes="unconfigured")
        prior_texts: list[str] = []
        rows: list[ChunkAuditRow] = []

        for index, chunk in enumerate(chunks):
            summary = summaries[index]
            chunk_text = summary["chunk_text"]
            structural_features = structural_result.chunk_features(chunk)
            left_text = chunk_texts[index - 1] if index > 0 else ""
            right_text = chunk_texts[index + 1] if index + 1 < len(chunk_texts) else ""
            left_context_text = self._context_text(chunk_texts, index=index, direction=-1)
            right_context_text = self._context_text(chunk_texts, index=index, direction=1)
            left_similarity = self._lexical_similarity(chunk_text, left_text)
            right_similarity = self._lexical_similarity(chunk_text, right_text)
            left_context_similarity = self._lexical_similarity(chunk_text, left_context_text)
            right_context_similarity = self._lexical_similarity(chunk_text, right_context_text)
            max_previous_similarity = max(
                (self._lexical_similarity(chunk_text, prior_text) for prior_text in prior_texts),
                default=0.0,
            )
            prior_texts.append(chunk_text)

            previous_substantive_index = self._nearest_substantive_index(summaries, index=index, direction=-1)
            next_substantive_index = self._nearest_substantive_index(summaries, index=index, direction=1)
            previous_substantive_text = chunk_texts[previous_substantive_index] if previous_substantive_index is not None else ""
            next_substantive_text = chunk_texts[next_substantive_index] if next_substantive_index is not None else ""
            previous_substantive_distance = (index - previous_substantive_index) if previous_substantive_index is not None else None
            next_substantive_distance = (next_substantive_index - index) if next_substantive_index is not None else None
            previous_substantive_similarity = self._lexical_similarity(chunk_text, previous_substantive_text)
            next_substantive_similarity = self._lexical_similarity(chunk_text, next_substantive_text)

            duplicate_penalty = self._duplicate_penalty(chunk, max_previous_similarity)
            heading_score = self._refined_heading_score(
                summary=summary,
                next_summary=summaries[next_substantive_index] if next_substantive_index is not None else None,
                left_context_similarity=left_context_similarity,
                right_context_similarity=right_context_similarity,
                next_substantive_distance=next_substantive_distance,
            )
            proposition_score = self._refined_proposition_score(
                summary=summary,
                heading_score=heading_score,
                left_context_similarity=left_context_similarity,
                right_context_similarity=right_context_similarity,
                next_substantive_distance=next_substantive_distance,
            )
            heuristic_viability = self._heuristic_viability(
                token_substance=summary["token_substance"],
                lexical_density=summary["lexical_density"],
                type_richness=summary["type_richness"],
                right_independence=summary["right_independence"],
                left_independence=summary["left_independence"],
                novelty=1.0 - max_previous_similarity,
                rhetorical_penalty=summary["rhetorical_penalty"],
                duplicate_penalty=duplicate_penalty,
                proposition_score=proposition_score,
                heading_score=heading_score,
                admin_score=summary["admin_score"],
                toc_score=summary["toc_score"],
                list_item_score=summary["list_item_score"],
            )
            suggested_action = self._suggested_action(
                heading_score=heading_score,
                proposition_score=proposition_score,
                admin_score=summary["admin_score"],
                toc_score=summary["toc_score"],
                artifact_score=summary["artifact_score"],
                list_item_score=summary["list_item_score"],
                docling_apparatus_score=float(structural_features["docling_apparatus_score"]),
                docling_repeated_header_score=float(structural_features["docling_repeated_header_score"]),
                docling_caption_score=float(structural_features["docling_caption_score"]),
                docling_footnote_score=float(structural_features["docling_footnote_score"]),
                rhetorical_penalty=summary["rhetorical_penalty"],
                duplicate_penalty=duplicate_penalty,
                previous_substantive_distance=previous_substantive_distance,
                next_substantive_distance=next_substantive_distance,
                previous_substantive_similarity=previous_substantive_similarity,
                next_substantive_similarity=next_substantive_similarity,
                has_left=bool(left_text),
                has_right=bool(right_text),
            )

            rows.append(
                ChunkAuditRow(
                    document_id=document.id,
                    source_name=document.source_name,
                    source_path=document.source_path,
                    chunk_index=index,
                    chunk_text=chunk_text,
                    left_chunk_text=left_text,
                    right_chunk_text=right_text,
                    left_context_text=left_context_text,
                    right_context_text=right_context_text,
                    previous_substantive_text=previous_substantive_text,
                    next_substantive_text=next_substantive_text,
                    previous_substantive_distance=previous_substantive_distance,
                    next_substantive_distance=next_substantive_distance,
                    chunk_size=len(chunk),
                    token_count=summary["token_count"],
                    content_token_count=summary["content_token_count"],
                    sentence_count=summary["sentence_count"],
                    element_ids=[element.id for element in chunk],
                    element_types=[element.type for element in chunk],
                    page_numbers=summary["page_numbers"],
                    type_histogram=summary["type_histogram"],
                    contains_title=summary["contains_title"],
                    contains_non_text=summary["contains_non_text"],
                    singleton_chunk=summary["singleton_chunk"],
                    left_similarity=left_similarity,
                    right_similarity=right_similarity,
                    left_context_similarity=left_context_similarity,
                    right_context_similarity=right_context_similarity,
                    previous_substantive_similarity=previous_substantive_similarity,
                    next_substantive_similarity=next_substantive_similarity,
                    max_previous_similarity=max_previous_similarity,
                    token_substance=summary["token_substance"],
                    lexical_density=summary["lexical_density"],
                    type_richness=summary["type_richness"],
                    left_independence=summary["left_independence"],
                    right_independence=summary["right_independence"],
                    novelty=1.0 - max_previous_similarity,
                    rhetorical_penalty=summary["rhetorical_penalty"],
                    duplicate_penalty=duplicate_penalty,
                    heading_score=heading_score,
                    proposition_score=proposition_score,
                    admin_score=summary["admin_score"],
                    toc_score=summary["toc_score"],
                    artifact_score=summary["artifact_score"],
                    list_item_score=summary["list_item_score"],
                    docling_enabled=bool(structural_features["docling_enabled"]),
                    docling_failed=bool(structural_features["docling_failed"]),
                    docling_section_header_score=float(structural_features["docling_section_header_score"]),
                    docling_apparatus_score=float(structural_features["docling_apparatus_score"]),
                    docling_repeated_header_score=float(structural_features["docling_repeated_header_score"]),
                    docling_caption_score=float(structural_features["docling_caption_score"]),
                    docling_footnote_score=float(structural_features["docling_footnote_score"]),
                    docling_table_score=float(structural_features["docling_table_score"]),
                    docling_picture_score=float(structural_features["docling_picture_score"]),
                    docling_labels=list(structural_features["docling_labels"]),
                    docling_matched_texts=list(structural_features["docling_matched_texts"]),
                    heuristic_viability=heuristic_viability,
                    rhetorical_markers=summary["rhetorical_markers"],
                    suggested_action=suggested_action,
                )
            )
        return rows

    def export_jsonl(self, document: ExtractedDocument, output_path: str | Path) -> Path:
        """Write document audit rows to a JSONL file and return the path."""
        rows = self.rows_from_document(document)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(json.dumps(row.to_dict(), ensure_ascii=False) for row in rows)
        path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        return path

    def _chunk_text(self, chunk: list[ExtractedElement]) -> str:
        return "\n".join(self.preprocessor.to_text(element) for element in chunk)

    def _summarize_chunk(self, chunk: list[ExtractedElement], chunk_text: str) -> dict[str, object]:
        tokens = self._tokens(chunk_text)
        content_tokens = [token for token in tokens if self._is_content_token(token)]
        type_histogram = self._type_histogram(chunk)
        rhetorical_markers = self._rhetorical_markers(chunk_text)
        sentence_count = self._sentence_count(chunk_text)
        contains_title = "title" in type_histogram
        contains_non_text = any(element.type not in {"text", "title"} for element in chunk)
        singleton_chunk = len(chunk) == 1
        token_substance = min(1.0, len(content_tokens) / 24.0)
        lexical_density = (len(content_tokens) / len(tokens)) if tokens else 0.0
        type_richness = min(1.0, len(type_histogram) / 3.0)
        rhetorical_penalty = self._rhetorical_penalty(chunk, rhetorical_markers, chunk_text)
        admin_score = self._admin_score(chunk_text=chunk_text, page_numbers=sorted({element.page_number for element in chunk}))
        toc_score = self._toc_score(chunk_text=chunk_text)
        artifact_score = self._artifact_score(
            chunk=chunk,
            chunk_text=chunk_text,
            contains_non_text=contains_non_text,
            content_token_count=len(content_tokens),
        )
        list_item_score = self._list_item_score(chunk_text=chunk_text, sentence_count=sentence_count, token_count=len(tokens))
        heading_score = self._base_heading_score(
            chunk_text=chunk_text,
            contains_title=contains_title,
            sentence_count=sentence_count,
            token_count=len(tokens),
            content_token_count=len(content_tokens),
            contains_non_text=contains_non_text,
            list_item_score=list_item_score,
        )
        proposition_score = self._base_proposition_score(
            chunk_text=chunk_text,
            token_count=len(tokens),
            content_token_count=len(content_tokens),
            sentence_count=sentence_count,
            contains_non_text=contains_non_text,
            heading_score=heading_score,
            admin_score=admin_score,
            toc_score=toc_score,
            list_item_score=list_item_score,
        )
        return {
            "chunk_text": chunk_text,
            "token_count": len(tokens),
            "content_token_count": len(content_tokens),
            "sentence_count": sentence_count,
            "type_histogram": type_histogram,
            "page_numbers": sorted({element.page_number for element in chunk}),
            "contains_title": contains_title,
            "contains_non_text": contains_non_text,
            "singleton_chunk": singleton_chunk,
            "token_substance": token_substance,
            "lexical_density": lexical_density,
            "type_richness": type_richness,
            "left_independence": 1.0,
            "right_independence": 1.0,
            "rhetorical_markers": rhetorical_markers,
            "rhetorical_penalty": rhetorical_penalty,
            "admin_score": admin_score,
            "toc_score": toc_score,
            "artifact_score": artifact_score,
            "list_item_score": list_item_score,
            "base_heading_score": heading_score,
            "base_proposition_score": proposition_score,
        }

    def _context_text(self, chunk_texts: list[str], *, index: int, direction: int) -> str:
        pieces: list[str] = []
        current = index + direction
        steps = 0
        while 0 <= current < len(chunk_texts) and steps < self.CONTEXT_DEPTH:
            pieces.append(chunk_texts[current])
            current += direction
            steps += 1
        if direction < 0:
            pieces.reverse()
        return "\n\n".join(piece for piece in pieces if piece)

    def _nearest_substantive_index(self, summaries: list[dict[str, object]], *, index: int, direction: int) -> int | None:
        current = index + direction
        steps = 0
        while 0 <= current < len(summaries) and steps < self.SUBSTANTIVE_SCAN_DEPTH:
            if self._is_substantive_anchor(summaries[current]):
                return current
            current += direction
            steps += 1
        return None

    def _is_substantive_anchor(self, summary: dict[str, object]) -> bool:
        proposition_score = float(summary["base_proposition_score"])
        heading_score = float(summary["base_heading_score"])
        admin_score = float(summary["admin_score"])
        toc_score = float(summary["toc_score"])
        artifact_score = float(summary["artifact_score"])
        return (
            proposition_score >= 0.45
            and admin_score < 0.7
            and toc_score < 0.7
            and artifact_score < 0.85
            and proposition_score >= heading_score - 0.1
        )

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-zÀ-ÿ0-9_]+", (text or "").lower())

    def _sentence_count(self, text: str) -> int:
        stripped = (text or "").strip()
        if not stripped:
            return 0
        pieces = [piece for piece in re.split(r"[.!?]+", stripped) if piece.strip()]
        return max(1, len(pieces))

    def _type_histogram(self, chunk: list[ExtractedElement]) -> dict[str, int]:
        histogram: dict[str, int] = {}
        for element in chunk:
            histogram[element.type] = histogram.get(element.type, 0) + 1
        return histogram

    def _is_content_token(self, token: str) -> bool:
        return len(token) > 2 and token not in STOPWORDS and not token.isdigit()

    def _lexical_similarity(self, left_text: str, right_text: str) -> float:
        left_tokens = {token for token in self._tokens(left_text) if self._is_content_token(token)}
        right_tokens = {token for token in self._tokens(right_text) if self._is_content_token(token)}
        if not left_tokens or not right_tokens:
            return 0.0
        union = left_tokens | right_tokens
        return len(left_tokens & right_tokens) / len(union)

    def _rhetorical_markers(self, text: str) -> list[str]:
        markers = []
        normalized = " ".join((text or "").split())
        for name, pattern in RHETORICAL_PATTERNS:
            if pattern.match(normalized):
                markers.append(name)
        return markers

    def _rhetorical_penalty(
        self,
        chunk: list[ExtractedElement],
        rhetorical_markers: list[str],
        chunk_text: str,
    ) -> float:
        penalty = 0.0
        if rhetorical_markers:
            penalty += 0.55
        if len(chunk) == 1 and rhetorical_markers:
            penalty += 0.25
        if len(self._tokens(chunk_text)) <= 4 and rhetorical_markers:
            penalty += 0.1
        return min(1.0, penalty)

    def _duplicate_penalty(self, chunk: list[ExtractedElement], max_previous_similarity: float) -> float:
        penalty = 0.0
        if max_previous_similarity >= 0.9:
            penalty = 0.9
        elif max_previous_similarity >= 0.75:
            penalty = 0.6
        elif max_previous_similarity >= 0.6:
            penalty = 0.3
        if len(chunk) == 1 and max_previous_similarity >= 0.75:
            penalty = min(1.0, penalty + 0.15)
        return penalty

    def _heuristic_viability(
        self,
        *,
        token_substance: float,
        lexical_density: float,
        type_richness: float,
        right_independence: float,
        left_independence: float,
        novelty: float,
        rhetorical_penalty: float,
        duplicate_penalty: float,
        proposition_score: float,
        heading_score: float,
        admin_score: float,
        toc_score: float,
        list_item_score: float,
    ) -> float:
        score = (
            (0.16 * token_substance)
            + (0.13 * lexical_density)
            + (0.10 * type_richness)
            + (0.10 * right_independence)
            + (0.08 * left_independence)
            + (0.08 * novelty)
            + (0.18 * proposition_score)
            - (0.14 * heading_score)
            - (0.12 * admin_score)
            - (0.10 * toc_score)
            - (0.10 * list_item_score)
            - (0.18 * rhetorical_penalty)
            - (0.16 * duplicate_penalty)
        )
        return max(0.0, min(1.0, score))

    def _suggested_action(
        self,
        *,
        heading_score: float,
        proposition_score: float,
        admin_score: float,
        toc_score: float,
        artifact_score: float,
        list_item_score: float,
        docling_apparatus_score: float,
        docling_repeated_header_score: float,
        docling_caption_score: float,
        docling_footnote_score: float,
        rhetorical_penalty: float,
        duplicate_penalty: float,
        previous_substantive_distance: int | None,
        next_substantive_distance: int | None,
        previous_substantive_similarity: float,
        next_substantive_similarity: float,
        has_left: bool,
        has_right: bool,
    ) -> str:
        if duplicate_penalty >= 0.75:
            return "duplicate_drop"
        if docling_apparatus_score >= 0.72 and proposition_score < 0.82:
            return "support_only"
        if rhetorical_penalty >= 0.7 and has_right:
            return "attach_right"
        if heading_score >= 0.72 and proposition_score < 0.72:
            if next_substantive_distance is not None and (previous_substantive_distance is None or next_substantive_distance <= previous_substantive_distance):
                return "attach_right"
            if has_left:
                return "attach_left"
        if list_item_score >= 0.7 and proposition_score < 0.75 and has_left:
            return "attach_left"
        if artifact_score >= 0.72 and proposition_score < 0.7:
            if previous_substantive_similarity >= next_substantive_similarity and has_left:
                return "attach_left"
            if has_right:
                return "attach_right"
        if (admin_score >= 0.72 or toc_score >= 0.72) and proposition_score < 0.7:
            if has_right and (next_substantive_distance is None or next_substantive_distance <= 2):
                return "attach_right"
            if has_left:
                return "attach_left"
        if proposition_score >= 0.72:
            return "standalone"
        if next_substantive_similarity > previous_substantive_similarity and has_right:
            return "attach_right"
        if has_left:
            return "attach_left"
        return "standalone"

    def _base_heading_score(
        self,
        *,
        chunk_text: str,
        contains_title: bool,
        sentence_count: int,
        token_count: int,
        content_token_count: int,
        contains_non_text: bool,
        list_item_score: float,
    ) -> float:
        normalized = " ".join(chunk_text.split())
        score = 0.0
        if contains_title:
            score += 0.25
        if NUMBERED_HEADING_PATTERN.match(normalized):
            score += 0.35
        if FIGURE_TABLE_LABEL_PATTERN.match(normalized):
            score += 0.2
        if token_count <= 10 and sentence_count <= 1 and self._looks_like_phrase(normalized):
            score += 0.18
        if token_count <= 6 and contains_non_text:
            score += 0.08
        if list_item_score >= 0.5:
            score -= 0.08
        if content_token_count >= 10 and sentence_count >= 1:
            score -= 0.08
        return max(0.0, min(1.0, score))

    def _refined_heading_score(
        self,
        *,
        summary: dict[str, object],
        next_summary: dict[str, object] | None,
        left_context_similarity: float,
        right_context_similarity: float,
        next_substantive_distance: int | None,
    ) -> float:
        score = float(summary["base_heading_score"])
        if next_substantive_distance == 1:
            score += 0.15
        elif next_substantive_distance is not None and next_substantive_distance <= 2:
            score += 0.08
        if next_summary is not None and int(next_summary["content_token_count"]) >= int(summary["content_token_count"]) + 6:
            score += 0.12
        if right_context_similarity > left_context_similarity + 0.08 and int(summary["token_count"]) <= 14:
            score += 0.05
        if float(summary["base_proposition_score"]) >= 0.7:
            score -= 0.12
        return max(0.0, min(1.0, score))

    def _base_proposition_score(
        self,
        *,
        chunk_text: str,
        token_count: int,
        content_token_count: int,
        sentence_count: int,
        contains_non_text: bool,
        heading_score: float,
        admin_score: float,
        toc_score: float,
        list_item_score: float,
    ) -> float:
        score = 0.0
        verb_count = len(VERB_PATTERN.findall(chunk_text))
        if content_token_count >= 6:
            score += 0.2
        if content_token_count >= 8:
            score += 0.1
        if content_token_count >= 10:
            score += 0.15
        if token_count >= 12:
            score += 0.15
        if sentence_count >= 2:
            score += 0.15
        if verb_count >= 1:
            score += 0.15
        if contains_non_text and content_token_count >= 6:
            score += 0.08
        if heading_score >= 0.5 and sentence_count <= 1:
            score -= 0.1
        if admin_score >= 0.55:
            score -= 0.18
        if toc_score >= 0.55:
            score -= 0.2
        if list_item_score >= 0.55 and token_count <= 12:
            score -= 0.1
        return max(0.0, min(1.0, score))

    def _refined_proposition_score(
        self,
        *,
        summary: dict[str, object],
        heading_score: float,
        left_context_similarity: float,
        right_context_similarity: float,
        next_substantive_distance: int | None,
    ) -> float:
        score = float(summary["base_proposition_score"])
        if heading_score >= 0.72 and next_substantive_distance == 1 and int(summary["token_count"]) <= 14:
            score -= 0.12
        if right_context_similarity > left_context_similarity + 0.12 and int(summary["token_count"]) <= 10 and int(summary["sentence_count"]) <= 1:
            score -= 0.08
        if float(summary["list_item_score"]) >= 0.7 and int(summary["content_token_count"]) <= 8:
            score -= 0.06
        return max(0.0, min(1.0, score))

    def _admin_score(self, *, chunk_text: str, page_numbers: list[int]) -> float:
        normalized = " ".join(chunk_text.split())
        score = 0.0
        if ADMIN_PATTERN.search(normalized):
            score += 0.5
        if page_numbers and min(page_numbers) <= 3 and len(self._tokens(normalized)) <= 24:
            score += 0.1
        if re.search(r"\b(?:room\s+\d+|winnipeg|manitoba)\b", normalized, flags=re.IGNORECASE):
            score += 0.15
        if re.search(r"\b(?:copyright|all rights reserved|creative commons|licen[cs]e)\b", normalized, flags=re.IGNORECASE):
            score += 0.22
        if re.search(r"\b(?:edited by|correspondence|author contributions?|data availability|conflicts? of interest|funding|acknowledg(?:e)?ments?|ethics statement)\b", normalized, flags=re.IGNORECASE):
            score += 0.24
        if re.search(r"\b(?:received|accepted|published)\b", normalized, flags=re.IGNORECASE) and re.search(r"\b\d{4}\b", normalized):
            score += 0.28
        if "@" in normalized:
            score += 0.24
        number_refs = len(re.findall(r"\b\d{1,2}\b", normalized))
        if page_numbers and min(page_numbers) <= 2 and normalized.count(",") >= 8 and number_refs >= 4:
            score += 0.35
        return max(0.0, min(1.0, score))

    def _toc_score(self, *, chunk_text: str) -> float:
        normalized = " ".join(chunk_text.split())
        score = 0.0
        if TOC_PATTERN.search(normalized):
            score += 0.65
        number_count = len(re.findall(r"\b\d{1,3}\b", normalized))
        if number_count >= 3 and len(self._tokens(normalized)) >= 12:
            score += 0.18
        if ". . ." in normalized or "..." in normalized:
            score += 0.18
        if number_count >= 6:
            score += 0.12
        return max(0.0, min(1.0, score))

    def _artifact_score(
        self,
        *,
        chunk: list[ExtractedElement],
        chunk_text: str,
        contains_non_text: bool,
        content_token_count: int,
    ) -> float:
        normalized = " ".join(chunk_text.split())
        element_types = {element.type for element in chunk}
        score = 0.0
        if contains_non_text:
            score += 0.35
        if element_types & {"table", "figure", "image", "chart", "diagram", "flowchart", "formula"}:
            score += 0.2
        if FIGURE_TABLE_LABEL_PATTERN.match(normalized):
            score += 0.18
        if "unknown columns" in normalized.lower() or "no text content" in normalized.lower():
            score += 0.22
        if "formula:" in normalized.lower() and content_token_count <= 3:
            score += 0.15
        return max(0.0, min(1.0, score))

    def _list_item_score(self, *, chunk_text: str, sentence_count: int, token_count: int) -> float:
        normalized = " ".join(chunk_text.split())
        score = 0.0
        if LIST_ITEM_PATTERN.match(normalized):
            score += 0.55
        if re.match(r"^\d+\.\s+[A-ZÀ-ÿ]", normalized):
            score += 0.18
        if token_count <= 16 and sentence_count <= 1:
            score += 0.08
        return max(0.0, min(1.0, score))

    def _looks_like_phrase(self, text: str) -> bool:
        if not text:
            return False
        if any(punctuation in text for punctuation in ":;!?"):
            return False
        return text == text.title() or text.isupper() or NUMBERED_HEADING_PATTERN.match(text) is not None






