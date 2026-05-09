from contextus.builder.edge_builder import EdgeBuilder
from contextus.builder.config import BuilderConfig
from contextus.llm import LLMClient, LLMResponse
from contextus.node import Node, NodeType
import time


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, system: str, user: str, temperature: float = 0.0):
        response = self.responses.pop(0) if self.responses else 'RELATES_TO'
        return LLMResponse(content=response)


class SlowRelationLLM(LLMClient):
    def __init__(self, delay: float = 0.15):
        self.delay = delay

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        time.sleep(self.delay)
        return LLMResponse(content="RELATES_TO")


def make_node(name: str) -> Node:
    return Node(
        label=name,
        type=NodeType.DEFINITION,
        body=f'{name} body',
        scope=f'Covers {name} only.',
    )


def test_edge_builder_creates_sequential_edges_for_adjacent_nodes():
    builder = EdgeBuilder(llm_client=FakeLLM([]), source_document='doc.pdf')
    nodes = [make_node('A'), make_node('B')]
    edges = builder.build_edges(nodes)

    sequential = [edge for edge in edges if edge.metadata.get('kind') == 'sequential']
    assert len(sequential) == 1
    assert sequential[0].relations == ['leads_to']


def test_edge_builder_respects_semantic_edge_cap():
    config = BuilderConfig(MAX_SEMANTIC_EDGES_PER_NODE=2, SEMANTIC_EDGE_THRESHOLD=0.75)
    builder = EdgeBuilder(llm_client=FakeLLM(['RELATES_TO'] * 20), config=config)
    nodes = [make_node(f'N{i}') for i in range(5)]
    builder._embed_texts = lambda texts: __import__('numpy').array([
        [1.0, 0.0],
        [0.9, 0.1],
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
    ])

    edges = builder.build_edges(nodes)

    semantic = [edge for edge in edges if edge.metadata.get('kind') == 'semantic']
    per_source = {}
    for edge in semantic:
        per_source[edge.source_id] = per_source.get(edge.source_id, 0) + 1
    assert all(count <= 2 for count in per_source.values())


def test_edge_builder_defaults_unknown_llm_response_safely():
    builder = EdgeBuilder(llm_client=FakeLLM(['unknown', 'unknown']))
    nodes = [make_node('A'), make_node('B'), make_node('C')]
    builder._embed_texts = lambda texts: __import__('numpy').array([
        [1.0, 0.0],
        [0.0, 1.0],
        [1.0, 0.0],
    ])

    edges = builder.build_edges(nodes)

    semantic = [edge for edge in edges if edge.metadata.get('kind') == 'semantic']
    assert semantic
    assert all(edge.relations == ['relates_to'] for edge in semantic)


def test_edge_builder_classifies_independent_semantic_edges_concurrently():
    config = BuilderConfig(MAX_SEMANTIC_EDGES_PER_NODE=1, SEMANTIC_EDGE_THRESHOLD=0.1)
    builder = EdgeBuilder(llm_client=SlowRelationLLM(delay=0.15), config=config)
    nodes = [make_node(f'N{i}') for i in range(5)]
    builder._embed_texts = lambda texts: __import__('numpy').array([
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
    ])

    started = time.perf_counter()
    edges = builder.build_edges(nodes)
    elapsed = time.perf_counter() - started

    semantic = [edge for edge in edges if edge.metadata.get('kind') == 'semantic']
    assert len(semantic) >= 3
    assert builder.llm_calls == len(semantic)
    assert elapsed < 0.35
