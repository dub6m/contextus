import numpy as np

from contextus.builder.query_assembly import (
    ConsensusKnnPropositionEvidenceAssembler,
    PropositionQueryTimeEvidenceAssembler,
    QueryTimeEvidenceAssembler,
)
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage
from contextus.llm import LLMResponse


def make_element(element_id: str, content: str, *, order: int, element_type: str = "text") -> ExtractedElement:
    return ExtractedElement(
        id=element_id,
        type=element_type,
        page_number=1,
        order=order,
        bbox=(0.0, 0.0, 0.1, 0.1),
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


def keyword_embed(texts: list[str]) -> np.ndarray:
    vectors = []
    for text in texts:
        lowered = text.lower()
        vectors.append(
            [
                lowered.count("alpha"),
                lowered.count("banana"),
                lowered.count("gamma"),
                lowered.count("delta"),
                lowered.count("epsilon"),
                lowered.count("zeta"),
            ]
        )
    return np.asarray(vectors, dtype=float)


def bridge_embed(texts: list[str]) -> np.ndarray:
    vectors = []
    for text in texts:
        lowered = text.lower()
        vectors.append(
            [
                lowered.count("alpha"),
                lowered.count("nearby"),
                lowered.count("zeta"),
                lowered.count("boxes"),
                lowered.count("rows"),
            ]
        )
    return np.asarray(vectors, dtype=float)


def test_query_time_assembler_uses_top_five_candidate_cores():
    elements = [
        make_element("one", "alpha", order=1),
        make_element("two", "alpha alpha", order=2),
        make_element("three", "alpha alpha alpha", order=3),
        make_element("four", "alpha alpha alpha alpha", order=4),
        make_element("five", "alpha alpha alpha alpha alpha", order=5),
        make_element("six", "banana banana", order=6),
    ]

    result = QueryTimeEvidenceAssembler(embed_texts=keyword_embed, max_side_elements=0).assemble(
        make_document(elements),
        "alpha question",
    )

    assert len(result.packages) == 5
    assert {package.core_element_id for package in result.packages} == {"one", "two", "three", "four", "five"}


def test_query_time_assembler_rolls_back_unrecovered_left_drift():
    elements = [
        make_element("farther-banana", "banana banana", order=1),
        make_element("stray", "banana", order=2),
        make_element("core", "alpha answer", order=3),
        make_element("right", "alpha detail", order=4),
    ]
    assembler = QueryTimeEvidenceAssembler(
        embed_texts=keyword_embed,
        top_k_cores=1,
        lookahead_after_mark=1,
        max_side_elements=3,
    )

    result = assembler.assemble(make_document(elements), "alpha question")
    package = result.packages[0]

    assert "stray" not in package.element_ids
    assert "farther-banana" not in package.element_ids
    assert any(decision.action == "marked" for decision in package.decisions)
    assert any(decision.action == "rolled_back" for decision in package.decisions)


def test_query_time_assembler_keeps_marked_span_when_later_context_recovers():
    elements = [
        make_element("rescue", "alpha " * 30, order=1),
        make_element("stray", "banana", order=2),
        make_element("core", "alpha answer", order=3),
    ]
    assembler = QueryTimeEvidenceAssembler(
        embed_texts=keyword_embed,
        top_k_cores=1,
        lookahead_after_mark=3,
        max_side_elements=3,
    )

    result = assembler.assemble(make_document(elements), "alpha question")
    package = result.packages[0]

    assert package.element_ids == ["rescue", "stray", "core"]
    assert any(decision.action == "marked" for decision in package.decisions)
    assert any(decision.action == "recovered" for decision in package.decisions)


def test_query_time_assembler_expands_right_after_left():
    elements = [
        make_element("left", "alpha setup", order=1),
        make_element("core", "alpha gamma answer", order=2),
        make_element("right", "alpha citation", order=3),
    ]

    result = QueryTimeEvidenceAssembler(embed_texts=keyword_embed, top_k_cores=1).assemble(
        make_document(elements),
        "alpha gamma question",
    )
    package = result.packages[0]

    assert package.element_ids == ["left", "core", "right"]
    assert [decision.direction for decision in package.decisions[:2]] == ["left", "right"]
    assert all(decision.action == "kept" for decision in package.decisions[:2])


def test_query_time_assembler_stops_after_stagnant_additions():
    elements = [
        make_element("core", "alpha answer", order=1),
        make_element("flat-one", "alpha", order=2),
        make_element("flat-two", "alpha", order=3),
        make_element("flat-three", "alpha", order=4),
    ]

    result = QueryTimeEvidenceAssembler(
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=5,
        stagnant_addition_limit=1,
    ).assemble(make_document(elements), "alpha question")
    package = result.packages[0]

    assert "flat-three" not in package.element_ids
    assert any(
        decision.action == "stopped" and decision.reason == "prompt/core similarity stopped improving"
        for decision in package.decisions
    )


class PropositionLLM:
    def __init__(self, payload: str):
        self.payload = payload
        self.request_count = 0

    def complete_many(self, requests):
        self.request_count += len(requests)
        return [LLMResponse(self.payload) for _ in requests]


class SequenceLLM:
    def __init__(self, payloads: list[str]):
        self.payloads = payloads
        self.request_count = 0

    def complete_many(self, requests):
        responses = []
        for _request in requests:
            self.request_count += 1
            responses.append(LLMResponse(self.payloads.pop(0)))
        return responses


def test_proposition_query_assembler_selects_answer_bearing_proposition_core():
    elements = [
        make_element("heading", "Alpha Overview", order=1),
        make_element("body", "Tiny label", order=2),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"heading","propositions":["Alpha Overview"]},'
        '{"element_id":"body","propositions":["Gamma explains alpha answer in detail."]}'
        ']}'
    )

    result = PropositionQueryTimeEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
    ).assemble(make_document(elements), "gamma alpha question")

    assert result.propositions[1].element_id == "body"
    assert result.packages[0].core_element_id == "body"
    assert result.packages[0].package_id.startswith("query-proposition-package-")
    assert llm.request_count == 1


def test_proposition_query_assembler_falls_back_to_source_text_without_llm():
    elements = [
        make_element("core", "Alpha answer. Banana distraction.", order=1),
    ]

    result = PropositionQueryTimeEvidenceAssembler(
        llm_client=None,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
    ).assemble(make_document(elements), "alpha question")

    assert [proposition.text for proposition in result.propositions] == ["Alpha answer.", "Banana distraction."]
    assert result.packages[0].core_element_id == "core"


def test_proposition_query_assembler_attaches_explicit_support_reference():
    elements = [
        make_element("body", "Alpha claim.", order=1),
        make_element("middle", "banana filler", order=2),
        make_element("fig", "zeta visual evidence", order=3, element_type="figure"),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"body","propositions":["Alpha claim is illustrated by the figure. [SUPPORT fig]"]},'
        '{"element_id":"middle","propositions":["Banana filler."]}'
        ']}'
    )

    result = PropositionQueryTimeEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
    ).assemble(make_document(elements), "alpha question")
    package = result.packages[0]

    assert result.propositions[0].support_element_ids == ["fig"]
    assert package.core_element_id == "body"
    assert package.element_ids == ["body", "fig"]
    assert "[Support | fig]" in package.package_text
    assert any(decision.direction == "support" and decision.action == "attached" for decision in package.decisions)


def test_proposition_query_assembler_does_not_send_support_elements_for_generation():
    elements = [
        make_element("body", "Alpha claim.", order=1),
        make_element("fig", "Alpha support figure.", order=2, element_type="figure"),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"body","propositions":["Alpha claim."]}'
        ']}'
    )

    result = PropositionQueryTimeEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=2,
        max_side_elements=0,
    ).assemble(make_document(elements), "alpha question")

    assert llm.request_count == 1
    assert {proposition.element_id for proposition in result.propositions} == {"body", "fig"}


def test_consensus_knn_assembler_adds_non_contiguous_cluster_context():
    elements = [
        make_element("core", "Alpha claim.", order=1),
        make_element("filler", "banana filler", order=2),
        make_element("far", "Alpha detail.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"core","propositions":["Alpha claim."]},'
        '{"element_id":"filler","propositions":["Banana filler."]},'
        '{"element_id":"far","propositions":["Alpha detail."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1, 2),
        min_neighbor_stability=0.5,
        min_edge_similarity=0.2,
    ).assemble(make_document(elements), "alpha question")
    package = result.packages[0]

    assert package.core_element_id in {"core", "far"}
    assert {"core", "far"}.issubset(set(package.element_ids))
    assert "filler" not in package.element_ids
    assert any(decision.direction == "cluster" and decision.action == "attached" for decision in package.decisions)


def test_consensus_knn_assembler_keeps_isolated_noise_as_singleton():
    elements = [
        make_element("core", "gamma answer", order=1),
        make_element("other-one", "banana filler", order=2),
        make_element("other-two", "delta filler", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"core","propositions":["Gamma answer."]},'
        '{"element_id":"other-one","propositions":["Banana filler."]},'
        '{"element_id":"other-two","propositions":["Delta filler."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
    ).assemble(make_document(elements), "gamma question")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert package.element_ids == ["core"]


def test_consensus_knn_assembler_expands_primary_span_for_reference_closure():
    elements = [
        make_element("setup", "Alpha assumption.", order=1),
        make_element("core", "This proves the alpha alpha claim.", order=2),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"setup","propositions":["Alpha assumption."]},'
        '{"element_id":"core","propositions":["This proves the alpha alpha claim."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.0,
    ).assemble(make_document(elements), "alpha proof")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert package.element_ids == ["setup", "core"]


def test_consensus_knn_assembler_leaves_detached_ordered_span_out_of_package():
    elements = [
        make_element("core", "Alpha gamma claim.", order=1),
        make_element("middle", "banana filler", order=2),
        make_element("far", "Alpha distant detail.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"core","propositions":["Alpha gamma claim."]},'
        '{"element_id":"middle","propositions":["Banana filler."]},'
        '{"element_id":"far","propositions":["Alpha distant detail."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1, 2),
        min_neighbor_stability=0.5,
        min_edge_similarity=0.2,
        max_order_gap_for_span=1,
        max_attached_spans=0,
    ).assemble(make_document(elements), "alpha gamma question")
    package = result.packages[0]

    assert package.element_ids == ["core"]
    assert any(decision.direction == "span" and decision.action == "detached" for decision in package.decisions)


def test_consensus_knn_assembler_uses_language_map_for_core_selection():
    elements = [
        make_element("generic", "Closest pair overview.", order=1),
        make_element("proof", "Rows of boxes bound nearby points in the strip.", order=2),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"generic","propositions":["Closest pair overview."]},'
        '{"element_id":"proof","propositions":["Rows of boxes bound nearby points in the strip."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.0,
        use_language_map=True,
        language_core_weight=1.0,
    ).assemble(make_document(elements), "Why can only nearby points in the strip be closest?")

    assert result.packages[0].core_element_id == "proof"


def test_consensus_knn_assembler_uses_source_grounded_query_plan_for_core_discovery():
    elements = [
        make_element("surface", "Nearby filler.", order=1),
        make_element("proof", "Zeta boxes rows proof.", order=2),
    ]
    llm = SequenceLLM(
        [
            (
                '{"elements":['
                '{"element_id":"surface","propositions":["Nearby filler."]},'
                '{"element_id":"proof","propositions":["Zeta boxes rows proof."]}'
                ']}'
            ),
            (
                '{"interpreted_need":"The query points to the zeta boxes rows proof.",'
                '"query_type":"proof_explanation",'
                '"source_supported_terms":["zeta","boxes","rows"],'
                '"possible_missing_prerequisites":["zeta boxes"],'
                '"search_forms":["zeta boxes rows proof"],'
                '"uncertainties":[]}'
            ),
        ]
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=bridge_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.0,
        use_query_planner=True,
    ).assemble(make_document(elements), "nearby alpha question")

    assert result.retrieval_plan is not None
    assert result.retrieval_plan.search_forms == ["zeta boxes rows proof"]
    assert result.packages[0].core_element_id == "proof"


def test_consensus_knn_assembler_builds_multi_anchor_package_from_query_sub_needs():
    elements = [
        make_element("setup", "Zeta alpha setup defines the strip.", order=1),
        make_element("filler", "banana filler", order=2),
        make_element("proof", "Rows boxes zeta proof explains bounded nearby checks.", order=3),
    ]
    llm = SequenceLLM(
        [
            (
                '{"elements":['
                '{"element_id":"setup","propositions":[{"text":"Zeta alpha setup defines the strip.",'
                '"roles":[{"role":"definition","target":"Zeta","value":"the strip","confidence":0.9,"reason":"Defines the strip."}]}]},'
                '{"element_id":"filler","propositions":["Banana filler."]},'
                '{"element_id":"proof","propositions":[{"text":"Rows boxes zeta proof explains bounded nearby checks.",'
                '"roles":[{"role":"proof_reason","target":"bounded nearby checks","value":"rows boxes proof","confidence":0.9,"reason":"Explains the proof bound."}]}]}'
                ']}'
            ),
            (
                '{"interpreted_need":"Explain alpha nearby checks using setup and proof.",'
                '"query_type":"proof_explanation",'
                '"source_supported_terms":["zeta","strip","rows","boxes"],'
                '"possible_missing_prerequisites":["zeta strip"],'
                '"search_forms":["zeta strip rows boxes proof"],'
                '"uncertainties":[],'
                '"sub_needs":['
                '{"need":"define the strip","search_terms":["zeta","strip"],"expected_roles":["definition"]},'
                '{"need":"explain bounded nearby proof","search_terms":["rows","boxes","nearby"],"expected_roles":["proof_reason"]}'
                ']}'
            ),
        ]
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=bridge_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=2,
        use_query_planner=True,
    ).assemble(make_document(elements), "why alpha nearby")
    package = result.packages[0]

    assert result.retrieval_plan is not None
    assert len(result.retrieval_plan.sub_needs) == 2
    assert "setup" in package.element_ids
    assert "proof" in package.element_ids


def test_consensus_knn_assembler_completes_missing_definition_and_conclusion_roles():
    elements = [
        make_element("definition", "Let Z denote the alpha proof strip.", order=1),
        make_element("proof-label", "Proof.", order=2, element_type="title"),
        make_element("core", "Therefore gamma gamma alpha points in Z are close.", order=3),
        make_element("conclusion", "Therefore alpha only nearby points are checked.", order=4),
        make_element("filler", "banana filler", order=5),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"definition","propositions":["Let Z denote the alpha proof strip."]},'
        '{"element_id":"proof-label","propositions":["Proof."]},'
        '{"element_id":"core","propositions":["Therefore gamma gamma alpha points in Z are close."]},'
        '{"element_id":"conclusion","propositions":["Therefore alpha only nearby points are checked."]},'
        '{"element_id":"filler","propositions":["Banana filler."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        min_candidate_score=2.0,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "why gamma alpha nearby")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert "definition" in package.element_ids
    assert "conclusion" in package.element_ids
    assert "filler" not in package.element_ids
    assert any(decision.direction == "completion" and decision.action == "attached" for decision in package.decisions)
    diagnostics = package.completion_diagnostics
    assert diagnostics is not None
    traces = [candidate for round_trace in diagnostics.rounds for candidate in round_trace.candidates]
    assert any(trace.action == "attached" and "definition" in trace.element_ids for trace in traces)
    assert package.to_dict()["completion_diagnostics"]["rounds"][0]["candidates"]


def test_consensus_knn_assembler_uses_llm_role_hypotheses_for_completion():
    elements = [
        make_element("definition", "We write Z for the alpha strip.", order=1),
        make_element("filler", "Ordinary transition text.", order=2),
        make_element("core", "Gamma alpha points in Z are close.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"definition","propositions":[{'
        '"text":"Z is the alpha strip.",'
        '"roles":[{"role":"definition","target":"Z","value":"the alpha strip","confidence":0.95,"reason":"The source writes Z for the alpha strip."}]'
        '}]},'
        '{"element_id":"filler","propositions":["Ordinary transition text."]},'
        '{"element_id":"core","propositions":[{'
        '"text":"Therefore gamma alpha points in Z are close.",'
        '"roles":[{"role":"proof_conclusion","target":"points in Z","value":"points in Z are close","confidence":0.8,"reason":"The proposition is a conclusion."}]'
        '}]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "why gamma alpha")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert "definition" in package.element_ids
    assert result.propositions[0].roles[0].role == "definition"
    assert result.propositions[0].grounding is not None
    assert result.propositions[0].grounding.role_diagnostics[0].status == "grounded"
    assert any("role definition fills" in decision.reason for decision in package.decisions)


def test_proposition_grounding_audit_flags_support_mismatch_and_keeps_behavior_unchanged():
    elements = [
        make_element("source", "Alpha claim text with no visual support.", order=1),
    ]
    llm = PropositionLLM(
        '{"elements":[{'
        '"element_id":"source",'
        '"propositions":[{'
        '"text":"Alpha claim text has no visual support.",'
        '"roles":[{"role":"visual_support","target":"diagram","value":"diagram evidence","confidence":0.95,"reason":"Claims visual support."}]'
        '}]}]}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "alpha")

    proposition = result.propositions[0]
    assert proposition.grounding is not None
    role_grounding = proposition.grounding.role_diagnostics[0]
    assert role_grounding.status == "support_mismatch"
    assert role_grounding.support_grounded is False
    assert result.packages


def test_consensus_knn_assembler_adds_deterministic_ranking_diagnostics():
    elements = [
        make_element("setup", "Suppose alpha proof setup holds.", order=1),
        make_element("reason", "Because alpha bound explains nearby points.", order=2),
        make_element("conclusion", "Therefore alpha nearby points are checked.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"setup","propositions":[{'
        '"text":"Suppose alpha proof setup holds.",'
        '"roles":[{"role":"proof_setup","target":"alpha","value":"setup holds","confidence":0.9,"reason":"setup"}]'
        '}]},'
        '{"element_id":"reason","propositions":[{'
        '"text":"Because alpha bound explains nearby points.",'
        '"roles":[{"role":"proof_reason","target":"alpha bound","value":"explains nearby points","confidence":0.9,"reason":"reason"}]'
        '}]},'
        '{"element_id":"conclusion","propositions":[{'
        '"text":"Therefore alpha nearby points are checked.",'
        '"roles":[{"role":"proof_conclusion","target":"alpha nearby points","value":"points are checked","confidence":0.9,"reason":"conclusion"}]'
        '}]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=2,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "why alpha nearby")

    package = result.packages[0]
    assert package.ranking_diagnostics is not None
    assert package.score == package.ranking_diagnostics.final_score
    assert package.ranking_diagnostics.legacy_score != package.ranking_diagnostics.final_score
    assert package.ranking_diagnostics.role_coverage_score > 0.0
    assert "proof_reason" in package.ranking_diagnostics.package_roles


def test_consensus_knn_assembler_attaches_consecutive_role_span():
    elements = [
        make_element("definition", "We write Z for the alpha strip.", order=1),
        make_element("bound", "Points in Z only need alpha nearby comparisons.", order=2),
        make_element("core", "Gamma alpha points in Z are close.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"definition","propositions":[{'
        '"text":"Z is the alpha strip.",'
        '"roles":[{"role":"definition","target":"Z","value":"the alpha strip","confidence":0.95,"reason":"The proposition defines Z."}]'
        '}]},'
        '{"element_id":"bound","propositions":[{'
        '"text":"Points in Z only need alpha nearby comparisons.",'
        '"roles":[{"role":"quantity_bound","target":"points in Z","value":"only need alpha nearby comparisons","confidence":0.9,"reason":"The proposition gives a comparison bound."}]'
        '}]},'
        '{"element_id":"core","propositions":["Gamma alpha points in Z are close."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        min_candidate_score=2.0,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "why gamma alpha nearby")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert "definition" in package.element_ids
    assert "bound" in package.element_ids
    assert any("role span attachment" in decision.reason for decision in package.decisions)


def test_consensus_knn_assembler_makes_distant_same_role_candidates_compete():
    elements = [
        make_element("weak-definition", "Z is a strip.", order=1),
        make_element("filler", "Ordinary transition text.", order=2),
        make_element("strong-definition", "Z is the alpha proof strip.", order=3),
        make_element("core", "Therefore gamma alpha points in Z are close.", order=4),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"weak-definition","propositions":[{'
        '"text":"Z is a strip.",'
        '"roles":[{"role":"definition","target":"Z","value":"a strip","confidence":0.4,"reason":"The proposition defines Z."}]'
        '}]},'
        '{"element_id":"filler","propositions":["Ordinary transition text."]},'
        '{"element_id":"strong-definition","propositions":[{'
        '"text":"Z is the alpha proof strip.",'
        '"roles":[{"role":"definition","target":"Z","value":"the alpha proof strip","confidence":0.95,"reason":"The proposition defines Z."}]'
        '}]},'
        '{"element_id":"core","propositions":["Therefore gamma alpha points in Z are close."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "why gamma alpha")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert "strong-definition" in package.element_ids
    assert "weak-definition" not in package.element_ids
    diagnostics = package.completion_diagnostics
    assert diagnostics is not None
    assert diagnostics.rounds
    traces = [candidate for round_trace in diagnostics.rounds for candidate in round_trace.candidates]
    assert any(
        trace.action == "rejected"
        and "weak-definition" in trace.element_ids
        and trace.rejection_reason.startswith("fills_no_open_need")
        for trace in traces
    )
    assert package.to_dict()["completion_diagnostics"]["rounds"][0]["candidates"]


def test_consensus_knn_assembler_does_not_attach_repeated_filled_role_need():
    elements = [
        make_element("weak-definition", "Z is a strip.", order=1),
        make_element("strong-definition", "Z is the alpha proof strip.", order=2),
        make_element("core", "Therefore gamma alpha points in Z are close.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"weak-definition","propositions":[{'
        '"text":"Z is a strip.",'
        '"roles":[{"role":"definition","target":"Z","value":"a strip","confidence":0.45,"reason":"The proposition defines Z."}]'
        '}]},'
        '{"element_id":"strong-definition","propositions":[{'
        '"text":"Z is the alpha proof strip.",'
        '"roles":[{"role":"definition","target":"Z","value":"the alpha proof strip","confidence":0.95,"reason":"The proposition defines Z."}]'
        '}]},'
        '{"element_id":"core","propositions":["Therefore gamma alpha points in Z are close."]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=0,
        use_role_completion=True,
    ).assemble(make_document(elements), "why gamma alpha")
    package = result.packages[0]

    assert package.core_element_id == "core"
    assert "strong-definition" in package.element_ids
    assert "weak-definition" not in package.element_ids
    diagnostics = package.completion_diagnostics
    assert diagnostics is not None
    assert diagnostics.rounds
    traces = [candidate for round_trace in diagnostics.rounds for candidate in round_trace.candidates]
    assert any(
        trace.action == "rejected"
        and "weak-definition" in trace.element_ids
        and trace.rejection_reason.startswith("fills_no_open_need")
        for trace in traces
    )
    assert "definition:z" in package.to_dict()["completion_diagnostics"]["rounds"][0]["filled_before"]
