from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from contextus.builder import BuilderConfig, DocumentChunker, ElementPreprocessor
from contextus.builder.evidence import EvidenceHandleBuilder
from contextus.builder.evidence_eval import (
    RetrievalEvalItem,
    default_prompt_cases,
    evaluate_retrieval_collections,
    package_retrieval_items,
    render_retrieval_comparison_markdown,
)
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


def main() -> None:
    outdir = Path("chunk_runs") / f"evidence_vs_semantic_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)

    collections: dict[str, dict[str, list[RetrievalEvalItem]]] = {
        "evidence_core": {},
        "evidence_package": {},
        "semantic_walk_step6": {},
    }
    diagnostics: dict[str, object] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": "semantic_walk + heuristic Step 6 repair",
        "documents": {},
    }

    for extraction_path in DEFAULT_EXTRACTIONS:
        if not extraction_path.exists():
            continue
        document = load_document(extraction_path)
        document_key = safe_stem(document.source_name or extraction_path.stem)
        evidence_result = EvidenceHandleBuilder().build(document)
        semantic_items, semantic_summary = semantic_walk_step6_items(document_key, document)

        collections["evidence_package"][document_key] = package_retrieval_items(document_key, evidence_result)
        collections["evidence_core"][document_key] = evidence_core_items(document_key, evidence_result)
        collections["semantic_walk_step6"][document_key] = semantic_items
        diagnostics["documents"][document_key] = {
            "element_count": evidence_result.summary["element_count"],
            "evidence_package_count": len(collections["evidence_package"][document_key]),
            "semantic_walk_step6_count": len(semantic_items),
            "semantic_walk_step6": semantic_summary,
        }

    suite = evaluate_retrieval_collections(collections, default_prompt_cases(), top_k=5)
    diagnostics["collection_stats"] = collection_stats(collections)
    (outdir / "comparison.json").write_text(
        json.dumps(
            {
                "diagnostics": diagnostics,
                **suite.to_dict(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (outdir / "comparison.md").write_text(
        render_diagnostics_markdown(diagnostics) + "\n" + render_retrieval_comparison_markdown(suite),
        encoding="utf-8",
    )
    print(f"Saved evidence-vs-semantic artifacts to: {outdir}")
    print(json.dumps(suite.summary, indent=2))


def load_document(path: Path) -> ExtractedDocument:
    return ExtractionArtifactStore(path.parent).load(path)


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip("-") or "document"


def evidence_core_items(document_key: str, evidence_result) -> list[RetrievalEvalItem]:
    items = []
    for package in evidence_result.packages:
        core_text = "\n".join(segment.text for segment in package.segments if segment.role == "core")
        items.append(
            RetrievalEvalItem(
                collection_id="evidence_core",
                item_id=f"{package.package_id}::core",
                document_key=document_key,
                text=core_text,
                source_element_ids=list(package.core_element_ids),
                metadata={
                    "handle_id": package.handle_id,
                    "source_package_id": package.package_id,
                },
            )
        )
    return items


def semantic_walk_step6_items(
    document_key: str,
    document: ExtractedDocument,
) -> tuple[list[RetrievalEvalItem], dict[str, object]]:
    chunker = DocumentChunker(
        config=BuilderConfig(STEP5_REFINEMENT_STRATEGY="semantic_walk"),
        preprocessor=ElementPreprocessor(),
    )
    groups = chunker.build_repaired_groups(document, allow_llm=False, refinement_strategy="semantic_walk")
    items = []
    for index, group in enumerate(groups):
        text = "\n".join(element.text for element in group.elements if element.text)
        items.append(
            RetrievalEvalItem(
                collection_id="semantic_walk_step6",
                item_id=f"semantic-walk-step6-{index:05d}",
                document_key=document_key,
                text=text,
                source_element_ids=[element.element_id for element in group.elements],
                risk_flags=[],
                metadata={
                    "group_id": group.group_id,
                    "search_strategy": group.search_strategy,
                    "stability": group.stability,
                    "reason_summary": group.reason_summary,
                    "element_count": len(group.elements),
                    "repair_decisions": [
                        {
                            "action": decision.action,
                            "confidence": decision.confidence,
                            "source": decision.source,
                            "affected_element_ids": list(decision.affected_element_ids),
                        }
                        for decision in group.repair_decisions
                    ],
                },
            )
        )
    element_counts = [int(item.metadata.get("element_count", 0)) for item in items]
    summary = {
        "chunk_count": len(items),
        "avg_elements_per_chunk": round(sum(element_counts) / len(element_counts), 2) if element_counts else 0.0,
        "singletons": sum(1 for count in element_counts if count == 1),
        "llm_calls": chunker.llm_calls,
        "repair_actions": [
            {
                "action": decision.action,
                "confidence": decision.confidence,
                "source": decision.source,
                "affected_element_ids": list(decision.affected_element_ids),
            }
            for decision in chunker.repair_decisions
        ],
        "recoverable_errors": list(chunker.recoverable_errors),
    }
    return items, summary


def collection_stats(collections: dict[str, dict[str, list[RetrievalEvalItem]]]) -> dict[str, object]:
    stats: dict[str, object] = {}
    for collection_id, items_by_document in collections.items():
        collection_tokens = []
        by_document: dict[str, object] = {}
        for document_key, items in items_by_document.items():
            token_counts = [len(_tokens(item.text)) for item in items]
            collection_tokens.extend(token_counts)
            by_document[document_key] = _token_stats(token_counts)
        stats[collection_id] = {
            **_token_stats(collection_tokens),
            "documents": by_document,
        }
    return stats


def render_diagnostics_markdown(diagnostics: dict[str, object]) -> str:
    lines = [
        "# Evidence vs Semantic Diagnostics",
        "",
        f"- Baseline: `{diagnostics.get('baseline')}`",
        "",
        "## Collection Sizes",
        "",
    ]
    stats = diagnostics.get("collection_stats", {})
    if isinstance(stats, dict):
        for collection_id, data in stats.items():
            if not isinstance(data, dict):
                continue
            lines.extend(
                [
                    f"### {collection_id}",
                    "",
                    f"- Items: `{data.get('item_count')}`",
                    f"- Avg tokens: `{data.get('avg_tokens')}`",
                    f"- Max tokens: `{data.get('max_tokens')}`",
                    "",
                ]
            )
    documents = diagnostics.get("documents", {})
    if isinstance(documents, dict):
        lines.extend(["## Documents", ""])
        for document_key, data in documents.items():
            if not isinstance(data, dict):
                continue
            lines.extend(
                [
                    f"### {document_key}",
                    "",
                    f"- Elements: `{data.get('element_count')}`",
                    f"- Evidence packages: `{data.get('evidence_package_count')}`",
                    f"- Semantic Step 6 chunks: `{data.get('semantic_walk_step6_count')}`",
                    "",
                ]
            )
    return "\n".join(lines).strip() + "\n"


def _token_stats(token_counts: list[int]) -> dict[str, object]:
    return {
        "item_count": len(token_counts),
        "avg_tokens": round(sum(token_counts) / len(token_counts), 2) if token_counts else 0.0,
        "max_tokens": max(token_counts, default=0),
    }


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)?", text or "")


if __name__ == "__main__":
    main()
