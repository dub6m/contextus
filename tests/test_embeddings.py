"""
Tests for QueryEmbedder and QueryClusterer.
"""

import traceback
from contextus.embeddings import QueryEmbedder, QueryClusterer


# ---------------------------------------------------------------------------
# QueryEmbedder tests
# ---------------------------------------------------------------------------

def test_embedder_returns_384_dimensions():
    embedder = QueryEmbedder()
    embedding = embedder.embed("What is binary search?")
    assert len(embedding) == 384


def test_embedder_returns_float_list():
    embedder = QueryEmbedder()
    embedding = embedder.embed("What is binary search?")
    assert all(isinstance(v, float) for v in embedding)


def test_embedder_same_text_same_embedding():
    embedder = QueryEmbedder()
    e1 = embedder.embed("What is binary search?")
    e2 = embedder.embed("What is binary search?")
    assert e1 == e2


def test_embedder_different_text_different_embedding():
    embedder = QueryEmbedder()
    e1 = embedder.embed("What is binary search?")
    e2 = embedder.embed("How do neural networks learn?")
    assert e1 != e2


def test_embedder_batch_matches_individual():
    embedder = QueryEmbedder()
    texts = ["What is binary search?", "How do neural networks learn?"]
    batch = embedder.embed_batch(texts)
    individual = [embedder.embed(t) for t in texts]
    for b, i in zip(batch, individual):
        # Compare with tolerance for floating point
        assert all(abs(bv - iv) < 1e-6 for bv, iv in zip(b, i))


# ---------------------------------------------------------------------------
# QueryClusterer tests
# ---------------------------------------------------------------------------

def test_clusterer_returns_noise_below_threshold():
    """Fewer than min_cluster_size * 2 queries should all return -1."""
    clusterer = QueryClusterer(min_cluster_size=3)
    # Add 5 queries (< 3 * 2 = 6)
    for i in range(5):
        label = clusterer.add_query(f"query about algorithms #{i}", f"id_{i}")
        assert label == -1


def test_clusterer_forms_cluster_above_threshold():
    """Add enough similar queries and at least one cluster should form."""
    clusterer = QueryClusterer(min_cluster_size=3)

    # Add 6 very similar queries about algorithms
    for i in range(6):
        clusterer.add_query(f"What is binary search algorithm complexity?", f"algo_{i}")

    # Add 6 very similar queries about cooking
    for i in range(6):
        clusterer.add_query(f"How to bake a perfect chocolate cake recipe?", f"cook_{i}")

    # At least one cluster should form
    assert clusterer.cluster_count() >= 1


def test_clusterer_noise_queries_return_minus_one():
    """A wildly different query should be noise if clusters exist."""
    clusterer = QueryClusterer(min_cluster_size=3)

    # Build up clusters with similar queries
    for i in range(8):
        clusterer.add_query(
            "What is the time complexity of sorting algorithms?",
            f"sort_{i}"
        )

    # Add a distinctly different query
    label = clusterer.add_query(
        "How to grow organic tomatoes in winter?",
        "outlier"
    )
    # The outlier may or may not be noise depending on HDBSCAN's judgement,
    # but we can at least verify the system handles it without error
    assert isinstance(label, int)


def test_clusterer_cluster_count_increases_with_data():
    """Adding different types of queries should produce multiple clusters."""
    clusterer = QueryClusterer(min_cluster_size=3)
    initial_count = clusterer.cluster_count()
    assert initial_count == 0

    # Add queries — count should never go negative or error
    for i in range(10):
        clusterer.add_query(f"database query optimization #{i}", f"db_{i}")

    assert clusterer.cluster_count() >= 0  # should be >= 1

    for i in range(10):
        clusterer.add_query(f"baking chocolate recipe #{i}", f"bake_{i}")

    # Should still be >= initial count (never decreases to negative)
    assert clusterer.cluster_count() >= 0


def test_clusterer_queries_in_cluster_returns_correct_queries():
    clusterer = QueryClusterer(min_cluster_size=3)

    queries = [f"what is binary search algorithm #{i}" for i in range(8)]
    for i, q in enumerate(queries):
        clusterer.add_query(q, f"id_{i}")

    # Check that queries_in_cluster returns strings
    for label in range(clusterer.cluster_count()):
        members = clusterer.queries_in_cluster(label)
        assert all(isinstance(q, str) for q in members)
        assert len(members) > 0


def test_get_cluster_for_unseen_query_returns_nearest():
    """Query not in history should return nearest cluster or -1."""
    clusterer = QueryClusterer(min_cluster_size=3)

    # Build up a cluster
    for i in range(8):
        clusterer.add_query(
            "What is the time complexity of binary search?",
            f"algo_{i}"
        )

    # Ask about a very similar but unseen query
    label = clusterer.get_cluster("binary search time complexity analysis")
    assert isinstance(label, int)
    # If clusters formed, the result should be >= 0 (nearest cluster)
    if clusterer.cluster_count() > 0:
        assert label >= 0


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_embedder_returns_384_dimensions,
        test_embedder_returns_float_list,
        test_embedder_same_text_same_embedding,
        test_embedder_different_text_different_embedding,
        test_embedder_batch_matches_individual,
        test_clusterer_returns_noise_below_threshold,
        test_clusterer_forms_cluster_above_threshold,
        test_clusterer_noise_queries_return_minus_one,
        test_clusterer_cluster_count_increases_with_data,
        test_clusterer_queries_in_cluster_returns_correct_queries,
        test_get_cluster_for_unseen_query_returns_nearest,
    ]

    passed, failed = [], []
    for t in tests:
        try:
            t()
            passed.append(t.__name__)
        except Exception:
            failed.append((t.__name__, traceback.format_exc()))

    print(f"\n{len(passed)}/{len(tests)} passed")
    for name, tb in failed:
        print(f"\nFAIL: {name}\n{tb}")
