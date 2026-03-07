"""
Tests for the Router using MockLLMClient.
"""

import json
import traceback
from contextus import Node, NodeType, Edge, Graph, Router, RouterResult
from contextus.llm import LLMClient, LLMResponse


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._calls: list[str] = []  # tracks which system prompts were called

    def complete(self, system: str, user: str, temperature: float = 0.0) -> LLMResponse:
        self._calls.append(system[:30])
        content = (
            self._responses.pop(0) if self._responses
            else json.dumps({"done": True, "visit": [], "reason": "default"})
        )
        return LLMResponse(content=content)


# ---------------------------------------------------------------------------
# Graph fixtures
# ---------------------------------------------------------------------------

def make_algorithms_graph() -> tuple[Graph, dict]:
    g = Graph(name="Algorithms", description="Core algorithm concepts.")
    nodes = {}
    nodes["bsearch"] = g.add_node(Node(
        label="Binary Search",
        type=NodeType.DEFINITION,
        body="Finds a target in a sorted array by halving the search space.",
        scope="Definition of binary search only.",
    ))
    nodes["complexity"] = g.add_node(Node(
        label="O(log n) Complexity",
        type=NodeType.BEHAVIOR,
        body="Binary search runs in O(log n) time.",
        scope="Time complexity of binary search only.",
    ))
    g.add_edge(Edge(
        source_id=nodes["bsearch"].id,
        target_id=nodes["complexity"].id,
        relations=["has_behavior"],
        base_weight=0.9,
    ))
    return g, nodes


def make_datastructures_graph() -> tuple[Graph, dict]:
    g = Graph(name="DataStructures", description="Core data structure concepts.")
    nodes = {}
    nodes["array"] = g.add_node(Node(
        label="Array",
        type=NodeType.DEFINITION,
        body="A contiguous block of memory holding elements of the same type.",
        scope="Definition of arrays only. Not linked lists or other structures.",
    ))
    nodes["sorted"] = g.add_node(Node(
        label="Sorted Array",
        type=NodeType.CONSTRAINT,
        body="An array whose elements are ordered. Required for binary search.",
        scope="Properties and requirements of sorted arrays only.",
    ))
    g.add_edge(Edge(
        source_id=nodes["array"].id,
        target_id=nodes["sorted"].id,
        relations=["has_variant"],
        base_weight=0.8,
    ))
    return g, nodes


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

def test_register_and_list():
    mock = MockLLMClient([])
    router = Router(llm=mock)
    g, _ = make_algorithms_graph()
    router.register(g)
    assert "Algorithms" in router.registered_graphs()

def test_register_duplicate_raises():
    mock = MockLLMClient([])
    router = Router(llm=mock)
    g, _ = make_algorithms_graph()
    router.register(g)
    try:
        router.register(g)
        assert False, "Should have raised"
    except ValueError:
        pass

def test_unregister():
    mock = MockLLMClient([])
    router = Router(llm=mock)
    g, _ = make_algorithms_graph()
    router.register(g)
    router.unregister("Algorithms")
    assert "Algorithms" not in router.registered_graphs()

def test_unregister_unknown_raises():
    mock = MockLLMClient([])
    router = Router(llm=mock)
    try:
        router.unregister("nonexistent")
        assert False
    except KeyError:
        pass

def test_get_graph():
    mock = MockLLMClient([])
    router = Router(llm=mock)
    g, _ = make_algorithms_graph()
    router.register(g)
    assert router.get_graph("Algorithms").name == "Algorithms"


# ---------------------------------------------------------------------------
# Single graph dispatch tests
# ---------------------------------------------------------------------------

def test_query_no_graphs_returns_empty():
    mock = MockLLMClient([])
    router = Router(llm=mock)
    result = router.query("What is binary search?")
    assert result.traversals == []
    assert "No graphs" in result.dispatch_reason

def test_dispatch_selects_correct_graph():
    g_algo, nodes_algo = make_algorithms_graph()
    g_ds, _ = make_datastructures_graph()
    bsearch_id = nodes_algo["bsearch"].id
    complexity_id = nodes_algo["complexity"].id

    mock = MockLLMClient([
        # Router dispatch: select only Algorithms
        json.dumps({"selected": ["Algorithms"], "reason": "query is about algorithm definition"}),
        # Traversal anchor
        json.dumps({"anchor_id": bsearch_id, "reason": "most central"}),
        # Collector step: done immediately
        json.dumps({"visit": [], "done": True, "reason": "anchor is sufficient"}),
        # Verifier
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    router = Router(llm=mock)
    router.register(g_algo)
    router.register(g_ds)

    result = router.query("What is binary search?")
    assert len(result.traversals) == 1
    assert result.skipped_graphs == ["DataStructures"]
    assert any(n.label == "Binary Search" for n in result.all_nodes())

def test_dispatch_selects_no_graphs_returns_empty():
    g_algo, _ = make_algorithms_graph()

    mock = MockLLMClient([
        json.dumps({"selected": [], "reason": "query is unrelated to available graphs"}),
    ])
    router = Router(llm=mock)
    router.register(g_algo)

    result = router.query("What is the weather today?")
    assert result.traversals == []
    assert result.skipped_graphs == ["Algorithms"]

def test_dispatch_parse_failure_falls_back_to_all_graphs():
    g_algo, nodes_algo = make_algorithms_graph()
    bsearch_id = nodes_algo["bsearch"].id

    mock = MockLLMClient([
        # Dispatch returns garbage — should fall back to all graphs
        "not valid json at all",
        # Traversal anchor
        json.dumps({"anchor_id": bsearch_id, "reason": "central"}),
        # Collector: done
        json.dumps({"visit": [], "done": True, "reason": "sufficient"}),
        # Verifier
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    router = Router(llm=mock)
    router.register(g_algo)

    result = router.query("What is binary search?")
    assert len(result.traversals) == 1
    assert "defaulting to all" in result.dispatch_reason


# ---------------------------------------------------------------------------
# Multi-graph dispatch tests
# ---------------------------------------------------------------------------

def test_multi_graph_dispatch_both_selected():
    g_algo, nodes_algo = make_algorithms_graph()
    g_ds, nodes_ds = make_datastructures_graph()

    bsearch_id   = nodes_algo["bsearch"].id
    array_id     = nodes_ds["array"].id
    sorted_id    = nodes_ds["sorted"].id

    mock = MockLLMClient([
        # Router selects both graphs
        json.dumps({"selected": ["Algorithms", "DataStructures"], "reason": "query spans both domains"}),
        # --- Algorithms traversal ---
        json.dumps({"anchor_id": bsearch_id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "sufficient"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
        # --- DataStructures traversal ---
        json.dumps({"anchor_id": array_id, "reason": "central"}),
        json.dumps({"visit": [sorted_id], "done": False, "reason": "need sorted variant"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
        # --- Merge ---
        json.dumps({"redundant_pairs": [], "note": "no redundancies"}),
    ])
    router = Router(llm=mock)
    router.register(g_algo)
    router.register(g_ds)

    result = router.query("How does binary search work on arrays?")
    assert len(result.traversals) == 2
    assert result.skipped_graphs == []
    all_labels = {n.label for n in result.all_nodes()}
    assert "Binary Search" in all_labels
    assert "Array" in all_labels

def test_multi_graph_merge_removes_redundant_node():
    g_algo, nodes_algo = make_algorithms_graph()
    g_ds, nodes_ds = make_datastructures_graph()

    bsearch_id = nodes_algo["bsearch"].id
    array_id   = nodes_ds["array"].id

    mock = MockLLMClient([
        json.dumps({"selected": ["Algorithms", "DataStructures"], "reason": "both needed"}),
        # Algorithms traversal
        json.dumps({"anchor_id": bsearch_id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "sufficient"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
        # DataStructures traversal
        json.dumps({"anchor_id": array_id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "sufficient"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
        # Merge: mark array_id as redundant with bsearch_id (contrived but tests removal)
        json.dumps({"redundant_pairs": [[bsearch_id, array_id]], "note": "array covered by bsearch context"}),
    ])
    router = Router(llm=mock)
    router.register(g_algo)
    router.register(g_ds)

    result = router.query("test")
    all_ids = {n.id for n in result.all_nodes()}
    assert bsearch_id in all_ids       # first of pair kept
    assert array_id not in all_ids     # second of pair removed


# ---------------------------------------------------------------------------
# RouterResult helpers
# ---------------------------------------------------------------------------

def test_router_result_verified_true_when_all_verified():
    g, nodes = make_algorithms_graph()
    mock = MockLLMClient([
        json.dumps({"selected": ["Algorithms"], "reason": "relevant"}),
        json.dumps({"anchor_id": nodes["bsearch"].id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    router = Router(llm=mock)
    router.register(g)
    result = router.query("test")
    assert result.verified == True

def test_router_result_verified_false_when_any_unverified():
    g, nodes = make_algorithms_graph()
    mock = MockLLMClient([
        json.dumps({"selected": ["Algorithms"], "reason": "relevant"}),
        json.dumps({"anchor_id": nodes["bsearch"].id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "missing something", "note": "incomplete"}),
    ])
    router = Router(llm=mock)
    router.register(g)
    result = router.query("test")
    assert result.verified == False

def test_all_nodes_deduplicates():
    from contextus.traversal import TraversalResult, MultiPassResult
    g, nodes = make_algorithms_graph()
    n = nodes["bsearch"]
    tr1 = TraversalResult(query="q", nodes=[n], verified=True)
    tr2 = TraversalResult(query="q", nodes=[n], verified=True)
    mp1 = MultiPassResult(query="q", best=tr1, passes_run=1, verified=True, all_passes=[tr1])
    mp2 = MultiPassResult(query="q", best=tr2, passes_run=1, verified=True, all_passes=[tr2])
    rr = RouterResult(query="q", traversals=[mp1, mp2])
    assert len(rr.all_nodes()) == 1


# ---------------------------------------------------------------------------
# max_passes passthrough test
# ---------------------------------------------------------------------------

def test_router_passes_max_passes_to_engine():
    """Router(max_passes=2) results in at most 2 passes per graph."""
    g_algo, nodes_algo = make_algorithms_graph()
    bsearch_id = nodes_algo["bsearch"].id

    # Two passes per graph, each unverified
    mock = MockLLMClient([
        # Router dispatch
        json.dumps({"selected": ["Algorithms"], "reason": "relevant"}),
        # Pass 1: anchor + collector done + verifier unverified
        json.dumps({"anchor_id": bsearch_id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing.", "note": "incomplete"}),
        # Backtracking: unchosen neighbours picked up, still unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # Pass 2: anchor + collector done + verifier unverified
        json.dumps({"anchor_id": bsearch_id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing.", "note": "incomplete"}),
        # Backtracking
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # No pass 3 should happen
    ])
    router = Router(llm=mock, max_passes=2)
    router.register(g_algo)
    result = router.query("What is binary search?")
    assert len(result.traversals) == 1
    assert result.traversals[0].passes_run <= 2


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_register_and_list,
        test_register_duplicate_raises,
        test_unregister,
        test_unregister_unknown_raises,
        test_get_graph,
        test_query_no_graphs_returns_empty,
        test_dispatch_selects_correct_graph,
        test_dispatch_selects_no_graphs_returns_empty,
        test_dispatch_parse_failure_falls_back_to_all_graphs,
        test_multi_graph_dispatch_both_selected,
        test_multi_graph_merge_removes_redundant_node,
        test_router_result_verified_true_when_all_verified,
        test_router_result_verified_false_when_any_unverified,
        test_all_nodes_deduplicates,
        test_router_passes_max_passes_to_engine,
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
