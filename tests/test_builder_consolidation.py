from contextus.builder.consolidation import ChunkConsolidator
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


class FakeChunkActionModel:
    def __init__(self, predictions):
        self.predictions = dict(predictions)

    def predict_row(self, row):
        return dict(self.predictions[row["chunk_index"]])


def make_element(element_id: str, order: int, content: str, element_type: str = "text") -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type=element_type,
        page_number=1,
        order=order,
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.9,
        content=content,
        raw_text="",
        source="test",
        metadata={},
        asset_path=None,
    )


def make_document(elements: list[ExtractedElement]) -> ExtractedDocument:
    return ExtractedDocument(
        source_name="example.pdf",
        source_path="example.pdf",
        source_type="pdf",
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def test_consolidator_merges_attach_chunks_and_keeps_duplicate_as_supporting_evidence():
    chunks = [
        [make_element("e0", 1, "Proof", element_type="title")],
        [make_element("e1", 2, "Divide and conquer explains how the closest pair is solved efficiently.")],
        [make_element("e2", 3, "1. Maintain strip ordering.")],
        [make_element("e3", 4, "Closest pair problem definition")],
        [make_element("e4", 5, "Closest pair problem definition")],
    ]
    document = make_document([element for chunk in chunks for element in chunk])
    model = FakeChunkActionModel(
        {
            0: {"action": "attach_right", "confidence": 0.94, "needs_review": False, "used_rule": "heading_like"},
            1: {"action": "standalone", "confidence": 0.91, "needs_review": False},
            2: {"action": "attach_left", "confidence": 0.86, "needs_review": False, "used_rule": "list_item_parent"},
            3: {"action": "standalone", "confidence": 0.9, "needs_review": False},
            4: {"action": "duplicate_drop", "confidence": 0.95, "needs_review": False},
        }
    )
    consolidator = ChunkConsolidator(chunk_action_model=model)

    consolidated = consolidator.consolidate(document, chunks)

    assert len(consolidated) == 2
    assert [segment.chunk_index for segment in consolidated[0].node_text_segments()] == [1, 2]
    assert [segment.chunk_index for segment in consolidated[0].supporting_segments()] == [0]
    assert [segment.chunk_index for segment in consolidated[1].node_text_segments()] == [3]
    assert [segment.chunk_index for segment in consolidated[1].supporting_segments()] == [4]
    assert consolidator.last_action_counts == {"support_only": 1, "standalone": 2, "attach_left": 1, "duplicate_drop": 1}
    assert consolidator.last_effective_action_counts == {"support_only": 1, "standalone": 2, "attach_left": 1, "duplicate_drop": 1}


def test_consolidator_routes_uncertain_structural_chunks_to_support_only():
    chunks = [
        [make_element("e0", 1, "Proof", element_type="title")],
        [make_element("e1", 2, "Divide and conquer explains how the closest pair is solved efficiently.")],
    ]
    document = make_document([element for chunk in chunks for element in chunk])
    model = FakeChunkActionModel(
        {
            0: {"action": "attach_right", "confidence": 0.58, "needs_review": True, "used_rule": None},
            1: {"action": "standalone", "confidence": 0.91, "needs_review": False},
        }
    )
    consolidator = ChunkConsolidator(chunk_action_model=model)

    consolidated = consolidator.consolidate(document, chunks)

    assert len(consolidated) == 1
    assert [segment.chunk_index for segment in consolidated[0].node_text_segments()] == [1]
    assert [segment.chunk_index for segment in consolidated[0].supporting_segments()] == [0]
    assert consolidator.last_action_counts == {"support_only": 1, "standalone": 1}
    assert consolidator.last_effective_action_counts == {"support_only": 1, "standalone": 1}

def test_consolidator_keeps_orphan_support_only_chunks_in_document_support():
    chunks = [
        [make_element("e0", 1, "Acknowledgments", element_type="title")],
        [make_element("e1", 2, "Funding information for the publication.")],
    ]
    document = make_document([element for chunk in chunks for element in chunk])
    model = FakeChunkActionModel(
        {
            0: {"action": "support_only", "confidence": 0.95, "needs_review": False, "used_rule": "heading_like"},
            1: {"action": "support_only", "confidence": 0.9, "needs_review": False, "used_rule": "admin_like"},
        }
    )
    consolidator = ChunkConsolidator(chunk_action_model=model)

    consolidated = consolidator.consolidate(document, chunks)

    assert consolidated == []
    assert [segment.chunk_index for segment in consolidator.last_orphan_support_segments] == [0, 1]
    assert consolidator.last_effective_action_counts == {"support_only": 2}
