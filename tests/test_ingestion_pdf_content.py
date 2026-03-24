import sys
import threading
from types import SimpleNamespace

from contextus.ingestion.extractors import PdfContentExtractor
from contextus.ingestion.handlers.base import HandlerOutput
from contextus.ingestion.models import ExtractedElement


def make_element(
    *,
    element_type: str,
    content=None,
    raw_text: str = "",
):
    return ExtractedElement(
        type=element_type,
        page_number=1,
        order=1,
        bbox=(0.0, 0.0, 10.0, 10.0),
        content=content,
        raw_text=raw_text,
        source="test",
    )


def test_should_drop_blank_text_and_title_elements():
    extractor = PdfContentExtractor()

    blank_text = make_element(element_type="text", content="", raw_text="   ")
    blank_title = make_element(element_type="title", content=None, raw_text="")

    assert extractor._should_keep_element(blank_text, has_asset=False) is False
    assert extractor._should_keep_element(blank_title, has_asset=False) is False


def test_should_keep_blank_figure_when_asset_exists():
    extractor = PdfContentExtractor()

    blank_figure = make_element(
        element_type="figure",
        content={
            "format": "figure",
            "figure_type": "figure",
            "raw_text": "",
            "structured_content": None,
            "literal_description": None,
            "source_confidence": 0.0,
        },
        raw_text="",
    )

    assert extractor._should_keep_element(blank_figure, has_asset=True) is True


def test_should_keep_formula_with_asset_even_if_text_is_blank():
    extractor = PdfContentExtractor()

    blank_formula = make_element(
        element_type="formula",
        content={
            "format": "formula",
            "figure_type": "formula",
            "raw_text": "",
            "structured_content": {"latex": None, "mathml": None},
            "literal_description": None,
            "source_confidence": 0.0,
        },
        raw_text="",
    )

    assert extractor._should_keep_element(blank_formula, has_asset=True) is True


def test_should_keep_table_with_structured_content():
    extractor = PdfContentExtractor()

    table = make_element(
        element_type="table",
        content={
            "format": "table",
            "figure_type": "table",
            "raw_text": "",
            "structured_content": {"headers": ["A"], "rows": [["1"]], "markdown": ""},
            "literal_description": None,
            "source_confidence": 0.8,
        },
        raw_text="",
    )

    assert extractor._should_keep_element(table, has_asset=False) is True


def test_deduplicate_page_elements_drops_merged_aggregate_line():
    extractor = PdfContentExtractor()
    elements = [
        make_element(
            element_type="text",
            content="find a closest pair of points in the left half of P,",
            raw_text="find a closest pair of points in the left half of P,",
        ),
        make_element(
            element_type="text",
            content=(
                "find a closest pair of points in the left half of P, "
                "find a closest pair of points in the right half of P, "
                "find a closest pair with one point in the left half and the other point in the right half of P, "
                "return the pair that is the closest amongst the above three pairs."
            ),
            raw_text=(
                "find a closest pair of points in the left half of P, "
                "find a closest pair of points in the right half of P, "
                "find a closest pair with one point in the left half and the other point in the right half of P, "
                "return the pair that is the closest amongst the above three pairs."
            ),
        ),
        make_element(
            element_type="text",
            content="find a closest pair with one point in the left half and the other point in the right half of P,",
            raw_text="find a closest pair with one point in the left half and the other point in the right half of P,",
        ),
    ]
    for order, element in enumerate(elements, start=1):
        element.order = order

    kept, dropped, rewritten = extractor._deduplicate_page_elements(elements)

    assert dropped == 1
    assert rewritten == 1
    assert [element.content for element in kept] == [
        "find a closest pair of points in the left half of P,",
        "find a closest pair with one point in the left half and the other point in the right half of P,",
        "return the pair that is the closest amongst the above three pairs",
    ]
    assert [element.order for element in kept] == [1, 2, 3]
    assert kept[-1].metadata["overlap_cleanup"] is True
    assert kept[-1].metadata["overlap_cleanup_anchor"] == "prefix"


def test_deduplicate_page_elements_preserves_unique_residual_for_single_fragment_overlap():
    extractor = PdfContentExtractor()
    elements = [
        make_element(
            element_type="text",
            content="Closest pair problem definition",
            raw_text="Closest pair problem definition",
        ),
        make_element(
            element_type="text",
            content="Closest pair problem definition. The algorithm runs in O(n log n) time.",
            raw_text="Closest pair problem definition. The algorithm runs in O(n log n) time.",
        ),
    ]
    for order, element in enumerate(elements, start=1):
        element.order = order

    kept, dropped, rewritten = extractor._deduplicate_page_elements(elements)

    assert dropped == 1
    assert rewritten == 1
    assert [element.content for element in kept] == [
        "Closest pair problem definition",
        "The algorithm runs in O(n log n) time",
    ]


def test_deduplicate_page_elements_keeps_single_heading_reference():
    extractor = PdfContentExtractor()
    elements = [
        make_element(
            element_type="title",
            content="Safer, Healthier Communities",
            raw_text="Safer, Healthier Communities",
        ),
        make_element(
            element_type="text",
            content=(
                "The departmental strategic objectives reflect the elected government priorities listed in the department "
                "mandate letters. The government identified five provincial themes: Lowering costs for families, safer, "
                "healthier communities, growing the economy, and a government that works for you."
            ),
            raw_text=(
                "The departmental strategic objectives reflect the elected government priorities listed in the department "
                "mandate letters. The government identified five provincial themes: Lowering costs for families, safer, "
                "healthier communities, growing the economy, and a government that works for you."
            ),
        ),
    ]
    for order, element in enumerate(elements, start=1):
        element.order = order

    kept, dropped, rewritten = extractor._deduplicate_page_elements(elements)

    assert dropped == 0
    assert rewritten == 0
    assert kept == elements


def test_extract_parallelizes_non_text_llm_calls(monkeypatch, tmp_path):
    main_thread_id = threading.get_ident()

    class FakePage:
        def __init__(self, number=0):
            self.number = number
            self.rect = SimpleNamespace(width=100.0, height=200.0)

    class FakeDoc:
        def __init__(self):
            self.pages = [FakePage()]

        def __getitem__(self, index):
            return self.pages[index]

        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(open=lambda _path: FakeDoc()))

    class FakeTextHandler:
        def handle(self, page, bbox, scale_x, scale_y):
            return HandlerOutput(content="plain text", raw_text="plain text", source="pymupdf_text")

    class FakeFormulaHandler:
        def __init__(self):
            self.llm_client = object()
            self.thread_ids = []

        def prepare_inputs(self, page, bbox, scale_x, scale_y):
            return {"raw_text": "formula raw", "image_bytes": b"img"}

        def build_llm_output(self, *, raw_text, image_bytes):
            self.thread_ids.append(threading.get_ident())
            return HandlerOutput(
                content={
                    "format": "formula",
                    "figure_type": "formula",
                    "raw_text": raw_text,
                    "structured_content": {"latex": "x", "mathml": None},
                    "literal_description": None,
                    "source_confidence": 1.0,
                },
                raw_text=raw_text,
                source="openai_formula_vision",
                asset_bytes=image_bytes,
                asset_extension=".png",
            )

        def build_fallback_output(self, *, raw_text, image_bytes):
            raise AssertionError("Parallel formula task should not fall back.")

    extractor = PdfContentExtractor(non_text_concurrency=10)
    extractor.llm_client = object()
    extractor.text_handler = FakeTextHandler()
    fake_formula_handler = FakeFormulaHandler()
    extractor.formula_handler = fake_formula_handler

    source = tmp_path / "sample.pdf"
    source.write_text("pdf", encoding="utf-8")
    analyzed_pages = [
        {
            "page_number": 1,
            "detections": [
                {"type": "text", "bbox": [0, 0, 10, 10], "confidence": 1.0},
                {"type": "formula", "raw_type": "isolate_formula", "bbox": [10, 10, 20, 20], "confidence": 0.9},
            ],
        }
    ]

    document = extractor.extract(str(source), analyzed_pages, original_source_path=str(source))

    assert len(document.pages) == 1
    assert [element.source for element in document.pages[0].elements] == [
        "pymupdf_text",
        "openai_formula_vision",
    ]
    assert fake_formula_handler.thread_ids
    assert all(thread_id != main_thread_id for thread_id in fake_formula_handler.thread_ids)
