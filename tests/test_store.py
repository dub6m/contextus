"""
Tests for GraphStore — graph persistence via JSON files.

All tests use the `tmp_path` fixture so they never touch the real filesystem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextus import GraphStore, Graph, Node, NodeType, Edge


# ---------------------------------------------------------------------------
# Helpers — minimal graph factories
# ---------------------------------------------------------------------------

def make_graph(name: str = "TestGraph") -> Graph:
    """Minimal two-node graph for use in tests."""
    g = Graph(name=name, description=f"Test graph: {name}")
    n1 = g.add_node(Node(
        label="Alpha",
        type=NodeType.DEFINITION,
        body="Body of Alpha.",
        scope="Covers Alpha only.",
    ))
    n2 = g.add_node(Node(
        label="Beta",
        type=NodeType.BEHAVIOR,
        body="Body of Beta.",
        scope="Covers Beta only.",
    ))
    g.add_edge(Edge(
        source_id=n1.id,
        target_id=n2.id,
        relations=["depends_on"],
        base_weight=0.8,
    ))
    return g


def make_rich_graph(name: str = "RichGraph") -> Graph:
    """Graph exercising all node types relevant for roundtrip tests."""
    g = Graph(name=name, description="Graph with diverse node types.")

    n_def = g.add_node(Node(
        label="Concept",
        type=NodeType.DEFINITION,
        body="What the concept is.",
        scope="Covers definition only.",
    ))
    n_beh = g.add_node(Node(
        label="Behaviour",
        type=NodeType.BEHAVIOR,
        body="How it behaves.",
        scope="Covers behaviour only.",
    ))
    n_con = g.add_node(Node(
        label="Constraint",
        type=NodeType.CONSTRAINT,
        body="Rules that apply.",
        scope="Covers constraints only.",
    ))
    n_pro = g.add_node(Node(
        label="Procedure",
        type=NodeType.PROCEDURE,
        body="Steps to follow.",
        scope="Covers procedure only.",
    ))
    n_exc = g.add_node(Node(
        label="Exception",
        type=NodeType.EXCEPTION,
        body="Where rules break.",
        scope="Covers exceptions only.",
    ))
    n_rel = g.add_node(Node(
        label="Relation",
        type=NodeType.RELATION,
        body="Interaction mechanics.",
        scope="Covers relation only.",
    ))
    n_ex = g.add_node(Node(
        label="Example",
        type=NodeType.EXAMPLE,
        subtype="concrete",
        body="A concrete worked example.",
        scope="Covers example only.",
    ))
    n_stub = g.add_node(Node(
        label="Stub Node",
        type=NodeType.STUB,
        body="Stub — owned by another graph.",
        scope="Stub only. Full definition in OtherGraph.",
    ))

    g.add_edge(Edge(source_id=n_def.id, target_id=n_beh.id,  relations=["has_behavior"],  base_weight=0.9))
    g.add_edge(Edge(source_id=n_def.id, target_id=n_con.id,  relations=["has_constraint"], base_weight=0.85))
    g.add_edge(Edge(source_id=n_beh.id, target_id=n_exc.id,  relations=["has_exception"],  base_weight=0.7))
    g.add_edge(Edge(source_id=n_ex.id,  target_id=n_def.id,  relations=["demonstrates"],   base_weight=0.8))
    g.add_edge(Edge(source_id=n_def.id, target_id=n_stub.id, relations=["requires"],        base_weight=0.95))

    return g


# ===========================================================================
# Basic CRUD tests
# ===========================================================================

def test_save_creates_file(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()
    store.save(g)
    assert (tmp_path / "TestGraph.json").exists()


def test_save_returns_correct_path(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph("MyGraph")
    returned = store.save(g)
    assert returned == tmp_path / "MyGraph.json"


def test_load_returns_equivalent_graph(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()
    store.save(g)

    loaded = store.load("TestGraph")

    assert loaded.name == g.name
    assert loaded.description == g.description
    assert loaded.node_count() == g.node_count()
    assert loaded.edge_count() == g.edge_count()

    original_node_ids = {n.id for n in g.all_nodes()}
    loaded_node_ids   = {n.id for n in loaded.all_nodes()}
    assert original_node_ids == loaded_node_ids

    original_edge_ids = {e.id for e in g.all_edges()}
    loaded_edge_ids   = {e.id for e in loaded.all_edges()}
    assert original_edge_ids == loaded_edge_ids


def test_load_raises_on_missing_graph(tmp_path):
    store = GraphStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("DoesNotExist")


def test_exists_true_after_save(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()
    store.save(g)
    assert store.exists("TestGraph") is True


def test_exists_false_before_save(tmp_path):
    store = GraphStore(tmp_path)
    assert store.exists("NeverSaved") is False


def test_delete_removes_file(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()
    store.save(g)
    assert store.exists("TestGraph")

    store.delete("TestGraph")
    assert not store.exists("TestGraph")
    assert not (tmp_path / "TestGraph.json").exists()


def test_delete_raises_on_missing_graph(tmp_path):
    store = GraphStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.delete("Ghost")


# ===========================================================================
# Multi-graph tests
# ===========================================================================

def test_list_graphs_empty_on_new_store(tmp_path):
    store = GraphStore(tmp_path)
    assert store.list_graphs() == []


def test_list_graphs_returns_all_names(tmp_path):
    store = GraphStore(tmp_path)
    for name in ("Gamma", "Alpha", "Beta"):
        store.save(make_graph(name))

    names = store.list_graphs()
    assert set(names) == {"Alpha", "Beta", "Gamma"}


def test_list_graphs_sorted_alphabetically(tmp_path):
    store = GraphStore(tmp_path)
    for name in ("Zebra", "Apple", "Mango"):
        store.save(make_graph(name))

    assert store.list_graphs() == ["Apple", "Mango", "Zebra"]


def test_save_all_saves_all_graphs(tmp_path):
    store = GraphStore(tmp_path)
    graphs = [make_graph(n) for n in ("One", "Two", "Three")]
    paths = store.save_all(graphs)

    assert len(paths) == 3
    for p in paths:
        assert p.exists()

    assert set(store.list_graphs()) == {"One", "Two", "Three"}


def test_load_all_returns_all_graphs(tmp_path):
    store = GraphStore(tmp_path)
    for name in ("X", "Y", "Z"):
        store.save(make_graph(name))

    loaded = store.load_all()
    assert len(loaded) == 3
    assert {g.name for g in loaded} == {"X", "Y", "Z"}


def test_load_all_sorted_by_name(tmp_path):
    store = GraphStore(tmp_path)
    for name in ("Charlie", "Alpha", "Bravo"):
        store.save(make_graph(name))

    loaded = store.load_all()
    assert [g.name for g in loaded] == ["Alpha", "Bravo", "Charlie"]


# ===========================================================================
# Overwrite and persistence tests
# ===========================================================================

def test_save_overwrites_existing(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()
    store.save(g)

    # Mutate a node in the in-memory graph
    node = g.all_nodes()[0]
    original_body = node.body
    node.body = "Updated body after overwrite."
    assert node.body != original_body

    # Save again — must overwrite
    store.save(g)

    # Load and confirm mutation was persisted
    loaded = store.load("TestGraph")
    loaded_node = loaded.get_node(node.id)
    assert loaded_node.body == "Updated body after overwrite."


def test_json_is_human_readable(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()
    path = store.save(g)

    content = path.read_text(encoding="utf-8")

    # Must be valid JSON
    data = json.loads(content)
    assert isinstance(data, dict)

    # Must be indented (indent=2 produces newlines and leading spaces)
    assert "\n" in content
    assert "  " in content


# ===========================================================================
# Roundtrip fidelity tests
# ===========================================================================

def test_roundtrip_preserves_node_count(tmp_path):
    store = GraphStore(tmp_path)
    g = make_rich_graph()
    store.save(g)
    loaded = store.load("RichGraph")
    assert loaded.node_count() == g.node_count()


def test_roundtrip_preserves_edge_count(tmp_path):
    store = GraphStore(tmp_path)
    g = make_rich_graph()
    store.save(g)
    loaded = store.load("RichGraph")
    assert loaded.edge_count() == g.edge_count()


def test_roundtrip_preserves_node_types(tmp_path):
    store = GraphStore(tmp_path)
    g = make_rich_graph()
    store.save(g)
    loaded = store.load("RichGraph")

    original_types = {n.id: n.type for n in g.all_nodes()}
    for n in loaded.all_nodes():
        assert n.type == original_types[n.id], (
            f"Node {n.label!r}: expected type {original_types[n.id]}, got {n.type}"
        )


def test_roundtrip_preserves_stub_node(tmp_path):
    store = GraphStore(tmp_path)
    g = make_rich_graph()

    # Identify the stub node in the original
    stubs = [n for n in g.all_nodes() if n.is_stub]
    assert len(stubs) == 1, "Test setup: expected exactly one Stub node"
    stub_id = stubs[0].id

    store.save(g)
    loaded = store.load("RichGraph")

    loaded_stub = loaded.get_node(stub_id)
    assert loaded_stub.is_stub is True
    assert loaded_stub.type == NodeType.STUB


def test_roundtrip_preserves_example_subtype(tmp_path):
    store = GraphStore(tmp_path)
    g = make_rich_graph()

    examples = [n for n in g.all_nodes() if n.type == NodeType.EXAMPLE]
    assert len(examples) == 1, "Test setup: expected exactly one Example node"
    original_subtype = examples[0].subtype
    example_id = examples[0].id

    store.save(g)
    loaded = store.load("RichGraph")

    loaded_example = loaded.get_node(example_id)
    assert loaded_example.subtype == original_subtype


def test_roundtrip_preserves_cluster_weights(tmp_path):
    store = GraphStore(tmp_path)
    g = make_graph()

    # Set cluster_weights on the edge before saving
    edge = g.all_edges()[0]
    edge.update_cluster_weight(0,  0.95)
    edge.update_cluster_weight(1,  0.40)
    edge.update_cluster_weight(-1, 0.75)

    store.save(g)
    loaded = store.load("TestGraph")

    loaded_edge = loaded.get_edge(edge.id)
    assert loaded_edge.cluster_weights[0]  == pytest.approx(0.95)
    assert loaded_edge.cluster_weights[1]  == pytest.approx(0.40)
    assert loaded_edge.cluster_weights[-1] == pytest.approx(0.75)


def test_roundtrip_backwards_compat_derived_weight(tmp_path):
    """
    Manually write a JSON file using the old `derived_weight` field (pre-v0.1
    format). Loading it must migrate the value into cluster_weights[-1].
    """
    store = GraphStore(tmp_path)
    g = make_graph()

    # Serialise normally, then rewrite edges with old format
    data = json.loads(g.to_json())
    for ed in data["edges"]:
        ed.pop("cluster_weights", None)
        ed["derived_weight"] = 0.65

    path = tmp_path / "TestGraph.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    loaded = store.load("TestGraph")

    for edge in loaded.all_edges():
        assert edge.cluster_weights.get(-1) == pytest.approx(0.65), (
            f"Edge {edge.id!r}: expected cluster_weights[-1]=0.65, "
            f"got {edge.cluster_weights}"
        )


# ===========================================================================
# Storage directory tests
# ===========================================================================

def test_storage_dir_created_on_init(tmp_path):
    new_dir = tmp_path / "new_store"
    assert not new_dir.exists()
    GraphStore(new_dir)
    assert new_dir.exists()
    assert new_dir.is_dir()


def test_storage_dir_nested_created(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()
    GraphStore(nested)
    assert nested.exists()
    assert nested.is_dir()
