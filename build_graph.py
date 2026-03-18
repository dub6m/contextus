from __future__ import annotations

from pathlib import Path
import argparse

from dotenv import load_dotenv

from contextus.builder import AutoGraphBuilder, BuilderConfig
from contextus.ingestion.storage import ExtractionArtifactStore
from contextus.llm import CerebrasClient
from contextus.store import GraphStore


def main() -> None:
    """Build a graph from an extraction artifact and save it to graph storage."""
    load_dotenv()

    parser = argparse.ArgumentParser(description="Build a Contextus graph from an extraction artifact.")
    parser.add_argument("--extraction", "-e", required=True, help="Path to an extraction JSON artifact")
    parser.add_argument("--name", "-n", required=True, help="Name for the generated graph")
    parser.add_argument(
        "--docling-structure",
        action="store_true",
        help="Enable experimental Docling structural enrichment before role gating.",
    )
    args = parser.parse_args()

    extraction_path = Path(args.extraction)
    store = ExtractionArtifactStore(extraction_path.parent)
    document = store.load(extraction_path)

    config = BuilderConfig(DOCLING_ENABLE_STRUCTURAL_ENRICHMENT=args.docling_structure)
    builder = AutoGraphBuilder(llm_client=CerebrasClient(), config=config)
    graph = builder.build(document=document, graph_name=args.name)

    graph_store = GraphStore(Path("graphs"))
    path = graph_store.save(graph)
    print(f"Saved graph to: {path}")


if __name__ == "__main__":
    main()
