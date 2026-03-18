from pathlib import Path
import json

from contextus.builder.audit import ChunkAuditExporter
from contextus.builder.preprocessor import ElementPreprocessor
from contextus.builder.structural import ElementStructuralAnnotation, StructuralEnrichmentResult
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


class FakeChunker:
    def __init__(self, chunks):
        self._chunks = chunks

    def chunk(self, document):
        return self._chunks


class FakeStructuralEnricher:
    def __init__(self, annotations=None):
        self._annotations = annotations or {}

    def enrich(self, document):
        return StructuralEnrichmentResult(
            source_path=document.source_path,
            enabled=True,
            element_annotations=self._annotations,
        )


def make_element(element_type: str, order: int, **kwargs) -> ExtractedElement:
    return ExtractedElement(
        id=kwargs.pop("id", f"{element_type}-{order}"),
        type=element_type,
        page_number=kwargs.pop("page_number", 1),
        order=order,
        bbox=kwargs.pop("bbox", (0.0, 0.0, 1.0, 1.0)),
        confidence=kwargs.pop("confidence", 0.9),
        content=kwargs.pop("content", f"{element_type}-{order}"),
        raw_text=kwargs.pop("raw_text", ""),
        source=kwargs.pop("source", "test"),
        metadata=kwargs.pop("metadata", {}),
        asset_path=kwargs.pop("asset_path", None),
    )


def make_document(elements: list[ExtractedElement]) -> ExtractedDocument:
    return ExtractedDocument(
        source_name="doc.pdf",
        source_path="doc.pdf",
        source_type="pdf",
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def test_rows_from_document_exports_contextual_features():
    heading = make_element("title", 1, content="1.1 Basic arithmetic")
    body = make_element("text", 2, content="Addition and multiplication are basic arithmetic operations used throughout the chapter.")
    document = make_document([heading, body])
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[heading], [body]]),
        preprocessor=ElementPreprocessor(),
    )

    rows = exporter.rows_from_document(document)

    assert len(rows) == 2
    assert rows[0].right_context_text.startswith("Addition and multiplication")
    assert rows[0].next_substantive_distance == 1
    assert rows[0].heading_score > rows[0].proposition_score
    assert rows[0].suggested_action == "attach_right"


def test_rhetorical_singleton_suggests_attachment():
    intro = make_element("text", 1, content="Closest pair problem statement")
    proof = make_element("text", 2, content="Proof")
    body = make_element("text", 3, content="If the pair is closer than delta then both points lie in the strip")
    document = make_document([intro, proof, body])
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[intro], [proof], [body]]),
        preprocessor=ElementPreprocessor(),
    )

    rows = exporter.rows_from_document(document)
    proof_row = rows[1]

    assert proof_row.singleton_chunk is True
    assert proof_row.rhetorical_penalty >= 0.7
    assert proof_row.suggested_action == "attach_right"
    assert "proof" in proof_row.rhetorical_markers


def test_duplicate_singleton_is_flagged_for_drop():
    first = make_element("text", 1, content="Closest pair of points problem")
    second = make_element("text", 2, content="Closest pair of points problem")
    document = make_document([first, second])
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[first], [second]]),
        preprocessor=ElementPreprocessor(),
    )

    rows = exporter.rows_from_document(document)
    duplicate_row = rows[1]

    assert duplicate_row.max_previous_similarity == 1.0
    assert duplicate_row.duplicate_penalty >= 0.9
    assert duplicate_row.suggested_action == "duplicate_drop"


def test_shallow_list_item_defaults_to_parent_attachment():
    heading = make_element("title", 1, content="Strategic priorities")
    bullet = make_element("text", 2, content="2. Make life better for Manitobans.")
    following = make_element("text", 3, content="The department delivers programs intended to improve quality of life and public services.")
    document = make_document([heading, bullet, following])
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[heading], [bullet], [following]]),
        preprocessor=ElementPreprocessor(),
    )

    rows = exporter.rows_from_document(document)
    bullet_row = rows[1]

    assert bullet_row.list_item_score >= 0.7
    assert bullet_row.suggested_action == "attach_left"


def test_export_jsonl_writes_rows(tmp_path):
    element = make_element("text", 1, content="Closest pair definition")
    document = make_document([element])
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[element]]),
        preprocessor=ElementPreprocessor(),
    )

    output = exporter.export_jsonl(document, tmp_path / "audit.jsonl")

    lines = output.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["chunk_text"] == "Closest pair definition"
    assert payload["chunk_index"] == 0
    assert "left_context_text" in payload
    assert "heading_score" in payload
    assert "docling_apparatus_score" in payload


def test_publication_metadata_chunk_gets_high_admin_score():
    metadata = make_element("text", 1, content="RECEIVED 02 January 2025 ACCEPTED 07 April 2025 PUBLISHED 15 May 2025")
    document = make_document([metadata])
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[metadata]]),
        preprocessor=ElementPreprocessor(),
    )

    rows = exporter.rows_from_document(document)

    assert rows[0].admin_score >= 0.8
    assert rows[0].proposition_score < rows[0].admin_score


def test_docling_structural_signals_are_aggregated_into_rows():
    heading = make_element("title", 1, content="COPYRIGHT", id="e-heading")
    body = make_element("text", 2, content="Creative Commons Attribution License", id="e-body")
    document = make_document([heading, body])
    annotations = {
        "e-heading": ElementStructuralAnnotation(
            element_id="e-heading",
            page_number=1,
            section_header_score=0.88,
            apparatus_score=0.92,
            matched_labels=["section_header"],
            matched_texts=["COPYRIGHT"],
        ),
        "e-body": ElementStructuralAnnotation(
            element_id="e-body",
            page_number=1,
            apparatus_score=0.9,
            matched_labels=["text"],
            matched_texts=["Creative Commons Attribution License"],
        ),
    }
    exporter = ChunkAuditExporter(
        chunker=FakeChunker([[heading], [body]]),
        preprocessor=ElementPreprocessor(),
        structural_enricher=FakeStructuralEnricher(annotations),
    )

    rows = exporter.rows_from_document(document)

    assert rows[0].docling_enabled is True
    assert rows[0].docling_section_header_score >= 0.88
    assert rows[0].docling_apparatus_score >= 0.92
    assert rows[0].suggested_action == "support_only"
    assert "section_header" in rows[0].docling_labels
