from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from contextus.builder.evidence import EvidenceHandleBuilder
from contextus.builder.evidence_eval import (
    default_prompt_cases,
    evaluate_prompt_suite,
    render_prompt_suite_markdown,
)
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


def main() -> None:
    outdir = Path("chunk_runs") / f"evidence_prompt_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)
    builder = EvidenceHandleBuilder()
    results_by_key = {}

    for extraction_path in DEFAULT_EXTRACTIONS:
        if not extraction_path.exists():
            continue
        document = load_document(extraction_path)
        document_key = safe_stem(document.source_name or extraction_path.stem)
        results_by_key[document_key] = builder.build(document)

    suite = evaluate_prompt_suite(results_by_key, default_prompt_cases(), top_k=5)
    (outdir / "prompt_eval.json").write_text(
        json.dumps(suite.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (outdir / "prompt_eval.md").write_text(render_prompt_suite_markdown(suite), encoding="utf-8")
    print(f"Saved evidence prompt evaluation artifacts to: {outdir}")
    print(json.dumps(suite.summary, indent=2))


def load_document(path: Path) -> ExtractedDocument:
    return ExtractionArtifactStore(path.parent).load(path)


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip("-") or "document"


if __name__ == "__main__":
    main()
