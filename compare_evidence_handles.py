from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import json
import re

from contextus.builder.evidence import EvidenceHandleBuilder, EvidencePipelineResult
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


def main() -> None:
    outdir = Path("chunk_runs") / f"evidence_handles_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)
    builder = EvidenceHandleBuilder()
    summary: dict[str, object] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "documents": {},
    }

    for extraction_path in DEFAULT_EXTRACTIONS:
        if not extraction_path.exists():
            continue
        document = load_document(extraction_path)
        result = builder.build(document)
        doc_key = safe_stem(document.source_name or extraction_path.stem)
        (outdir / f"{doc_key}.evidence.json").write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (outdir / f"{doc_key}.evidence.md").write_text(render_document_markdown(result), encoding="utf-8")
        summary["documents"][doc_key] = result.summary

    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (outdir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    print(f"Saved evidence-handle artifacts to: {outdir}")


def load_document(path: Path) -> ExtractedDocument:
    return ExtractionArtifactStore(path.parent).load(path)


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip("-") or "document"


def render_summary_markdown(summary: dict[str, object]) -> str:
    lines = ["# Evidence Handle Signal Run", ""]
    documents = summary.get("documents", {})
    if isinstance(documents, dict):
        for doc_key, data in documents.items():
            if not isinstance(data, dict):
                continue
            lines.extend(
                [
                    f"## {doc_key}",
                    "",
                    f"- Elements: `{data.get('element_count')}`",
                    f"- Handles: `{data.get('handle_count')}`",
                    f"- Packages: `{data.get('package_count')}`",
                    f"- Avg tokens per element: `{data.get('avg_tokens_per_element')}`",
                    f"- Avg tokens per package: `{data.get('avg_tokens_per_package')}`",
                    f"- Avg context tokens per package: `{data.get('avg_context_tokens_per_package')}`",
                    f"- Marker counts: `{data.get('marker_counts')}`",
                    f"- Attachment counts: `{data.get('attachment_counts')}`",
                    f"- Risk counts: `{data.get('risk_counts')}`",
                    f"- Package attachment counts: `{data.get('package_attachment_counts')}`",
                    f"- Package risk counts: `{data.get('package_risk_counts')}`",
                    f"- Support elements: `{data.get('support_elements')}`",
                    f"- Heading elements: `{data.get('heading_elements')}`",
                    "",
                ]
            )
    return "\n".join(lines)


def render_document_markdown(result: EvidencePipelineResult) -> str:
    risk_counts: Counter[str] = Counter()
    for handle in result.handles:
        risk_counts.update(handle.risk_flags)
    lines = [
        f"# Evidence Handles: {result.source_name}",
        "",
        f"- Elements: `{result.summary['element_count']}`",
        f"- Handles: `{result.summary['handle_count']}`",
        f"- Packages: `{result.summary['package_count']}`",
        f"- Risk counts: `{dict(risk_counts)}`",
        f"- Package attachment counts: `{result.summary['package_attachment_counts']}`",
        f"- Package risk counts: `{result.summary['package_risk_counts']}`",
        "",
        "## Highest-Risk Handles",
        "",
    ]
    ranked = sorted(
        result.handles,
        key=lambda handle: (
            len(handle.risk_flags),
            1.0 - handle.feature_scores.get("reference_closure", 1.0),
            1.0 - handle.feature_scores.get("support_closure", 1.0),
            handle.feature_scores.get("noise_risk", 0.0),
        ),
        reverse=True,
    )
    for handle in ranked[:20]:
        if not handle.risk_flags:
            continue
        text = " ".join(handle.core_text.split())
        if len(text) > 240:
            text = text[:237].rstrip() + "..."
        lines.extend(
            [
                f"### Handle {handle.handle_index:03d}",
                "",
                f"- Elements: `{handle.core_element_ids}`",
                f"- Risks: `{handle.risk_flags}`",
                f"- Scores: `{handle.feature_scores}`",
                f"- Attachments: `{[(item.attachment_type, item.target_element_ids, item.score) for item in handle.attachments[:5]]}`",
                f"- Package: `{package_summary(result, handle.handle_id)}`",
                "",
                "```text",
                text,
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def package_summary(result: EvidencePipelineResult, handle_id: str) -> dict[str, object]:
    package = next(item for item in result.packages if item.handle_id == handle_id)
    return {
        "context_ids": package.context_element_ids,
        "types": package.included_attachment_types,
        "tokens": package.token_count,
        "scores": package.package_scores,
        "risks": package.risk_flags,
    }


if __name__ == "__main__":
    main()
