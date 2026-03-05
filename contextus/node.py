from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


class NodeType(str, Enum):
    DEFINITION  = "definition"   # what something is
    BEHAVIOR    = "behavior"     # how something works / what it does
    CONSTRAINT  = "constraint"   # rules, limits, conditions that apply
    EXAMPLE     = "example"      # concrete instance of another node
    RELATION    = "relation"     # a concept that is itself a relationship
    PROCEDURE   = "procedure"    # steps to do something
    EXCEPTION   = "exception"    # where a rule/behavior breaks down


@dataclass
class Node:
    """
    A single atomic unit of knowledge in the graph.

    Fields
    ------
    label    : short human-readable name for this node
    type     : what kind of knowledge this node holds
    body     : the actual knowledge content
    scope    : ONE sentence — what this node is and is NOT about.
               This is the field the traversal engine reads first.
               Write it like a contract: precise, unambiguous.
    aliases  : other names/terms this concept is known by
    metadata : arbitrary key-value store (source, author, timestamp, etc.)
    id       : stable unique identifier — auto-generated if not supplied
    """

    label:    str
    type:     NodeType
    body:     str
    scope:    str
    aliases:  list[str]          = field(default_factory=list)
    metadata: dict[str, Any]     = field(default_factory=dict)
    id:       str                = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if not self.label.strip():
            raise ValueError("Node label cannot be empty.")
        if not self.scope.strip():
            raise ValueError("Node scope cannot be empty — it is load-bearing for traversal.")
        if not self.body.strip():
            raise ValueError("Node body cannot be empty.")
        if isinstance(self.type, str):
            self.type = NodeType(self.type)

    def summary(self) -> str:
        """One-liner the traversal engine uses to decide relevance without reading body."""
        return f"[{self.type.value}] {self.label} — {self.scope}"

    def to_dict(self) -> dict:
        return {
            "id":       self.id,
            "label":    self.label,
            "type":     self.type.value,
            "body":     self.body,
            "scope":    self.scope,
            "aliases":  self.aliases,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        return cls(
            id=data["id"],
            label=data["label"],
            type=NodeType(data["type"]),
            body=data["body"],
            scope=data["scope"],
            aliases=data.get("aliases", []),
            metadata=data.get("metadata", {}),
        )
