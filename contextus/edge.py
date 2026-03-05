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
    derived_weight : runtime-updated weight based on traversal history
                     starts as None (unset) until the system has usage data
    metadata    : arbitrary key-value store
    id          : stable unique identifier — auto-generated if not supplied

    Weight semantics
    ----------------
    effective_weight = base_weight * (1 - alpha) + derived_weight * alpha
    where alpha is a blend factor (0.0 = fully manual, 1.0 = fully learned).
    Alpha is managed by the traversal engine, not the edge itself.
    When derived_weight is None, effective_weight == base_weight.
    """

    source_id:      str
    target_id:      str
    relations:      list[str]
    base_weight:    float               = 1.0
    derived_weight: float | None        = None
    metadata:       dict[str, Any]      = field(default_factory=dict)
    id:             str                 = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if not self.relations:
            raise ValueError("Edge must have at least one relation label.")
        if not (0.0 <= self.base_weight <= 1.0):
            raise ValueError("base_weight must be between 0.0 and 1.0.")
        if self.derived_weight is not None and not (0.0 <= self.derived_weight <= 1.0):
            raise ValueError("derived_weight must be between 0.0 and 1.0.")
        if self.source_id == self.target_id:
            raise ValueError("Self-loops are not permitted.")

    def effective_weight(self, alpha: float = 0.5) -> float:
        """
        Blended weight used by the traversal engine.
        Alpha controls how much runtime learning influences the weight.
        If no derived weight exists yet, returns base_weight as-is.
        """
        if self.derived_weight is None:
            return self.base_weight
        return self.base_weight * (1 - alpha) + self.derived_weight * alpha

    def update_derived_weight(self, new_weight: float) -> None:
        if not (0.0 <= new_weight <= 1.0):
            raise ValueError("derived_weight must be between 0.0 and 1.0.")
        self.derived_weight = new_weight

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "source_id":      self.source_id,
            "target_id":      self.target_id,
            "relations":      self.relations,
            "base_weight":    self.base_weight,
            "derived_weight": self.derived_weight,
            "metadata":       self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Edge:
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relations=data["relations"],
            base_weight=data.get("base_weight", 1.0),
            derived_weight=data.get("derived_weight"),
            metadata=data.get("metadata", {}),
        )
