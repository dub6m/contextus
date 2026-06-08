from collections import Counter

import numpy as np

from contextus.builder.query_assembly import (
    ConsensusKnnPropositionEvidenceAssembler,
    PropositionQueryTimeEvidenceAssembler,
    QueryAssemblyResult,
    QueryEvidenceProposition,
    QueryTimeEvidenceAssembler,
)
from contextus.builder.dependency_resolver import FactFrame, ResolvedPackage, SourceRef
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


def division_embed(texts: list[str]) -> np.ndarray:
    vectors = []
    for text in texts:
        lowered = text.lower()
        vectors.append(
            [
                lowered.count("alpha"),
                lowered.count("mitosis"),
                lowered.count("meiosis"),
                lowered.count("somatic"),
                lowered.count("haploid"),
                lowered.count("punnett"),
            ]
        )
    return np.asarray(vectors, dtype=float)


def relation_delta_embed(texts: list[str]) -> np.ndarray:
    vectors = []
    for text in texts:
        lowered = text.lower()
        if "heading" in lowered:
            vectors.append([1.0, 0.0, 0.0, 0.0])
        elif "body" in lowered:
            vectors.append([1.0, 1.0, 0.0, 0.0])
        elif "other" in lowered:
            vectors.append([0.0, 0.0, 1.0, 0.0])
        else:
            vectors.append([0.0, 0.0, 0.0, 1.0])
    return np.asarray(vectors, dtype=float)


def proposition_for(index: int, element: ExtractedElement) -> QueryEvidenceProposition:
    return QueryEvidenceProposition(
        proposition_id=f"{element.id}::p00",
        element_id=element.id,
        element_index=index,
        text=str(element.content),
    )


def test_query_assembly_result_serializes_dependency_packages():
    result = QueryAssemblyResult(
        prompt="alpha question",
        packages=[],
        dependency_packages=[
            ResolvedPackage(
                core_frames=[
                    FactFrame(
                        frame_id="frame:core",
                        source=SourceRef(element_id="core", proposition_id="core::p00"),
                        predicate="claim",
                    )
                ],
                selected_frames=[],
                selected_elements=[],
                resolved_needs=[],
                unresolved_needs=[],
            )
        ],
    )

    payload = result.to_dict()

    assert payload["dependency_packages"][0]["core_frames"][0]["frame_id"] == "frame:core"


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

    assert package.seed_core_element_id == "core"
    assert package.element_ids == ["core"]


def test_document_relation_geometry_scores_repeated_local_delta_family():
    elements = [
        make_element("h1", "heading one", order=1, element_type="title"),
        make_element("b1", "body one", order=2),
        make_element("h2", "heading two", order=3, element_type="title"),
        make_element("b2", "body two", order=4),
        make_element("other", "other topic", order=5),
    ]
    assembler = ConsensusKnnPropositionEvidenceAssembler(
        embed_texts=relation_delta_embed,
        min_relation_family_size=2,
        relation_family_similarity=0.95,
    )
    signals = [signal for signal in assembler._signal_builder.build(make_document(elements)).signals if signal.text.strip()]
    propositions = [proposition_for(index, element) for index, element in enumerate(elements)]
    embeddings = assembler._embed([proposition.text for proposition in propositions])
    geometry = assembler._document_relation_geometry(
        signals=signals,
        propositions=propositions,
        proposition_embeddings=embeddings,
        graph={},
    )

    assert geometry.score(0, 1) > 0.6
    assert geometry.score(0, 4) < 0.2
    assert geometry.best_family(0, 1) is not None


def test_cluster_candidate_score_uses_document_relation_geometry_bonus():
    elements = [
        make_element("h1", "heading one", order=1, element_type="title"),
        make_element("b1", "body one", order=2),
        make_element("h2", "heading two", order=3, element_type="title"),
        make_element("b2", "body two", order=4),
        make_element("other", "other topic", order=5),
    ]
    assembler = ConsensusKnnPropositionEvidenceAssembler(
        embed_texts=relation_delta_embed,
        min_relation_family_size=2,
        relation_family_similarity=0.95,
        relation_geometry_weight=0.2,
    )
    signals = [signal for signal in assembler._signal_builder.build(make_document(elements)).signals if signal.text.strip()]
    propositions = [proposition_for(index, element) for index, element in enumerate(elements)]
    embeddings = assembler._embed([proposition.text for proposition in propositions])
    geometry = assembler._document_relation_geometry(
        signals=signals,
        propositions=propositions,
        proposition_embeddings=embeddings,
        graph={},
    )

    related = assembler._cluster_candidate_score(
        signals=signals,
        proposition=propositions[1],
        core_prop_index=0,
        prop_index=1,
        prompt_similarity=0.2,
        core_similarity=0.2,
        language_score=0.0,
        edge=None,
        prompt_wants_support=False,
        relation_geometry=geometry,
    )
    unrelated = assembler._cluster_candidate_score(
        signals=signals,
        proposition=propositions[4],
        core_prop_index=0,
        prop_index=4,
        prompt_similarity=0.2,
        core_similarity=0.2,
        language_score=0.0,
        edge=None,
        prompt_wants_support=False,
        relation_geometry=geometry,
    )

    assert related > unrelated


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

    assert package.seed_core_element_id == "core"
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


def test_consensus_knn_assembler_uses_dependency_resolver_selected_role_target_as_anchor():
    elements = [
        make_element("core", "Alpha proof claim.", order=1),
        make_element("support", "Candidate points are bounded.", order=2),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"core","propositions":[{"text":"Alpha proof claim.",'
        '"roles":[{"role":"proof_reason","target":"alpha proof claim","value":"candidate points","confidence":0.9,"reason":"The proof depends on candidate points."}]}]},'
        '{"element_id":"support","propositions":[{"text":"Candidate points are bounded.",'
        '"roles":[{"role":"quantity_bound","target":"candidate points","value":"constant bound","confidence":0.9,"reason":"Bounds candidate points."}]}]}'
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
        use_dependency_resolver=True,
    ).assemble(make_document(elements), "alpha proof")

    assert result.dependency_packages
    assert result.dependency_packages[0].selected_elements == ("support",)
    assert result.packages[0].element_ids == ["core", "support"]


def test_consensus_knn_dependency_resolver_does_not_attach_repeated_role_target():
    elements = [
        make_element("core", "Mitosis and Meiosis", order=1),
        make_element("repeat", "Mitosis and Meiosis", order=2),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"core","propositions":[{"text":"Mitosis and Meiosis",'
        '"roles":[{"role":"heading","target":"mitosis and meiosis","value":"section title","confidence":0.9,"reason":"Heading."}]}]},'
        '{"element_id":"repeat","propositions":[{"text":"Mitosis and Meiosis",'
        '"roles":[{"role":"heading","target":"mitosis and meiosis","value":"repeated section title","confidence":0.9,"reason":"Repeated heading."}]}]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=division_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        use_dependency_resolver=True,
    ).assemble(make_document(elements), "mitosis meiosis")

    assert result.dependency_packages
    assert result.dependency_packages[0].selected_elements == ()


def test_consensus_knn_dependency_resolver_uses_document_native_terms_without_roles():
    elements = [
        make_element("core", "Alpha claim depends on candidate points.", order=1),
        make_element("support", "Candidate points have a constant bound.", order=2),
    ]

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=None,
        embed_texts=keyword_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        use_dependency_resolver=True,
    ).assemble(make_document(elements), "alpha claim")

    assert result.dependency_packages
    assert result.dependency_packages[0].selected_elements == ("support",)
    assert result.packages[0].element_ids == ["core", "support"]


def test_consensus_knn_dependency_resolver_rejects_repeated_document_native_label():
    elements = [
        make_element("core", "Mitosis and Meiosis", order=1),
        make_element("repeat", "Mitosis and Meiosis", order=2),
    ]

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=None,
        embed_texts=division_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        use_dependency_resolver=True,
    ).assemble(make_document(elements), "mitosis meiosis")

    assert result.dependency_packages
    assert result.dependency_packages[0].selected_elements == ()


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


def test_consensus_knn_assembler_returns_answer_bundle_with_one_package_per_sub_need():
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

    assert result.answer_bundle is not None
    assert [part.sub_need for part in result.answer_bundle.parts] == [
        "define the strip",
        "explain bounded nearby proof",
    ]
    assert result.answer_bundle.parts[0].package.seed_core_element_id == "setup"
    assert result.answer_bundle.parts[1].package.seed_core_element_id == "proof"
    assert result.answer_bundle.parts[0].package.package_id == "query-bundle-package-00000"
    assert result.answer_bundle.parts[1].package.package_id == "query-bundle-package-00001"


def test_consensus_knn_assembler_reports_source_traversal_audit():
    elements = [
        make_element("setup", "Alpha setup defines line L for the proof.", order=1),
        make_element("reason", "Because alpha points near line L are compared.", order=2),
        make_element("filler", "banana filler", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"setup","propositions":[{"text":"Alpha setup defines line L for the proof.",'
        '"roles":[{"role":"definition","target":"line L","value":"proof line","confidence":0.9,"reason":"Defines line L."}]}]},'
        '{"element_id":"reason","propositions":[{"text":"Because alpha points near line L are compared.",'
        '"roles":[{"role":"proof_reason","target":"comparison","value":"near line L","confidence":0.9,"reason":"Explains the proof comparison."}]}]},'
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
        max_attached_spans=0,
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "alpha setup proof")

    assert result.source_traversals
    trace = result.source_traversals[0]
    assert trace.anchor_element_id == "setup"
    assert "reason" in trace.accepted_element_ids
    accepted_candidates = [candidate for candidate in trace.candidates if candidate.action == "accepted"]
    assert any(candidate.element_id == "reason" for candidate in accepted_candidates)
    assert any("adjacent_next" in candidate.relation_tags for candidate in accepted_candidates)


def test_source_traversal_uses_bridge_without_adding_it_as_evidence():
    elements = [
        make_element("setup", "Alpha setup defines line L for the proof.", order=1),
        make_element("bridge", "and the of", order=2),
        make_element("reason", "Because alpha line L comparison completes the proof.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"setup","propositions":[{"text":"Alpha setup defines line L for the proof.",'
        '"roles":[{"role":"definition","target":"line L","value":"proof line","confidence":0.9,"reason":"Defines line L."}]}]},'
        '{"element_id":"bridge","propositions":["and the of"]},'
        '{"element_id":"reason","propositions":[{"text":"Because alpha line L comparison completes the proof.",'
        '"roles":[{"role":"proof_reason","target":"comparison","value":"line L comparison","confidence":0.9,"reason":"Explains the comparison."}]}]}'
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
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "alpha setup proof")

    trace = result.source_traversals[0]
    assert "reason" in trace.accepted_element_ids
    assert "bridge" not in trace.accepted_element_ids
    assert any(candidate.element_id == "bridge" and candidate.action == "bridge" for candidate in trace.candidates)


def test_source_traversal_rejects_redundant_successor_after_path_is_sufficient():
    elements = [
        make_element("setup", "Alpha setup defines line L for the proof.", order=1),
        make_element("reason", "Because alpha line L comparison completes the proof.", order=2),
        make_element("repeat", "Because alpha line L comparison completes the proof.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"setup","propositions":[{"text":"Alpha setup defines line L for the proof.",'
        '"roles":[{"role":"definition","target":"line L","value":"proof line","confidence":0.9,"reason":"Defines line L."}]}]},'
        '{"element_id":"reason","propositions":[{"text":"Because alpha line L comparison completes the proof.",'
        '"roles":[{"role":"proof_reason","target":"comparison","value":"line L comparison","confidence":0.9,"reason":"Explains the comparison."}]}]},'
        '{"element_id":"repeat","propositions":[{"text":"Because alpha line L comparison completes the proof.",'
        '"roles":[{"role":"proof_reason","target":"comparison","value":"line L comparison","confidence":0.9,"reason":"Repeats the comparison."}]}]}'
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
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "alpha setup proof")

    trace = result.source_traversals[0]
    assert "reason" in trace.accepted_element_ids
    rejected = [candidate for candidate in trace.candidates if candidate.element_id == "repeat"]
    assert rejected
    assert all(candidate.action == "rejected" for candidate in rejected)


def test_source_traversal_rejects_adjacent_wrong_topic_instead_of_bridging():
    elements = [
        make_element("setup", "Alpha setup defines line L for the proof.", order=1),
        make_element("wrong", "Delta meiosis table explains inheritance.", order=2),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"setup","propositions":[{"text":"Alpha setup defines line L for the proof.",'
        '"roles":[{"role":"definition","target":"line L","value":"proof line","confidence":0.9,"reason":"Defines line L."}]}]},'
        '{"element_id":"wrong","propositions":[{"text":"Delta meiosis table explains inheritance.",'
        '"roles":[{"role":"proof_reason","target":"inheritance","value":"meiosis table","confidence":0.9,"reason":"Explains another topic."}]}]}'
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
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "alpha setup proof")

    trace = result.source_traversals[0]
    assert "wrong" not in trace.accepted_element_ids
    wrong_candidates = [candidate for candidate in trace.candidates if candidate.element_id == "wrong"]
    assert wrong_candidates
    assert all(candidate.action == "rejected" for candidate in wrong_candidates)


def test_source_traversal_rejects_support_candidate_that_shares_only_prompt_word():
    elements = [
        make_element("anchor", "Alpha meiosis produces four haploid cells.", order=1),
        make_element("good", "Meiosis produces haploid outcome after chromosome division.", order=2),
        make_element("wrong-figure", "Figure: Alpha shows a Punnett square with brown eye rows.", order=3, element_type="figure"),
        make_element("filler", "banana filler", order=4),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"anchor","propositions":[{"text":"Alpha meiosis produces four haploid cells.",'
        '"roles":[{"role":"visual_support","target":"meiosis","value":"four haploid cells","confidence":0.9,"reason":"Names the figure claim."}]}]},'
        '{"element_id":"good","propositions":[{"text":"Meiosis produces haploid outcome after chromosome division.",'
        '"roles":[{"role":"proof_reason","target":"haploid outcome","value":"chromosome division","confidence":0.9,"reason":"Explains the same claim."}]}]},'
        '{"element_id":"wrong-figure","propositions":[{"text":"Figure: Alpha shows a Punnett square with brown eye rows.",'
        '"roles":[{"role":"visual_support","target":"Punnett square","value":"brown eye rows","confidence":0.9,"reason":"Different figure."}]}]},'
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
        max_attached_spans=0,
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "What does the alpha figure show?")

    trace = result.source_traversals[0]
    assert "good" in trace.accepted_element_ids
    assert "wrong-figure" not in trace.accepted_element_ids
    wrong_candidates = [candidate for candidate in trace.candidates if candidate.element_id == "wrong-figure"]
    assert wrong_candidates
    assert all(candidate.action == "rejected" for candidate in wrong_candidates)


def test_source_traversal_rejects_non_support_candidate_with_foreign_claim_units():
    elements = [
        make_element("anchor", "Alpha meiosis produces four haploid cells.", order=1),
        make_element("wrong-text", "Alpha mitosis replicates somatic cells.", order=2),
        make_element("filler-1", "banana filler one", order=3),
        make_element("filler-2", "banana filler two", order=4),
        make_element("filler-3", "banana filler three", order=5),
        make_element("filler-4", "banana filler four", order=6),
        make_element("filler-5", "banana filler five", order=7),
        make_element("filler-6", "banana filler six", order=8),
        make_element("filler-7", "banana filler seven", order=9),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"anchor","propositions":[{"text":"Alpha meiosis produces four haploid cells.",'
        '"roles":[{"role":"visual_support","target":"meiosis","value":"four haploid cells","confidence":0.9,"reason":"Names the path claim."}]}]},'
        '{"element_id":"wrong-text","propositions":[{"text":"Alpha mitosis replicates somatic cells.",'
        '"roles":[{"role":"proof_reason","target":"mitosis","value":"somatic cell replication","confidence":0.9,"reason":"Nearby but different claim."}]}]},'
        '{"element_id":"filler-1","propositions":["Banana filler one."]},'
        '{"element_id":"filler-2","propositions":["Banana filler two."]},'
        '{"element_id":"filler-3","propositions":["Banana filler three."]},'
        '{"element_id":"filler-4","propositions":["Banana filler four."]},'
        '{"element_id":"filler-5","propositions":["Banana filler five."]},'
        '{"element_id":"filler-6","propositions":["Banana filler six."]},'
        '{"element_id":"filler-7","propositions":["Banana filler seven."]}'
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
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "alpha meiosis haploid cells")

    trace = result.source_traversals[0]
    assert "wrong-text" not in trace.accepted_element_ids
    wrong_candidates = [candidate for candidate in trace.candidates if candidate.element_id == "wrong-text"]
    assert wrong_candidates
    assert all(candidate.action == "rejected" for candidate in wrong_candidates)
    assert any("different claim path" in candidate.reason for candidate in wrong_candidates)


def test_source_traversal_accepts_symbolic_list_frame_continuation():
    elements = [
        make_element("intro", "Alpha procedure creates local Q objects.", order=1),
        make_element("item-qx", "1. Alpha Qx is sorted by x coordinate.", order=2),
        make_element("item-qy", "2. Alpha Qy is sorted by y coordinate.", order=3),
        make_element("wrong-text", "Alpha mitosis replicates somatic cells.", order=4),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"intro","propositions":[{"text":"Alpha procedure creates local Q objects.",'
        '"roles":[{"role":"procedure","target":"Q objects","value":"creates local objects","confidence":0.9,"reason":"Procedure setup."}]}]},'
        '{"element_id":"item-qx","propositions":[{"text":"Alpha Qx is sorted by x coordinate.",'
        '"roles":[{"role":"procedure","target":"Qx","value":"sorted by x coordinate","confidence":0.9,"reason":"List item."}]}]},'
        '{"element_id":"item-qy","propositions":[{"text":"Alpha Qy is sorted by y coordinate.",'
        '"roles":[{"role":"procedure","target":"Qy","value":"sorted by y coordinate","confidence":0.9,"reason":"List item."}]}]},'
        '{"element_id":"wrong-text","propositions":[{"text":"Alpha mitosis replicates somatic cells.",'
        '"roles":[{"role":"proof_reason","target":"mitosis","value":"somatic cell replication","confidence":0.9,"reason":"Different claim."}]}]}'
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
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "alpha procedure creates q objects")

    trace = result.source_traversals[0]
    assert "item-qy" in trace.accepted_element_ids
    frame_candidates = [candidate for candidate in trace.candidates if candidate.element_id == "item-qy"]
    assert frame_candidates
    assert any(candidate.frame_continuation == "list_frame_continuation" for candidate in frame_candidates)
    assert "wrong-text" not in trace.accepted_element_ids


def test_source_traversal_starts_second_center_for_source_backed_prompt_aspect():
    elements = [
        make_element("mitosis", "Alpha mitosis explains somatic cell division.", order=1),
        make_element("meiosis", "Alpha meiosis produces haploid reproductive cells.", order=2),
        make_element("wrong", "Alpha Punnett square tracks eye color rows.", order=3),
    ]
    llm = PropositionLLM(
        '{"elements":['
        '{"element_id":"mitosis","propositions":[{"text":"Alpha mitosis explains somatic cell division.",'
        '"roles":[{"role":"comparison","target":"mitosis","value":"somatic cell division","confidence":0.9,"reason":"One comparison side."}]}]},'
        '{"element_id":"meiosis","propositions":[{"text":"Alpha meiosis produces haploid reproductive cells.",'
        '"roles":[{"role":"comparison","target":"meiosis","value":"haploid reproductive cells","confidence":0.9,"reason":"Second comparison side."}]}]},'
        '{"element_id":"wrong","propositions":[{"text":"Alpha Punnett square tracks eye color rows.",'
        '"roles":[{"role":"comparison","target":"Punnett square","value":"eye color rows","confidence":0.9,"reason":"Different comparison topic."}]}]}'
        ']}'
    )

    result = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm,
        embed_texts=division_embed,
        top_k_cores=1,
        max_side_elements=0,
        k_values=(1,),
        min_neighbor_stability=1.0,
        min_edge_similarity=0.9,
        max_attached_spans=0,
        source_traversal_rounds=2,
    ).assemble(make_document(elements), "compare alpha mitosis somatic and meiosis haploid")

    trace = result.source_traversals[0]
    assert {"mitosis", "meiosis"} <= set(trace.accepted_element_ids)
    assert len(trace.centers) >= 2
    assert any(candidate.element_id == "meiosis" and candidate.center_decision == "new_center" for candidate in trace.candidates)
    assert "wrong" not in trace.accepted_element_ids
    traversal_package_element_sets = [set(package.element_ids) for package in result.source_traversal_packages]
    assert any({"mitosis"} <= element_ids for element_ids in traversal_package_element_sets)
    assert any({"meiosis"} <= element_ids for element_ids in traversal_package_element_sets)
    assert result.source_traversal_answer_bundle is not None
    bundle_part_element_sets = [
        set(part.evidence_element_ids)
        for part in result.source_traversal_answer_bundle.parts
    ]
    assert any({"mitosis"} <= element_ids for element_ids in bundle_part_element_sets)
    assert any({"meiosis"} <= element_ids for element_ids in bundle_part_element_sets)


def test_source_traversal_claim_alignment_blocks_different_support_object():
    assembler = ConsensusKnnPropositionEvidenceAssembler(embed_texts=keyword_embed)
    path_signature = assembler._source_traversal_claim_units("Alpha meiosis produces four haploid cells.")
    candidate_units = assembler._source_traversal_claim_units("Figure: Alpha shows a Punnett square with brown eye rows.")
    prompt_units = assembler._source_traversal_claim_units("What does the alpha figure show?")
    document_texts = [
        "Alpha meiosis produces four haploid cells.",
        "Meiosis produces haploid outcome after chromosome division.",
        "Figure: Alpha shows a Punnett square with brown eye rows.",
        "banana filler",
    ]
    document_unit_counts = Counter()
    document_claim_unit_counts = Counter()
    for text in document_texts:
        document_unit_counts.update(assembler._source_traversal_units(text))
        document_claim_unit_counts.update(assembler._source_traversal_claim_units(text))

    alignment = assembler._source_traversal_claim_alignment(
        candidate_claim_units=candidate_units,
        path_signature=path_signature,
        path_signature_tokens=assembler._source_traversal_claim_tokens(path_signature),
        prompt_claim_tokens=assembler._source_traversal_claim_tokens(prompt_units),
        relation_tags={"adjacent_next"},
        candidate_support_like=True,
        document_unit_counts=document_unit_counts,
        document_claim_unit_counts=document_claim_unit_counts,
        document_size=len(document_texts),
    )

    assert not alignment["ok"]
    assert "different claim path" in str(alignment["reason"])


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

    assert package.seed_core_element_id == "core"
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

    assert package.seed_core_element_id == "core"
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

    assert package.seed_core_element_id == "core"
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

    assert package.seed_core_element_id == "core"
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

    assert package.seed_core_element_id == "core"
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
