"""
Deep integration tests for Contextus.

These tests require a real CEREBRAS_API_KEY and run against a real LLM.
All tests are decorated with @requires_api and are skipped automatically
when the key is not present — they never break the CI suite for users
without a key.

Non-determinism is expected. Tests assert structural invariants and
directional trends rather than exact outputs.
"""
from __future__ import annotations

import os
import pytest

from contextus import (
    Node,
    NodeType,
    Edge,
    Graph,
    CerebrasClient,
    MultiPassEngine,
    MultiPassResult,
    WeightSystem,
    Router,
    RouterResult,
)


# ---------------------------------------------------------------------------
# Skip marker — applied to every test in this file
# ---------------------------------------------------------------------------

CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
requires_api = pytest.mark.skipif(
    not CEREBRAS_API_KEY,
    reason="CEREBRAS_API_KEY not set",
)


# ---------------------------------------------------------------------------
# Graph fixture — recurrence relations graph derived from lecture material
# ---------------------------------------------------------------------------

def build_recurrence_graph() -> Graph:
    g = Graph(
        name="RecurrenceRelations",
        description="Core concepts needed to analyse the running time of recursive algorithms.",
    )

    # --- Definition nodes ---
    n_rec = g.add_node(Node(
        label="Recurrence Relation",
        type=NodeType.STUB,
        body="A recurrence relation defines a sequence where each term depends on previous terms. Full definition in AlgorithmsFoundations graph.",
        scope="Stub only. Full definition owned by AlgorithmsFoundations graph.",
    ))

    n_rt = g.add_node(Node(
        label="Recursion Tree",
        type=NodeType.DEFINITION,
        body="A recursion tree is a visual representation of a recurrence where each node represents the cost of a single subproblem excluding recursive calls. The root is the original problem. Children represent recursive subproblems.",
        scope="Covers only the definition of a recursion tree as a structure. Not how to construct one or how to calculate running time from it.",
    ))

    n_mt = g.add_node(Node(
        label="Master Theorem",
        type=NodeType.DEFINITION,
        body="The Master Theorem gives asymptotic bounds for recurrences of the form T(n) = aT(n/b) + g(n) where g(n) is O(n^q) and T(1) = d, for constants a, b, q, d. Three cases determine the bound based on the relationship between log_b(a) and q.",
        scope="Covers only the statement of the Master Theorem and its three cases. Not its proof or how to apply it.",
    ))

    # --- Behavior nodes ---
    n_construct = g.add_node(Node(
        label="Recursion Tree Construction",
        type=NodeType.BEHAVIOR,
        body="To construct a recursion tree: the root represents the cost of the original problem excluding recursive calls. Each node at level k has children representing its recursive subproblems at level k+1. The process continues until the base case is reached. For T(n) = 2T(n/2) + n, the root has cost n and two children each of cost n/2.",
        scope="Covers how a recursion tree is constructed level by level. Not how running time is calculated from the completed tree.",
    ))

    n_runtime = g.add_node(Node(
        label="Running Time from Recursion Tree",
        type=NodeType.BEHAVIOR,
        body="To calculate total running time from a recursion tree: sum the costs at each level, then sum across all levels. For T(n) = 2T(n/2) + n, each level sums to n and there are log2(n) + 1 levels, giving T(n) = O(n log n).",
        scope="Covers how to calculate total running time by summing level costs. Depends on the tree already being constructed.",
    ))

    n_mt_case1 = g.add_node(Node(
        label="Master Theorem Case 1",
        type=NodeType.BEHAVIOR,
        body="If log_b(a) < q, then the cost is dominated by the root level and T(n) is O(n^q).",
        scope="Covers only Case 1 of the Master Theorem where log_b(a) < q. Not Cases 2 or 3.",
    ))

    n_mt_case2 = g.add_node(Node(
        label="Master Theorem Case 2",
        type=NodeType.BEHAVIOR,
        body="If log_b(a) = q, then cost is equal at every level and T(n) is O(n^q log n).",
        scope="Covers only Case 2 of the Master Theorem where log_b(a) = q. Not Cases 1 or 3.",
    ))

    n_mt_case3 = g.add_node(Node(
        label="Master Theorem Case 3",
        type=NodeType.BEHAVIOR,
        body="If log_b(a) > q, then the cost is dominated by the leaf level and T(n) is O(n^(log_b(a))).",
        scope="Covers only Case 3 of the Master Theorem where log_b(a) > q. Not Cases 1 or 2.",
    ))

    # --- Constraint nodes ---
    n_mt_constraint = g.add_node(Node(
        label="Master Theorem Applicability",
        type=NodeType.CONSTRAINT,
        body="The Master Theorem applies only to recurrences of the form T(n) = aT(n/b) + g(n) where: a >= 1, b > 1, g(n) is O(n^q) for some constant q, and T(1) = d for some constant d. If the recurrence does not fit this form, the Master Theorem cannot be used.",
        scope="Covers only the conditions under which the Master Theorem applies. Not what to do when it does not apply.",
    ))

    # --- Procedure nodes ---
    n_mt_proof = g.add_node(Node(
        label="Master Theorem Proof",
        type=NodeType.PROCEDURE,
        body="1. Assume without loss of generality that n is a power of b. 2. At level k of the recursion tree there are a^k subproblems each of size n/b^k. 3. Running time at level k is a^k * O((n/b^k)^q) = O(n^q) * (a/b^q)^k. 4. Sum from k=0 to log_b(n). 5. Apply geometric series analysis for the three cases based on whether a/b^q is less than, equal to, or greater than 1.",
        scope="Covers the step-by-step proof of the Master Theorem only. Not the statement of the theorem or how to apply it.",
    ))

    n_rt_apply = g.add_node(Node(
        label="Applying the Recursion Tree Method",
        type=NodeType.PROCEDURE,
        body="1. Write the recurrence. 2. Draw the root with cost equal to the non-recursive part of T(n). 3. Add children for each recursive call, each with cost equal to the non-recursive part of their subproblem. 4. Repeat until base case. 5. Sum costs at each level. 6. Count the number of levels. 7. Sum across all levels to get total running time.",
        scope="Covers the step-by-step procedure for applying the recursion tree method to a recurrence. Not the proof of why it works.",
    ))

    # --- Example nodes ---
    n_ex_concrete = g.add_node(Node(
        label="T(n) = 2T(n/2) + n Worked Example",
        type=NodeType.EXAMPLE,
        subtype="concrete",
        body="For T(n) = 2T(n/2) + n: root cost is n, two children each cost n/2, four grandchildren each cost n/4. Each level sums to n. There are log2(n) + 1 levels. Total: T(n) = n * (log2(n) + 1) = O(n log n). This matches the result from applying the Master Theorem with a=2, b=2, g(n)=n, q=1: log_2(2) = 1 = q, so Case 2 applies giving O(n log n).",
        scope="Concrete worked example of the recursion tree method and Master Theorem applied to T(n) = 2T(n/2) + n only.",
    ))

    # --- Exception nodes ---
    n_mt_exception = g.add_node(Node(
        label="Master Theorem Non-Polynomial Gap",
        type=NodeType.EXCEPTION,
        body="The Master Theorem does not cover all cases. If g(n) is not polynomially related to n^(log_b(a)) — for example g(n) = n log n — none of the three cases apply directly. In such cases the recursion tree method or substitution method must be used instead.",
        scope="Covers only the case where Master Theorem fails due to a non-polynomial gap between g(n) and n^(log_b(a)). Not other failure modes.",
    ))

    # --- Relation nodes ---
    n_relation = g.add_node(Node(
        label="Recurrence to Asymptotic Bound",
        type=NodeType.RELATION,
        body="The transformation from a recurrence relation to its asymptotic running time bound has two paths: the recursion tree method (visual, works for any recurrence) and the Master Theorem (formulaic, works only when applicability constraints are met). Both paths produce the same bound when both apply.",
        scope="Covers the relationship between recurrence relations and asymptotic bounds via recursion trees and Master Theorem. Not either method in isolation.",
    ))

    # --- Edges ---
    g.add_edge(Edge(source_id=n_rt.id,          target_id=n_rec.id,           relations=["represents"],         base_weight=0.90))
    g.add_edge(Edge(source_id=n_construct.id,   target_id=n_rt.id,            relations=["constructs"],         base_weight=0.95))
    g.add_edge(Edge(source_id=n_runtime.id,     target_id=n_construct.id,     relations=["depends_on"],         base_weight=0.95))
    g.add_edge(Edge(source_id=n_rt_apply.id,    target_id=n_rt.id,            relations=["has_procedure"],      base_weight=0.85))
    g.add_edge(Edge(source_id=n_mt.id,          target_id=n_rec.id,           relations=["analyses"],           base_weight=0.90))
    g.add_edge(Edge(source_id=n_mt.id,          target_id=n_mt_constraint.id, relations=["has_constraint"],     base_weight=0.95))
    g.add_edge(Edge(source_id=n_mt.id,          target_id=n_mt_proof.id,      relations=["has_procedure"],      base_weight=0.75))
    g.add_edge(Edge(source_id=n_mt_case1.id,    target_id=n_mt.id,            relations=["is_case_of"],         base_weight=0.90))
    g.add_edge(Edge(source_id=n_mt_case2.id,    target_id=n_mt.id,            relations=["is_case_of"],         base_weight=0.90))
    g.add_edge(Edge(source_id=n_mt_case3.id,    target_id=n_mt.id,            relations=["is_case_of"],         base_weight=0.90))
    g.add_edge(Edge(source_id=n_ex_concrete.id, target_id=n_rt_apply.id,      relations=["demonstrates"],       base_weight=0.80))
    g.add_edge(Edge(source_id=n_ex_concrete.id, target_id=n_mt_case2.id,      relations=["demonstrates"],       base_weight=0.80))
    g.add_edge(Edge(source_id=n_mt_exception.id, target_id=n_mt_constraint.id, relations=["has_exception"],     base_weight=0.70))
    g.add_edge(Edge(source_id=n_relation.id,    target_id=n_rt.id,            relations=["connects"],           base_weight=0.85))
    g.add_edge(Edge(source_id=n_relation.id,    target_id=n_mt.id,            relations=["connects"],           base_weight=0.85))

    return g


# ---------------------------------------------------------------------------
# Shared graph — built once per process, reused across non-weight tests.
# Weight tests build their own fresh graph to avoid cross-test contamination
# from edge.cluster_weights mutation.
# ---------------------------------------------------------------------------

GRAPH = build_recurrence_graph()


def make_engine(max_passes: int = 3) -> MultiPassEngine:
    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    return MultiPassEngine(
        graph=GRAPH,
        llm=llm,
        max_passes=max_passes,
        max_depth=10,
        alpha=0.5,
    )


def make_weight_system() -> WeightSystem:
    ws = WeightSystem(learning_rate=0.15, min_cluster_size=3)
    ws.register(GRAPH)
    return ws


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def run_query_n_times(
    engine: MultiPassEngine,
    query: str,
    graph_name: str,
    n: int,
) -> list[MultiPassResult]:
    """Run the same query n times independently. Returns all results."""
    results = []
    for _ in range(n):
        result = engine.query(query, graph_name=graph_name)
        results.append(result)
    return results


def count_verified(results: list[MultiPassResult]) -> int:
    """Count how many results in a list are verified."""
    return sum(1 for r in results if r.verified)


def edges_with_cluster_signal(graph: Graph, cluster_label: int) -> list:
    """Return all edges in a graph that have a weight for the given cluster label."""
    return [e for e in graph.all_edges() if cluster_label in e.cluster_weights]


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

def assert_structural_invariants(
    result: MultiPassResult,
    max_passes: int = 3,
    allow_empty: bool = False,
) -> None:
    """
    Assert all structural invariants on a MultiPassResult.

    Invariant 1 — No duplicate node IDs.
    Invariant 2 — Edge endpoints exist in the collected node set.
    Invariant 3 — At least one node present (unless allow_empty=True).
    Invariant 4 — Stub nodes have no outbound edges in the result.
    Invariant 5 — No Verifier noise nodes appear in the final result.
    Invariant 6 — passes_run is within [1, max_passes].
    Invariant 7 — If verified=True, missing_description must be empty.
    """
    nodes = result.nodes()
    edges = result.edges()

    # Invariant 1 — no duplicate nodes
    node_ids = [n.id for n in nodes]
    assert len(node_ids) == len(set(node_ids)), (
        f"Invariant 1 failed — duplicate node IDs in result: {node_ids}"
    )

    # Invariant 2 — edge endpoints both present in collected nodes
    node_id_set = set(node_ids)
    for edge in edges:
        assert edge.source_id in node_id_set, (
            f"Invariant 2 failed — edge source {edge.source_id!r} "
            f"not found in collected nodes {node_id_set}"
        )
        assert edge.target_id in node_id_set, (
            f"Invariant 2 failed — edge target {edge.target_id!r} "
            f"not found in collected nodes {node_id_set}"
        )

    # Invariant 3 — at least one node (skipped for queries allowed to return empty)
    if not allow_empty:
        assert len(nodes) >= 1, (
            "Invariant 3 failed — result contains no nodes"
        )

    # Invariant 4 — stub nodes are never the source of a collected edge
    stub_ids = {n.id for n in nodes if n.is_stub}
    for edge in edges:
        assert edge.source_id not in stub_ids, (
            f"Invariant 4 failed — stub node {edge.source_id!r} "
            f"has an outbound edge in the result"
        )

    # Invariant 5 — noise nodes removed before returning final result
    if result.best is not None:
        noise_ids = set(result.best.noise_ids)
        for n in nodes:
            assert n.id not in noise_ids, (
                f"Invariant 5 failed — noise node {n.id!r} ({n.label!r}) "
                f"still present in final result"
            )

    # Invariant 6 — passes_run within [1, max_passes]
    assert result.passes_run >= 1, (
        f"Invariant 6 failed — passes_run={result.passes_run} < 1"
    )
    assert result.passes_run <= max_passes, (
        f"Invariant 6 failed — passes_run={result.passes_run} > max_passes={max_passes}"
    )

    # Invariant 7 — verified flag consistency
    if result.verified:
        missing = result.missing_description()
        assert not missing, (
            f"Invariant 7 failed — result verified=True but "
            f"missing_description={missing!r}"
        )


# ===========================================================================
# Single-graph traversal tests
# ===========================================================================

@requires_api
def test_shallow_query_invariants():
    """
    Shallow query: should anchor on the Recursion Tree definition with
    minimal further traversal. Asserts all structural invariants hold.
    """
    engine = make_engine(max_passes=3)
    result = engine.query("What is a recursion tree?", graph_name=GRAPH.name)
    assert_structural_invariants(result, max_passes=3)


@requires_api
def test_multi_hop_query_invariants():
    """
    Multi-hop query requiring a chain: Recursion Tree → Construction →
    Running Time. Asserts all structural invariants hold.
    """
    engine = make_engine(max_passes=3)
    result = engine.query(
        "How do I calculate the running time of a recursive algorithm using a recursion tree?",
        graph_name=GRAPH.name,
    )
    assert_structural_invariants(result, max_passes=3)


@requires_api
def test_master_theorem_query_invariants():
    """
    Master Theorem application query. Expects the Master Theorem definition,
    its constraint, and at least one case node. Asserts all structural
    invariants hold.
    """
    engine = make_engine(max_passes=3)
    result = engine.query(
        "How do I use the Master Theorem to find the asymptotic bound of a recurrence?",
        graph_name=GRAPH.name,
    )
    assert_structural_invariants(result, max_passes=3)


@requires_api
def test_unrelated_query_returns_minimal_result():
    """
    A query completely unrelated to the graph content. The result may be
    unverified or empty — structural invariants must still hold for any nodes
    that are returned, but an empty result is acceptable here.
    """
    engine = make_engine(max_passes=3)
    result = engine.query("What is photosynthesis?", graph_name=GRAPH.name)
    assert_structural_invariants(result, max_passes=3, allow_empty=True)


@requires_api
def test_stub_node_behaviour():
    """
    Query designed to traverse to the Recurrence Relation stub node.
    Asserts: stub node may appear in the result, but must have no outbound
    edges in result.edges() (Invariant 4). This is also covered by
    assert_structural_invariants but is made explicit here.
    """
    engine = make_engine(max_passes=3)
    result = engine.query(
        "What is a recurrence relation and how does it relate to recursion trees?",
        graph_name=GRAPH.name,
    )
    assert_structural_invariants(result, max_passes=3)

    # Explicit stub check: any stub in the result has no outbound edges
    stub_ids = {n.id for n in result.nodes() if n.is_stub}
    if stub_ids:
        for edge in result.edges():
            assert edge.source_id not in stub_ids, (
                f"Stub node {edge.source_id!r} expanded — "
                f"found as source of edge {edge.id!r}"
            )


# ===========================================================================
# Multi-pass behaviour tests
# ===========================================================================

@requires_api
def test_multi_pass_improves_or_maintains_coverage():
    """
    Run a complex query 3 times independently using fresh MultiPassEngine
    instances (each with max_passes=3). Assert that at least one of the 3
    independent runs returns verified=True. A complex query on a complete
    graph should verify within 3 passes.
    """
    query = "Explain the complete recursion tree method including how to construct the tree and how to calculate running time from it"
    results = []
    for _ in range(3):
        engine = make_engine(max_passes=3)
        r = engine.query(query, graph_name=GRAPH.name)
        assert_structural_invariants(r, max_passes=3)
        results.append(r)

    verified_count = count_verified(results)
    assert verified_count >= 1, (
        f"Expected at least one verified result across 3 independent runs, "
        f"got {verified_count}. Per-run verified: "
        f"{[r.verified for r in results]}"
    )


@requires_api
def test_multi_pass_passes_run_gte_one():
    """
    passes_run must be >= 1 for any query on any graph (Invariant 6).
    Tested explicitly here on a simple query.
    """
    engine = make_engine(max_passes=3)
    result = engine.query("What is a recursion tree?", graph_name=GRAPH.name)
    assert result.passes_run >= 1, (
        f"passes_run={result.passes_run} for a non-empty graph"
    )


@requires_api
def test_multi_pass_result_has_more_nodes_than_single_pass():
    """
    For a complex query, a multi-pass result (max_passes=3) should collect
    at least as many nodes as a single pass (max_passes=1). The multi-pass
    best result is the maximum across all passes, so it cannot be worse.
    """
    query = (
        "Explain both the recursion tree method and the Master Theorem, "
        "including when the Master Theorem applies and what its three cases are"
    )

    single_engine = make_engine(max_passes=1)
    single_result = single_engine.query(query, graph_name=GRAPH.name)

    multi_engine = make_engine(max_passes=3)
    multi_result = multi_engine.query(query, graph_name=GRAPH.name)

    assert_structural_invariants(single_result, max_passes=1)
    assert_structural_invariants(multi_result, max_passes=3)

    single_count = len(single_result.nodes())
    multi_count = len(multi_result.nodes())

    assert multi_count >= single_count, (
        f"Multi-pass result ({multi_count} nodes) has fewer nodes than "
        f"single-pass result ({single_count} nodes)"
    )


# ===========================================================================
# Weight accumulation tests
# ===========================================================================

@requires_api
def test_weight_accumulation_verified_edges_increase():
    """
    Run a query that produces verified results 5 times against a fresh graph.
    Observe each result with a WeightSystem. Assert that edges used in
    verified traversals accumulate cluster signal (cluster_weights non-empty
    and effective weight reflects derived signal).
    """
    fresh_graph = build_recurrence_graph()
    ws = WeightSystem(learning_rate=0.15, min_cluster_size=3)
    ws.register(fresh_graph)

    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    engine = MultiPassEngine(
        graph=fresh_graph,
        llm=llm,
        max_passes=3,
        max_depth=10,
        alpha=0.5,
    )

    query = "What is a recursion tree and how is it constructed?"
    results = []
    for _ in range(5):
        result = engine.query(query, graph_name=fresh_graph.name)
        ws.observe_multi(result)
        results.append(result)

    verified_results = [r for r in results if r.verified]

    # At least one verified result must have occurred for the weight test
    # to be meaningful. If the LLM never verifies, skip the weight check.
    if not verified_results:
        pytest.skip(
            "No verified results across 5 runs — cannot assert weight signal. "
            "This indicates a graph coverage or LLM issue, not a weight system bug."
        )

    # Collect edge IDs that appeared in verified results
    verified_edge_ids: set[str] = set()
    for r in verified_results:
        for edge in r.edges():
            verified_edge_ids.add(edge.id)

    # For those edges in the fresh_graph, assert derived signal has been added
    edges_with_signal = 0
    for eid in verified_edge_ids:
        try:
            live_edge = fresh_graph.get_edge(eid)
        except KeyError:
            continue
        if live_edge.cluster_weights:
            edges_with_signal += 1

    assert edges_with_signal > 0, (
        "No edges accumulated derived signal after 5 runs with verified results. "
        "WeightSystem.observe_multi is not updating cluster_weights."
    )


@requires_api
def test_weight_accumulation_unvisited_edges_unchanged():
    """
    Run a shallow query that only touches a subset of the graph (recursion tree
    subtree). Assert that edges in the Master Theorem subtree — which should
    not be reached by a shallow recursion-tree-only query — have empty
    cluster_weights after the run.
    """
    fresh_graph = build_recurrence_graph()
    ws = WeightSystem(learning_rate=0.15, min_cluster_size=3)
    ws.register(fresh_graph)

    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    engine = MultiPassEngine(
        graph=fresh_graph,
        llm=llm,
        max_passes=1,  # single pass — shallow traversal
        max_depth=5,
        alpha=0.5,
    )

    result = engine.query("What is a recursion tree?", graph_name=fresh_graph.name)
    ws.observe_multi(result)

    visited_node_ids = {n.id for n in result.nodes()}

    # Any edge in fresh_graph where NEITHER endpoint was visited should have
    # no cluster_weights (the WeightSystem only touches edges in the result)
    for edge in fresh_graph.all_edges():
        source_visited = edge.source_id in visited_node_ids
        target_visited = edge.target_id in visited_node_ids
        if not source_visited and not target_visited:
            assert not edge.cluster_weights, (
                f"Edge {edge.id!r} (relations={edge.relations}) "
                f"was never traversed but has cluster_weights={edge.cluster_weights}. "
                "WeightSystem is incorrectly updating unvisited edges."
            )


@requires_api
def test_cluster_forms_after_repeated_similar_queries():
    """
    Run 6 or more structurally similar queries (all about recursion trees).
    With min_cluster_size=3, HDBSCAN requires at least min_cluster_size * 2 = 6
    points to form a cluster. After 6 similar queries the clusterer should
    report at least one cluster with label >= 0.
    """
    fresh_graph = build_recurrence_graph()
    ws = WeightSystem(learning_rate=0.15, min_cluster_size=3)
    ws.register(fresh_graph)

    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    engine = MultiPassEngine(
        graph=fresh_graph,
        llm=llm,
        max_passes=2,
        max_depth=8,
        alpha=0.5,
    )

    similar_queries = [
        "What is a recursion tree?",
        "How is a recursion tree defined?",
        "Describe the structure of a recursion tree.",
        "What does a recursion tree represent?",
        "Explain the recursion tree concept.",
        "What is the definition of a recursion tree in algorithm analysis?",
    ]

    for query in similar_queries:
        result = engine.query(query, graph_name=fresh_graph.name)
        ws.observe_multi(result)

    stats = ws.cluster_stats()
    cluster_count = stats["cluster_count"]

    assert cluster_count >= 1, (
        f"Expected at least 1 cluster after {len(similar_queries)} similar queries, "
        f"got {cluster_count}. cluster_stats={stats}"
    )


# ===========================================================================
# Router integration tests
# ===========================================================================

@requires_api
def test_router_single_graph_dispatch_invariants():
    """
    Register only the recurrence graph with the router. Run a relevant query.
    Assert structural invariants on each MultiPassResult. Assert
    skipped_graphs is empty since only one graph is registered and it is
    relevant.
    """
    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    router = Router(llm=llm, max_passes=3, max_depth=10, alpha=0.5)
    router.register(GRAPH)

    router_result = router.query("What is the Master Theorem?")

    assert isinstance(router_result, RouterResult)

    # If the router correctly dispatches, it should have exactly one traversal
    # and no skipped graphs (only one graph registered, and the query is relevant)
    assert len(router_result.skipped_graphs) == 0, (
        f"Expected no skipped graphs with a single registered graph and a "
        f"relevant query, but skipped={router_result.skipped_graphs}"
    )

    # Structural invariants on each dispatched traversal
    for traversal in router_result.traversals:
        assert_structural_invariants(traversal, max_passes=3)


@requires_api
def test_router_irrelevant_query_dispatches_to_no_graphs():
    """
    Run a completely unrelated query through the router. The router should
    decide no graphs are relevant. result.traversals must be empty and
    result.all_nodes() must be empty.
    """
    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    router = Router(llm=llm, max_passes=3, max_depth=10, alpha=0.5)
    router.register(GRAPH)

    router_result = router.query("What is photosynthesis and how does it work?")

    assert isinstance(router_result, RouterResult)
    assert len(router_result.traversals) == 0, (
        f"Expected zero traversals for an unrelated query, "
        f"got {len(router_result.traversals)} traversals"
    )
    assert len(router_result.all_nodes()) == 0, (
        f"Expected no nodes for an unrelated query, "
        f"got {len(router_result.all_nodes())} nodes"
    )


@requires_api
def test_router_result_verified_flag_correct():
    """
    Run a query designed to produce a verified result. Assert that
    RouterResult.verified correctly reflects the verified status of the
    underlying MultiPassResult. RouterResult.verified is True only when
    all dispatched traversals are verified.
    """
    llm = CerebrasClient(api_key=CEREBRAS_API_KEY)
    router = Router(llm=llm, max_passes=3, max_depth=10, alpha=0.5)
    router.register(GRAPH)

    router_result = router.query(
        "What is a recursion tree? Provide only its definition."
    )

    assert isinstance(router_result, RouterResult)

    if router_result.traversals:
        # RouterResult.verified must equal AND of all traversal verified flags
        expected_verified = all(t.verified for t in router_result.traversals)
        assert router_result.verified == expected_verified, (
            f"RouterResult.verified={router_result.verified} does not match "
            f"AND of traversal verified flags={expected_verified}. "
            f"Per-traversal: {[t.verified for t in router_result.traversals]}"
        )
    else:
        # No traversals dispatched — verified must be False
        assert not router_result.verified, (
            "RouterResult.verified=True but no traversals were dispatched"
        )
