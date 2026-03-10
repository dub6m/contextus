from contextus.ingestion.models import ExtractedDocument, ExtractedPage
from contextus.ingestion.storage import ExtractionArtifactStore


def test_store_saves_and_loads_document(tmp_path):
    store = ExtractionArtifactStore(tmp_path)
    document = ExtractedDocument(
        source_name='lecture.pdf',
        source_path='C:/docs/lecture.pdf',
        source_type='pdf',
        pages=[ExtractedPage(page_number=1, width=10.0, height=20.0, elements=[])],
    )

    path = store.save(document)
    loaded = store.load(path)

    assert path.exists()
    assert path.name == 'lecture.extraction.json'
    assert loaded.source_type == 'pdf'
    assert loaded.pages[0].height == 20.0
