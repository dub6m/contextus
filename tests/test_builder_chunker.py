from contextus.builder.chunker import DocumentChunker
from contextus.builder.config import BuilderConfig
from contextus.builder.preprocessor import ElementPreprocessor
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


class DummyLLM:
    def complete(self, system: str, user: str, temperature: float = 0.0):
        raise AssertionError('LLM should not be called in this test unless explicitly mocked')


def make_element(element_type: str, order: int, **kwargs) -> ExtractedElement:
    return ExtractedElement(
        id=kwargs.pop('id', f'{element_type}-{order}'),
        type=element_type,
        page_number=kwargs.pop('page_number', 1),
        order=order,
        bbox=kwargs.pop('bbox', (0.0, 0.0, 1.0, 1.0)),
        confidence=kwargs.pop('confidence', 0.9),
        content=kwargs.pop('content', f'{element_type}-{order}'),
        raw_text=kwargs.pop('raw_text', ''),
        source=kwargs.pop('source', 'test'),
        metadata=kwargs.pop('metadata', {}),
        asset_path=kwargs.pop('asset_path', None),
    )


def make_document(elements: list[ExtractedElement]) -> ExtractedDocument:
    return ExtractedDocument(
        source_name='doc.pdf',
        source_path='doc.pdf',
        source_type='pdf',
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def make_chunker(**kwargs) -> DocumentChunker:
    chunker = DocumentChunker(llm_client=DummyLLM(), preprocessor=ElementPreprocessor(), **kwargs)
    chunker._summary_similarity = lambda left, right: 0.5
    chunker._score_cross_encoder = lambda left, right: 0.5
    return chunker


def test_chunker_splits_before_title():
    elements = [make_element('text', 1, content='Alpha'), make_element('title', 2, content='Heading')]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert chunker.boundary_log[0].tier_used == '0'
    assert chunker.boundary_log[0].decision == 'split'


def test_chunker_splits_on_low_confidence():
    elements = [make_element('text', 1, confidence=0.2, content='A'), make_element('text', 2, content='B')]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.9], 0.9, 0.0)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert 'low confidence' in chunker.boundary_log[0].notes


def test_chunker_free_merges_on_high_prior_without_model_call():
    elements = [make_element('text', 1, content='A'), make_element('text', 2, content='B')]
    chunker = make_chunker(type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1], 0.1, 0.0)
    chunker._summary_similarity = lambda left, right: (_ for _ in ()).throw(AssertionError('should not use summary similarity'))

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 1
    assert chunker.boundary_log[0].decision == 'merge'
    assert 'free merge' in chunker.boundary_log[0].notes


def test_chunker_populates_boundary_log():
    elements = [
        make_element('text', 1, content='A'),
        make_element('text', 2, content='B'),
        make_element('title', 3, content='C'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.9, 0.9], 0.9, 0.0)
    chunker._summary_similarity = lambda left, right: 0.95
    chunker._score_cross_encoder = lambda left, right: 0.8

    chunker.chunk(make_document(elements))

    assert len(chunker.boundary_log) == 2


def test_chunker_computes_dynamic_depth_scores():
    chunker = make_chunker()
    chunker._embed_texts = lambda texts: __import__('numpy').array([
        [1.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
    ])

    scores, mu, sigma = chunker._compute_similarity_stats(['a', 'b', 'c'])

    assert scores == [1.0, 0.0]
    assert mu == 0.5
    assert sigma > 0.0


def test_chunker_splits_conservatively_on_llm_budget_exhaustion():
    elements = [make_element('text', 1, content='A'), make_element('table', 2, content={'headers': ['X'], 'rows': [['X'], ['1']]})]
    config = BuilderConfig(MAX_LLM_CALLS_PER_BOUNDARY=0)
    chunker = make_chunker(config=config)
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.1)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert chunker.boundary_log[0].tier_used == '2'
    assert chunker.boundary_log[0].decision == 'split'
    assert 'budget exhausted' in chunker.boundary_log[0].notes


def test_chunker_records_recoverable_error_on_unresolved_boundary():
    elements = [
        make_element('text', 1, content='A'),
        make_element('figure', 2, content={'figure_type': 'image', 'ocr_text': ''}),
    ]
    config = BuilderConfig(
        ANCHOR_MIN_CONFIRMED=1,
        ANCHOR_WARMUP_THRESHOLD=0.0,
        MAX_PROBE_STEPS_PER_GROUP=0,
        MAX_LOCAL_RECOVERY_STEPS=0,
    )
    chunker = make_chunker(config=config)
    chunker._compute_similarity_stats = lambda texts: ([0.55], 0.55, 0.1)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert chunker.recoverable_errors
    assert 'defaulted to split' in chunker.recoverable_errors[0]
