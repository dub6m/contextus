import pytest

from contextus import Node, NodeType, Edge, Graph


# ------------------------------------------------------------------
# Node tests
# ------------------------------------------------------------------

def make_node(label="Binary Search", ntype=NodeType.DEFINITION) -> Node:
    return Node(
        label=label,
        type=ntype,
        body="Binary search is a search algorithm that finds a target value within a sorted array by repeatedly halving the search space.",
        scope="Covers only the definition of binary search. Does not cover implementation, complexity, or variants.",
        aliases=["binary chop", "half-interval search"],
    )

def test_node_creation():
    n = make_node()
    assert n.label == "Binary Search"
    assert n.type == NodeType.DEFINITION
    assert len(n.aliases) == 2
    assert n.id is not None

def test_node_summary():
    n = make_node()
    assert "[definition]" in n.summary()
    assert "Binary Search" in n.summary()

def test_node_empty_label_raises():
    with pytest.raises(ValueError):
        Node(label="", type=NodeType.DEFINITION, body="x", scope="x")

def test_node_empty_scope_raises():
    with pytest.raises(ValueError):
        Node(label="X", type=NodeType.DEFINITION, body="x", scope="")

def test_node_serialization_roundtrip():
    n = make_node()
    assert Node.from_dict(n.to_dict()).label == n.label
    assert Node.from_dict(n.to_dict()).id == n.id


# ------------------------------------------------------------------
# Edge tests
# ------------------------------------------------------------------

def test_edge_creation():
    e = Edge(source_id="a", target_id="b", relations=["depends_on"])
    assert e.base_weight == 1.0
    assert e.derived_weight is None

def test_edge_effective_weight_no_derived():
    e = Edge(source_id="a", target_id="b", relations=["r"], base_weight=0.8)
    assert e.effective_weight() == 0.8

def test_edge_effective_weight_blended():
    e = Edge(source_id="a", target_id="b", relations=["r"], base_weight=0.8)
    e.update_derived_weight(0.4)
    # alpha=0.5: 0.8 * 0.5 + 0.4 * 0.5 = 0.6
    assert abs(e.effective_weight(alpha=0.5) - 0.6) < 1e-9

def test_edge_self_loop_raises():
    with pytest.raises(ValueError):
        Edge(source_id="a", target_id="a", relations=["r"])

def test_edge_empty_relations_raises():
    with pytest.raises(ValueError):
        Edge(source_id="a", target_id="b", relations=[])

def test_edge_invalid_weight_raises():
    with pytest.raises(ValueError):
        Edge(source_id="a", target_id="b", relations=["r"], base_weight=1.5)

def test_edge_serialization_roundtrip():
    e = Edge(source_id="a", target_id="b", relations=["depends_on", "clarifies"], base_weight=0.7)
    e2 = Edge.from_dict(e.to_dict())
    assert e2.relations == e.relations
    assert e2.base_weight == e.base_weight


# ------------------------------------------------------------------
# Graph tests
# ------------------------------------------------------------------

def build_graph() -> tuple[Graph, Node, Node, Node]:
    g = Graph(name="Test Graph", description="For testing.")
    n1 = g.add_node(make_node("Binary Search", NodeType.DEFINITION))
    n2 = g.add_node(Node(
        label="O(log n) complexity",
        type=NodeType.BEHAVIOR,
        body="Binary search runs in O(log n) time because it halves the search space each step.",
        scope="Covers only the time complexity of binary search. Not space complexity or comparisons.",
    ))
    n3 = g.add_node(Node(
        label="Sorted array requirement",
        type=NodeType.CONSTRAINT,
        body="Binary search requires the input array to be sorted in advance.",
        scope="Covers only the precondition of a sorted input. Does not cover sorting algorithms.",
    ))
    return g, n1, n2, n3

def test_graph_add_and_get_node():
    g, n1, _, _ = build_graph()
    assert g.get_node(n1.id).label == "Binary Search"
    assert g.node_count() == 3

def test_graph_add_duplicate_node_raises():
    g, n1, _, _ = build_graph()
    with pytest.raises(ValueError):
        g.add_node(n1)

def test_graph_add_edge():
    g, n1, n2, _ = build_graph()
    e = g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["has_behavior"]))
    assert g.edge_count() == 1
    assert g.get_edge(e.id).relations == ["has_behavior"]

def test_graph_neighbors_out():
    g, n1, n2, n3 = build_graph()
    g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["has_behavior"]))
    g.add_edge(Edge(source_id=n1.id, target_id=n3.id, relations=["has_constraint"]))
    out = g.neighbors_out(n1.id)
    assert len(out) == 2
    labels = {node.label for node, _ in out}
    assert "O(log n) complexity" in labels
    assert "Sorted array requirement" in labels

def test_graph_neighbors_in():
    g, n1, n2, _ = build_graph()
    g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["has_behavior"]))
    inc = g.neighbors_in(n2.id)
    assert len(inc) == 1
    assert inc[0][0].label == "Binary Search"

def test_graph_remove_node_cleans_edges():
    g, n1, n2, _ = build_graph()
    g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["has_behavior"]))
    assert g.edge_count() == 1
    g.remove_node(n1.id)
    assert g.node_count() == 2
    assert g.edge_count() == 0

def test_graph_edge_unknown_node_raises():
    g, n1, _, _ = build_graph()
    with pytest.raises(KeyError):
        g.add_edge(Edge(source_id=n1.id, target_id="nonexistent", relations=["r"]))

def test_graph_summary_contains_nodes():
    g, _, _, _ = build_graph()
    s = g.summary()
    assert "Binary Search" in s
    assert "O(log n) complexity" in s

def test_graph_serialization_roundtrip():
    g, n1, n2, n3 = build_graph()
    g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["has_behavior"], base_weight=0.9))
    g2 = Graph.from_json(g.to_json())
    assert g2.name == g.name
    assert g2.node_count() == 3
    assert g2.edge_count() == 1
    assert g2.get_node(n1.id).label == "Binary Search"


# ------------------------------------------------------------------
# Stub node tests
# ------------------------------------------------------------------

def make_stub(label="Sorting", body="Sorting — arranging elements in order. See graph:algorithms.") -> Node:
    return Node(
        label=label,
        type=NodeType.STUB,
        body=body,
        scope="Placeholder for the sorting concept owned by the algorithms graph.",
    )

def test_stub_node_creation():
    n = make_stub()
    assert n.label == "Sorting"
    assert n.type == NodeType.STUB
    assert n.id is not None

def test_is_stub_true_for_stub_nodes():
    n = make_stub()
    assert n.is_stub is True

def test_is_stub_false_for_other_types():
    for ntype in NodeType:
        if ntype == NodeType.STUB:
            continue
        n = make_node(ntype=ntype)
        assert n.is_stub is False, f"is_stub should be False for {ntype}"

def test_stub_allows_empty_body():
    """Stub nodes may have minimal body — the empty-body check is bypassed."""
    n = Node(
        label="Placeholder",
        type=NodeType.STUB,
        body="",
        scope="Intentionally empty stub.",
    )
    assert n.type == NodeType.STUB
    assert n.body == ""

def test_stub_serialization_roundtrip():
    n = make_stub()
    d = n.to_dict()
    n2 = Node.from_dict(d)
    assert n2.label == n.label
    assert n2.type == NodeType.STUB
    assert n2.id == n.id
    assert n2.body == n.body
    assert n2.scope == n.scope
    assert n2.is_stub is True

def test_stub_node_added_to_graph():
    g = Graph(name="Test", description="Stubs in graph.")
    stub = g.add_node(make_stub())
    assert g.node_count() == 1
    assert g.get_node(stub.id).type == NodeType.STUB

def test_stub_node_retrieved_by_id():
    g = Graph(name="Test", description="Retrieve stub.")
    stub = g.add_node(make_stub("Hashing"))
    retrieved = g.get_node(stub.id)
    assert retrieved.label == "Hashing"
    assert retrieved.is_stub is True

def test_stub_summary_format():
    n = make_stub()
    s = n.summary()
    assert s.startswith("[stub]")
    assert "Sorting" in s


# ------------------------------------------------------------------
# Example subtype tests
# ------------------------------------------------------------------

def make_example(subtype=None) -> Node:
    return Node(
        label="Binary search on [1,3,5,7]",
        type=NodeType.EXAMPLE,
        body="Search for 5 in [1,3,5,7]: mid=3<5, narrow to right half, mid=5 → found.",
        scope="Concrete walkthrough of binary search on a small sorted array.",
        subtype=subtype,
    )

def test_example_subtype_concrete():
    n = make_example(subtype="concrete")
    assert n.subtype == "concrete"

def test_example_subtype_analogy():
    n = make_example(subtype="analogy")
    assert n.subtype == "analogy"

def test_example_subtype_none():
    n = make_example(subtype=None)
    assert n.subtype is None

def test_example_invalid_subtype_raises():
    with pytest.raises(ValueError, match="Invalid subtype"):
        make_example(subtype="narrative")

def test_subtype_on_non_example_raises():
    with pytest.raises(ValueError, match="only valid for example"):
        Node(
            label="X",
            type=NodeType.DEFINITION,
            body="body",
            scope="scope",
            subtype="concrete",
        )

def test_subtype_serialization_roundtrip():
    n = make_example(subtype="analogy")
    d = n.to_dict()
    assert d["subtype"] == "analogy"
    n2 = Node.from_dict(d)
    assert n2.subtype == "analogy"

def test_subtype_none_serialization_roundtrip():
    n = make_example(subtype=None)
    d = n.to_dict()
    assert d["subtype"] is None
    n2 = Node.from_dict(d)
    assert n2.subtype is None

def test_summary_includes_subtype_when_present():
    n = make_example(subtype="concrete")
    assert "[example:concrete]" in n.summary()

def test_summary_omits_subtype_when_none():
    n = make_example(subtype=None)
    assert "[example]" in n.summary()
    assert ":" not in n.summary().split("]")[0]  # no colon inside the tag
