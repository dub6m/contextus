"""
Tests for the traversal engine using a MockLLMClient.
The mock simulates deterministic LLM responses so traversal logic
can be tested without a live API key.
"""

import json
from contextus import Node, NodeType, Edge, Graph
from contextus.llm import LLMClient, LLMResponse
from contextus.traversal import TraversalEngine, TraversalResult, _parse_json


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """
    Deterministic mock. Each call pops a response from the queue.
    If the queue is empty, returns a safe default (done=true).
    """
    def __init__(self, responses: list[str]):
        self._responses = list(responses)

    def complete(self, system: str, user: str, temperature: float = 0.0) -> LLMResponse:
        if self._responses:
            content = self._responses.pop(0)
        else:
            content = json.dumps({"done": True, "visit": [], "reason": "default done"})
        return LLMResponse(content=content)


# ---------------------------------------------------------------------------
# Shared graph fixture
# ---------------------------------------------------------------------------

def build_binary_search_graph():
    """
    A small but realistic graph about binary search.

           [definition] Binary Search
                  |  has_behavior
           [behavior] O(log n) Complexity
                  |  violated_by
           [constraint] Sorted Array Requirement
                  |  is_example_of
           [example] Searching a Phone Book
    """
    g = Graph(name="Binary Search Knowledge", description="Core facts about binary search.")

    n_def = g.add_node(Node(
        label="Binary Search",
        type=NodeType.DEFINITION,
        body="Binary search is an algorithm that finds a target in a sorted array by repeatedly halving the search space.",
        scope="Covers only the definition of binary search. Not implementation, complexity, or variants.",
        aliases=["binary chop"],
    ))
    n_beh = g.add_node(Node(
        label="O(log n) Complexity",
        type=NodeType.BEHAVIOR,
        body="Binary search runs in O(log n) time because it halves the search space on each iteration.",
        scope="Covers only the time complexity of binary search. Not space complexity.",
    ))
    n_con = g.add_node(Node(
        label="Sorted Array Requirement",
        type=NodeType.CONSTRAINT,
        body="Binary search requires the input array to be sorted. An unsorted array will produce incorrect results.",
        scope="Covers only the sorted precondition. Not how to sort an array.",
    ))
    n_ex = g.add_node(Node(
        label="Searching a Phone Book",
        type=NodeType.EXAMPLE,
        body="Opening a phone book to the middle and discarding half based on alphabetical order is binary search in practice.",
        scope="A real-world analogy for binary search only.",
    ))

    g.add_edge(Edge(source_id=n_def.id, target_id=n_beh.id, relations=["has_behavior"],    base_weight=0.9))
    g.add_edge(Edge(source_id=n_def.id, target_id=n_con.id, relations=["has_constraint"],  base_weight=0.95))
    g.add_edge(Edge(source_id=n_def.id, target_id=n_ex.id,  relations=["has_example"],     base_weight=0.7))
    g.add_edge(Edge(source_id=n_beh.id, target_id=n_con.id, relations=["violated_by"],     base_weight=0.8))

    return g, n_def, n_beh, n_con, n_ex


# ---------------------------------------------------------------------------
# _parse_json utility tests
# ---------------------------------------------------------------------------

def test_parse_json_clean():
    assert _parse_json('{"a": 1}') == {"a": 1}

def test_parse_json_markdown_fence():
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}

def test_parse_json_embedded():
    assert _parse_json('Here is the result: {"a": 1} done') == {"a": 1}

def test_parse_json_invalid():
    assert _parse_json("not json at all") is None


# ---------------------------------------------------------------------------
# Anchor selection tests
# ---------------------------------------------------------------------------

def test_anchor_selection_returns_correct_node():
    g, n_def, *_ = build_binary_search_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": n_def.id, "reason": "most central node"}),
        # Verifier response
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=1)
    result = engine.query("What is binary search?")
    assert n_def in result.nodes

def test_anchor_bad_response_returns_empty():
    g, *_ = build_binary_search_graph()
    mock = MockLLMClient([
        "not json",   # anchor fails
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=1)
    result = engine.query("What is binary search?")
    assert result.nodes == []
    assert result.verified == False


# ---------------------------------------------------------------------------
# Collector traversal tests
# ---------------------------------------------------------------------------

def test_collector_visits_approved_neighbors():
    g, n_def, n_beh, n_con, n_ex = build_binary_search_graph()
    mock = MockLLMClient([
        # Anchor
        json.dumps({"anchor_id": n_def.id, "reason": "central"}),
        # Step from n_def: visit behavior and constraint, not example
        json.dumps({"visit": [n_beh.id, n_con.id], "done": False, "reason": "need complexity and constraint"}),
        # Step from n_beh: done
        json.dumps({"visit": [], "done": True, "reason": "sufficient"}),
        # Verifier
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "complete"}),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=5)
    result = engine.query("What is binary search and what are its constraints?")
    collected_labels = {n.label for n in result.nodes}
    assert "Binary Search" in collected_labels
    assert "O(log n) Complexity" in collected_labels
    assert "Sorted Array Requirement" in collected_labels
    assert "Searching a Phone Book" not in collected_labels

def test_collector_done_immediately_stops_traversal():
    g, n_def, *_ = build_binary_search_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": n_def.id, "reason": "central"}),
        # Collector says done immediately after anchor
        json.dumps({"visit": [], "done": True, "reason": "anchor is enough"}),
        # Verifier
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=5)
    result = engine.query("Define binary search briefly.")
    assert len(result.nodes) == 1
    assert result.nodes[0].label == "Binary Search"


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

def test_verifier_removes_noise_nodes():
    g, n_def, n_beh, n_con, n_ex = build_binary_search_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": n_def.id, "reason": "central"}),
        json.dumps({"visit": [n_beh.id, n_ex.id], "done": False, "reason": "grabbing some neighbors"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        # Verifier flags the example as noise
        json.dumps({
            "complete": True,
            "noise_ids": [n_ex.id],
            "missing_description": "",
            "note": "example not needed for this query"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=5)
    result = engine.query("What is the time complexity of binary search?")
    ids = result.node_ids()
    assert n_ex.id not in ids
    assert n_def.id in ids
    assert n_beh.id in ids

def test_verifier_marks_incomplete():
    g, n_def, *_ = build_binary_search_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": n_def.id, "reason": "central"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        # Verifier says incomplete
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Missing constraint node about sorted array requirement.",
            "note": "incomplete"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock)
    result = engine.query("What are all the requirements to use binary search?")
    assert result.verified == False
    assert "Missing" in result.verifier_note

def test_verifier_marks_complete():
    g, n_def, n_beh, n_con, _ = build_binary_search_graph()
    # anchor(1) + step from n_def(2) + verifier(3) = 3 calls total
    # n_beh and n_con have no unvisited/unqueued neighbors so no step call needed for them
    mock = MockLLMClient([
        json.dumps({"anchor_id": n_def.id, "reason": "central"}),
        json.dumps({"visit": [n_beh.id, n_con.id], "done": False, "reason": "need both"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "all good"}),
    ])
    engine = TraversalEngine(graph=g, llm=mock)
    result = engine.query("Explain binary search including complexity and constraints.")
    assert result.verified == True


# ---------------------------------------------------------------------------
# Edge collection tests
# ---------------------------------------------------------------------------

def test_edges_collected_between_visited_nodes():
    g, n_def, n_beh, n_con, _ = build_binary_search_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": n_def.id, "reason": "central"}),
        json.dumps({"visit": [n_beh.id, n_con.id], "done": False, "reason": "need both"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = TraversalEngine(graph=g, llm=mock)
    result = engine.query("Explain binary search.")
    edge_source_targets = {(e.source_id, e.target_id) for e in result.edges}
    assert (n_def.id, n_beh.id) in edge_source_targets
    assert (n_def.id, n_con.id) in edge_source_targets


# ---------------------------------------------------------------------------
# Max depth safety net
# ---------------------------------------------------------------------------

def test_max_depth_stops_runaway_traversal():
    g, n_def, n_beh, n_con, n_ex = build_binary_search_graph()
    # Collector always says keep going — max_depth should cut it off
    always_continue = [
        json.dumps({"anchor_id": n_def.id, "reason": "start"}),
    ] + [
        json.dumps({"visit": [n_beh.id], "done": False, "reason": "keep going"})
        for _ in range(20)
    ] + [
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"})
    ]
    mock = MockLLMClient(always_continue)
    engine = TraversalEngine(graph=g, llm=mock, max_depth=3)
    result = engine.query("anything")
    # Should not blow up and should have stopped
    assert len(result.nodes) <= g.node_count()


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_parse_json_clean,
        test_parse_json_markdown_fence,
        test_parse_json_embedded,
        test_parse_json_invalid,
        test_anchor_selection_returns_correct_node,
        test_anchor_bad_response_returns_empty,
        test_collector_visits_approved_neighbors,
        test_collector_done_immediately_stops_traversal,
        test_verifier_removes_noise_nodes,
        test_verifier_marks_incomplete,
        test_verifier_marks_complete,
        test_edges_collected_between_visited_nodes,
        test_max_depth_stops_runaway_traversal,
    ]

    passed, failed = [], []
    import traceback
    for t in tests:
        try:
            t()
            passed.append(t.__name__)
        except Exception:
            failed.append((t.__name__, traceback.format_exc()))

    print(f"\n{len(passed)}/{len(tests)} passed")
    for name, tb in failed:
        print(f"\nFAIL: {name}\n{tb}")
