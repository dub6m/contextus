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
    cluster_label:       int       = -1


# ---------------------------------------------------------------------------
# Weight System
# ---------------------------------------------------------------------------

class WeightSystem:
    """
    Observes TraversalResult and RouterResult outcomes and updates
    per-cluster derived weights on edges via an Exponential Moving Average (EMA).

    Query clustering is automatic: each observed query is embedded locally
    (sentence-transformers all-MiniLM-L6-v2) and clustered via HDBSCAN.
    Similar queries share derived weights; dissimilar queries do not interfere.

    Formula
    -------
    On each observation of an edge in a traversal with cluster_label C:

        signal = 1.0  if the traversal was verified (complete, no noise)
                 0.0  if the traversal was not verified

        current = edge.cluster_weights.get(C)
        if current is None:
            edge.cluster_weights[C] = signal     # cold start
        else:
            edge.cluster_weights[C] = current * (1 - lr) + signal * lr

    This means:
    - An edge useful for cluster-0 queries trends toward 1.0 *for cluster 0*
    - The same edge may trend toward 0.0 for cluster 1 if it causes noise there
    - Noise queries (cluster -1) update a global fallback weight
    - Edges never traversed for a cluster have no weight for that cluster

    Parameters
    ----------
    learning_rate : float (0.0 – 1.0)
        Controls how fast new evidence overwrites old.
    min_cluster_size : int
        Minimum queries to form a cluster (passed to HDBSCAN).
    """

    def __init__(
        self,
        learning_rate:    float = 0.1,
        min_cluster_size: int   = 3,
    ):
        if not (0.0 < learning_rate <= 1.0):
            raise ValueError("learning_rate must be in (0.0, 1.0].")
        self.learning_rate    = learning_rate
        self._graphs: dict[str, "Graph"] = {}
        self._history: list[TraversalRecord] = []

        from .embeddings import QueryClusterer, QueryEmbedder
        self._clusterer = QueryClusterer(min_cluster_size=min_cluster_size)
        self._embedder  = QueryEmbedder()  # lazy loaded

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

        # Get cluster label for this query
        import uuid
        cluster_label = self._clusterer.add_query(result.query, str(uuid.uuid4()))

        self._apply_signal(graph, result, cluster_label)

        self._history.append(TraversalRecord(
            query=result.query,
            graph_name=result.graph_name,
            edge_ids=[e.id for e in result.edges],
            verified=result.verified,
            missing_description=result.missing_description,
            noise_ids=list(result.noise_ids),
            cluster_label=cluster_label,
        ))

    def observe_multi(self, result: "MultiPassResult") -> None:
        """
        Observes all passes within a MultiPassResult.
        Only the best result's edges are used for weight updates.
        Intermediate passes are logged to history but do not update weights.
        """
        # Get cluster label for this query (add once, not per pass)
        import uuid
        cluster_label = self._clusterer.add_query(result.query, str(uuid.uuid4()))

        # Log all passes to history
        for pass_result in result.all_passes:
            self._history.append(TraversalRecord(
                query=pass_result.query,
                graph_name=pass_result.graph_name,
                edge_ids=[e.id for e in pass_result.edges],
                verified=pass_result.verified,
                missing_description=pass_result.missing_description,
                noise_ids=list(pass_result.noise_ids),
                cluster_label=cluster_label,
            ))

        # Only update weights from the best pass
        if result.best is not None:
            graph = self._graphs.get(result.best.graph_name)
            if graph is None:
                return
            self._apply_signal(graph, result.best, cluster_label)

    def observe_router(self, result: "RouterResult") -> None:
        """
        Convenience method — observes all traversals within a RouterResult.
        """
        for traversal in result.traversals:
            self.observe_multi(traversal)

    # ------------------------------------------------------------------
    # Signal application (shared logic)
    # ------------------------------------------------------------------

    def _apply_signal(
        self, graph: "Graph", result: "TraversalResult", cluster_label: int
    ) -> None:
        """Apply the three-case signal logic to edge weights."""
        # Case 1 — Verified: reward all traversed edges
        if result.verified:
            for edge in result.edges:
                try:
                    live_edge = graph.get_edge(edge.id)
                    self._update_edge(live_edge, 1.0, cluster_label)
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
                    self._update_edge(live_edge, 0.0, cluster_label)
                # else: skip update — these edges were fine
        # Case 2 — Incomplete graph (missing_description but no noise):
        # skip update entirely — do not penalise
        elif result.missing_description:
            pass
        # Fallback — unverified with no verifier detail
        else:
            for edge in result.edges:
                try:
                    live_edge = graph.get_edge(edge.id)
                    self._update_edge(live_edge, 0.0, cluster_label)
                except KeyError:
                    continue

    # ------------------------------------------------------------------
    # Weight update
    # ------------------------------------------------------------------

    def _update_edge(self, edge: object, signal: float, cluster_label: int = -1) -> None:
        """
        Apply one EMA step to an edge's weight for the given cluster.
        Cold start: if no weight exists for this cluster, set directly to signal.
        """
        current = edge.cluster_weights.get(cluster_label)
        if current is None:
            edge.update_cluster_weight(cluster_label, signal)
        else:
            new_weight = current * (1 - self.learning_rate) + signal * self.learning_rate
            edge.update_cluster_weight(cluster_label, new_weight)

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
                "cluster_weights": dict(edge.cluster_weights),
                "effective_weight_a05_global": edge.effective_weight(alpha=0.5, cluster_label=-1),
            })
        return stats

    def reset_derived_weights(self, graph_name: str) -> None:
        """
        Clears all cluster weights for a graph, reverting edges to base_weight only.
        Does not clear history.
        """
        graph = self._graphs.get(graph_name)
        if graph is None:
            raise KeyError(f"No graph named '{graph_name}' registered.")
        for edge in graph.all_edges():
            edge.cluster_weights.clear()

    def cluster_stats(self) -> dict:
        """
        Returns information about the current query clustering state.
        Useful for diagnostics.
        """
        return {
            "cluster_count":   self._clusterer.cluster_count(),
            "total_queries":   len(self._clusterer._queries),
            "queries_per_cluster": {
                label: self._clusterer.queries_in_cluster(label)
                for label in range(self._clusterer.cluster_count())
            }
        }
