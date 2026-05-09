from contextus.builder.chunker import BoundaryElementView, ChunkRepairDecision, RefinedChunkGroup
from contextus.builder.node_candidate import NodeCandidateBuilder
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


def make_element(element_id: str, content: str, *, element_type: str = "text", page: int = 1, order: int = 1) -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type=element_type,
        page_number=page,
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
        source_name="doc.pdf",
        source_path="doc.pdf",
        source_type="pdf",
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def test_node_candidate_builder_creates_one_candidate_per_chunk():
    title = make_element("a", "Closest Pair", element_type="title", order=1)
    body = make_element("b", "The closest pair problem asks for the nearest two points.", order=2)
    builder = NodeCandidateBuilder()

    candidates = builder.build_candidates(make_document([title, body]), [[title, body]])

    assert len(candidates) == 1
    assert candidates[0].title == "Closest Pair"
    assert candidates[0].source_element_ids == ["a", "b"]
    assert candidates[0].quality_flags["low_information"] is False


def test_node_candidate_builder_marks_quality_flags_without_assigning_roles():
    title = make_element("a", "Heredity", element_type="title", order=1)
    figure = make_element("b", "Figure: a Punnett square", element_type="figure", order=2)
    second_title = make_element("c", "Punnett Square", element_type="title", order=3)
    builder = NodeCandidateBuilder()

    candidates = builder.build_candidates(make_document([title, figure, second_title]), [[title, figure, second_title]])

    assert candidates[0].quality_flags["mostly_visual"] is True
    assert candidates[0].quality_flags["support_heavy"] is True
    assert candidates[0].quality_flags["multiple_headings"] is True
    assert "support_candidate" not in candidates[0].metadata


def test_node_candidate_builder_preserves_repair_metadata_from_repaired_group():
    element = make_element("a", "where", order=1)
    view = BoundaryElementView(
        element_id="a",
        element_type="text",
        page_number=1,
        order=1,
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.9,
        text="where",
        raw_text="",
        source="test",
        asset_path=None,
        metadata={},
    )
    group = RefinedChunkGroup(
        group_id="g1",
        group_index=0,
        source_block_id="b1",
        elements=[view],
        start_element_index=0,
        end_element_index=0,
        repair_decisions=[
            ChunkRepairDecision(
                action="merge_heading_with_next",
                confidence=0.9,
                source="heuristic",
                affected_element_ids=["a"],
            )
        ],
    )
    builder = NodeCandidateBuilder()

    candidate = builder.build_candidates(make_document([element]), [group])[0]

    assert candidate.metadata["step7_source"] == "repaired_group"
    assert candidate.metadata["source_group_id"] == "g1"
    assert candidate.metadata["repair_decisions"][0]["action"] == "merge_heading_with_next"
    assert candidate.quality_flags["ends_mid_thought"] is True


def test_node_candidate_builder_marks_repeated_titles_as_possible_duplicates():
    first = make_element("a", "Closest Pair", element_type="title", order=1)
    second = make_element("b", "Closest Pair", element_type="title", order=2)
    builder = NodeCandidateBuilder()

    candidates = builder.build_candidates(make_document([first, second]), [[first], [second]])

    assert candidates[0].quality_flags["possible_duplicate_title"] is True
    assert candidates[1].quality_flags["possible_duplicate_title"] is True
