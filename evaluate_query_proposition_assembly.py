from __future__ import annotations

from datetime import datetime
from dataclasses import asdict
from pathlib import Path
import json
import os
import re

from dotenv import load_dotenv

from contextus.builder import (
    ConsensusKnnPropositionEvidenceAssembler,
    PropositionQueryTimeEvidenceAssembler,
    QueryAssembledPackage,
    RetrievalCollectionEvaluation,
    RetrievalComparisonSuiteResult,
    RetrievalEvalItem,
    default_prompt_cases,
    evaluate_retrieval_collection,
    render_retrieval_comparison_markdown,
)
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore
from contextus.llm import CerebrasClient, LLMClient, OpenAIResponsesClient


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


def main() -> None:
    load_dotenv(override=True)
    outdir = Path("chunk_runs") / f"query_proposition_assembly_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)
    documents = {
        safe_stem(document.source_name or path.stem): document
        for path in DEFAULT_EXTRACTIONS
        if path.exists()
        for document in [load_document(path)]
    }
    llm_client = make_llm_client()
    assembler_kind = os.environ.get("QUERY_PROPOSITION_ASSEMBLER", "linear").strip().lower()
    assembler_cls = (
        ConsensusKnnPropositionEvidenceAssembler
        if assembler_kind in {"cluster", "consensus", "knn"}
        else PropositionQueryTimeEvidenceAssembler
    )
    use_language_map = os.environ.get("QUERY_LANGUAGE_MAP", "").strip().lower() in {"1", "true", "yes", "on"}
    use_span_competition = os.environ.get("QUERY_SPAN_COMPETITION", "").strip().lower() in {"1", "true", "yes", "on"}
    use_query_planner = os.environ.get("QUERY_RETRIEVAL_PLAN", "").strip().lower() in {"1", "true", "yes", "on"}
    use_role_completion = os.environ.get("QUERY_ROLE_COMPLETION", "").strip().lower() in {"1", "true", "yes", "on"}
    query_planner_bridge_slots = int(os.environ.get("QUERY_RETRIEVAL_PLAN_BRIDGE_SLOTS", "1"))
    assembler = assembler_cls(
        llm_client=llm_client,
        top_k_cores=5,
        proposition_batch_size=int(os.environ.get("QUERY_PROPOSITION_BATCH_SIZE", "6")),
        **(
            {
                "use_language_map": use_language_map,
                "use_span_competition": use_span_competition,
                "use_query_planner": use_query_planner,
                "use_role_completion": use_role_completion,
                "query_planner_bridge_slots": query_planner_bridge_slots,
            }
            if assembler_cls is ConsensusKnnPropositionEvidenceAssembler
            else {}
        ),
    )

    evaluations: list[RetrievalCollectionEvaluation] = []
    query_traces: dict[str, object] = {}
    document_propositions: dict[str, object] = {}
    for document_key, document in documents.items():
        bootstrap = assembler.assemble(document, "__bootstrap_propositions__")
        document_propositions[document_key] = [asdict(proposition) for proposition in bootstrap.propositions]

    for case in default_prompt_cases():
        document = documents.get(case.document_key)
        if document is None:
            continue
        query_result = assembler.assemble(document, case.prompt)
        query_traces[case.case_id] = query_result.to_dict()
        evaluations.append(
            evaluate_retrieval_collection(
                query_package_items(case.document_key, query_result.packages),
                case,
                collection_id="query_proposition_assembled",
                top_k=5,
            )
        )

    suite = RetrievalComparisonSuiteResult(evaluations=evaluations)
    diagnostics = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "llm_client": type(llm_client).__name__ if llm_client is not None else None,
        "query_assembler": {
            "kind": type(assembler).__name__,
            "top_k_cores": 5,
            "proposition_batch_size": assembler.proposition_batch_size,
            "lookahead_after_mark": assembler.lookahead_after_mark,
            "major_query_drop": assembler.major_query_drop,
            "major_core_shift": assembler.major_core_shift,
            "recovery_slack": assembler.recovery_slack,
            "max_side_elements": assembler.max_side_elements,
            "max_package_tokens": assembler.max_package_tokens,
            "stagnant_addition_limit": assembler.stagnant_addition_limit,
            "k_values": list(getattr(assembler, "k_values", ())),
            "min_neighbor_stability": getattr(assembler, "min_neighbor_stability", None),
            "min_edge_similarity": getattr(assembler, "min_edge_similarity", None),
            "max_cluster_hops": getattr(assembler, "max_cluster_hops", None),
            "max_cluster_propositions": getattr(assembler, "max_cluster_propositions", None),
            "min_candidate_score": getattr(assembler, "min_candidate_score", None),
            "max_order_gap_for_span": getattr(assembler, "max_order_gap_for_span", None),
            "max_attached_spans": getattr(assembler, "max_attached_spans", None),
            "min_span_attach_score": getattr(assembler, "min_span_attach_score", None),
            "span_expansion_radius": getattr(assembler, "span_expansion_radius", None),
            "min_span_expansion_gain": getattr(assembler, "min_span_expansion_gain", None),
            "span_completeness_slack": getattr(assembler, "span_completeness_slack", None),
            "use_span_competition": getattr(assembler, "use_span_competition", None),
            "use_query_planner": getattr(assembler, "use_query_planner", None),
            "use_role_completion": getattr(assembler, "use_role_completion", None),
            "role_completion_max_attachments": getattr(assembler, "role_completion_max_attachments", None),
            "role_completion_max_extra_tokens": getattr(assembler, "role_completion_max_extra_tokens", None),
            "role_completion_search_radius": getattr(assembler, "role_completion_search_radius", None),
            "query_planner_bridge_slots": getattr(assembler, "query_planner_bridge_slots", None),
            "query_planner_max_map_items": getattr(assembler, "query_planner_max_map_items", None),
            "query_planner_max_search_forms": getattr(assembler, "query_planner_max_search_forms", None),
            "use_language_map": getattr(assembler, "use_language_map", None),
            "language_core_weight": getattr(assembler, "language_core_weight", None),
            "language_candidate_weight": getattr(assembler, "language_candidate_weight", None),
            "language_candidate_slots": getattr(assembler, "language_candidate_slots", None),
            "min_language_core_score": getattr(assembler, "min_language_core_score", None),
        },
        "documents": {
            document_key: {
                "proposition_count": len(propositions),
            }
            for document_key, propositions in document_propositions.items()
        },
    }
    (outdir / "query_proposition_assembly.json").write_text(
        json.dumps(
            {
                "diagnostics": diagnostics,
                "summary": suite.summary,
                "evaluations": [evaluation_to_dict(item) for item in evaluations],
                "document_propositions": document_propositions,
                "query_traces": query_traces,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (outdir / "query_proposition_assembly.md").write_text(
        render_diagnostics_markdown(diagnostics) + "\n" + render_retrieval_comparison_markdown(suite),
        encoding="utf-8",
    )
    (outdir / "completion_diagnostics.md").write_text(
        render_completion_diagnostics_markdown(query_traces),
        encoding="utf-8",
    )
    (outdir / "role_grounding_diagnostics.md").write_text(
        render_role_grounding_diagnostics_markdown(document_propositions),
        encoding="utf-8",
    )
    (outdir / "ranking_diagnostics.md").write_text(
        render_ranking_diagnostics_markdown(query_traces),
        encoding="utf-8",
    )
    print(f"Saved query proposition assembly artifacts to: {outdir}")
    print(json.dumps(suite.summary, indent=2))


def make_llm_client() -> LLMClient | None:
    provider = os.environ.get("QUERY_PROPOSITION_LLM", "cerebras").strip().lower()
    if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
        return OpenAIResponsesClient()
    if provider != "openai" and os.environ.get("CEREBRAS_API_KEY"):
        return CerebrasClient()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIResponsesClient()
    return None


def load_document(path: Path) -> ExtractedDocument:
    return ExtractionArtifactStore(path.parent).load(path)


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip("-") or "document"


def query_package_items(
    document_key: str,
    packages: list[QueryAssembledPackage],
) -> list[RetrievalEvalItem]:
    return [
        RetrievalEvalItem(
            collection_id="query_proposition_assembled",
            item_id=package.package_id,
            document_key=document_key,
            text=package.package_text,
            source_element_ids=[package.core_element_id],
            context_element_ids=[element_id for element_id in package.element_ids if element_id != package.core_element_id],
            attachment_types=[
                "query_cluster_consensus"
                if package.package_id.startswith("query-cluster-package-")
                else "query_proposition_expansion"
            ],
            risk_flags=[],
            metadata={
                "score": package.score,
                "ranking_diagnostics": asdict(package.ranking_diagnostics)
                if package.ranking_diagnostics is not None
                else None,
                "core_prompt_similarity": package.core_prompt_similarity,
                "package_prompt_similarity": package.package_prompt_similarity,
                "package_core_similarity": package.package_core_similarity,
                "token_count": package.token_count,
            },
        )
        for package in packages
    ]


def evaluation_to_dict(evaluation: RetrievalCollectionEvaluation) -> dict[str, object]:
    return {
        "case": evaluation.case.__dict__,
        "collection_id": evaluation.collection_id,
        "hit_at_1": evaluation.hit_at_1,
        "hit_at_3": evaluation.hit_at_3,
        "best_hit_rank": evaluation.best_hit_rank,
        "top": [hit.__dict__ for hit in evaluation.top],
    }


def render_diagnostics_markdown(diagnostics: dict[str, object]) -> str:
    lines = ["# Query Proposition Assembly Diagnostics", ""]
    lines.append(f"- Created at: `{diagnostics['created_at']}`")
    lines.append(f"- LLM client: `{diagnostics['llm_client']}`")
    lines.append("")
    lines.append("## Documents")
    for document_key, summary in diagnostics["documents"].items():  # type: ignore[union-attr]
        lines.append(f"- `{document_key}`: `{summary['proposition_count']}` propositions")
    lines.append("")
    return "\n".join(lines)


def render_completion_diagnostics_markdown(query_traces: dict[str, object]) -> str:
    lines = ["# Completion Diagnostics", ""]
    for case_id, raw_trace in query_traces.items():
        trace = raw_trace if isinstance(raw_trace, dict) else {}
        lines.append(f"## {case_id}")
        lines.append("")
        packages = trace.get("packages", []) if isinstance(trace, dict) else []
        if not isinstance(packages, list) or not packages:
            lines.append("_No packages._")
            lines.append("")
            continue
        for rank, raw_package in enumerate(packages, start=1):
            package = raw_package if isinstance(raw_package, dict) else {}
            diagnostics = package.get("completion_diagnostics") if isinstance(package, dict) else None
            lines.append(
                f"### Package {rank}: `{package.get('package_id', '')}`"
            )
            lines.append("")
            lines.append(f"- Core: `{package.get('core_element_id', '')}`")
            lines.append(f"- Score: `{package.get('score', '')}`")
            lines.append(f"- Tokens: `{package.get('token_count', '')}`")
            if not isinstance(diagnostics, dict):
                lines.append("- Completion diagnostics: none")
                lines.append("")
                continue
            lines.append(f"- Completion enabled: `{diagnostics.get('enabled')}`")
            if diagnostics.get("disabled_reason"):
                lines.append(f"- Disabled reason: `{diagnostics.get('disabled_reason')}`")
            lines.append(f"- Completion needed initially: `{diagnostics.get('completion_needed_initial')}`")
            rounds = diagnostics.get("rounds", [])
            if not isinstance(rounds, list) or not rounds:
                lines.append("- Rounds: none")
                lines.append("")
                continue
            for raw_round in rounds:
                round_trace = raw_round if isinstance(raw_round, dict) else {}
                lines.append("")
                lines.append(f"#### Round {round_trace.get('round_number', '')}")
                lines.append("")
                lines.append(f"- Selected before: `{_join_markdown_list(round_trace.get('selected_before'))}`")
                lines.append(f"- Needed before: `{_join_markdown_list(round_trace.get('needed_before'))}`")
                lines.append(f"- Filled before: `{_join_markdown_list(round_trace.get('filled_before'))}`")
                lines.append(f"- Open before: `{_join_markdown_list(round_trace.get('open_before'))}`")
                lines.append(f"- Attached: `{_join_markdown_list(round_trace.get('attached_element_ids'))}`")
                lines.append(f"- Open after: `{_join_markdown_list(round_trace.get('open_after'))}`")
                candidates = round_trace.get("candidates", [])
                lines.append("")
                lines.append("| Action | Candidate | Score | Useful keys | Why | Preview |")
                lines.append("| --- | --- | ---: | --- | --- | --- |")
                if isinstance(candidates, list):
                    for raw_candidate in candidates:
                        candidate = raw_candidate if isinstance(raw_candidate, dict) else {}
                        action = str(candidate.get("action", ""))
                        reason = str(candidate.get("rejection_reason") or candidate.get("reason") or "")
                        lines.append(
                            "| "
                            + " | ".join(
                                [
                                    _escape_table_cell(action),
                                    "`" + _escape_table_cell(_join_markdown_list(candidate.get("element_ids"))) + "`",
                                    _escape_table_cell(str(candidate.get("score", ""))),
                                    "`" + _escape_table_cell(_join_markdown_list(candidate.get("useful_open_keys"))) + "`",
                                    _escape_table_cell(reason),
                                    _escape_table_cell(str(candidate.get("text_preview", ""))),
                                ]
                            )
                            + " |"
                        )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_ranking_diagnostics_markdown(query_traces: dict[str, object]) -> str:
    lines = ["# Deterministic Ranking Diagnostics", ""]
    lines.append(
        "This report explains the final deterministic package score. The old embedding-style score is kept as `legacy_score` for comparison."
    )
    lines.append("")
    for case_id, raw_trace in query_traces.items():
        trace = raw_trace if isinstance(raw_trace, dict) else {}
        lines.append(f"## {case_id}")
        lines.append("")
        packages = trace.get("packages", []) if isinstance(trace, dict) else []
        if not isinstance(packages, list) or not packages:
            lines.append("_No packages._")
            lines.append("")
            continue
        lines.append(
            "| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |"
        )
        lines.append(
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"
        )
        for rank, raw_package in enumerate(packages, start=1):
            package = raw_package if isinstance(raw_package, dict) else {}
            diagnostics = package.get("ranking_diagnostics") if isinstance(package, dict) else None
            diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rank),
                        "`" + _escape_table_cell(str(package.get("package_id", ""))) + "`",
                        "`" + _escape_table_cell(str(package.get("core_element_id", ""))) + "`",
                        _escape_table_cell(str(diagnostics.get("final_score", package.get("score", "")))),
                        _escape_table_cell(str(diagnostics.get("legacy_score", ""))),
                        _escape_table_cell(str(diagnostics.get("profile_alignment_score", ""))),
                        _escape_table_cell(str(diagnostics.get("directness_score", ""))),
                        _escape_table_cell(str(diagnostics.get("assembly_confidence_score", ""))),
                        _escape_table_cell(str(diagnostics.get("plan_coverage_score", ""))),
                        _escape_table_cell(str(diagnostics.get("role_coverage_score", ""))),
                        _escape_table_cell(str(diagnostics.get("completion_closure_score", ""))),
                        _escape_table_cell(str(diagnostics.get("relevance_score", ""))),
                        _escape_table_cell(str(diagnostics.get("source_coherence_score", ""))),
                        _escape_table_cell(_join_markdown_list(diagnostics.get("positive_reasons"))),
                        _escape_table_cell(_join_markdown_list(diagnostics.get("negative_reasons"))),
                    ]
                )
                + " |"
            )
        lines.append("")
        for rank, raw_package in enumerate(packages, start=1):
            package = raw_package if isinstance(raw_package, dict) else {}
            diagnostics = package.get("ranking_diagnostics") if isinstance(package, dict) else None
            if not isinstance(diagnostics, dict):
                continue
            lines.append(f"### Package {rank}: `{package.get('package_id', '')}`")
            lines.append("")
            lines.append(f"- Roles seen: `{_join_markdown_list(diagnostics.get('package_roles'))}`")
            lines.append(f"- Expected roles: `{_join_markdown_list(diagnostics.get('expected_roles'))}`")
            lines.append(f"- Covered sub-needs: `{_join_markdown_list(diagnostics.get('covered_sub_needs'))}`")
            lines.append(f"- Missing sub-needs: `{_join_markdown_list(diagnostics.get('missing_sub_needs'))}`")
            lines.append(f"- Open completion keys: `{_join_markdown_list(diagnostics.get('open_completion_keys'))}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_role_grounding_diagnostics_markdown(document_propositions: dict[str, object]) -> str:
    lines = ["# Role Grounding Diagnostics", ""]
    lines.append(
        "Audit-only report. These labels do not change proposition selection, completion, or ranking."
    )
    lines.append("")
    grouped: dict[str, list[tuple[str, dict[str, object]]]] = {
        "support_mismatch": [],
        "ungrounded": [],
        "vague_target": [],
        "weak": [],
        "grounded": [],
    }
    for document_key, raw_props in document_propositions.items():
        props = raw_props if isinstance(raw_props, list) else []
        for raw_prop in props:
            proposition = raw_prop if isinstance(raw_prop, dict) else {}
            grounding = proposition.get("grounding")
            if not isinstance(grounding, dict):
                continue
            severity = str(grounding.get("severity") or "weak")
            grouped.setdefault(severity, []).append((document_key, proposition))

    for severity in ("support_mismatch", "ungrounded", "vague_target", "weak", "grounded"):
        items = grouped.get(severity, [])
        lines.append(f"## {severity}")
        lines.append("")
        lines.append(f"- Count: `{len(items)}`")
        lines.append("")
        for document_key, proposition in items[:80]:
            grounding = proposition.get("grounding") if isinstance(proposition.get("grounding"), dict) else {}
            lines.append(f"### `{proposition.get('proposition_id', '')}`")
            lines.append("")
            lines.append(f"- Document: `{document_key}`")
            lines.append(f"- Element: `{proposition.get('element_id', '')}`")
            lines.append(f"- Proposition: {str(proposition.get('text', ''))}")
            lines.append(f"- Source overlap: `{grounding.get('source_overlap_ratio', '')}`")
            lines.append(f"- Kept terms: `{_join_markdown_list(grounding.get('kept_terms'))}`")
            lines.append(f"- Novel terms: `{_join_markdown_list(grounding.get('novel_terms'))}`")
            role_diags = grounding.get("role_diagnostics", [])
            if isinstance(role_diags, list) and role_diags:
                lines.append("")
                lines.append("| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |")
                lines.append("| --- | --- | --- | --- | ---: | ---: | --- | --- |")
                for raw_role in role_diags:
                    role = raw_role if isinstance(raw_role, dict) else {}
                    target_source = f"P={role.get('target_in_proposition')} S={role.get('target_in_source')}"
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _escape_table_cell(str(role.get("role", ""))),
                                _escape_table_cell(str(role.get("target", ""))),
                                _escape_table_cell(str(role.get("status", ""))),
                                _escape_table_cell(target_source),
                                _escape_table_cell(str(role.get("target_token_overlap", ""))),
                                _escape_table_cell(str(role.get("role_symbol_overlap", ""))),
                                _escape_table_cell(str(role.get("behavior_match", ""))),
                                _escape_table_cell(_join_markdown_list(role.get("notes"))),
                            ]
                        )
                        + " |"
                    )
            lines.append("")
        if len(items) > 80:
            lines.append(f"_Omitted {len(items) - 80} additional `{severity}` propositions._")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _join_markdown_list(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def _escape_table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip()


if __name__ == "__main__":
    main()
