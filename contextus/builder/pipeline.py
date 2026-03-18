from __future__ import annotations

from collections import Counter
from pathlib import Path

from contextus import Graph
from contextus.ingestion.models import ExtractedDocument
from contextus.llm import LLMClient

from .audit import ChunkAuditExporter
from .chunker import DocumentChunker
from .config import BuilderConfig
from .consolidation import ChunkConsolidator
from .edge_builder import EdgeBuilder
from .node_builder import NodeBuilder
from .preprocessor import ElementPreprocessor
from .training import ChunkActionModel


class AutoGraphBuilder:
    """Orchestrates ExtractedDocument -> Graph conversion."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: BuilderConfig | None = None,
        chunk_action_model: ChunkActionModel | None = None,
    ) -> None:
        """Create a builder pipeline backed by one shared LLM client."""
        self.llm_client = llm_client
        self.config = config or BuilderConfig()
        self.preprocessor = ElementPreprocessor()
        self.chunker = DocumentChunker(
            llm_client=llm_client,
            config=self.config,
            preprocessor=self.preprocessor,
        )
        self.audit_exporter = ChunkAuditExporter(
            chunker=self.chunker,
            preprocessor=self.preprocessor,
            config=self.config,
        )
        self.chunk_action_model = chunk_action_model or self._load_chunk_action_model()
        self.consolidator = ChunkConsolidator(
            chunk_action_model=self.chunk_action_model,
            audit_exporter=self.audit_exporter,
            preprocessor=self.preprocessor,
        )
        self.node_builder = NodeBuilder(
            llm_client=llm_client,
            preprocessor=self.preprocessor,
        )
        self.edge_builder = EdgeBuilder(
            llm_client=llm_client,
            config=self.config,
        )

    def build(self, document: ExtractedDocument, graph_name: str) -> Graph:
        """Build and return a populated graph from one extraction artifact."""
        ordered_elements = sorted(
            (element for page in document.pages for element in page.elements),
            key=lambda item: (item.page_number, item.order),
        )
        for element in ordered_elements:
            self.preprocessor.to_text(element)

        chunks = self.chunker.chunk(document)
        consolidated_chunks = self.consolidator.consolidate(document, chunks)
        nodes = self.node_builder.build_nodes(consolidated_chunks)
        self.edge_builder.source_document = document.source_name
        edges = self.edge_builder.build_edges(nodes)

        graph = Graph(
            name=graph_name,
            description=f"Auto-built graph from {document.source_name}",
            metadata={
                "source_document": document.source_name,
                "builder": "contextus.builder",
                "raw_chunk_count": len(chunks),
                "canonical_chunk_count": len(consolidated_chunks),
                "predicted_chunk_actions": dict(self.consolidator.last_action_counts),
                "effective_chunk_actions": dict(self.consolidator.last_effective_action_counts),
                "chunk_action_model": type(self.chunk_action_model).__name__ if self.chunk_action_model is not None else None,
                "document_supporting_evidence_count": len(self.consolidator.last_orphan_support_segments),
                "document_supporting_evidence": [
                    {
                        "chunk_index": segment.chunk_index,
                        "action": segment.action,
                        "source": segment.source,
                        "confidence": segment.confidence,
                        "needs_review": segment.needs_review,
                        "page_numbers": segment.page_numbers(),
                        "element_ids": segment.element_ids(),
                        "text": segment.text,
                        "rationale": segment.rationale,
                    }
                    for segment in self.consolidator.last_orphan_support_segments
                ],
            },
        )
        for node in nodes:
            graph.add_node(node)
        for edge in edges:
            graph.add_edge(edge)

        counts = Counter(entry.tier_used for entry in self.chunker.boundary_log)
        total_llm_calls = self.chunker.llm_calls + self.node_builder.llm_calls + self.edge_builder.llm_calls
        print(f"Built graph '{graph_name}': {graph.node_count()} nodes, {graph.edge_count()} edges")
        print(
            "Chunking: "
            f"{len(self.chunker.boundary_log)} boundaries - "
            f"Tier 0: {counts.get('0', 0)}, "
            f"Tier 1a: {counts.get('1a', 0)}, "
            f"Tier 1b: {counts.get('1b', 0)}, "
            f"Tier 2: {counts.get('2', 0)}"
        )
        print(
            "Consolidation: "
            f"{len(chunks)} raw chunks -> {len(consolidated_chunks)} canonical chunks | "
            f"predicted={dict(self.consolidator.last_action_counts)} | "
            f"effective={dict(self.consolidator.last_effective_action_counts)}"
        )
        print(f"LLM calls total: {total_llm_calls}")
        return graph

    def _load_chunk_action_model(self) -> ChunkActionModel | None:
        path = Path(self.config.CHUNK_ACTION_MODEL_PATH)
        if not path.exists():
            return None
        try:
            return ChunkActionModel.load(path)
        except Exception:
            return None