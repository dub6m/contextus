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
    element = make_element(
        'formula',
        id='formula-a',
        content={
            'format': 'formula',
            'figure_type': 'formula',
            'raw_text': '',
            'structured_content': {'latex': r'\frac{a}{b} + x^2_1 + \sum', 'mathml': None},
            'literal_description': None,
            'source_confidence': 0.95,
        },
    )
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
            'format': 'table',
            'figure_type': 'table',
            'raw_text': 'Name Value Alpha 10 Beta 20',
            'structured_content': {
                'headers': ['Name', 'Value'],
                'rows': [['Alpha', '10'], ['Beta', '20']],
                'markdown': '| Name | Value |\n| --- | --- |\n| Alpha | 10 |\n| Beta | 20 |',
            },
            'literal_description': None,
            'source_confidence': 0.92,
        },
    )
    text = preprocessor.to_text(element)
    assert 'Table with columns Name, Value.' in text
    assert 'Name=Alpha' in text


def test_to_text_uses_figure_description_and_raw_text():
    preprocessor = ElementPreprocessor()
    element = make_element(
        'figure',
        id='figure-a',
        content={
            'format': 'figure',
            'figure_type': 'diagram',
            'raw_text': 'Nearest pair split band',
            'structured_content': {'nodes': [{'id': 'n1', 'label': 'Split'}, {'id': 'n2', 'label': 'Merge'}], 'edges': []},
            'literal_description': 'A divide-and-conquer diagram.',
            'source_confidence': 0.88,
        },
    )
    text = preprocessor.to_text(element)
    assert text.startswith('Figure (diagram):')
    assert 'Split' in text
    assert 'divide-and-conquer diagram' in text.lower()


def test_to_text_figure_falls_back_to_no_text_content():
    preprocessor = ElementPreprocessor()
    element = make_element(
        'image',
        id='image-a',
        content={
            'format': 'figure',
            'figure_type': 'image',
            'raw_text': '',
            'structured_content': None,
            'literal_description': None,
            'source_confidence': 0.4,
        },
    )
    assert preprocessor.to_text(element) == 'Figure (image): no text content'


def test_to_text_summarizes_chart_structured_content():
    preprocessor = ElementPreprocessor()
    element = make_element(
        'chart',
        id='chart-a',
        content={
            'format': 'figure',
            'figure_type': 'chart',
            'raw_text': 'Q1 Q2 Revenue',
            'structured_content': {
                'chart_type': 'bar',
                'axes': {'x_label': 'Quarter', 'y_label': 'Revenue'},
                'series': [{'name': 'Revenue', 'values': [{'x': 'Q1', 'y': '10'}]}],
                'findings': ['Revenue rises from Q1 to Q2'],
            },
            'literal_description': None,
            'source_confidence': 0.91,
        },
    )
    text = preprocessor.to_text(element)
    assert 'type=bar' in text
    assert 'axes x=Quarter, y=Revenue' in text
    assert 'Revenue rises from Q1 to Q2' in text


def test_to_text_returns_fallback_on_empty_content():
    preprocessor = ElementPreprocessor()
    element = make_element('text', id='text-empty', content='', raw_text='')
    assert preprocessor.to_text(element) == 'Element of type text on page 1'
