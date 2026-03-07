from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass
class Edge:
    """
    A directed, weighted, multi-labelled connection between two nodes.

    Fields
    ------
    source_id   : id of the node this edge originates from
    target_id   : id of the node this edge points to
    relations   : one or more strings describing the nature of this connection
                  e.g. ["depends_on"], ["is_example_of", "clarifies"]
    base_weight : manually assigned weight at construction time (0.0 – 1.0)
                  reflects how strong/important this relationship is by design
    cluster_weights : runtime-updated weights keyed by query cluster label
                      maps cluster_label -> derived_weight for that cluster
                      cluster -1 is the global fallback (noise queries)
    metadata    : arbitrary key-value store
    id          : stable unique identifier — auto-generated if not supplied

    Weight semantics
    ----------------
    effective_weight = base_weight * (1 - alpha) + derived * alpha
    where alpha is a blend factor (0.0 = fully manual, 1.0 = fully learned)
    and derived is looked up from cluster_weights for the given cluster.
    Falls back: specific cluster → cluster -1 (global) → base_weight.
    """

    source_id:       str
    target_id:       str
    relations:       list[str]
    base_weight:     float               = 1.0
    cluster_weights: dict[int, float]    = field(default_factory=dict)
    metadata:        dict[str, Any]      = field(default_factory=dict)
    id:              str                 = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if not self.relations:
            raise ValueError("Edge must have at least one relation label.")
        if not (0.0 <= self.base_weight <= 1.0):
            raise ValueError("base_weight must be between 0.0 and 1.0.")
        for label, w in self.cluster_weights.items():
            if not (0.0 <= w <= 1.0):
                raise ValueError(
                    f"cluster_weights[{label}] must be between 0.0 and 1.0."
                )
        if self.source_id == self.target_id:
            raise ValueError("Self-loops are not permitted.")

    def effective_weight(self, alpha: float = 0.5, cluster_label: int = -1) -> float:
        """
        Returns blended weight for the given cluster.
        Falls back to cluster -1 (global) if no weight exists for the cluster.
        Falls back to base_weight if no derived weight exists at all.
        """
        derived = self.cluster_weights.get(cluster_label)
        if derived is None:
            derived = self.cluster_weights.get(-1)
        if derived is None:
            return self.base_weight
        return self.base_weight * (1 - alpha) + derived * alpha

    def update_cluster_weight(self, cluster_label: int, new_weight: float) -> None:
        """Update derived weight for a specific cluster."""
        if not (0.0 <= new_weight <= 1.0):
            raise ValueError("Weight must be between 0.0 and 1.0.")
        self.cluster_weights[cluster_label] = new_weight

    def get_cluster_weight(self, cluster_label: int) -> float | None:
        """Returns derived weight for a cluster, or None if not set."""
        return self.cluster_weights.get(cluster_label)

    # --- Backwards compatibility properties ---

    @property
    def derived_weight(self) -> float | None:
        """Backwards-compatible accessor — returns global fallback weight."""
        return self.cluster_weights.get(-1)

    @derived_weight.setter
    def derived_weight(self, value: float | None) -> None:
        """Backwards-compatible setter — sets global fallback weight."""
        if value is None:
            self.cluster_weights.pop(-1, None)
        else:
            self.cluster_weights[-1] = value

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "source_id":       self.source_id,
            "target_id":       self.target_id,
            "relations":       self.relations,
            "base_weight":     self.base_weight,
            "cluster_weights": {str(k): v for k, v in self.cluster_weights.items()},
            "metadata":        self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Edge:
        # Backwards compatibility: migrate old derived_weight to cluster_weights
        cluster_weights = {}
        if "cluster_weights" in data:
            cluster_weights = {int(k): v for k, v in data["cluster_weights"].items()}
        elif "derived_weight" in data and data["derived_weight"] is not None:
            cluster_weights = {-1: data["derived_weight"]}

        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relations=data["relations"],
            base_weight=data.get("base_weight", 1.0),
            cluster_weights=cluster_weights,
            metadata=data.get("metadata", {}),
        )
