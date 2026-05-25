from contextus.builder.evidence import EvidenceHandleBuilder
from contextus.builder.evidence_eval import (
    EvidencePromptCase,
    EvidencePromptSuiteResult,
    RetrievalEvalItem,
    evaluate_retrieval_collections,
    evaluate_prompt_case,
    render_prompt_suite_markdown,
    render_retrieval_comparison_markdown,
)
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage


def make_element(
    element_id: str,
    content,
    *,
    element_type: str = "text",
    order: int = 1,
    bbox=(0.0, 0.0, 0.1, 0.1),
    asset_path: str | None = None,
) -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type=element_type,
        page_number=1,
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


def test_prompt_evaluator_compares_package_text_against_core_only_text():
    document = make_document(
        [
            make_element("heading", "Cell Biology", element_type="title", order=1),
            make_element(
                "figure",
                {"raw_text": "A labeled diagram showing nucleus cytoplasm and membrane."},
                element_type="figure",
                order=2,
                bbox=(0.8, 0.8, 0.9, 0.9),
                asset_path="assets/cell.png",
            ),
            make_element(
                "other",
                "A separate note about cultural evolution.",
                order=3,
                bbox=(0.0, 0.0, 0.1, 0.1),
            ),
        ]
    )
    result = EvidenceHandleBuilder().build(document)
    case = EvidencePromptCase(
        case_id="cell-figure",
        document_key="doc",
        family="visual-support",
        prompt="What does the Cell Biology figure show about the nucleus?",
        expected_terms=(("cell biology",), ("nucleus",)),
    )

    evaluation = evaluate_prompt_case(result, case, top_k=3)

    assert evaluation.package_hit_at_1 is True
    assert evaluation.core_hit_at_3 is False
    assert evaluation.package_top[0].attachment_types == ["heading"]


def test_prompt_evaluator_markdown_includes_prompt_and_hit_counts():
    document = make_document([make_element("body", "Mitosis divides somatic cells.", order=1)])
    result = EvidenceHandleBuilder().build(document)
    case = EvidencePromptCase(
        case_id="mitosis",
        document_key="doc",
        family="definition",
        prompt="What does mitosis divide?",
        expected_terms=(("mitosis",), ("somatic",)),
    )
    evaluation = evaluate_prompt_case(result, case, top_k=1)

    markdown = render_prompt_suite_markdown(EvidencePromptSuiteResult(evaluations=[evaluation]))

    assert "What does mitosis divide?" in markdown
    assert "expected `2/2`" in markdown


def test_retrieval_collection_comparison_reports_pairwise_winner():
    case = EvidencePromptCase(
        case_id="above-three",
        document_key="doc",
        family="reference",
        prompt="What are the above three pairs?",
        expected_terms=(("above three pairs",), ("left half",), ("right half",)),
    )
    collections = {
        "core": {
            "doc": [
                RetrievalEvalItem(
                    collection_id="core",
                    item_id="core-1",
                    document_key="doc",
                    text="return the pair that is the closest amongst the above three pairs",
                    source_element_ids=["core"],
                )
            ]
        },
        "package": {
            "doc": [
                RetrievalEvalItem(
                    collection_id="package",
                    item_id="package-1",
                    document_key="doc",
                    text=(
                        "find a closest pair with one point in the left half and "
                        "the other point in the right half. return the above three pairs"
                    ),
                    source_element_ids=["core"],
                    context_element_ids=["previous"],
                    attachment_types=["previous"],
                )
            ]
        },
    }

    result = evaluate_retrieval_collections(collections, [case], top_k=1)
    markdown = render_retrieval_comparison_markdown(result)

    assert result.summary["collections"]["package"]["hit_at_1"] == 1
    assert result.summary["collections"]["core"]["hit_at_1"] == 0
    assert result.summary["pairwise_rank_deltas"]["core vs package"]["package_better"] == 1
    assert "above-three" in markdown
