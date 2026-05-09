"""Auto-graph builder package for Contextus."""

from .config import BuilderConfig
from .preprocessor import ElementPreprocessor
from .audit import ChunkAuditExporter, ChunkAuditRow
from .node_candidate import NodeCandidate, NodeCandidateBuilder
from .chunker import (
    ActiveConcept,
    BoundaryCandidate,
    BoundaryDecision,
    BoundaryElementView,
    BoundaryPreliminaryDecision,
    BoundarySignals,
    ChunkRepairDecision,
    ConceptProbeDecision,
    DocumentChunker,
    RefinedChunkGroup,
    TentativeBlock,
)
from .node_builder import NodeBuilder
from .edge_builder import EdgeBuilder
from .pipeline import AutoGraphBuilder
from .structural import DoclingStructuralEnricher, ElementStructuralAnnotation, StructuralEnrichmentResult

__all__ = [
    "AutoGraphBuilder",
    "ActiveConcept",
    "BoundaryCandidate",
    "BoundaryDecision",
    "BoundaryElementView",
    "BoundaryPreliminaryDecision",
    "BoundarySignals",
    "BuilderConfig",
    "ChunkAuditExporter",
    "ChunkAuditRow",
    "ChunkRepairDecision",
    "ConceptProbeDecision",
    "DocumentChunker",
    "DoclingStructuralEnricher",
    "EdgeBuilder",
    "ElementStructuralAnnotation",
    "ElementPreprocessor",
    "NodeBuilder",
    "NodeCandidate",
    "NodeCandidateBuilder",
    "RefinedChunkGroup",
    "StructuralEnrichmentResult",
    "TentativeBlock",
]
