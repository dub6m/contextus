from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from copy import deepcopy

from .graph import Graph
from .node import Node, NodeType
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
    backtrack_count:     int             = 0

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


@dataclass
class SessionRecord:
    """
    Tracks traversal state within a single query session.
    Created at query start, discarded at query end.
    Never persisted. Never affects derived weights.
    """
    # All edges attempted in this session: edge_id -> outcome
    # outcome is "collected", "rejected_by_collector", or "dead_end"
    attempted_edges: dict[str, str] = field(default_factory=dict)

    # Decision points: node_id -> list of neighbour node ids NOT chosen by Collector
    # These are available for backtracking
    unchosen_neighbours: dict[str, list[str]] = field(default_factory=dict)

    # Order in which decision points were made, for backtracking in reverse order
    decision_point_order: list[str] = field(default_factory=list)


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

    def query(self, query: str, graph_name: str = "", previous_context: str = "") -> TraversalResult:
        result = TraversalResult(query=query, graph_name=graph_name)
        session = SessionRecord()

        # Step 1 — find anchor node
        anchor = self._find_anchor(query, previous_context=previous_context)
        if anchor is None:
            result.reasoning = "Could not identify a relevant anchor node."
            return result

        # Step 2 — BFS traversal driven by Collector
        collected_ids: set[str] = set()
        queued_ids:    set[str] = {anchor.id}
        queue:         list[str] = [anchor.id]
        expansions = 0
        done = False

        expansions, done = self._bfs_phase(
            query, result, session, collected_ids, queued_ids, queue, expansions, done,
            previous_context=previous_context,
        )

        # Step 3 — Verifier reviews collected subgraph
        result = self._verify(query, result)

        if result.verified:
            return result

        # Step 4 — Backtracking if unverified with missing coverage
        best_result = deepcopy(result)

        while (
            not result.verified
            and result.missing_description
            and expansions < self.max_depth
        ):
            # Find the most recent decision point with unchosen neighbours
            backtrack_node_id = None
            for dp_id in reversed(session.decision_point_order):
                if session.unchosen_neighbours.get(dp_id):
                    backtrack_node_id = dp_id
                    break

            if backtrack_node_id is None:
                break  # No more decision points to try

            result.backtrack_count += 1

            # Enqueue unchosen neighbours from this decision point
            unchosen = session.unchosen_neighbours.pop(backtrack_node_id)
            for nid in unchosen:
                if nid not in collected_ids and nid not in queued_ids:
                    queued_ids.add(nid)
                    queue.append(nid)

            # Continue BFS from where we left off
            expansions, done = self._bfs_phase(
                query, result, session, collected_ids, queued_ids, queue, expansions, done,
                previous_context=previous_context,
            )

            # Re-verify
            result = self._verify(query, result)

            # Track the best result (most nodes after noise removal)
            if len(result.nodes) > len(best_result.nodes):
                best_result = deepcopy(result)

            if result.verified:
                return result

        # Return the best result if nothing verified
        if not result.verified and len(best_result.nodes) > len(result.nodes):
            best_result.backtrack_count = result.backtrack_count
            return best_result

        return result

    # ------------------------------------------------------------------
    # BFS phase (used by query and backtracking)
    # ------------------------------------------------------------------

    def _bfs_phase(
        self,
        query:            str,
        result:           TraversalResult,
        session:          SessionRecord,
        collected_ids:    set[str],
        queued_ids:       set[str],
        queue:            list[str],
        expansions:       int,
        done:             bool,
        previous_context: str = "",
    ) -> tuple[int, bool]:
        """Run one BFS phase, updating result and session in place.
        Returns updated (expansions, done)."""

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
                    session.attempted_edges[edge.id] = "collected"
                for edge in self.graph.get_edge_between(node_id, existing_id):
                    if edge not in result.edges:
                        result.edges.append(edge)
                    session.attempted_edges[edge.id] = "collected"

            # Stub nodes: collect as boundary markers but never expand
            if node.is_stub:
                expansions += 1
                continue

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
                query, result.nodes, unvisited,
                previous_context=previous_context,
            )
            result.reasoning = reason

            # Record edge outcomes
            visit_id_set = set(visit_ids)
            for n, e in unvisited:
                if n.id in visit_id_set:
                    session.attempted_edges[e.id] = "collected"
                else:
                    session.attempted_edges[e.id] = "rejected_by_collector"

            # Record unchosen neighbours for backtracking
            unchosen = [n.id for n, _ in unvisited if n.id not in visit_id_set]
            if unchosen:
                session.unchosen_neighbours[node_id] = unchosen
                session.decision_point_order.append(node_id)

            if not done and visit_ids:
                # Weight-sort approved neighbors before enqueuing
                approved = [
                    (n, e) for n, e in unvisited if n.id in visit_id_set
                ]
                approved.sort(
                    key=lambda ne: ne[1].effective_weight(self.alpha),
                    reverse=True,
                )
                for n, _ in approved:
                    queued_ids.add(n.id)
                    queue.append(n.id)

        return expansions, done

    # ------------------------------------------------------------------
    # Collector: anchor selection
    # ------------------------------------------------------------------

    def _find_anchor(self, query: str, previous_context: str = "") -> Node | None:
        all_nodes = self.graph.all_nodes()
        if not all_nodes:
            return None

        node_list = "\n".join(
            f'  {{"id": "{n.id}", "type": "{n.type.value}", '
            f'"label": "{n.label}", "scope": "{n.scope}"}}'
            for n in all_nodes
        )
        user_prompt = f'Query: "{query}"\n\nNodes:\n[\n{node_list}\n]'
        if previous_context:
            user_prompt += f"\n\n{previous_context}"

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
        previous_context: str = "",
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
        if previous_context:
            user_prompt += f"\n\n{previous_context}"

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


# ---------------------------------------------------------------------------
# Multi-pass result
# ---------------------------------------------------------------------------

@dataclass
class MultiPassResult:
    """
    Result from a multi-pass traversal attempt.
    Wraps the best TraversalResult across all passes.
    """
    query:        str
    graph_name:   str                   = ""
    best:         TraversalResult       = None   # the result being returned
    all_passes:   list[TraversalResult]  = field(default_factory=list)
    passes_run:   int                   = 0
    verified:     bool                  = False

    def nodes(self) -> list:
        return self.best.nodes if self.best else []

    def edges(self) -> list:
        return self.best.edges if self.best else []

    def missing_description(self) -> str:
        return self.best.missing_description if self.best else ""

    def summary(self) -> str:
        lines = [
            f"Query      : {self.query}",
            f"Passes run : {self.passes_run}",
            f"Verified   : {self.verified}",
            f"Nodes      : {len(self.nodes())}",
        ]
        if not self.verified and self.missing_description():
            lines.append(f"Missing    : {self.missing_description()}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Multi-pass engine
# ---------------------------------------------------------------------------

class MultiPassEngine:
    """
    Runs up to max_passes full traversal passes on a query.
    Each pass after the first receives context from the previous attempt.
    Backtracking within each pass is handled by TraversalEngine.

    Exit conditions (in priority order):
    1. A pass returns verified — return immediately
    2. max_passes reached — return best unverified result
    3. No nodes collected on a pass — return best result so far

    Parameters
    ----------
    graph      : the Graph to traverse
    llm        : any LLMClient implementation
    max_passes : maximum number of full traversal passes (default 3)
    max_depth  : passed through to TraversalEngine
    alpha      : passed through to TraversalEngine
    """

    def __init__(
        self,
        graph:      Graph,
        llm:        LLMClient,
        max_passes: int   = 3,
        max_depth:  int   = 10,
        alpha:      float = 0.5,
    ):
        self.graph      = graph
        self.llm        = llm
        self.max_passes = max_passes
        self.max_depth  = max_depth
        self.alpha      = alpha

    def query(self, query: str, graph_name: str = "") -> MultiPassResult:
        mp_result = MultiPassResult(query=query, graph_name=graph_name)
        previous_context = ""

        for pass_num in range(1, self.max_passes + 1):
            engine = TraversalEngine(
                graph=self.graph,
                llm=self.llm,
                max_depth=self.max_depth,
                alpha=self.alpha,
            )
            pass_result = engine.query(
                query, graph_name=graph_name,
                previous_context=previous_context,
            )
            mp_result.all_passes.append(pass_result)
            mp_result.passes_run = pass_num

            # Early exit: zero nodes collected
            if not pass_result.nodes:
                break

            # Track best result (most nodes; on tie prefer latest pass)
            if mp_result.best is None or len(pass_result.nodes) >= len(mp_result.best.nodes):
                mp_result.best = pass_result

            # Exit on verification
            if pass_result.verified:
                mp_result.verified = True
                return mp_result

            # Build context for next pass
            collected_labels = ", ".join(n.label for n in pass_result.nodes)
            previous_context = (
                f"Previous attempt summary:\n"
                f"- Collected nodes: {collected_labels}\n"
                f"- Verifier finding: {pass_result.verifier_note}\n"
                f"- What was missing: {pass_result.missing_description}\n\n"
                f"Do not repeat the same traversal path. "
                f"Use this context to approach the query differently and fill the identified gaps."
            )

        return mp_result
