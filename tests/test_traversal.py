"""
Tests for the traversal engine using a MockLLMClient.
The mock simulates deterministic LLM responses so traversal logic
can be tested without a live API key.
"""

import json
from contextus import Node, NodeType, Edge, Graph
from contextus.llm import LLMClient, LLMResponse
from contextus.traversal import TraversalEngine, TraversalResult, SessionRecord, MultiPassEngine, MultiPassResult, _parse_json


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
        # Backtracking discovers unchosen neighbours and re-verifies
        # Second verifier also says incomplete
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Still missing something.",
            "note": "still incomplete"
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
# SessionRecord tests
# ---------------------------------------------------------------------------

def test_session_record_initialises_empty():
    sr = SessionRecord()
    assert sr.attempted_edges == {}
    assert sr.unchosen_neighbours == {}
    assert sr.decision_point_order == []

def test_session_record_is_not_persisted():
    """Two separate calls to engine.query() do not share session state."""
    g, n_def, n_beh, n_con, n_ex = build_binary_search_graph()

    responses = (
        # --- First query ---
        [
            # Anchor
            json.dumps({"anchor_id": n_def.id, "reason": "central"}),
            # Step from n_def: visit behavior only (leaves constraint + example unchosen)
            json.dumps({"visit": [n_beh.id], "done": False, "reason": "enough"}),
            # Step from n_beh: done
            json.dumps({"visit": [], "done": True, "reason": "done"}),
            # Verifier: complete
            json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
        ]
        +
        # --- Second query ---
        [
            # Anchor
            json.dumps({"anchor_id": n_def.id, "reason": "central"}),
            # Step from n_def: visit constraint only
            json.dumps({"visit": [n_con.id], "done": False, "reason": "enough"}),
            # Step from n_con: done (n_con has inbound from n_beh but n_beh not queued)
            json.dumps({"visit": [], "done": True, "reason": "done"}),
            # Verifier: complete
            json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
        ]
    )
    mock = MockLLMClient(responses)
    engine = TraversalEngine(graph=g, llm=mock, max_depth=5)

    r1 = engine.query("first query")
    r2 = engine.query("second query")

    # Each query should only have nodes from its own session
    r1_labels = {n.label for n in r1.nodes}
    r2_labels = {n.label for n in r2.nodes}

    assert "O(log n) Complexity" in r1_labels
    assert "Sorted Array Requirement" not in r1_labels

    assert "Sorted Array Requirement" in r2_labels
    assert "O(log n) Complexity" not in r2_labels


# ---------------------------------------------------------------------------
# Backtracking graph fixture
# ---------------------------------------------------------------------------

def build_backtrack_graph():
    """
    Graph for backtracking tests:
        A (definition)
        ├── B (behavior)    ← correct path, leads to verified result
        ├── C (behavior)    ← wrong path, leads to unverified result
        └── D (constraint)  ← backtrack target
    """
    g = Graph(name="Backtrack Test", description="For backtracking tests.")

    a = g.add_node(Node(
        label="A",
        type=NodeType.DEFINITION,
        body="Node A is the root concept.",
        scope="Root node for backtracking test.",
    ))
    b = g.add_node(Node(
        label="B",
        type=NodeType.BEHAVIOR,
        body="Node B is the correct destination.",
        scope="Correct path target.",
    ))
    c = g.add_node(Node(
        label="C",
        type=NodeType.BEHAVIOR,
        body="Node C is a wrong turn.",
        scope="Wrong path target.",
    ))
    d = g.add_node(Node(
        label="D",
        type=NodeType.CONSTRAINT,
        body="Node D is the backtrack target.",
        scope="Backtrack target.",
    ))

    g.add_edge(Edge(source_id=a.id, target_id=b.id, relations=["has_behavior"], base_weight=0.9))
    g.add_edge(Edge(source_id=a.id, target_id=c.id, relations=["has_behavior"], base_weight=0.8))
    g.add_edge(Edge(source_id=a.id, target_id=d.id, relations=["has_constraint"], base_weight=0.7))

    return g, a, b, c, d


# ---------------------------------------------------------------------------
# Backtracking tests
# ---------------------------------------------------------------------------

def test_backtracking_triggered_on_missing_description():
    """
    First pass: Collector visits C (wrong path). Verifier says unverified + missing.
    Backtracking: picks up D (unchosen). Verifier says verified.
    """
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Anchor → A
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        # Step from A: visit only C (leaves B and D unchosen)
        json.dumps({"visit": [c.id], "done": False, "reason": "try C first"}),
        # Step from C: no unvisited neighbors, so no collector call needed → done
        # (C has no outbound edges to unvisited nodes → BFS ends)
        # Verifier 1: unverified, missing description
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Missing constraint D.",
            "note": "incomplete"
        }),
        # Backtracking: B and D are enqueued from A's unchosen list
        # Step from B: no further neighbors
        # Step from D: no further neighbors
        # Verifier 2: verified
        json.dumps({
            "complete": True,
            "noise_ids": [],
            "missing_description": "",
            "note": "all good"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=10)
    result = engine.query("Explain A fully")
    assert result.verified is True
    assert result.backtrack_count == 1

def test_backtracking_not_triggered_on_noise_only():
    """
    Verifier returns unverified with noise_ids but empty missing_description.
    Backtracking should NOT occur.
    """
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Anchor → A
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        # Step from A: visit B and C (leaves D unchosen)
        json.dumps({"visit": [b.id, c.id], "done": False, "reason": "grab B and C"}),
        # BFS continues — B and C have no unvisited neighbors
        # Verifier: noise only, no missing
        json.dumps({
            "complete": False,
            "noise_ids": [c.id],
            "missing_description": "",
            "note": "C is noise"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=10)
    result = engine.query("What is A?")
    assert result.backtrack_count == 0

def test_backtracking_respects_max_depth():
    """max_depth=2 should prevent backtracking from running further expansions."""
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Anchor → A
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        # Step from A: visit C only (1 expansion for A, leaves B+D unchosen)
        json.dumps({"visit": [c.id], "done": False, "reason": "try C"}),
        # C expansion (2nd expansion — now at max_depth=2)
        # C has no unvisited neighbors
        # Verifier 1: unverified + missing
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Missing D.",
            "note": "incomplete"
        }),
        # Backtracking would try but max_depth already reached → no further expansion
        # (the while loop condition `expansions < self.max_depth` fails)
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=2)
    result = engine.query("Explain A")
    # Should not have backtracked because depth is exhausted
    assert result.backtrack_count == 0

def test_backtracking_skips_already_collected_nodes():
    """Nodes already in collected_ids are not re-expanded during backtracking."""
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Anchor → A
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        # Step from A: visit B and C (leaves D unchosen)
        json.dumps({"visit": [b.id, c.id], "done": False, "reason": "visit B and C"}),
        # B expansion: no unvisited neighbors
        # C expansion: no unvisited neighbors
        # Verifier 1: unverified, missing D
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Missing D.",
            "note": "incomplete"
        }),
        # Backtracking: D is enqueued. B and C already collected → skipped.
        # D expansion: no unvisited neighbors
        # Verifier 2: verified
        json.dumps({
            "complete": True,
            "noise_ids": [],
            "missing_description": "",
            "note": "complete"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=10)
    result = engine.query("Explain A fully")
    assert result.verified is True
    # D should be in the result, B and C should also be there (collected earlier)
    labels = {n.label for n in result.nodes}
    assert "D" in labels
    assert "B" in labels
    assert "C" in labels

def test_stub_node_not_expanded():
    """Stub node is added to result but _collector_step is never called for it."""
    g = Graph(name="Stub Test", description="Test stub behavior.")

    root = g.add_node(Node(
        label="Root",
        type=NodeType.DEFINITION,
        body="Root concept.",
        scope="Root.",
    ))
    stub = g.add_node(Node(
        label="External Concept",
        type=NodeType.STUB,
        body="External — see graph:other.",
        scope="Stub placeholder.",
    ))
    leaf = g.add_node(Node(
        label="Leaf",
        type=NodeType.BEHAVIOR,
        body="A real leaf node.",
        scope="Leaf behavior.",
    ))

    g.add_edge(Edge(source_id=root.id, target_id=stub.id, relations=["references"], base_weight=0.5))
    g.add_edge(Edge(source_id=stub.id, target_id=leaf.id, relations=["details"], base_weight=0.6))

    mock = MockLLMClient([
        # Anchor → root
        json.dumps({"anchor_id": root.id, "reason": "root"}),
        # Step from root: visit stub
        json.dumps({"visit": [stub.id], "done": False, "reason": "need stub"}),
        # Stub is dequeued but NOT expanded — no collector call for it.
        # BFS ends because nothing else is in the queue.
        # Verifier
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=10)
    result = engine.query("What is root?")

    # Stub should be collected
    labels = {n.label for n in result.nodes}
    assert "External Concept" in labels

    # Leaf should NOT be collected — stub was not expanded
    assert "Leaf" not in labels


# ---------------------------------------------------------------------------
# Return value tests
# ---------------------------------------------------------------------------

def test_returns_verified_result_when_backtracking_succeeds():
    """When backtracking produces a verified result, that's what we get back."""
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        # Visit only C
        json.dumps({"visit": [c.id], "done": False, "reason": "try C"}),
        # Verifier 1: missing
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Missing D.",
            "note": "incomplete"
        }),
        # Backtracking picks up B + D
        # Verifier 2: verified
        json.dumps({
            "complete": True,
            "noise_ids": [],
            "missing_description": "",
            "note": "now complete"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=10)
    result = engine.query("Explain A")
    assert result.verified is True

def test_returns_most_complete_result_when_all_unverified():
    """When no pass verifies, return the result with the most nodes."""
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        # Visit only C
        json.dumps({"visit": [c.id], "done": False, "reason": "try C"}),
        # Verifier 1: missing (2 nodes: A, C)
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Missing D.",
            "note": "incomplete"
        }),
        # Backtracking picks up B + D (now 4 nodes: A, C, B, D)
        # Verifier 2: still unverified but more complete
        json.dumps({
            "complete": False,
            "noise_ids": [],
            "missing_description": "Still missing something.",
            "note": "still incomplete"
        }),
    ])
    engine = TraversalEngine(graph=g, llm=mock, max_depth=10)
    result = engine.query("Explain A fully")
    assert result.verified is False
    # Should have all 4 nodes (the most complete result)
    assert len(result.nodes) == 4


# ---------------------------------------------------------------------------
# MultiPassResult tests
# ---------------------------------------------------------------------------

def test_multi_pass_result_nodes_delegates_to_best():
    n = Node(label="X", type=NodeType.DEFINITION, body="body", scope="scope")
    tr = TraversalResult(query="q", nodes=[n], verified=True)
    mpr = MultiPassResult(query="q", best=tr, passes_run=1, verified=True)
    assert mpr.nodes() == [n]

def test_multi_pass_result_verified_false_when_no_passes():
    mpr = MultiPassResult(query="q")
    assert mpr.verified is False
    assert mpr.nodes() == []
    assert mpr.edges() == []

def test_multi_pass_result_summary_includes_missing_when_unverified():
    tr = TraversalResult(query="q", missing_description="Need more nodes", verified=False)
    mpr = MultiPassResult(query="q", best=tr, passes_run=1, verified=False)
    s = mpr.summary()
    assert "Missing" in s
    assert "Need more nodes" in s


# ---------------------------------------------------------------------------
# MultiPassEngine tests
# ---------------------------------------------------------------------------

def test_multi_pass_returns_immediately_on_first_pass_verified():
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Pass 1: anchor -> A, collector visits B, verifier verified
        # B has no unvisited neighbours (only A is a neighbour and it's collected),
        # so no collector step is called for B.
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [b.id], "done": False, "reason": "get B"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=3, max_depth=10)
    result = engine.query("Explain A")
    assert result.passes_run == 1
    assert result.verified is True
    assert len(result.all_passes) == 1

def test_multi_pass_runs_second_pass_when_first_unverified():
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Pass 1: anchor -> A, visits C only, verifier unverified + missing
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [c.id], "done": False, "reason": "try C"}),
        # Verifier 1 (first pass) - unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing D.", "note": "incomplete"}),
        # Backtracking picks up B + D, second verifier still unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # Pass 2: anchor -> A, visits D, verifier verified
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [d.id], "done": False, "reason": "get D this time"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "all good"}),
    ])
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=3, max_depth=10)
    result = engine.query("Explain A")
    assert result.passes_run == 2
    assert result.verified is True

def test_multi_pass_runs_maximum_three_passes():
    g, a, b, c, d = build_backtrack_graph()
    # Each pass: anchor + collector done + verifier unverified (no unchosen neighbours for backtracking)
    responses = []
    for _ in range(3):
        responses.extend([
            json.dumps({"anchor_id": a.id, "reason": "root"}),
            json.dumps({"visit": [], "done": True, "reason": "done"}),
            json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing stuff.", "note": "incomplete"}),
            # Backtracking: unchosen neighbours exist, verifier still says incomplete
            json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        ])
    mock = MockLLMClient(responses)
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=3, max_depth=10)
    result = engine.query("Explain A")
    assert result.passes_run == 3
    assert result.verified is False

def test_multi_pass_returns_best_unverified_after_max_passes():
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Pass 1: anchor A, visits C only -> 2 nodes (A, C)
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [c.id], "done": False, "reason": "try C"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing.", "note": "incomplete"}),
        # Backtracking picks up B+D -> all 4 nodes, still unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # Pass 2: anchor A, visits B only -> 2 nodes (A, B)
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [b.id], "done": True, "reason": "try B"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing.", "note": "incomplete"}),
    ])
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=2, max_depth=10)
    result = engine.query("Explain A")
    assert result.verified is False
    # Best should be pass 1 (4 nodes after backtracking) not pass 2 (2 nodes)
    assert len(result.nodes()) >= 4

def test_multi_pass_early_exit_on_zero_nodes():
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Pass 1: anchor A, collector done, verifier unverified
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing D.", "note": "incomplete"}),
        # Backtracking picks up B+C+D, verifier still unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # Pass 2: anchor fails -> zero nodes
        "not json at all",
    ])
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=3, max_depth=10)
    result = engine.query("Explain A")
    assert result.passes_run == 2
    # Best should be from pass 1
    assert len(result.nodes()) > 0

def test_multi_pass_previous_context_appended_to_prompts():
    """On pass 2, the user prompt should contain 'Previous attempt summary'."""
    g, a, b, c, d = build_backtrack_graph()

    class CapturingMockLLMClient(MockLLMClient):
        def __init__(self, responses):
            super().__init__(responses)
            self.user_prompts = []

        def complete(self, system, user, temperature=0.0):
            self.user_prompts.append(user)
            return super().complete(system, user, temperature)

    mock = CapturingMockLLMClient([
        # Pass 1: anchor + done + unverified
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing D.", "note": "incomplete"}),
        # Backtracking: unchosen neighbours visited, still unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # Pass 2: anchor + done + verified
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [], "done": True, "reason": "done"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=3, max_depth=10)
    engine.query("Explain A")

    # The anchor prompt for pass 2 should contain previous context
    # Pass 1 uses prompts [0,1,2] (anchor, collector, verifier) + [3] (backtrack verifier)
    # Pass 2 anchor is the next prompt after pass 1 finishes
    pass2_prompts = [p for p in mock.user_prompts if "Previous attempt summary" in p]
    assert len(pass2_prompts) > 0, "Pass 2 should receive previous attempt context"

def test_multi_pass_each_pass_has_independent_session_record():
    """Backtrack state from pass 1 should not carry into pass 2."""
    g, a, b, c, d = build_backtrack_graph()
    mock = MockLLMClient([
        # Pass 1: anchor A, visits C (leaves B+D unchosen), verifier unverified
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [c.id], "done": False, "reason": "try C"}),
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Missing D.", "note": "incomplete"}),
        # Backtracking: B+D enqueued, still unverified
        json.dumps({"complete": False, "noise_ids": [], "missing_description": "Still missing.", "note": "still incomplete"}),
        # Pass 2: fresh start, anchor A, visits D, verified
        json.dumps({"anchor_id": a.id, "reason": "root"}),
        json.dumps({"visit": [d.id], "done": False, "reason": "get D"}),
        json.dumps({"complete": True, "noise_ids": [], "missing_description": "", "note": "ok"}),
    ])
    engine = MultiPassEngine(graph=g, llm=mock, max_passes=3, max_depth=10)
    result = engine.query("Explain A")
    # Pass 2 should work independently
    assert result.passes_run == 2
    assert result.verified is True


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
        test_session_record_initialises_empty,
        test_session_record_is_not_persisted,
        test_backtracking_triggered_on_missing_description,
        test_backtracking_not_triggered_on_noise_only,
        test_backtracking_respects_max_depth,
        test_backtracking_skips_already_collected_nodes,
        test_stub_node_not_expanded,
        test_returns_verified_result_when_backtracking_succeeds,
        test_returns_most_complete_result_when_all_unverified,
        test_multi_pass_result_nodes_delegates_to_best,
        test_multi_pass_result_verified_false_when_no_passes,
        test_multi_pass_result_summary_includes_missing_when_unverified,
        test_multi_pass_returns_immediately_on_first_pass_verified,
        test_multi_pass_runs_second_pass_when_first_unverified,
        test_multi_pass_runs_maximum_three_passes,
        test_multi_pass_returns_best_unverified_after_max_passes,
        test_multi_pass_early_exit_on_zero_nodes,
        test_multi_pass_previous_context_appended_to_prompts,
        test_multi_pass_each_pass_has_independent_session_record,
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
