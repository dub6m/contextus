"""
Tests for the WeightSystem.
"""

import traceback
from contextus import Node, NodeType, Edge, Graph, WeightSystem
from contextus.traversal import TraversalResult, MultiPassResult
from contextus.router import RouterResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_graph() -> tuple[Graph, Node, Node, Node, Edge, Edge]:
    g = Graph(name="TestGraph", description="Weight system test graph.")
    n1 = g.add_node(Node(label="A", type=NodeType.DEFINITION, body="node a", scope="scope a"))
    n2 = g.add_node(Node(label="B", type=NodeType.BEHAVIOR,   body="node b", scope="scope b"))
    n3 = g.add_node(Node(label="C", type=NodeType.CONSTRAINT, body="node c", scope="scope c"))
    e1 = g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["r1"], base_weight=0.8))
    e2 = g.add_edge(Edge(source_id=n2.id, target_id=n3.id, relations=["r2"], base_weight=0.6))
    return g, n1, n2, n3, e1, e2


def make_traversal(
    graph_name: str,
    edges: list[Edge],
    verified: bool,
    *,
    noise_ids: list[str] | None = None,
    missing_description: str = "",
) -> TraversalResult:
    return TraversalResult(
        query="test query",
        graph_name=graph_name,
        edges=edges,
        verified=verified,
        noise_ids=noise_ids or [],
        missing_description=missing_description,
    )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------

def test_construction_default_lr():
    ws = WeightSystem()
    assert ws.learning_rate == 0.1

def test_construction_custom_lr():
    ws = WeightSystem(learning_rate=0.3)
    assert ws.learning_rate == 0.3

def test_invalid_lr_raises():
    try:
        WeightSystem(learning_rate=0.0)
        assert False, "Should have raised"
    except ValueError:
        pass
    try:
        WeightSystem(learning_rate=1.1)
        assert False, "Should have raised"
    except ValueError:
        pass

def test_lr_of_one_is_valid():
    ws = WeightSystem(learning_rate=1.0)
    assert ws.learning_rate == 1.0


# ---------------------------------------------------------------------------
# Cold start — first observation sets derived_weight directly
# ---------------------------------------------------------------------------

def test_cold_start_verified_sets_derived_to_one():
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1, e2], verified=True))
    live_e1 = g.get_edge(e1.id)
    assert live_e1.derived_weight == 1.0

def test_cold_start_unverified_sets_derived_to_zero():
    """Unverified with noise_ids triggers a 0.0 penalty on noise edges."""
    g, n1, n2, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    # Both endpoints of e1 (n1, n2) are in noise_ids → Case 3, signal 0.0
    ws.observe(make_traversal(
        "TestGraph", [e1], verified=False,
        noise_ids=[n1.id, n2.id],
    ))
    live_e1 = g.get_edge(e1.id)
    assert live_e1.derived_weight == 0.0

def test_untouched_edge_stays_none():
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    # Only observe e1
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    live_e2 = g.get_edge(e2.id)
    assert len(live_e2.cluster_weights) == 0


# ---------------------------------------------------------------------------
# EMA update behaviour
# ---------------------------------------------------------------------------

def test_ema_verified_moves_weight_up():
    g, n1, n2, _, e1, _ = make_graph()
    ws = WeightSystem(learning_rate=0.2)
    ws.register(g)
    # Seed with 0.0 via noise-based penalty (both endpoints are noise)
    ws.observe(make_traversal(
        "TestGraph", [e1], verified=False,
        noise_ids=[n1.id, n2.id],
    ))
    assert g.get_edge(e1.id).derived_weight == 0.0
    # Now observe verified — should move up
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    dw = g.get_edge(e1.id).derived_weight
    assert dw > 0.0
    # expected: 0.0 * 0.8 + 1.0 * 0.2 = 0.2
    assert abs(dw - 0.2) < 1e-9

def test_ema_unverified_moves_weight_down():
    """Unverified with noise_ids penalises noise edges, pulling weight down."""
    g, n1, n2, _, e1, _ = make_graph()
    ws = WeightSystem(learning_rate=0.2)
    ws.register(g)
    # Seed with 1.0
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    assert g.get_edge(e1.id).derived_weight == 1.0
    # Now observe unverified with noise — should move down
    ws.observe(make_traversal(
        "TestGraph", [e1], verified=False,
        noise_ids=[n1.id, n2.id],
    ))
    dw = g.get_edge(e1.id).derived_weight
    assert dw < 1.0
    # expected: 1.0 * 0.8 + 0.0 * 0.2 = 0.8
    assert abs(dw - 0.8) < 1e-9

def test_repeated_verified_converges_toward_one():
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem(learning_rate=0.2)
    ws.register(g)
    for _ in range(50):
        ws.observe(make_traversal("TestGraph", [e1], verified=True))
    dw = g.get_edge(e1.id).derived_weight
    assert dw > 0.99

def test_repeated_unverified_converges_toward_zero():
    """Repeated noise-based unverified traversals converge toward zero."""
    g, n1, n2, _, e1, _ = make_graph()
    ws = WeightSystem(learning_rate=0.2)
    ws.register(g)
    # Seed high
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    for _ in range(50):
        ws.observe(make_traversal(
            "TestGraph", [e1], verified=False,
            noise_ids=[n1.id, n2.id],
        ))
    dw = g.get_edge(e1.id).derived_weight
    assert dw < 0.01

def test_lr_one_always_takes_latest_signal():
    """With lr=1.0, derived_weight is always exactly the latest signal."""
    g, n1, n2, _, e1, _ = make_graph()
    ws = WeightSystem(learning_rate=1.0)
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    assert g.get_edge(e1.id).derived_weight == 1.0
    # Unverified with noise → 0.0
    ws.observe(make_traversal(
        "TestGraph", [e1], verified=False,
        noise_ids=[n1.id, n2.id],
    ))
    assert g.get_edge(e1.id).derived_weight == 0.0
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    assert g.get_edge(e1.id).derived_weight == 1.0


# ---------------------------------------------------------------------------
# Base weight is never touched
# ---------------------------------------------------------------------------

def test_base_weight_never_modified():
    g, _, _, _, e1, _ = make_graph()
    original_base = e1.base_weight
    ws = WeightSystem(learning_rate=0.5)
    ws.register(g)
    for _ in range(20):
        ws.observe(make_traversal("TestGraph", [e1], verified=True))
    assert g.get_edge(e1.id).base_weight == original_base


# ---------------------------------------------------------------------------
# Unregistered graph is silently skipped
# ---------------------------------------------------------------------------

def test_unregistered_graph_skipped_silently():
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    # do NOT register g
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    # Edge should be untouched
    assert len(g.get_edge(e1.id).cluster_weights) == 0


# ---------------------------------------------------------------------------
# observe_router
# ---------------------------------------------------------------------------

def test_observe_router_updates_all_traversals():
    g1, n1, n2, _, e1, _ = make_graph()
    g2 = Graph(name="OtherGraph", description="second graph")
    n_a = g2.add_node(Node(label="X", type=NodeType.DEFINITION, body="x", scope="scope x"))
    n_b = g2.add_node(Node(label="Y", type=NodeType.BEHAVIOR,   body="y", scope="scope y"))
    e3  = g2.add_edge(Edge(source_id=n_a.id, target_id=n_b.id, relations=["r"], base_weight=0.5))

    ws = WeightSystem()
    ws.register(g1)
    ws.register(g2)

    t1 = make_traversal("TestGraph",  [e1], verified=True)
    t2 = make_traversal("OtherGraph", [e3], verified=False, noise_ids=[n_a.id, n_b.id])

    mp1 = MultiPassResult(query="test", graph_name="TestGraph", best=t1, passes_run=1, verified=True, all_passes=[t1])
    mp2 = MultiPassResult(query="test", graph_name="OtherGraph", best=t2, passes_run=1, verified=False, all_passes=[t2])

    rr = RouterResult(query="test", traversals=[mp1, mp2])
    ws.observe_router(rr)

    assert g1.get_edge(e1.id).derived_weight == 1.0
    assert g2.get_edge(e3.id).derived_weight == 0.0


# ---------------------------------------------------------------------------
# History logging
# ---------------------------------------------------------------------------

def test_history_records_each_observation():
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1],     verified=True))
    ws.observe(make_traversal("TestGraph", [e1, e2], verified=False))
    h = ws.history()
    assert len(h) == 2
    assert h[0].verified == True
    assert h[1].verified == False
    assert e2.id in h[1].edge_ids

def test_history_returns_copy():
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    h = ws.history()
    h.clear()
    assert len(ws.history()) == 1  # internal list not affected


# ---------------------------------------------------------------------------
# Edge stats
# ---------------------------------------------------------------------------

def test_edge_stats_returns_all_edges():
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    stats = ws.edge_stats("TestGraph")
    assert len(stats) == 2

def test_edge_stats_reflects_updates():
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    stats = {s["edge_id"]: s for s in ws.edge_stats("TestGraph")}
    assert -1 in stats[e1.id]["cluster_weights"]
    assert stats[e1.id]["cluster_weights"][-1] == 1.0

def test_edge_stats_unknown_graph_raises():
    ws = WeightSystem()
    try:
        ws.edge_stats("nonexistent")
        assert False
    except KeyError:
        pass


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_clears_derived_weights():
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1, e2], verified=True))
    assert len(g.get_edge(e1.id).cluster_weights) > 0
    ws.reset_derived_weights("TestGraph")
    assert len(g.get_edge(e1.id).cluster_weights) == 0
    assert len(g.get_edge(e2.id).cluster_weights) == 0

def test_reset_does_not_clear_history():
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    ws.reset_derived_weights("TestGraph")
    assert len(ws.history()) == 1


# ---------------------------------------------------------------------------
# New tests — three-case signal logic
# ---------------------------------------------------------------------------

def test_incomplete_graph_skips_update():
    """
    Case 2: unverified with missing_description but empty noise_ids.
    The Collector made sensible choices — the graph lacks needed nodes.
    derived_weight should remain None (no update at all).
    """
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal(
        "TestGraph", [e1, e2], verified=False,
        missing_description="Need a node covering regulatory constraints",
    ))
    assert len(g.get_edge(e1.id).cluster_weights) == 0
    assert len(g.get_edge(e2.id).cluster_weights) == 0


def test_noise_only_penalises_noise_edges():
    """
    Case 3: unverified with noise_ids populated.
    Only edges where *both* endpoints are noise nodes get signal 0.0.
    Other traversed edges remain unupdated.
    """
    g, n1, n2, n3, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    # Mark n2 and n3 as noise — e2 (n2→n3) has both endpoints as noise
    # e1 (n1→n2) has only one endpoint as noise → should be skipped
    ws.observe(make_traversal(
        "TestGraph", [e1, e2], verified=False,
        noise_ids=[n2.id, n3.id],
    ))
    # e2 connects two noise nodes → penalised
    assert g.get_edge(e2.id).derived_weight == 0.0
    # e1 has only target in noise → no update
    assert g.get_edge(e1.id).derived_weight is None


def test_mixed_missing_and_noise_applies_case3():
    """
    Result with both missing_description non-empty AND noise_ids non-empty.
    Should behave as Case 3: penalise noise edges, skip the rest.
    """
    g, n1, n2, n3, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal(
        "TestGraph", [e1, e2], verified=False,
        noise_ids=[n2.id, n3.id],
        missing_description="Missing economic impact analysis",
    ))
    # e2 (n2→n3) — both endpoints noise → penalised
    assert g.get_edge(e2.id).derived_weight == 0.0
    # e1 (n1→n2) — only one endpoint noise → skipped
    assert len(g.get_edge(e1.id).cluster_weights) == 0


def test_traversal_record_stores_verifier_details():
    """
    After observing, history records should contain missing_description
    and noise_ids from the TraversalResult.
    """
    g, n1, n2, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal(
        "TestGraph", [e1], verified=False,
        noise_ids=[n1.id, n2.id],
        missing_description="Need a regulation node",
    ))
    record = ws.history()[0]
    assert record.missing_description == "Need a regulation node"
    assert set(record.noise_ids) == {n1.id, n2.id}


# ---------------------------------------------------------------------------
# observe_multi tests
# ---------------------------------------------------------------------------

def test_observe_multi_updates_weights_from_best_only():
    """
    Only the best pass's edges should have weights updated.
    Intermediate pass edges should not.
    """
    g, n1, n2, n3, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)

    # Pass 1 (intermediate): uses e1, unverified
    pass1 = make_traversal("TestGraph", [e1], verified=False, missing_description="Missing C")
    # Pass 2 (best): uses e2, verified
    pass2 = make_traversal("TestGraph", [e2], verified=True)

    mpr = MultiPassResult(
        query="test",
        graph_name="TestGraph",
        best=pass2,
        all_passes=[pass1, pass2],
        passes_run=2,
        verified=True,
    )
    ws.observe_multi(mpr)

    # e2 from best pass should be updated (signal 1.0)
    assert g.get_edge(e2.id).derived_weight == 1.0
    # e1 from intermediate pass should NOT be updated
    assert len(g.get_edge(e1.id).cluster_weights) == 0


def test_observe_multi_logs_all_passes_to_history():
    """
    All passes should appear in history regardless of which is best.
    """
    g, n1, n2, n3, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)

    pass1 = make_traversal("TestGraph", [e1], verified=False, missing_description="Missing C")
    pass2 = make_traversal("TestGraph", [e2], verified=True)

    mpr = MultiPassResult(
        query="test",
        graph_name="TestGraph",
        best=pass2,
        all_passes=[pass1, pass2],
        passes_run=2,
        verified=True,
    )
    ws.observe_multi(mpr)

    h = ws.history()
    assert len(h) == 2  # both passes logged
    assert h[0].verified is False
    assert h[1].verified is True


# ---------------------------------------------------------------------------
# Cluster-aware tests
# ---------------------------------------------------------------------------

def test_observe_uses_cluster_label_from_clusterer():
    """After observing, edge weight should be stored under the cluster label."""
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    # At minimum, some weight should exist (cluster -1 for noise queries)
    live_e1 = g.get_edge(e1.id)
    assert len(live_e1.cluster_weights) > 0
    # The cluster label should be -1 (below threshold → noise)
    assert -1 in live_e1.cluster_weights


def test_observe_global_fallback_when_noise():
    """When query is noise (cluster -1), weight stored under -1."""
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    live_e1 = g.get_edge(e1.id)
    assert live_e1.cluster_weights.get(-1) == 1.0


def test_cluster_stats_returns_correct_structure():
    """cluster_stats() should return expected keys."""
    ws = WeightSystem()
    stats = ws.cluster_stats()
    assert "cluster_count" in stats
    assert "total_queries" in stats
    assert "queries_per_cluster" in stats
    assert stats["cluster_count"] == 0
    assert stats["total_queries"] == 0


def test_reset_clears_all_cluster_weights():
    """After reset, cluster_weights should be empty for all edges."""
    g, _, _, _, e1, e2 = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1, e2], verified=True))
    # Both edges should have weights
    assert len(g.get_edge(e1.id).cluster_weights) > 0
    ws.reset_derived_weights("TestGraph")
    assert len(g.get_edge(e1.id).cluster_weights) == 0
    assert len(g.get_edge(e2.id).cluster_weights) == 0


def test_history_stores_cluster_label():
    """After observe, history record should have cluster_label set."""
    g, _, _, _, e1, _ = make_graph()
    ws = WeightSystem()
    ws.register(g)
    ws.observe(make_traversal("TestGraph", [e1], verified=True))
    record = ws.history()[0]
    assert hasattr(record, "cluster_label")
    assert isinstance(record.cluster_label, int)


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_construction_default_lr,
        test_construction_custom_lr,
        test_invalid_lr_raises,
        test_lr_of_one_is_valid,
        test_cold_start_verified_sets_derived_to_one,
        test_cold_start_unverified_sets_derived_to_zero,
        test_untouched_edge_stays_none,
        test_ema_verified_moves_weight_up,
        test_ema_unverified_moves_weight_down,
        test_repeated_verified_converges_toward_one,
        test_repeated_unverified_converges_toward_zero,
        test_lr_one_always_takes_latest_signal,
        test_base_weight_never_modified,
        test_unregistered_graph_skipped_silently,
        test_observe_router_updates_all_traversals,
        test_history_records_each_observation,
        test_history_returns_copy,
        test_edge_stats_returns_all_edges,
        test_edge_stats_reflects_updates,
        test_edge_stats_unknown_graph_raises,
        test_reset_clears_derived_weights,
        test_reset_does_not_clear_history,
        # Three-case signal tests
        test_incomplete_graph_skips_update,
        test_noise_only_penalises_noise_edges,
        test_mixed_missing_and_noise_applies_case3,
        test_traversal_record_stores_verifier_details,
        # observe_multi tests
        test_observe_multi_updates_weights_from_best_only,
        test_observe_multi_logs_all_passes_to_history,
        # cluster-aware tests
        test_observe_uses_cluster_label_from_clusterer,
        test_observe_global_fallback_when_noise,
        test_cluster_stats_returns_correct_structure,
        test_reset_clears_all_cluster_weights,
        test_history_stores_cluster_label,
    ]

    passed, failed = [], []
    for t in tests:
        try:
            t()
            passed.append(t.__name__)
        except Exception:
            failed.append((t.__name__, traceback.format_exc()))

    print("\n" + str(len(passed)) + "/" + str(len(tests)) + " passed")
    for name, tb in failed:
        print("\nFAIL: " + name + "\n" + tb)
