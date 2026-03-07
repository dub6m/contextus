"""
Query embedding and clustering for query-conditioned edge weights.

Uses sentence-transformers (all-MiniLM-L6-v2) for local embeddings
and HDBSCAN for automatic cluster discovery.
"""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Query Embedder
# ---------------------------------------------------------------------------

class QueryEmbedder:
    """
    Lightweight local embedding model for query clustering.
    Uses sentence-transformers all-MiniLM-L6-v2.
    No API calls required.

    The model is lazy-loaded on first use to avoid slowing down
    library import for users who don't use the weight system.
    """

    def __init__(self):
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, text: str) -> list[float]:
        """Returns a 384-dimensional embedding for the given text."""
        self._load_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds multiple texts efficiently in one call."""
        self._load_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embeddings]


# ---------------------------------------------------------------------------
# Query Clusterer
# ---------------------------------------------------------------------------

class QueryClusterer:
    """
    Maintains a growing set of query embeddings and clusters them
    using HDBSCAN. Clusters are recomputed when new queries are added.

    Parameters
    ----------
    min_cluster_size : int (default 3)
        Minimum number of similar queries to form a cluster.
        Queries that don't belong to any cluster are marked as noise (label -1).
    """

    def __init__(self, min_cluster_size: int = 3):
        self._min_cluster_size = min_cluster_size
        self._embedder = QueryEmbedder()
        self._queries: list[str] = []          # query strings
        self._query_ids: list[str] = []        # corresponding IDs
        self._embeddings: list[list[float]] = []
        self._labels: list[int] = []           # cluster labels per query

    def add_query(self, query: str, query_id: str) -> int:
        """
        Add a query to the clusterer. Returns the cluster label assigned
        to this query. Returns -1 if the query is noise (no cluster yet).
        Reclusters all queries after adding.
        """
        embedding = self._embedder.embed(query)
        self._queries.append(query)
        self._query_ids.append(query_id)
        self._embeddings.append(embedding)
        self._recluster()
        return self._labels[-1]

    def get_cluster(self, query: str) -> int:
        """
        Returns the cluster label for a query string.
        If the query has been added, returns its stored label.
        If not added, embeds it and finds nearest cluster via
        distance to cluster centroids.
        Returns -1 if no suitable cluster exists.
        """
        # Check if query already exists
        for i, q in enumerate(self._queries):
            if q == query:
                return self._labels[i]

        # Not seen before — find nearest cluster
        if not self._labels or self.cluster_count() == 0:
            return -1

        embedding = np.array(self._embedder.embed(query))
        embeddings_arr = np.array(self._embeddings)
        labels_arr = np.array(self._labels)

        # Compute centroid of each cluster
        unique_labels = set(labels_arr)
        unique_labels.discard(-1)
        if not unique_labels:
            return -1

        best_label = -1
        best_dist = float("inf")
        for label in unique_labels:
            mask = labels_arr == label
            centroid = embeddings_arr[mask].mean(axis=0)
            dist = np.linalg.norm(embedding - centroid)
            if dist < best_dist:
                best_dist = dist
                best_label = label

        return int(best_label)

    def cluster_count(self) -> int:
        """Number of clusters currently identified (excluding noise)."""
        if not self._labels:
            return 0
        unique = set(self._labels)
        unique.discard(-1)
        return len(unique)

    def queries_in_cluster(self, cluster_label: int) -> list[str]:
        """Returns all query strings assigned to a given cluster label."""
        return [
            q for q, lbl in zip(self._queries, self._labels)
            if lbl == cluster_label
        ]

    def _recluster(self) -> None:
        """Runs HDBSCAN over all stored embeddings."""
        n = len(self._embeddings)
        # HDBSCAN needs at least min_cluster_size * 2 points to form clusters
        if n < self._min_cluster_size * 2:
            self._labels = [-1] * n
            return

        import hdbscan

        embeddings_arr = np.array(self._embeddings)
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self._min_cluster_size,
            metric="euclidean",
        )
        clusterer.fit(embeddings_arr)
        self._labels = clusterer.labels_.tolist()
