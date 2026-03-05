from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

from .graph import Graph
from .llm import LLMClient
from .traversal import TraversalEngine, TraversalResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RouterResult:
    """
    Aggregated result across all graphs the router dispatched to.

    Each graph that was queried contributes a TraversalResult.
    The router also records which graphs were skipped and why.
    """
    query:           str
    traversals:      list[TraversalResult]  = field(default_factory=list)
    skipped_graphs:  list[str]              = field(default_factory=list)  # graph names
    dispatch_reason: str                    = ""

    @property
    def verified(self) -> bool:
        """True only if every dispatched traversal came back verified."""
        return bool(self.traversals) and all(t.verified for t in self.traversals)

    def all_nodes(self):
        """Deduplicated nodes across all traversal results."""
        seen = set()
        nodes = []
        for t in self.traversals:
            for n in t.nodes:
                if n.id not in seen:
                    seen.add(n.id)
                    nodes.append(n)
        return nodes

    def all_edges(self):
        """Deduplicated edges across all traversal results."""
        seen = set()
        edges = []
        for t in self.traversals:
            for e in t.edges:
                if e.id not in seen:
                    seen.add(e.id)
                    edges.append(e)
        return edges

    def summary(self) -> str:
        lines = [
            f"Query          : {self.query}",
            f"Graphs queried : {len(self.traversals)}",
            f"Graphs skipped : {len(self.skipped_graphs)} {self.skipped_graphs}",
            f"Overall verified: {self.verified}",
            f"Total nodes    : {len(self.all_nodes())}",
            f"Dispatch reason: {self.dispatch_reason}",
        ]
        for t in self.traversals:
            lines.append(f"\n  [{t.query[:40]}...]")
            for n in t.nodes:
                lines.append(f"    - {n.summary()}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ROUTER_DISPATCH_SYSTEM = """
You are the Router — a dispatch agent for a multi-graph knowledge retrieval system.

Your job is to decide which graphs are relevant to a query, given a summary of each graph's contents.

You will be given:
- A query
- A list of graphs, each with: name, description, and a list of node summaries

Rules:
1. Select ONLY graphs whose content is necessary to satisfy the query.
2. A graph is relevant if it contains nodes that would be needed to answer or execute the query.
3. It is correct to select zero graphs if none are relevant.
4. It is correct to select all graphs if all are relevant.
5. Do not select a graph just because it is loosely related — only if it is genuinely needed.

Respond ONLY with a JSON object in this exact format (no markdown, no explanation):
{
  "selected": ["<graph_name>", ...],
  "reason": "<one sentence explaining the dispatch decision>"
}
""".strip()

ROUTER_MERGE_SYSTEM = """
You are the Router — a merge agent for a multi-graph knowledge retrieval system.

Multiple graphs were queried and each returned a subgraph. Your job is to identify
any nodes that are REDUNDANT across graphs (cover the same concept) so they can be deduplicated.

You will be given:
- A query
- Nodes from multiple graphs, each tagged with their graph name

Respond ONLY with a JSON object in this exact format (no markdown, no explanation):
{
  "redundant_pairs": [["<node_id_a>", "<node_id_b>"], ...],
  "note": "<one sentence>"
}

A redundant pair means both nodes cover the same concept and only one is needed.
If there are no redundancies, return an empty list.
""".strip()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Router:
    """
    Dispatches a query to one or more graphs, runs traversal on each,
    and merges the results into a single RouterResult.

    Graphs are registered with the router. The router uses each graph's
    auto-generated summary to decide which graphs are relevant to a query.

    Parameters
    ----------
    llm       : any LLMClient — same provider used for traversal
    max_depth : passed through to each TraversalEngine
    alpha     : edge weight blend factor, passed through to each TraversalEngine
    """

    def __init__(
        self,
        llm:       LLMClient,
        max_depth: int   = 10,
        alpha:     float = 0.5,
    ):
        self.llm       = llm
        self.max_depth = max_depth
        self.alpha     = alpha
        self._graphs:  dict[str, Graph] = {}   # name -> Graph

    # ------------------------------------------------------------------
    # Graph registry
    # ------------------------------------------------------------------

    def register(self, graph: Graph) -> None:
        """Add a graph to the router's registry."""
        if graph.name in self._graphs:
            raise ValueError(
                f"A graph named '{graph.name}' is already registered. "
                "Graph names must be unique."
            )
        self._graphs[graph.name] = graph

    def unregister(self, name: str) -> None:
        if name not in self._graphs:
            raise KeyError(f"No graph named '{name}' is registered.")
        del self._graphs[name]

    def registered_graphs(self) -> list[str]:
        return list(self._graphs.keys())

    def get_graph(self, name: str) -> Graph:
        if name not in self._graphs:
            raise KeyError(f"No graph named '{name}' is registered.")
        return self._graphs[name]

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def query(self, query: str) -> RouterResult:
        result = RouterResult(query=query)

        if not self._graphs:
            result.dispatch_reason = "No graphs registered."
            return result

        # Step 1 — decide which graphs to dispatch to
        selected_names, reason = self._dispatch(query)
        result.dispatch_reason = reason

        skipped = [n for n in self._graphs if n not in selected_names]
        result.skipped_graphs = skipped

        if not selected_names:
            return result

        # Step 2 — run traversal on each selected graph
        for name in selected_names:
            graph = self._graphs[name]
            engine = TraversalEngine(
                graph=graph,
                llm=self.llm,
                max_depth=self.max_depth,
                alpha=self.alpha,
            )
            traversal = engine.query(query, graph_name=name)
            result.traversals.append(traversal)

        # Step 3 — merge results if more than one graph was queried
        if len(result.traversals) > 1:
            result = self._merge(query, result)

        return result

    # ------------------------------------------------------------------
    # Dispatch decision
    # ------------------------------------------------------------------

    def _dispatch(self, query: str) -> tuple[list[str], str]:
        """Returns (list of selected graph names, reason string)."""
        graph_summaries = "\n\n".join(
            f'Graph name: "{name}"\n{graph.summary()}'
            for name, graph in self._graphs.items()
        )
        user_prompt = f'Query: "{query}"\n\nAvailable graphs:\n\n{graph_summaries}'

        raw = self.llm.complete(system=ROUTER_DISPATCH_SYSTEM, user=user_prompt)
        parsed = _parse_json(raw.content)

        if not parsed:
            # Fallback: dispatch to all graphs
            return list(self._graphs.keys()), "Dispatch parsing failed — defaulting to all graphs."

        selected = [
            name for name in parsed.get("selected", [])
            if name in self._graphs
        ]
        reason = parsed.get("reason", "")
        return selected, reason

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def _merge(self, query: str, result: RouterResult) -> RouterResult:
        """
        Identifies redundant nodes across traversal results and removes duplicates.
        Keeps the first occurrence (by traversal order) when a redundancy is found.
        """
        all_nodes = result.all_nodes()
        if not all_nodes:
            return result

        # Tag nodes with their source graph for the LLM
        node_list = []
        for t_idx, t in enumerate(result.traversals):
            graph_name = t.graph_name
            for n in t.nodes:
                node_list.append(
                    f'  {{"id": "{n.id}", "graph": "{graph_name}", '
                    f'"type": "{n.type.value}", "label": "{n.label}", "scope": "{n.scope}"}}'
                )

        user_prompt = (
            f'Query: "{query}"\n\n'
            f'Nodes from all queried graphs:\n[\n' + "\n".join(node_list) + "\n]"
        )

        raw = self.llm.complete(system=ROUTER_MERGE_SYSTEM, user=user_prompt)
        parsed = _parse_json(raw.content)

        if not parsed:
            return result  # merge failed — return unmerged

        redundant_pairs = parsed.get("redundant_pairs", [])
        if not redundant_pairs:
            return result

        # For each redundant pair, drop the second node (keep the first)
        ids_to_remove: set[str] = set()
        for pair in redundant_pairs:
            if len(pair) == 2:
                ids_to_remove.add(pair[1])

        # Remove from each traversal result
        for t in result.traversals:
            t.nodes = [n for n in t.nodes if n.id not in ids_to_remove]
            t.edges = [
                e for e in t.edges
                if e.source_id not in ids_to_remove
                and e.target_id not in ids_to_remove
            ]

        return result

        sample_node_id = traversal.nodes[0].id
        for name, graph in self._graphs.items():
            try:
                graph.get_node(sample_node_id)
                return name
            except KeyError:
                continue
        return "unknown"


# ---------------------------------------------------------------------------
# Utility (duplicated from traversal.py to keep router self-contained)
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict | None:
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
