from contextus.builder.evidence import EvidenceHandleBuilder
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


def make_element(
    element_id: str,
    content,
    *,
    element_type: str = "text",
    page: int = 1,
    order: int = 1,
    bbox=(0.0, 0.0, 0.1, 0.1),
    asset_path: str | None = None,
) -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type=element_type,
        page_number=page,
        order=order,
        bbox=bbox,
        confidence=0.9,
        content=content,
        raw_text="",
        source="test",
        metadata={},
        asset_path=asset_path,
    )


def make_document(elements: list[ExtractedElement]) -> ExtractedDocument:
    return ExtractedDocument(
        source_name="doc.pdf",
        source_path="doc.pdf",
        source_type="pdf",
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def handle_for(result, element_id: str):
    return next(handle for handle in result.handles if handle.core_element_ids == [element_id])


def package_for(result, element_id: str):
    return next(package for package in result.packages if package.core_element_ids == [element_id])


def signal_for(result, element_id: str):
    return next(signal for signal in result.signals if signal.element_id == element_id)


def test_evidence_builder_records_raw_signals_and_heading_candidate():
    title = make_element("h", "Inheritance", element_type="title", order=1)
    body = make_element("b", "Allows subclasses to override behavior.", order=2)

    result = EvidenceHandleBuilder().build(make_document([body, title]))

    body_signal = signal_for(result, "b")
    assert body_signal.element_index == 1
    assert body_signal.word_count == 5
    assert body_signal.token_count >= body_signal.word_count
    assert body_signal.heading_path[0].element_id == "h"

    body_handle = handle_for(result, "b")
    assert any(attachment.attachment_type == "heading" for attachment in body_handle.attachments)
    assert body_handle.feature_scores["heading_dependency"] > 0


def test_reference_marker_creates_previous_attachment_without_merging():
    setup = make_element("setup", "Inheritance lets a class derive from another class.", order=1)
    target = make_element("target", "This allows subclasses to override behavior.", order=2)

    result = EvidenceHandleBuilder().build(make_document([setup, target]))

    target_signal = signal_for(result, "target")
    assert [marker.text.lower() for marker in target_signal.markers] == ["this"]

    target_handle = handle_for(result, "target")
    previous = [attachment for attachment in target_handle.attachments if attachment.attachment_type == "previous"]
    assert previous
    assert previous[0].target_element_ids == ["setup"]
    assert target_handle.core_element_ids == ["target"]

    target_package = package_for(result, "target")
    assert "setup" in target_package.context_element_ids
    assert "Previous Context" in target_package.package_text
    assert target_package.package_scores["reference_closure"] >= 0.9


def test_support_marker_and_caption_candidates_are_non_destructive():
    body = make_element("body", "As shown in the figure, DNA stores inherited information.", order=1)
    figure = make_element(
        "figure",
        {"raw_text": "DNA double helix diagram"},
        element_type="figure",
        order=2,
        bbox=(0.1, 0.1, 0.5, 0.5),
        asset_path="assets/dna.png",
    )
    caption = make_element(
        "caption",
        "Figure: DNA double helix.",
        order=3,
        bbox=(0.1, 0.52, 0.5, 0.6),
    )

    result = EvidenceHandleBuilder().build(make_document([body, figure, caption]))

    body_handle = handle_for(result, "body")
    assert any(attachment.attachment_type == "support" for attachment in body_handle.attachments)
    assert body_handle.feature_scores["support_closure"] > 0.6

    figure_handle = handle_for(result, "figure")
    caption_candidates = [attachment for attachment in figure_handle.attachments if attachment.attachment_type == "caption"]
    assert caption_candidates
    assert caption_candidates[0].target_element_ids == ["caption"]
    assert figure_handle.core_element_ids == ["figure"]

    body_package = package_for(result, "body")
    assert "figure" in body_package.context_element_ids
    assert "support" in body_package.included_attachment_types
    assert body_package.package_scores["support_closure"] >= 0.88

    figure_package = package_for(result, "figure")
    assert "caption" in figure_package.context_element_ids
    assert "caption" in figure_package.included_attachment_types


def test_support_element_keeps_weak_heading_context():
    heading = make_element("heading", "Cell Biology", element_type="title", order=1)
    filler = [
        make_element(
            f"filler-{index}",
            f"Background detail {index}.",
            order=index + 2,
            bbox=(0.0, 0.0, 0.1, 0.1),
        )
        for index in range(8)
    ]
    figure = make_element(
        "figure",
        {
            "raw_text": (
                "A detailed labeled cell diagram showing nucleus cytoplasm ribosomes "
                "mitochondrion membrane chromosome material organelles and annotations."
            )
        },
        element_type="figure",
        order=11,
        bbox=(0.8, 0.8, 0.9, 0.9),
        asset_path="assets/cell.png",
    )

    result = EvidenceHandleBuilder().build(make_document([heading, *filler, figure]))

    figure_handle = handle_for(result, "figure")
    heading_attachment = next(
        attachment for attachment in figure_handle.attachments if attachment.attachment_type == "heading"
    )
    assert heading_attachment.score < 0.55

    figure_package = package_for(result, "figure")
    assert figure_package.context_element_ids == ["heading"]
    assert figure_package.included_attachment_types == ["heading"]
    assert "package_support_closure_low" not in figure_package.risk_flags


def test_list_items_get_sibling_candidates_but_remain_separate_handles():
    elements = [
        make_element("h", "Algorithm Steps", element_type="title", order=1),
        make_element("a", "1. Sort points by x-coordinate.", order=2, bbox=(0.1, 0.1, 0.2, 0.2)),
        make_element("b", "2. Split points into left and right halves.", order=3, bbox=(0.1, 0.2, 0.2, 0.3)),
    ]

    result = EvidenceHandleBuilder().build(make_document(elements))

    first_signal = signal_for(result, "a")
    second_signal = signal_for(result, "b")
    assert first_signal.list_signal is not None
    assert second_signal.list_signal is not None
    assert first_signal.list_signal.run_id == second_signal.list_signal.run_id

    first_handle = handle_for(result, "a")
    assert any(attachment.attachment_type == "list_siblings" for attachment in first_handle.attachments)
    assert [handle.core_element_ids for handle in result.handles] == [["h"], ["a"], ["b"]]

    first_package = package_for(result, "a")
    assert "b" in first_package.context_element_ids
    assert "list_siblings" in first_package.included_attachment_types


def test_duplicate_neighbor_context_is_not_selected():
    first = make_element("first", "REQUIREMENTS FOR", order=1)
    second = make_element("second", "REQUIREMENTS FOR", order=2)

    result = EvidenceHandleBuilder().build(make_document([first, second]))

    second_handle = handle_for(result, "second")
    assert any(attachment.attachment_type == "previous" for attachment in second_handle.attachments)

    second_package = package_for(result, "second")
    assert second_package.context_element_ids == []
    assert second_package.included_attachment_types == []


def test_heading_package_keeps_small_nonduplicate_lead_context():
    heading = make_element("heading", "Mitosis and Meiosis", element_type="title", order=1)
    lead = make_element("lead", "Mitosis replicates somatic cells.", order=2)

    result = EvidenceHandleBuilder().build(make_document([heading, lead]))

    heading_package = package_for(result, "heading")
    assert heading_package.context_element_ids == ["lead"]
    assert heading_package.included_attachment_types == ["next"]


def test_repeated_short_text_is_marked_as_boilerplate_like():
    elements = [
        make_element("f1", "Contextus", order=1),
        make_element("body", "The algorithm finds the closest pair of points.", order=2),
        make_element("f2", "Contextus", order=3),
    ]

    result = EvidenceHandleBuilder().build(make_document(elements))

    first = handle_for(result, "f1")
    assert "boilerplate_like" in first.risk_flags
    assert signal_for(result, "body").lexical_keyword_density > signal_for(result, "f1").lexical_keyword_density

    first_package = package_for(result, "f1")
    assert first_package.context_element_ids == []


def test_context_package_budget_skips_nonessential_large_context():
    heading = make_element("heading", "Large Section", element_type="title", order=1)
    core = make_element("core", "This is the key claim.", order=2)
    large_next = make_element("large", " ".join(["large context"] * 200), order=3)

    result = EvidenceHandleBuilder(max_context_tokens=10).build(make_document([heading, core, large_next]))

    core_package = package_for(result, "core")
    assert "heading" in core_package.context_element_ids
    assert "large" not in core_package.context_element_ids
    assert "context_budget_exceeded" not in core_package.risk_flags
