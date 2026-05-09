from contextus import Edge, Graph, Node, NodeType
from contextus.builder.pipeline import AutoGraphBuilder
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage
from contextus.llm import LLMResponse


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, system: str, user: str, temperature: float = 0.0):
        response = self.responses.pop(0)
        return LLMResponse(content=response)


def make_document() -> ExtractedDocument:
    elements = [
        ExtractedElement(
            id='e1',
            type='text',
            page_number=1,
            order=1,
            bbox=(0.0, 0.0, 1.0, 1.0),
            confidence=0.9,
            content='Closest pair definition',
            raw_text='',
            source='test',
            metadata={},
            asset_path=None,
        ),
        ExtractedElement(
            id='e2',
            type='title',
            page_number=1,
            order=2,
            bbox=(0.0, 0.0, 1.0, 1.0),
            confidence=0.9,
            content='Algorithm',
            raw_text='',
            source='test',
            metadata={},
            asset_path=None,
        ),
    ]
    return ExtractedDocument(
        source_name='closest-pair.pdf',
        source_path='closest-pair.pdf',
        source_type='pdf',
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def test_pipeline_builds_graph_and_prints_summary(capsys):
    llm = FakeLLM([
        '{"label":"Closest Pair","type":"definition","body":"Defines the closest pair problem.","scope":"Covers the closest pair problem definition only.","aliases":[]}',
        '{"label":"Closest Pair Algorithm","type":"procedure","body":"Describes the closest pair algorithm.","scope":"Covers the closest pair algorithm steps only.","aliases":[]}',
    ])
    builder = AutoGraphBuilder(llm_client=llm)
    builder.chunker._compute_similarity_stats = lambda texts: ([0.2], 0.2, 0.0)

    graph = builder.build(make_document(), 'Closest Pair Algorithm')
    captured = capsys.readouterr().out

    assert graph.node_count() == 2
    assert graph.edge_count() == 1
    assert "Built graph 'Closest Pair Algorithm': 2 nodes, 1 edges" in captured
    assert 'Chunking:' in captured
    assert 'Step 7 node candidates:' in captured
    assert 'LLM calls total:' in captured
    assert graph.metadata["node_candidate_count"] == 2
    assert graph.all_nodes()[0].metadata["node_candidate_index"] == 0
