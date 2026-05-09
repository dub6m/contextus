from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable
import argparse
import json
import re
import time

from dotenv import load_dotenv

from contextus.builder import BuilderConfig
from contextus.builder.chunker import DocumentChunker, RefinedChunkGroup, _RepairGroupState
from contextus.builder.preprocessor import ElementPreprocessor
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore
from contextus.llm import CerebrasClient, LLMClient


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Compare Step 5 chunking strategies and save inspectable artifacts.")
    parser.add_argument(
        "--extraction",
        "-e",
        action="append",
        type=Path,
        help="Extraction artifact to compare. Can be passed more than once. Defaults to closest-pair and inheritance.",
    )
    parser.add_argument(
        "--strategy",
        "-s",
        action="append",
        choices=["block", "semantic_walk", "level4", "semantic"],
        help="Strategy to compare. Defaults to block and level4.",
    )
    parser.add_argument("--outdir", "-o", type=Path, help="Output directory under chunk_runs.")
    parser.add_argument("--skip-step6-llm", action="store_true", help="Run only heuristic Step 6 repair.")
    args = parser.parse_args()

    extraction_paths = args.extraction or DEFAULT_EXTRACTIONS
    strategies = args.strategy or ["block", "level4"]
    outdir = args.outdir or Path("chunk_runs") / f"block_vs_level4_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)

    llm = CerebrasClient()
    summary: dict[str, object] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "strategies": strategies,
        "step6_llm": not args.skip_step6_llm,
        "documents": {},
    }

    for extraction_path in extraction_paths:
        document = load_document(extraction_path)
        doc_key = safe_stem(document.source_name or extraction_path.stem)
        summary["documents"][doc_key] = {}
        print(f"Loaded {doc_key} from {extraction_path}", flush=True)
        for strategy in strategies:
            normalized_strategy = normalize_strategy(strategy)
            print(f"Running {doc_key} / {normalized_strategy}...", flush=True)
            result = run_strategy(
                document=document,
                llm=llm,
                strategy=normalized_strategy,
                allow_step6_llm=not args.skip_step6_llm,
            )
            prefix = outdir / f"{doc_key}.{normalized_strategy}"
            write_json(output_path(prefix, "step5.json"), result["step5_groups"])
            write_json(output_path(prefix, "step6.json"), result["step6_groups"])
            output_path(prefix, "step5.md").write_text(
                render_groups_markdown(
                    title=f"{document.source_name} - {normalized_strategy} Step 5",
                    groups=result["step5_groups"],
                ),
                encoding="utf-8",
            )
            output_path(prefix, "step6.md").write_text(
                render_groups_markdown(
                    title=f"{document.source_name} - {normalized_strategy} Step 6",
                    groups=result["step6_groups"],
                ),
                encoding="utf-8",
            )
            summary["documents"][doc_key][normalized_strategy] = result["summary"]
            step5 = result["summary"]["step5"]
            step6 = result["summary"]["step6"]
            print(
                f"Saved {doc_key} / {normalized_strategy}: "
                f"Step 5 chunks={step5['chunks']}, Step 6 chunks={step6['chunks']}, "
                f"LLM calls={result['summary']['llm_calls_total']}",
                flush=True,
            )

    write_json(outdir / "summary.json", summary)
    (outdir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    print(f"Saved comparison artifacts to: {outdir}")


def load_document(path: Path) -> ExtractedDocument:
    store = ExtractionArtifactStore(path.parent)
    return store.load(path)


def normalize_strategy(strategy: str) -> str:
    return "semantic_walk" if strategy in {"level4", "semantic"} else strategy


def run_strategy(
    *,
    document: ExtractedDocument,
    llm: LLMClient,
    strategy: str,
    allow_step6_llm: bool,
) -> dict[str, object]:
    config = BuilderConfig(STEP5_REFINEMENT_STRATEGY=strategy)
    preprocessor = ElementPreprocessor()
    chunker = DocumentChunker(llm_client=llm, config=config, preprocessor=preprocessor)

    started = time.perf_counter()
    step5_groups = build_step5_groups(chunker, document=document, strategy=strategy)
    step5_elapsed = time.perf_counter() - started
    step5_llm_calls = chunker.llm_calls
    step5_recoverable_errors = list(chunker.recoverable_errors)
    step5_payload = group_payloads(step5_groups)

    started = time.perf_counter()
    repaired_groups = chunker._repair_refined_groups(document_id=document.id, groups=step5_groups)
    if allow_step6_llm:
        repaired_groups = chunker._llm_audit_repaired_groups(document_id=document.id, groups=repaired_groups)
    chunker.refined_groups = repaired_groups
    step6_elapsed = time.perf_counter() - started
    step6_payload = group_payloads(repaired_groups)

    return {
        "step5_groups": step5_payload,
        "step6_groups": step6_payload,
        "summary": {
            "step5_elapsed_seconds": round(step5_elapsed, 2),
            "step6_elapsed_seconds": round(step6_elapsed, 2),
            "llm_calls_total": chunker.llm_calls,
            "llm_calls_step5": step5_llm_calls,
            "llm_calls_step6": chunker.llm_calls - step5_llm_calls,
            "recoverable_errors": step5_recoverable_errors + list(chunker.recoverable_errors),
            "step5": summarize_payloads(step5_payload),
            "step6": summarize_payloads(step6_payload, chunker=chunker),
            "repair_actions": dict(Counter(decision.action for decision in chunker.repair_decisions)),
        },
    }


def build_step5_groups(
    chunker: DocumentChunker,
    *,
    document: ExtractedDocument,
    strategy: str,
) -> list[RefinedChunkGroup]:
    elements = chunker._sorted_elements(document)
    chunker.boundary_candidates = []
    chunker.tentative_blocks = []
    chunker.refined_groups = []
    chunker.repair_decisions = []
    chunker.boundary_log = []
    chunker.llm_calls = 0
    chunker.recoverable_errors = []
    if not elements:
        return []

    texts = [chunker.preprocessor.to_text(element) for element in elements]
    if len(elements) == 1:
        chunker.tentative_blocks = chunker._single_tentative_block(document.id, elements[0], texts[0])
    else:
        adjacent_similarities, _, _ = chunker._compute_similarity_stats(texts)
        chunker.boundary_candidates = chunker._build_boundary_candidates(
            document_id=document.id,
            elements=elements,
            texts=texts,
            context_window=chunker.config.BOUNDARY_CONTEXT_WINDOW,
            adjacent_similarities=adjacent_similarities,
        )
        chunker.tentative_blocks = chunker._build_tentative_blocks(document.id, chunker.boundary_candidates)
    chunker.refined_groups = chunker._build_refined_groups(
        document_id=document.id,
        tentative_blocks=chunker.tentative_blocks,
        allow_llm=True,
        refinement_strategy=strategy,
    )
    return chunker.refined_groups


def group_payloads(groups: Iterable[RefinedChunkGroup]) -> list[dict[str, object]]:
    payloads = []
    for group in groups:
        elements = list(group.elements)
        payloads.append(
            {
                "group_index": group.group_index,
                "group_id": group.group_id,
                "source_block_id": group.source_block_id,
                "search_strategy": group.search_strategy,
                "stability": group.stability,
                "reason_summary": group.reason_summary,
                "element_ids": [element.element_id for element in elements],
                "element_types": [element.element_type for element in elements],
                "page_numbers": sorted({element.page_number for element in elements}),
                "chunk_text": "\n".join(element.text for element in elements if element.text),
            }
        )
    return payloads


def summarize_payloads(
    payloads: list[dict[str, object]],
    *,
    chunker: DocumentChunker | None = None,
) -> dict[str, object]:
    element_counts = [len(payload["element_ids"]) for payload in payloads]
    risk_flags: Counter[str] = Counter()
    if chunker is not None:
        states = [
            _RepairGroupState(
                source_group_ids=[str(payload["group_id"])],
                source_block_ids=[str(payload["source_block_id"])],
                elements=group.elements,
                internal_boundaries=[],
                probe_decisions=[],
                repair_decisions=[],
                stability=group.stability,
                reason_summary=group.reason_summary,
            )
            for payload, group in zip(payloads, chunker.refined_groups)
        ]
        for index in range(len(states)):
            risk_flags.update(chunker._local_audit_risk_flags(states, index))
    return {
        "chunks": len(payloads),
        "element_counts": element_counts,
        "avg_elements_per_chunk": round(sum(element_counts) / len(element_counts), 2) if element_counts else 0.0,
        "singletons": sum(1 for count in element_counts if count == 1),
        "singleton_text": sum(
            1
            for payload in payloads
            if len(payload["element_types"]) == 1 and payload["element_types"][0] == "text"
        ),
        "multiple_headings": sum(
            1
            for payload in payloads
            if sum(1 for item in payload["element_types"] if item in {"title", "heading", "section_header"}) > 1
        ),
        "strategy_counts": dict(Counter(str(payload["search_strategy"]) for payload in payloads)),
        "risk_flags": dict(risk_flags),
    }


def render_groups_markdown(*, title: str, groups: list[dict[str, object]]) -> str:
    lines = [f"# {title}", ""]
    for payload in groups:
        text = str(payload["chunk_text"])
        lines.extend(
            [
                f"## Chunk {payload['group_index']}",
                "",
                f"- Strategy: `{payload['search_strategy']}`",
                f"- Stability: `{payload['stability']}`",
                f"- Pages: `{payload['page_numbers']}`",
                f"- Element count: `{len(payload['element_ids'])}`",
                f"- Element types: `{payload['element_types']}`",
                f"- Element ids: `{payload['element_ids']}`",
                f"- Reason: {payload['reason_summary']}",
                "",
                "```text",
                text.strip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def render_summary_markdown(summary: dict[str, object]) -> str:
    lines = ["# Step 5 Strategy Comparison", ""]
    documents = summary.get("documents", {})
    if isinstance(documents, dict):
        for doc_key, strategies in documents.items():
            lines.extend([f"## {doc_key}", ""])
            if not isinstance(strategies, dict):
                continue
            for strategy, data in strategies.items():
                if not isinstance(data, dict):
                    continue
                step5 = data.get("step5", {})
                step6 = data.get("step6", {})
                lines.extend(
                    [
                        f"### {strategy}",
                        "",
                        f"- LLM calls: `{data.get('llm_calls_total')}` total (`{data.get('llm_calls_step5')}` Step 5, `{data.get('llm_calls_step6')}` Step 6)",
                        f"- Elapsed: `{data.get('step5_elapsed_seconds')}`s Step 5, `{data.get('step6_elapsed_seconds')}`s Step 6",
                        f"- Step 5 chunks: `{step5.get('chunks')}` avg elements `{step5.get('avg_elements_per_chunk')}` singletons `{step5.get('singletons')}`",
                        f"- Step 6 chunks: `{step6.get('chunks')}` avg elements `{step6.get('avg_elements_per_chunk')}` singletons `{step6.get('singletons')}`",
                        f"- Step 6 risk flags: `{step6.get('risk_flags')}`",
                        f"- Repair actions: `{data.get('repair_actions')}`",
                        "",
                    ]
                )
    return "\n".join(lines)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def output_path(prefix: Path, suffix: str) -> Path:
    return prefix.parent / f"{prefix.name}.{suffix}"


def safe_stem(value: str) -> str:
    stem = Path(value).stem
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "document"


if __name__ == "__main__":
    main()
