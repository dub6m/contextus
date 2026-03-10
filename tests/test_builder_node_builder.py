from contextus.builder.node_builder import NodeBuilder
from contextus.ingestion.models import ExtractedElement
from contextus.llm import LLMResponse
from contextus.node import NodeType


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, system: str, user: str, temperature: float = 0.0):
        return LLMResponse(content=self.responses.pop(0))


def make_element(element_id: str, page: int = 1, order: int = 1, content: str = 'content') -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type='text',
        page_number=page,
        order=order,
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.9,
        content=content,
        raw_text='',
        source='test',
        metadata={},
        asset_path=None,
    )


def test_node_builder_builds_node_from_valid_llm_response():
    llm = FakeLLM([
        '{"label":"Closest Pair","type":"definition","body":"Defines the closest pair problem.","scope":"Covers the closest pair problem definition only.","aliases":["nearest pair"]}'
    ])
    builder = NodeBuilder(llm)

    nodes = builder.build_nodes([[make_element('e1')]])

    assert len(nodes) == 1
    assert nodes[0].label == 'Closest Pair'
    assert nodes[0].type == NodeType.DEFINITION
    assert nodes[0].aliases == ['nearest pair']


def test_node_builder_falls_back_to_stub_on_parse_failure():
    llm = FakeLLM(['not json', 'still not json'])
    builder = NodeBuilder(llm)

    nodes = builder.build_nodes([[make_element('e1', content='Fallback body text')]])

    assert nodes[0].type == NodeType.STUB
    assert nodes[0].scope == builder.FALLBACK_SCOPE
    assert nodes[0].body == 'Fallback body text'


def test_node_builder_metadata_contains_source_element_ids():
    llm = FakeLLM([
        '{"label":"Closest Pair","type":"definition","body":"Defines the closest pair problem.","scope":"Covers the closest pair problem definition only.","aliases":[]}'
    ])
    builder = NodeBuilder(llm)
    chunk = [make_element('a', page=1, order=1), make_element('b', page=2, order=1)]

    nodes = builder.build_nodes([chunk])

    assert nodes[0].metadata['source_element_ids'] == ['a', 'b']
    assert nodes[0].metadata['source_page_numbers'] == [1, 2]
    assert nodes[0].metadata['chunk_size'] == 2
