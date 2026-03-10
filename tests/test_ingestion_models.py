from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


def test_extracted_element_roundtrip():
    element = ExtractedElement(
        type='table',
        page_number=2,
        order=5,
        bbox=(1.0, 2.0, 3.0, 4.0),
        confidence=0.91,
        content={'format': 'table', 'markdown': '| A |'},
        raw_text='| A |',
        source='pdfplumber_table',
        metadata={'needs_review': False},
        asset_path='assets/table.png',
    )

    restored = ExtractedElement.from_dict(element.to_dict())
    assert restored.type == 'table'
    assert restored.bbox == (1.0, 2.0, 3.0, 4.0)
    assert restored.asset_path == 'assets/table.png'


def test_extracted_document_roundtrip():
    document = ExtractedDocument(
        source_name='sample.pdf',
        source_path='C:/tmp/sample.pdf',
        source_type='pdf',
        pages=[
            ExtractedPage(
                page_number=1,
                width=612.0,
                height=792.0,
                elements=[
                    ExtractedElement(
                        type='text',
                        page_number=1,
                        order=1,
                        bbox=(0.0, 0.0, 10.0, 10.0),
                        content='Hello world',
                        raw_text='Hello world',
                        source='pymupdf_text',
                    )
                ],
            )
        ],
    )

    restored = ExtractedDocument.from_json(document.to_json())
    assert restored.source_name == 'sample.pdf'
    assert len(restored.pages) == 1
    assert restored.pages[0].elements[0].content == 'Hello world'
