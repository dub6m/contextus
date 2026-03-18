from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from contextus.ingestion.models import ExtractedDocument, ExtractedElement

from .preprocessor import ElementPreprocessor


TOKEN_PATTERN = re.compile(r"[A-Za-zÀ-ÿ0-9_]+")
APPARATUS_HEADING_PATTERN = re.compile(
    r"\b(?:open access|reviewed by|correspondence|citation|copyright|author contributions?|data availability|informed consent|ethics statement|conflicts? of interest|funding|acknowledg(?:e)?ments?|disclaimer|references?)\b",
    re.IGNORECASE,
)
APPARATUS_TEXT_PATTERN = re.compile(
    r"\b(?:received|accepted|published|creative commons|licen[cs]e|correspondence|author contributions?|data availability|informed consent|ethics statement|conflicts? of interest|funding|acknowledg(?:e)?ments?|disclaimer)\b",
    re.IGNORECASE,
)
NON_TEXT_TYPES = {"table", "figure", "image", "chart", "diagram", "flowchart"}


@dataclass
class ElementStructuralAnnotation:
    """Docling-derived structural hints attached to one extracted element."""

    element_id: str
    page_number: int
    section_header_score: float = 0.0
    apparatus_score: float = 0.0
    repeated_header_score: float = 0.0
    caption_score: float = 0.0
    footnote_score: float = 0.0
    table_score: float = 0.0
    picture_score: float = 0.0
    matched_labels: list[str] = field(default_factory=list)
    matched_texts: list[str] = field(default_factory=list)

    def add_match(self, *, label: str, text: str) -> None:
        """Track one matched Docling label/text pair once."""
        if label and label not in self.matched_labels:
            self.matched_labels.append(label)
        cleaned = " ".join((text or "").split())
        if cleaned and cleaned not in self.matched_texts:
            self.matched_texts.append(cleaned)


@dataclass
class StructuralEnrichmentResult:
    """Aggregated Docling structural hints for one extracted document."""

    source_path: str | None
    enabled: bool
    failed: bool = False
    notes: str = ""
    element_annotations: dict[str, ElementStructuralAnnotation] = field(default_factory=dict)

    def chunk_features(self, chunk: list[ExtractedElement]) -> dict[str, Any]:
        """Return chunk-level structural scores aggregated from element annotations."""
        annotations = [
            self.element_annotations.get(element.id)
            for element in chunk
            if element.id in self.element_annotations
        ]
        labels: list[str] = []
        texts: list[str] = []
        for annotation in annotations:
            if annotation is None:
                continue
            for label in annotation.matched_labels:
                if label not in labels:
                    labels.append(label)
            for text in annotation.matched_texts:
                if text not in texts:
                    texts.append(text)
        return {
            "docling_enabled": self.enabled and not self.failed,
            "docling_failed": self.failed,
            "docling_section_header_score": max((annotation.section_header_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_apparatus_score": max((annotation.apparatus_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_repeated_header_score": max((annotation.repeated_header_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_caption_score": max((annotation.caption_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_footnote_score": max((annotation.footnote_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_table_score": max((annotation.table_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_picture_score": max((annotation.picture_score for annotation in annotations if annotation is not None), default=0.0),
            "docling_labels": labels,
            "docling_matched_texts": texts[:5],
        }


@dataclass
class _DoclingItemRecord:
    """Internal normalized Docling item representation for matching."""

    label: str
    text: str
    normalized_text: str
    page_numbers: list[int]
    apparatus_like: bool = False
    repeated_header_like: bool = False


class DoclingStructuralEnricher:
    """Adds Docling structural hints without replacing the extraction artifact."""

    def __init__(
        self,
        *,
        preprocessor: ElementPreprocessor | None = None,
        artifacts_path: str | Path | None = None,
        enabled: bool = True,
    ) -> None:
        """Create a Docling-based enricher with lazy converter initialization."""
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.artifacts_path = Path(artifacts_path) if artifacts_path else None
        self.enabled = enabled
        self._converter: Any = None
        self._cache: dict[tuple[str, int], StructuralEnrichmentResult] = {}

    def enrich(self, document: ExtractedDocument) -> StructuralEnrichmentResult:
        """Return Docling structural hints for the given extracted document."""
        if not self.enabled:
            return StructuralEnrichmentResult(source_path=None, enabled=False, notes="disabled")
        pdf_path = self._pdf_path(document)
        if pdf_path is None:
            return StructuralEnrichmentResult(source_path=None, enabled=False, notes="no_pdf_source")
        if self.artifacts_path is None or not self.artifacts_path.exists():
            return StructuralEnrichmentResult(source_path=str(pdf_path), enabled=False, notes="missing_artifacts")

        cache_key = (str(pdf_path.resolve()), len(document.pages))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            converter = self._get_converter()
            result = converter.convert(pdf_path.resolve(), page_range=(1, max(1, len(document.pages))))
            docling_document = result.document
            records = self._collect_docling_items(docling_document)
            enriched = self._annotate_elements(document=document, item_records=records)
        except Exception as exc:
            enriched = StructuralEnrichmentResult(
                source_path=str(pdf_path),
                enabled=True,
                failed=True,
                notes=f"{type(exc).__name__}: {exc}",
            )

        self._cache[cache_key] = enriched
        return enriched

    def _get_converter(self) -> Any:
        if self._converter is not None:
            return self._converter

        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption

        options = PdfPipelineOptions(
            artifacts_path=str(self.artifacts_path),
            do_ocr=False,
            do_table_structure=True,
            do_picture_classification=False,
            do_picture_description=False,
            do_formula_enrichment=False,
            do_code_enrichment=False,
            force_backend_text=True,
        )
        self._converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        return self._converter

    def _pdf_path(self, document: ExtractedDocument) -> Path | None:
        candidates = [document.processed_path, document.source_path]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists() and path.suffix.lower() == ".pdf":
                return path
        return None

    def _collect_docling_items(self, document: Any) -> list[_DoclingItemRecord]:
        items: list[_DoclingItemRecord] = []
        header_pages: dict[str, set[int]] = defaultdict(set)
        raw_items: list[tuple[str, str, list[int]]] = []

        for item, _level in document.iterate_items():
            label = str(getattr(getattr(item, "label", None), "value", getattr(item, "label", None)) or "")
            text = self._item_text(item)
            pages = sorted(
                {
                    int(getattr(prov, "page_no"))
                    for prov in (getattr(item, "prov", None) or [])
                    if getattr(prov, "page_no", None) is not None
                }
            )
            raw_items.append((label, text, pages))
            normalized = self._normalize_text(text)
            if label == "section_header" and normalized:
                for page_no in pages:
                    header_pages[normalized].add(page_no)

        repeated_headers = {
            text
            for text, pages in header_pages.items()
            if len(pages) >= 2 and len(self._content_tokens(text)) <= 12
        }

        for label, text, pages in raw_items:
            normalized = self._normalize_text(text)
            items.append(
                _DoclingItemRecord(
                    label=label,
                    text=text,
                    normalized_text=normalized,
                    page_numbers=pages,
                    apparatus_like=self._is_apparatus_item(label=label, text=text),
                    repeated_header_like=label == "section_header" and normalized in repeated_headers,
                )
            )
        return items

    def _annotate_elements(
        self,
        *,
        document: ExtractedDocument,
        item_records: list[_DoclingItemRecord],
    ) -> StructuralEnrichmentResult:
        by_page: dict[int, list[_DoclingItemRecord]] = defaultdict(list)
        for record in item_records:
            for page_no in record.page_numbers:
                by_page[page_no].append(record)

        annotations: dict[str, ElementStructuralAnnotation] = {}
        for page in document.pages:
            page_records = by_page.get(page.page_number, [])
            if not page_records:
                continue
            for element in page.elements:
                annotation = ElementStructuralAnnotation(
                    element_id=element.id,
                    page_number=element.page_number,
                )
                element_text = self._element_text(element)
                normalized_element_text = self._normalize_text(element_text)
                element_type = element.type
                for record in page_records:
                    similarity = 0.0
                    if normalized_element_text and record.normalized_text:
                        similarity = self._text_similarity(normalized_element_text, record.normalized_text)

                    if element_type == "table" and record.label == "table":
                        annotation.table_score = max(annotation.table_score, 0.72)
                        annotation.add_match(label=record.label, text=record.text)
                    if element_type in NON_TEXT_TYPES and record.label == "picture":
                        annotation.picture_score = max(annotation.picture_score, 0.65)
                        annotation.add_match(label=record.label, text=record.text)

                    if similarity <= 0.0:
                        continue
                    if record.label == "section_header" and similarity >= 0.48:
                        annotation.section_header_score = max(annotation.section_header_score, similarity)
                        annotation.add_match(label=record.label, text=record.text)
                    if record.apparatus_like and similarity >= 0.42:
                        apparatus_score = max(0.72, similarity)
                        annotation.apparatus_score = max(annotation.apparatus_score, apparatus_score)
                        annotation.add_match(label=record.label, text=record.text)
                    if record.repeated_header_like and similarity >= 0.48:
                        repeated_score = min(1.0, 0.78 + (similarity * 0.2))
                        annotation.repeated_header_score = max(annotation.repeated_header_score, repeated_score)
                        annotation.add_match(label=record.label, text=record.text)
                    if record.label == "caption" and similarity >= 0.45:
                        annotation.caption_score = max(annotation.caption_score, similarity)
                        annotation.add_match(label=record.label, text=record.text)
                    if record.label == "footnote" and similarity >= 0.45:
                        annotation.footnote_score = max(annotation.footnote_score, similarity)
                        annotation.add_match(label=record.label, text=record.text)

                if any(
                    score > 0.0
                    for score in (
                        annotation.section_header_score,
                        annotation.apparatus_score,
                        annotation.repeated_header_score,
                        annotation.caption_score,
                        annotation.footnote_score,
                        annotation.table_score,
                        annotation.picture_score,
                    )
                ):
                    annotations[element.id] = annotation

        return StructuralEnrichmentResult(
            source_path=document.processed_path or document.source_path,
            enabled=True,
            element_annotations=annotations,
        )

    def _is_apparatus_item(self, *, label: str, text: str) -> bool:
        normalized = " ".join((text or "").split())
        if label == "section_header" and APPARATUS_HEADING_PATTERN.search(normalized):
            return True
        return bool(APPARATUS_TEXT_PATTERN.search(normalized))

    def _item_text(self, item: Any) -> str:
        text = str(getattr(item, "text", "") or getattr(item, "orig", "") or "").strip()
        return text

    def _element_text(self, element: ExtractedElement) -> str:
        if element.raw_text:
            return element.raw_text
        if isinstance(element.content, str) and element.content.strip():
            return element.content
        return self.preprocessor.to_text(element)

    def _normalize_text(self, text: str) -> str:
        tokens = TOKEN_PATTERN.findall((text or "").lower())
        return " ".join(tokens)

    def _content_tokens(self, text: str) -> list[str]:
        return [token for token in TOKEN_PATTERN.findall((text or "").lower()) if len(token) > 2]

    def _text_similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._content_tokens(left))
        right_tokens = set(self._content_tokens(right))
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = left_tokens & right_tokens
        union = left_tokens | right_tokens
        jaccard = len(intersection) / len(union)
        containment = len(intersection) / min(len(left_tokens), len(right_tokens))
        return max(jaccard, containment * 0.9)
