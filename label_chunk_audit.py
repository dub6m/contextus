from __future__ import annotations

from pathlib import Path
import argparse

from dotenv import load_dotenv

from contextus.builder import ChunkAuditLabeler, LLMChunkAuditLabeler
from contextus.llm import CerebrasClient


def main() -> None:
    """Apply policy or LLM weak labels to chunk-audit rows."""
    parser = argparse.ArgumentParser(description="Label chunk-audit rows with a local policy or LLM weak supervision.")
    parser.add_argument("--input", "-i", required=True, help="Input chunk-audit JSONL path")
    parser.add_argument("--output", "-o", required=True, help="Output labeled JSONL path")
    parser.add_argument("--limit", "-n", type=int, help="Maximum number of rows to label")
    parser.add_argument("--offset", type=int, default=0, help="Row offset before labeling begins")
    parser.add_argument(
        "--mode",
        choices=("policy", "llm"),
        default="policy",
        help="Labeling mode. 'policy' is local and deterministic; 'llm' uses Cerebras.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel labeling workers. Only used in llm mode; recommend 1-2.",
    )
    args = parser.parse_args()

    worker_count = max(1, args.workers)
    if args.mode == "llm":
        load_dotenv(override=True)
        labeler = LLMChunkAuditLabeler(
            llm_client=CerebrasClient(),
            llm_client_factory=CerebrasClient if worker_count > 1 else None,
        )
    else:
        labeler = ChunkAuditLabeler()

    path = labeler.label_file(
        input_path=Path(args.input),
        output_path=Path(args.output),
        limit=args.limit,
        offset=args.offset,
        workers=worker_count,
    )
    print(f"Saved labeled chunk audit rows to: {path}")
    print(f"Mode: {args.mode}")
    print(f"LLM calls: {getattr(labeler, 'llm_calls', 0)}")
    print(f"Workers: {worker_count if args.mode == 'llm' else 1}")


if __name__ == "__main__":
    main()
