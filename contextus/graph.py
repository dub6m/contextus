from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import json
import uuid

from .node import Node, NodeType
from .edge import Edge


@dataclass
class Graph:
    """
    A directed, weighted knowledge graph.

    Nodes hold atomic units of knowledge.
    Edges hold directed, typed, weighted relationships between nodes.

    Internals
    ---------
    _nodes      : id -> Node
    _edges      : id -> Edge
    _out_edges  : source_id -> list of edge ids   (outbound index)
    _in_edges   : target_id -> list of edge ids   (inbound index)
    """

    name:        str
    description: str                        = ""
    metadata:    dict[str, Any]             = field(default_factory=dict)
    id:          str                        = field(default_factory=lambda: str(uuid.uuid4()))

    _nodes:     dict[str, Node]             = field(default_factory=dict, init=False, repr=False)
    _edges:     dict[str, Edge]             = field(default_factory=dict, init=False, repr=False)
    _out_edges: dict[str, list[str]]        = field(default_factory=dict, init=False, repr=False)
    _in_edges:  dict[str, list[str]]        = field(default_factory=dict, init=False, repr=False)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> Node:
        if node.id in self._nodes:
            raise ValueError(f"Node with id '{node.id}' already exists.")
        self._nodes[node.id] = node
        self._out_edges[node.id] = []
        self._in_edges[node.id] = []
        return node

    def get_node(self, node_id: str) -> Node:
        if node_id not in self._nodes:
            raise KeyError(f"Node '{node_id}' not found.")
        return self._nodes[node_id]

    def remove_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            raise KeyError(f"Node '{node_id}' not found.")
        # Remove all edges connected to this node
        edge_ids = self._out_edges[node_id] + self._in_edges[node_id]
        for edge_id in set(edge_ids):
            self._remove_edge_by_id(edge_id)
        del self._nodes[node_id]
        del self._out_edges[node_id]
        del self._in_edges[node_id]

    def all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def node_count(self) -> int:
        return len(self._nodes)

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, edge: Edge) -> Edge:
        if edge.source_id not in self._nodes:
            raise KeyError(f"Source node '{edge.source_id}' not found.")
        if edge.target_id not in self._nodes:
            raise KeyError(f"Target node '{edge.target_id}' not found.")
        if edge.id in self._edges:
            raise ValueError(f"Edge with id '{edge.id}' already exists.")
        self._edges[edge.id] = edge
        self._out_edges[edge.source_id].append(edge.id)
        self._in_edges[edge.target_id].append(edge.id)
        return edge

    def get_edge(self, edge_id: str) -> Edge:
        if edge_id not in self._edges:
            raise KeyError(f"Edge '{edge_id}' not found.")
        return self._edges[edge_id]

    def remove_edge(self, edge_id: str) -> None:
        if edge_id not in self._edges:
            raise KeyError(f"Edge '{edge_id}' not found.")
        self._remove_edge_by_id(edge_id)

    def _remove_edge_by_id(self, edge_id: str) -> None:
        edge = self._edges.pop(edge_id, None)
        if edge:
            self._out_edges[edge.source_id].remove(edge_id)
            self._in_edges[edge.target_id].remove(edge_id)

    def all_edges(self) -> list[Edge]:
        return list(self._edges.values())

    def edge_count(self) -> int:
        return len(self._edges)

    # ------------------------------------------------------------------
    # Traversal helpers (used by the traversal engine, not end users)
    # ------------------------------------------------------------------

    def neighbors_out(self, node_id: str) -> list[tuple[Node, Edge]]:
        """All nodes reachable from node_id via outbound edges, with the edge."""
        return [
            (self._nodes[self._edges[eid].target_id], self._edges[eid])
            for eid in self._out_edges.get(node_id, [])
        ]

    def neighbors_in(self, node_id: str) -> list[tuple[Node, Edge]]:
        """All nodes that point to node_id via inbound edges, with the edge."""
        return [
            (self._nodes[self._edges[eid].source_id], self._edges[eid])
            for eid in self._in_edges.get(node_id, [])
        ]

    def neighbors_all(self, node_id: str) -> list[tuple[Node, Edge]]:
        """All connected nodes regardless of direction."""
        return self.neighbors_out(node_id) + self.neighbors_in(node_id)

    def get_edge_between(self, source_id: str, target_id: str) -> list[Edge]:
        """All edges from source to target (there can be more than one)."""
        return [
            self._edges[eid]
            for eid in self._out_edges.get(source_id, [])
            if self._edges[eid].target_id == target_id
        ]

    # ------------------------------------------------------------------
    # Graph summary (used by the router for multi-graph dispatch)
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """
        Auto-generated summary of the graph's contents.
        The router reads this to decide whether to dispatch a query here.
        """
        node_summaries = "\n".join(
            f"  - {node.summary()}" for node in self._nodes.values()
        )
        return (
            f"Graph: {self.name}\n"
            f"Description: {self.description}\n"
            f"Nodes ({self.node_count()}):\n{node_summaries}"
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "description": self.description,
            "metadata":    self.metadata,
            "nodes":       [n.to_dict() for n in self._nodes.values()],
            "edges":       [e.to_dict() for e in self._edges.values()],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> Graph:
        g = cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )
        for nd in data.get("nodes", []):
            g.add_node(Node.from_dict(nd))
        for ed in data.get("edges", []):
            g.add_edge(Edge.from_dict(ed))
        return g

    @classmethod
    def from_json(cls, json_str: str) -> Graph:
        return cls.from_dict(json.loads(json_str))
