from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import Graph
    from .traversal import TraversalResult, MultiPassResult
    from .router import RouterResult


# ---------------------------------------------------------------------------
# Traversal record — one entry per traversal observed
# ---------------------------------------------------------------------------

@dataclass
class TraversalRecord:
    """
    A single observation logged by the WeightSystem.
    Kept for auditability — not used in weight calculation directly
    (that's done incrementally via EMA), but useful for debugging
    and future formula improvements.
    """
    query:               str
    graph_name:          str
    edge_ids:            list[str]
    verified:            bool
    missing_description: str       = ""
    noise_ids:           list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Weight System
# ---------------------------------------------------------------------------

class WeightSystem:
    """
    Observes TraversalResult and RouterResult outcomes and updates the
    derived_weight on edges in their source graphs via an Exponential
    Moving Average (EMA).

    Formula
    -------
    On each observation of an edge in a traversal:

        signal = 1.0  if the traversal was verified (complete, no noise)
                 0.0  if the traversal was not verified

        if edge.derived_weight is None:
            edge.derived_weight = signal          # cold start: first observation sets it directly
        else:
            edge.derived_weight = edge.derived_weight * (1 - lr) + signal * lr

    This means:
    - An edge that consistently appears in verified traversals trends toward 1.0
    - An edge that consistently appears in unverified traversals trends toward 0.0
    - An edge never traversed is never touched (derived_weight stays None)
    - The base_weight is never modified — it remains the human-defined prior

    Parameters
    ----------
    learning_rate : float (0.0 – 1.0)
        Controls how fast new evidence overwrites old.
        High (e.g. 0.3) = recent traversals matter more, adapts quickly.
        Low  (e.g. 0.05) = history is weighted heavily, adapts slowly.
        Default 0.1 is a conservative starting point.

    graphs : dict[str, Graph]
        name -> Graph mapping. The WeightSystem needs to look up edges
        by id across graphs. Pass all graphs you want it to manage.
        Graphs can be added/removed after construction.
    """

    def __init__(
        self,
        learning_rate: float = 0.1,
    ):
        if not (0.0 < learning_rate <= 1.0):
            raise ValueError("learning_rate must be in (0.0, 1.0].")
        self.learning_rate = learning_rate
        self._graphs: dict[str, "Graph"] = {}
        self._history: list[TraversalRecord] = []

    # ------------------------------------------------------------------
    # Graph registry
    # ------------------------------------------------------------------

    def register(self, graph: "Graph") -> None:
        self._graphs[graph.name] = graph

    def unregister(self, name: str) -> None:
        if name not in self._graphs:
            raise KeyError(f"No graph named '{name}' registered in WeightSystem.")
        del self._graphs[name]

    # ------------------------------------------------------------------
    # Observation entry points
    # ------------------------------------------------------------------

    def observe(self, result: "TraversalResult") -> None:
        """
        Update edge weights from a single TraversalResult.
        Call this after every traversal — verified or not.

        Three-case signal logic:
        - Case 1 (verified): signal = 1.0 for all edges.
        - Case 2 (unverified, incomplete graph only): skip update entirely.
          The Collector made sensible choices but the graph lacks needed nodes.
        - Case 3 (unverified, noise present): signal = 0.0 only for edges
          where both endpoints are noise nodes; skip all other edges.
        """
        graph = self._graphs.get(result.graph_name)
        if graph is None:
            return  # graph not registered with this WeightSystem — skip silently

        # Case 1 — Verified: reward all traversed edges
        if result.verified:
            for edge in result.edges:
                try:
                    live_edge = graph.get_edge(edge.id)
                    self._update_edge(live_edge, 1.0)
                except KeyError:
                    continue
        # Case 3 — Noise present (may also have missing_description):
        # penalise only edges connecting two noise nodes, skip the rest
        elif result.noise_ids:
            noise_set = set(result.noise_ids)
            for edge in result.edges:
                try:
                    live_edge = graph.get_edge(edge.id)
                except KeyError:
                    continue
                if edge.source_id in noise_set and edge.target_id in noise_set:
                    self._update_edge(live_edge, 0.0)
                # else: skip update — these edges were fine
        # Case 2 — Incomplete graph (missing_description but no noise):
        # skip update entirely — do not penalise
        elif result.missing_description:
            pass
        # Fallback — unverified with no verifier detail (shouldn't happen,
        # but mirrors old behaviour for safety)
        else:
            for edge in result.edges:
                try:
                    live_edge = graph.get_edge(edge.id)
                    self._update_edge(live_edge, 0.0)
                except KeyError:
                    continue

        self._history.append(TraversalRecord(
            query=result.query,
            graph_name=result.graph_name,
            edge_ids=[e.id for e in result.edges],
            verified=result.verified,
            missing_description=result.missing_description,
            noise_ids=list(result.noise_ids),
        ))

    def observe_multi(self, result: "MultiPassResult") -> None:
        """
        Observes all passes within a MultiPassResult.
        Only the best result's edges are used for weight updates.
        Intermediate passes are logged to history but do not update weights.
        """
        # Log all passes to history
        for pass_result in result.all_passes:
            self._history.append(TraversalRecord(
                query=pass_result.query,
                graph_name=pass_result.graph_name,
                edge_ids=[e.id for e in pass_result.edges],
                verified=pass_result.verified,
                missing_description=pass_result.missing_description,
                noise_ids=list(pass_result.noise_ids),
            ))

        # Only update weights from the best pass
        if result.best is not None:
            # Call observe but we already logged history above,
            # so we do weight updates manually here
            graph = self._graphs.get(result.best.graph_name)
            if graph is None:
                return

            best = result.best
            if best.verified:
                for edge in best.edges:
                    try:
                        live_edge = graph.get_edge(edge.id)
                        self._update_edge(live_edge, 1.0)
                    except KeyError:
                        continue
            elif best.noise_ids:
                noise_set = set(best.noise_ids)
                for edge in best.edges:
                    try:
                        live_edge = graph.get_edge(edge.id)
                    except KeyError:
                        continue
                    if edge.source_id in noise_set and edge.target_id in noise_set:
                        self._update_edge(live_edge, 0.0)
            elif best.missing_description:
                pass  # Case 2: skip
            else:
                for edge in best.edges:
                    try:
                        live_edge = graph.get_edge(edge.id)
                        self._update_edge(live_edge, 0.0)
                    except KeyError:
                        continue

    def observe_router(self, result: "RouterResult") -> None:
        """
        Convenience method — observes all traversals within a RouterResult.
        """
        for traversal in result.traversals:
            self.observe_multi(traversal)

    # ------------------------------------------------------------------
    # Weight update
    # ------------------------------------------------------------------

    def _update_edge(self, edge: object, signal: float) -> None:
        """
        Apply one EMA step to an edge's derived_weight.
        Cold start: if derived_weight is None, set it directly to signal.
        """
        if edge.derived_weight is None:
            edge.derived_weight = signal
        else:
            edge.derived_weight = (
                edge.derived_weight * (1 - self.learning_rate)
                + signal * self.learning_rate
            )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def history(self) -> list[TraversalRecord]:
        """Full log of all observations."""
        return list(self._history)

    def edge_stats(self, graph_name: str) -> list[dict]:
        """
        Returns a summary of all edges in a graph with their current weights.
        Useful for debugging and understanding what the system has learned.
        """
        graph = self._graphs.get(graph_name)
        if graph is None:
            raise KeyError(f"No graph named '{graph_name}' registered.")

        stats = []
        for edge in graph.all_edges():
            stats.append({
                "edge_id":        edge.id,
                "source":         edge.source_id,
                "target":         edge.target_id,
                "relations":      edge.relations,
                "base_weight":    edge.base_weight,
                "derived_weight": edge.derived_weight,
                "effective_weight_a05": edge.effective_weight(alpha=0.5),
            })
        return stats

    def reset_derived_weights(self, graph_name: str) -> None:
        """
        Clears all derived weights for a graph, reverting edges to base_weight only.
        Does not clear history.
        """
        graph = self._graphs.get(graph_name)
        if graph is None:
            raise KeyError(f"No graph named '{graph_name}' registered.")
        for edge in graph.all_edges():
            edge.derived_weight = None
