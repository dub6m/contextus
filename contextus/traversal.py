from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

from .graph import Graph
from .node import Node
from .edge import Edge
from .llm import LLMClient


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TraversalResult:
    """
    The subgraph the traversal engine determined is necessary and sufficient
    to satisfy the query. No more, no less.
    """
    query:               str
    graph_name:          str             = ""
    nodes:               list[Node]      = field(default_factory=list)
    edges:               list[Edge]      = field(default_factory=list)
    reasoning:           str             = ""
    verified:            bool            = False
    verifier_note:       str             = ""
    noise_ids:           list[str]       = field(default_factory=list)
    missing_description: str             = ""

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def summary(self) -> str:
        lines = [
            f"Query     : {self.query}",
            f"Verified  : {self.verified}",
            f"Nodes ({len(self.nodes)}):",
        ]
        for n in self.nodes:
            lines.append(f"  - {n.summary()}")
        if self.verifier_note:
            lines.append(f"Verifier  : {self.verifier_note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

COLLECTOR_ANCHOR_SYSTEM = """
You are the Collector — a traversal agent operating over a knowledge graph.

Your job is to identify the best ANCHOR NODE to begin traversal from, given a query.
The anchor is the single node whose content is most directly and centrally relevant to the query.

You will be given:
- A query
- A list of nodes, each with: id, type, label, and scope (one sentence describing what the node covers)

Respond ONLY with a JSON object in this exact format (no markdown, no explanation):
{"anchor_id": "<node_id>", "reason": "<one sentence why>"}
""".strip()

COLLECTOR_STEP_SYSTEM = """
You are the Collector — a traversal agent operating over a knowledge graph.

Your job is to decide which neighboring nodes to visit next given:
- The original query
- The nodes already collected
- The candidate neighbors (each with: id, type, label, scope, edge relations to the current node)

Rules:
1. Only include a neighbor if it is NECESSARY to fully satisfy the query.
2. Reject any neighbor that is redundant, tangential, or not needed.
3. You may include zero neighbors if the already-collected nodes are sufficient.
4. Do not revisit nodes already in the collected set.

Respond ONLY with a JSON object in this exact format (no markdown, no explanation):
{
  "visit": ["<node_id>", ...],
  "done": true | false,
  "reason": "<one sentence>"
}

Set "done" to true when the collected nodes are sufficient to fully answer the query and no further traversal is needed.
""".strip()

VERIFIER_SYSTEM = """
You are the Verifier — a quality control agent for a knowledge graph retrieval system.

You will be given:
- A query
- A subgraph (set of nodes) the Collector has assembled

Your job is to determine:
1. Is anything MISSING? (nodes needed to fully answer the query that are not present)
2. Is anything UNNECESSARY? (nodes that add no value and are noise)

Respond ONLY with a JSON object in this exact format (no markdown, no explanation):
{
  "complete": true | false,
  "noise_ids": ["<node_id>", ...],
  "missing_description": "<describe what is missing, or empty string if nothing>",
  "note": "<one sentence summary of your assessment>"
}
""".strip()


# ---------------------------------------------------------------------------
# Traversal Engine
# ---------------------------------------------------------------------------

class TraversalEngine:
    """
    Drives LLM-guided traversal over a Graph to extract the minimal subgraph
    needed to satisfy a query.

    Two roles:
    - Collector : anchors, steps through the graph node-by-node via a queue,
                  asks the LLM at each expansion which neighbors to enqueue.
    - Verifier  : reviews the collected subgraph for completeness and noise.

    Traversal is BFS-style with a single queue. The LLM is called once per
    node expansion (not once per frontier batch), which means:
      - LLM call count == number of nodes expanded
      - The queue tracks what's already been scheduled to avoid duplicate calls

    Parameters
    ----------
    graph     : the Graph to traverse
    llm       : any LLMClient implementation
    max_depth : hard cap on node expansions (safety net)
    alpha     : edge weight blend factor (0=base only, 1=derived only)
    """

    def __init__(
        self,
        graph:     Graph,
        llm:       LLMClient,
        max_depth: int   = 10,
        alpha:     float = 0.5,
    ):
        self.graph     = graph
        self.llm       = llm
        self.max_depth = max_depth
        self.alpha     = alpha

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def query(self, query: str, graph_name: str = "") -> TraversalResult:
        result = TraversalResult(query=query, graph_name=graph_name)

        # Step 1 — find anchor node
        anchor = self._find_anchor(query)
        if anchor is None:
            result.reasoning = "Could not identify a relevant anchor node."
            return result

        # Step 2 — BFS traversal driven by Collector
        #
        # collected_ids : nodes already added to result
        # queued_ids    : nodes scheduled for expansion (to avoid duplicate enqueuing)
        # queue         : ordered list of node ids to expand next
        #
        collected_ids: set[str] = set()
        queued_ids:    set[str] = {anchor.id}
        queue:         list[str] = [anchor.id]
        expansions = 0
        done = False

        while queue and expansions < self.max_depth and not done:
            node_id = queue.pop(0)

            if node_id in collected_ids:
                continue

            # Collect node
            node = self.graph.get_node(node_id)
            collected_ids.add(node_id)
            result.nodes.append(node)

            # Collect edges between this node and already-collected nodes
            for existing_id in collected_ids - {node_id}:
                for edge in self.graph.get_edge_between(existing_id, node_id):
                    if edge not in result.edges:
                        result.edges.append(edge)
                for edge in self.graph.get_edge_between(node_id, existing_id):
                    if edge not in result.edges:
                        result.edges.append(edge)

            # Ask Collector which neighbors to enqueue
            neighbors = self.graph.neighbors_all(node_id)
            unvisited = [
                (n, e) for n, e in neighbors
                if n.id not in collected_ids and n.id not in queued_ids
            ]

            expansions += 1

            if not unvisited:
                continue

            visit_ids, done, reason = self._collector_step(
                query, result.nodes, unvisited
            )
            result.reasoning = reason

            if not done and visit_ids:
                # Weight-sort approved neighbors before enqueuing
                approved = [
                    (n, e) for n, e in unvisited if n.id in visit_ids
                ]
                approved.sort(
                    key=lambda ne: ne[1].effective_weight(self.alpha),
                    reverse=True,
                )
                for n, _ in approved:
                    queued_ids.add(n.id)
                    queue.append(n.id)

        # Step 3 — Verifier reviews collected subgraph
        result = self._verify(query, result)
        return result

    # ------------------------------------------------------------------
    # Collector: anchor selection
    # ------------------------------------------------------------------

    def _find_anchor(self, query: str) -> Node | None:
        all_nodes = self.graph.all_nodes()
        if not all_nodes:
            return None

        node_list = "\n".join(
            f'  {{"id": "{n.id}", "type": "{n.type.value}", '
            f'"label": "{n.label}", "scope": "{n.scope}"}}'
            for n in all_nodes
        )
        user_prompt = f'Query: "{query}"\n\nNodes:\n[\n{node_list}\n]'

        raw = self.llm.complete(system=COLLECTOR_ANCHOR_SYSTEM, user=user_prompt)
        parsed = _parse_json(raw.content)
        if not parsed or "anchor_id" not in parsed:
            return None

        try:
            return self.graph.get_node(parsed["anchor_id"])
        except KeyError:
            return None

    # ------------------------------------------------------------------
    # Collector: single node expansion step
    # ------------------------------------------------------------------

    def _collector_step(
        self,
        query:      str,
        collected:  list[Node],
        candidates: list[tuple[Node, Edge]],
    ) -> tuple[list[str], bool, str]:
        """Returns (node_ids_to_visit, done_flag, reason_string)."""

        collected_summary = "\n".join(
            f'  - [{n.type.value}] "{n.label}": {n.scope}'
            for n in collected
        )
        candidate_list = "\n".join(
            f'  {{"id": "{n.id}", "type": "{n.type.value}", "label": "{n.label}", '
            f'"scope": "{n.scope}", "relations": {e.relations}}}'
            for n, e in candidates
        )
        user_prompt = (
            f'Query: "{query}"\n\n'
            f'Already collected:\n{collected_summary}\n\n'
            f'Candidate neighbors:\n[\n{candidate_list}\n]'
        )

        raw = self.llm.complete(system=COLLECTOR_STEP_SYSTEM, user=user_prompt)
        parsed = _parse_json(raw.content)
        if not parsed:
            return [], True, "Failed to parse Collector response."

        return (
            parsed.get("visit", []),
            parsed.get("done", False),
            parsed.get("reason", ""),
        )

    # ------------------------------------------------------------------
    # Verifier
    # ------------------------------------------------------------------

    def _verify(self, query: str, result: TraversalResult) -> TraversalResult:
        if not result.nodes:
            result.verifier_note = "No nodes collected — nothing to verify."
            return result

        node_descriptions = "\n".join(
            f'  {{"id": "{n.id}", "type": "{n.type.value}", '
            f'"label": "{n.label}", "scope": "{n.scope}", "body": "{n.body[:300]}"}}'
            for n in result.nodes
        )
        user_prompt = (
            f'Query: "{query}"\n\n'
            f'Collected subgraph:\n[\n{node_descriptions}\n]'
        )

        raw = self.llm.complete(system=VERIFIER_SYSTEM, user=user_prompt)
        parsed = _parse_json(raw.content)
        if not parsed:
            result.verifier_note = "Failed to parse Verifier response."
            return result

        noise_ids    = parsed.get("noise_ids", [])
        missing_desc = parsed.get("missing_description", "")

        # Store raw Verifier findings on the result for downstream consumers
        result.noise_ids           = list(noise_ids)
        result.missing_description = missing_desc

        noise_set = set(noise_ids)
        if noise_set:
            result.nodes = [n for n in result.nodes if n.id not in noise_set]
            result.edges = [
                e for e in result.edges
                if e.source_id not in noise_set and e.target_id not in noise_set
            ]

        result.verified      = parsed.get("complete", False)
        result.verifier_note = parsed.get("note", "")
        if missing_desc:
            result.verifier_note += f" | Missing: {missing_desc}"

        return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict | None:
    """Robustly extract a JSON object from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None
