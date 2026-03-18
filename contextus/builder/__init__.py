"""Auto-graph builder package for Contextus."""

from .config import BuilderConfig
from .preprocessor import ElementPreprocessor
from .audit import ChunkAuditExporter, ChunkAuditRow
from .consolidation import ChunkConsolidator, ConsolidatedChunk, EvidenceChunk
from .labeler import ChunkAuditLabeler, ChunkLabelDecision, LLMChunkAuditLabeler
from .chunker import BoundaryDecision, DocumentChunker
from .node_builder import NodeBuilder
from .edge_builder import EdgeBuilder
from .pipeline import AutoGraphBuilder
from .structural import DoclingStructuralEnricher, ElementStructuralAnnotation, StructuralEnrichmentResult
from .training import AttachmentDirectionResolver, ChunkActionDataset, ChunkActionModel, DirectionalResolution, StageMetrics, TrainingResult

__all__ = [
    "AutoGraphBuilder",
    "BoundaryDecision",
    "BuilderConfig",
    "AttachmentDirectionResolver",
    "ChunkActionDataset",
    "ChunkActionModel",
    "ChunkConsolidator",
    "DirectionalResolution",
    "EvidenceChunk",
    "ChunkAuditExporter",
    "ChunkAuditLabeler",
    "ConsolidatedChunk",
    "ChunkAuditRow",
    "ChunkLabelDecision",
    "DocumentChunker",
    "DoclingStructuralEnricher",
    "EdgeBuilder",
    "ElementStructuralAnnotation",
    "ElementPreprocessor",
    "LLMChunkAuditLabeler",
    "NodeBuilder",
    "StageMetrics",
    "StructuralEnrichmentResult",
    "TrainingResult",
]
