from contextus.builder.preprocessor import ElementPreprocessor
from contextus.ingestion.models import ExtractedElement


def make_element(element_type: str, **kwargs) -> ExtractedElement:
    return ExtractedElement(
        id=kwargs.pop('id', f'{element_type}-1'),
        type=element_type,
        page_number=kwargs.pop('page_number', 1),
        order=kwargs.pop('order', 1),
        bbox=kwargs.pop('bbox', (0.0, 0.0, 1.0, 1.0)),
        confidence=kwargs.pop('confidence', 0.9),
        content=kwargs.pop('content', ''),
        raw_text=kwargs.pop('raw_text', ''),
        source=kwargs.pop('source', 'test'),
        metadata=kwargs.pop('metadata', {}),
        asset_path=kwargs.pop('asset_path', None),
    )


def test_to_text_returns_text_content_for_text_elements():
    preprocessor = ElementPreprocessor()
    element = make_element('text', id='text-a', content='Hello world')
    assert preprocessor.to_text(element) == 'Hello world'


def test_to_text_converts_formula_to_readable_text():
    preprocessor = ElementPreprocessor()
    element = make_element('formula', id='formula-a', content={'latex': r'\frac{a}{b} + x^2_1 + \sum'})
    text = preprocessor.to_text(element)
    assert text.startswith('Formula: ')
    assert 'a divided by b' in text
    assert 'to the power of' in text
    assert 'subscript' in text
    assert 'sum of' in text


def test_to_text_summarizes_table():
    preprocessor = ElementPreprocessor()
    element = make_element(
        'table',
        id='table-a',
        content={
            'headers': ['Name', 'Value'],
            'rows': [['Name', 'Value'], ['Alpha', '10'], ['Beta', '20']],
        },
    )
    text = preprocessor.to_text(element)
    assert 'Table with columns Name, Value.' in text
    assert 'Name=Alpha' in text


def test_to_text_uses_figure_ocr_text():
    preprocessor = ElementPreprocessor()
    element = make_element('figure', id='figure-a', content={'figure_type': 'diagram', 'ocr_text': 'nearest pair'})
    assert preprocessor.to_text(element) == 'Figure (diagram): nearest pair'


def test_to_text_figure_falls_back_to_no_text_content():
    preprocessor = ElementPreprocessor()
    element = make_element('image', id='image-a', content={'figure_type': 'image'})
    assert preprocessor.to_text(element) == 'Figure (image): no text content'


def test_to_text_returns_fallback_on_empty_content():
    preprocessor = ElementPreprocessor()
    element = make_element('text', id='text-empty', content='', raw_text='')
    assert preprocessor.to_text(element) == 'Element of type text on page 1'
