from __future__ import annotations

from collections import Counter

from contextus import Graph
from contextus.ingestion.models import ExtractedDocument
from contextus.llm import LLMClient

from .audit import ChunkAuditExporter
from .chunker import DocumentChunker
from .config import BuilderConfig
from .edge_builder import EdgeBuilder
from .node_candidate import NodeCandidateBuilder
from .node_builder import NodeBuilder
from .preprocessor import ElementPreprocessor


class AutoGraphBuilder:
    """Orchestrates ExtractedDocument -> Graph conversion."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: BuilderConfig | None = None,
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
        self.node_builder = NodeBuilder(
            llm_client=llm_client,
            preprocessor=self.preprocessor,
        )
        self.node_candidate_builder = NodeCandidateBuilder(preprocessor=self.preprocessor)
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

        chunks = self.chunker.build_repaired_groups(document)
        node_candidates = self.node_candidate_builder.build_candidates(document, chunks)
        nodes = self.node_builder.build_nodes(node_candidates)
        self.edge_builder.source_document = document.source_name
        edges = self.edge_builder.build_edges(nodes)

        graph = Graph(
            name=graph_name,
            description=f"Auto-built graph from {document.source_name}",
            metadata={
                "source_document": document.source_name,
                "builder": "contextus.builder",
                "repaired_chunk_count": len(chunks),
                "node_candidate_count": len(node_candidates),
                "step7": "node_candidate_creation",
                "node_candidate_quality_counts": self._node_candidate_quality_counts(node_candidates),
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
            "Step 7 node candidates: "
            f"{len(chunks)} repaired chunks -> {len(node_candidates)} node candidates | "
            f"quality_flags={self._node_candidate_quality_counts(node_candidates)}"
        )
        print(f"LLM calls total: {total_llm_calls}")
        return graph

    def _node_candidate_quality_counts(self, node_candidates) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for candidate in node_candidates:
            for flag, enabled in candidate.quality_flags.items():
                if enabled:
                    counts[flag] += 1
        return dict(counts)
