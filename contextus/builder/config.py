from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BuilderConfig:
    """Tunable parameters for the auto-graph builder pipeline."""

    MIN_CONFIDENCE: float = 0.4
    FREE_MERGE_PRIOR: float = 0.85

    EMBEDDING_MODEL: str = "nomic-ai/nomic-embed-text-v1.5"
    EMBEDDING_FALLBACK: str = "all-MiniLM-L6-v2"
    DEPTH_SCORE_SENSITIVITY: float = 0.5

    CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    CROSS_ENCODER_MERGE_THRESHOLD: float = 0.7
    CROSS_ENCODER_SPLIT_THRESHOLD: float = 0.3

    LLM_CONTEXT_WINDOW_SIZE: int = 3
    MAX_LLM_CALLS_PER_BOUNDARY: int = 3

    ANCHOR_MIN_CONFIRMED: int = 2
    ANCHOR_WARMUP_THRESHOLD: float = 0.65
    WARMUP_MERGE_THRESHOLD: float = 0.68
    POSTERIOR_EPSILON: float = 0.02
    POSTERIOR_MERGE_THRESHOLD: float = 0.82
    POSTERIOR_COMMIT_THRESHOLD: float = 0.9
    MAX_PROBE_STEPS_PER_GROUP: int = 8
    PROBE_WINDOW_RADIUS: int = 1
    ANCHOR_MAX_FULL_ELEMENTS: int = 4
    ANCHOR_EDGE_ELEMENTS: int = 2
    MAX_LOCAL_RECOVERY_STEPS: int = 2
    ROLLBACK_MERGE_THRESHOLD: float = 0.86

    SEMANTIC_EDGE_THRESHOLD: float = 0.75
    MAX_SEMANTIC_EDGES_PER_NODE: int = 5
