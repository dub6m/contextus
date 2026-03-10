from pathlib import Path

import pytest

from contextus.ingestion.models import ExtractedDocument, ExtractedPage
from contextus.ingestion.router import DocumentExtractionRouter


class FakeAnalyzer:
    def __init__(self):
        self.calls = []

    def analyze(self, file_path: str, max_pages=None):
        self.calls.append((file_path, max_pages))
        return [{'page_number': 1, 'detections': []}]


class FakeExtractor:
    def __init__(self):
        self.calls = []

    def extract(self, file_path: str, analyzed_pages, **kwargs):
        self.calls.append((file_path, analyzed_pages, kwargs))
        return ExtractedDocument(
            source_name=Path(kwargs['original_source_path']).name,
            source_path=kwargs['original_source_path'],
            source_type=Path(kwargs['original_source_path']).suffix.lstrip('.'),
            processed_path=file_path,
            converted_from=kwargs.get('converted_from'),
            pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=[])],
        )


class FakeConverter:
    def __init__(self):
        self.calls = []

    def convert(self, pptx_path: str, out_dir=None):
        self.calls.append((pptx_path, out_dir))
        pdf_path = Path(out_dir) / 'converted.pdf'
        pdf_path.write_text('pdf', encoding='utf-8')
        return str(pdf_path)


def test_extract_pdf_uses_pdf_pipeline(tmp_path):
    source = tmp_path / 'sample.pdf'
    source.write_text('pdf', encoding='utf-8')
    analyzer = FakeAnalyzer()
    extractor = FakeExtractor()
    router = DocumentExtractionRouter(pdf_analyzer=analyzer, pdf_extractor=extractor)

    document = router.extract(str(source), max_pages=3)

    assert document.source_name == 'sample.pdf'
    assert analyzer.calls == [(str(source), 3)]
    assert extractor.calls[0][2]['converted_from'] is None


def test_extract_pptx_converts_then_cleans_up(tmp_path):
    source = tmp_path / 'slides.pptx'
    source.write_text('pptx', encoding='utf-8')
    analyzer = FakeAnalyzer()
    extractor = FakeExtractor()
    converter = FakeConverter()
    router = DocumentExtractionRouter(
        pdf_analyzer=analyzer,
        pdf_extractor=extractor,
        pptx_converter=converter,
    )

    document = router.extract(str(source))

    converted_path = Path(extractor.calls[0][0])
    assert document.converted_from == 'pptx'
    assert converter.calls
    assert analyzer.calls[0][0].endswith('converted.pdf')
    assert not converted_path.exists()


def test_extract_rejects_unsupported_extension(tmp_path):
    source = tmp_path / 'notes.txt'
    source.write_text('hello', encoding='utf-8')
    router = DocumentExtractionRouter(pdf_analyzer=FakeAnalyzer(), pdf_extractor=FakeExtractor())

    with pytest.raises(ValueError):
        router.extract(str(source))
