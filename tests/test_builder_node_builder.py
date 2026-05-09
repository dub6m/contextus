from contextus.builder.node_candidate import NodeCandidate
from contextus.builder.node_builder import NodeBuilder
from contextus.ingestion.models import ExtractedElement
from contextus.llm import LLMResponse
from contextus.node import NodeType
import time


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, system: str, user: str, temperature: float = 0.0):
        self.prompts.append(user)
        return LLMResponse(content=self.responses.pop(0))


class SlowNodeLLM:
    def __init__(self, delay: float = 0.15):
        self.delay = delay

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        time.sleep(self.delay)
        label = " ".join(user.split()[:2]) or "Node"
        return LLMResponse(
            content=(
                '{"label":"'
                + label.replace('"', '')
                + '","type":"definition","body":"Generated body.","scope":"Generated scope.","aliases":[]}'
            )
        )


def make_element(element_id: str, page: int = 1, order: int = 1, content: str = 'content', element_type: str = 'text') -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type=element_type,
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


def test_node_builder_uses_node_candidate_context_and_metadata():
    llm = FakeLLM([
        '{"label":"Punnett Square","type":"example","body":"Shows how a Punnett square represents inheritance outcomes.","scope":"Covers the Punnett square example in this chunk only.","aliases":[]}'
    ])
    builder = NodeBuilder(llm)
    element = make_element('a', content='Figure: Punnett square inheritance outcomes', element_type='figure')
    candidate = NodeCandidate(
        candidate_id='node-candidate-00000',
        candidate_index=0,
        elements=[element],
        text='Figure: Punnett square inheritance outcomes',
        title='Punnett Square',
        summary='Figure: Punnett square inheritance outcomes',
        source_page_numbers=[1],
        source_element_ids=['a'],
        element_types=['figure'],
        quality_flags={'mostly_visual': True},
        metadata={'step7_source': 'repaired_group'},
    )

    nodes = builder.build_nodes([candidate])

    assert 'Candidate title: Punnett Square' in llm.prompts[0]
    assert nodes[0].metadata['node_candidate_id'] == 'node-candidate-00000'
    assert nodes[0].metadata['node_candidate_quality_flags'] == {'mostly_visual': True}


def test_node_builder_builds_independent_nodes_concurrently():
    llm = SlowNodeLLM(delay=0.15)
    builder = NodeBuilder(llm)
    chunks = [
        [make_element("a", content="Alpha concept")],
        [make_element("b", content="Beta concept")],
        [make_element("c", content="Gamma concept")],
    ]

    started = time.perf_counter()
    nodes = builder.build_nodes(chunks)
    elapsed = time.perf_counter() - started

    assert len(nodes) == 3
    assert builder.llm_calls == 3
    assert elapsed < 0.35
