from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from contextus.builder import BuilderConfig, DocumentChunker, ElementPreprocessor
from contextus.builder.evidence import EvidenceHandleBuilder
from contextus.builder.evidence_eval import (
    RetrievalCollectionEvaluation,
    RetrievalComparisonSuiteResult,
    RetrievalEvalItem,
    default_prompt_cases,
    evaluate_retrieval_collection,
    package_retrieval_items,
    render_retrieval_comparison_markdown,
)
from contextus.builder.query_assembly import QueryAssembledPackage, QueryTimeEvidenceAssembler
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


def main() -> None:
    outdir = Path("chunk_runs") / f"query_assembly_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)
    documents = {
        safe_stem(document.source_name or path.stem): document
        for path in DEFAULT_EXTRACTIONS
        if path.exists()
        for document in [load_document(path)]
    }
    static_collections = build_static_collections(documents)
    assembler = QueryTimeEvidenceAssembler(top_k_cores=5)

    evaluations: list[RetrievalCollectionEvaluation] = []
    query_traces: dict[str, object] = {}
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
                collection_id="query_assembled",
                top_k=5,
            )
        )
        for collection_id, items_by_document in static_collections.items():
            evaluations.append(
                evaluate_retrieval_collection(
                    items_by_document.get(case.document_key, []),
                    case,
                    collection_id=collection_id,
                    top_k=5,
                )
            )

    suite = RetrievalComparisonSuiteResult(evaluations=evaluations)
    diagnostics = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "query_assembler": {
            "top_k_cores": 5,
            "lookahead_after_mark": assembler.lookahead_after_mark,
            "major_query_drop": assembler.major_query_drop,
            "major_core_shift": assembler.major_core_shift,
            "recovery_slack": assembler.recovery_slack,
            "max_side_elements": assembler.max_side_elements,
            "max_package_tokens": assembler.max_package_tokens,
            "stagnant_addition_limit": assembler.stagnant_addition_limit,
        },
    }
    (outdir / "query_assembly.json").write_text(
        json.dumps(
            {
                "diagnostics": diagnostics,
                "summary": suite.summary,
                "evaluations": [evaluation_to_dict(item) for item in evaluations],
                "query_traces": query_traces,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (outdir / "query_assembly.md").write_text(render_retrieval_comparison_markdown(suite), encoding="utf-8")
    print(f"Saved query assembly artifacts to: {outdir}")
    print(json.dumps(suite.summary, indent=2))


def load_document(path: Path) -> ExtractedDocument:
    return ExtractionArtifactStore(path.parent).load(path)


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip("-") or "document"


def build_static_collections(
    documents: dict[str, ExtractedDocument],
) -> dict[str, dict[str, list[RetrievalEvalItem]]]:
    evidence_builder = EvidenceHandleBuilder()
    return {
        "evidence_package": {
            document_key: package_retrieval_items(document_key, evidence_builder.build(document))
            for document_key, document in documents.items()
        },
        "semantic_walk_step6": {
            document_key: semantic_walk_step6_items(document_key, document)
            for document_key, document in documents.items()
        },
    }


def query_package_items(
    document_key: str,
    packages: list[QueryAssembledPackage],
) -> list[RetrievalEvalItem]:
    return [
        RetrievalEvalItem(
            collection_id="query_assembled",
            item_id=package.package_id,
            document_key=document_key,
            text=package.package_text,
            source_element_ids=[package.core_element_id],
            context_element_ids=[element_id for element_id in package.element_ids if element_id != package.core_element_id],
            attachment_types=["query_embedding_expansion"],
            risk_flags=[],
            metadata={
                "score": package.score,
                "core_prompt_similarity": package.core_prompt_similarity,
                "package_prompt_similarity": package.package_prompt_similarity,
                "package_core_similarity": package.package_core_similarity,
                "token_count": package.token_count,
            },
        )
        for package in packages
    ]


def semantic_walk_step6_items(document_key: str, document: ExtractedDocument) -> list[RetrievalEvalItem]:
    chunker = DocumentChunker(
        config=BuilderConfig(STEP5_REFINEMENT_STRATEGY="semantic_walk"),
        preprocessor=ElementPreprocessor(),
    )
    groups = chunker.build_repaired_groups(document, allow_llm=False, refinement_strategy="semantic_walk")
    items = []
    for index, group in enumerate(groups):
        items.append(
            RetrievalEvalItem(
                collection_id="semantic_walk_step6",
                item_id=f"semantic-walk-step6-{index:05d}",
                document_key=document_key,
                text="\n".join(element.text for element in group.elements if element.text),
                source_element_ids=[element.element_id for element in group.elements],
                metadata={
                    "group_id": group.group_id,
                    "element_count": len(group.elements),
                    "stability": group.stability,
                    "search_strategy": group.search_strategy,
                },
            )
        )
    return items


def evaluation_to_dict(evaluation: RetrievalCollectionEvaluation) -> dict[str, object]:
    return {
        "case": evaluation.case.__dict__,
        "collection_id": evaluation.collection_id,
        "hit_at_1": evaluation.hit_at_1,
        "hit_at_3": evaluation.hit_at_3,
        "best_hit_rank": evaluation.best_hit_rank,
        "top": [hit.__dict__ for hit in evaluation.top],
    }


if __name__ == "__main__":
    main()
