from __future__ import annotations

from pathlib import Path
import argparse

from contextus.builder import ChunkAuditExporter
from contextus.ingestion.storage import ExtractionArtifactStore


def main() -> None:
    """Export chunk audit rows from one extraction artifact to JSONL."""
    parser = argparse.ArgumentParser(description="Export chunk-audit rows from an extraction artifact.")
    parser.add_argument("--extraction", "-e", required=True, help="Path to an extraction JSON artifact")
    parser.add_argument("--output", "-o", help="Output JSONL path; defaults to audits/<stem>.chunks.jsonl")
    args = parser.parse_args()

    extraction_path = Path(args.extraction)
    store = ExtractionArtifactStore(extraction_path.parent)
    document = store.load(extraction_path)

    default_output = Path("audits") / f"{Path(document.source_name).stem}.chunks.jsonl"
    output_path = Path(args.output) if args.output else default_output

    exporter = ChunkAuditExporter()
    path = exporter.export_jsonl(document=document, output_path=output_path)
    print(f"Saved chunk audit rows to: {path}")


if __name__ == "__main__":
    main()
