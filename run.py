"""
Contextus — end-to-end integration run.

Exercises: multi-pass traversal via MultiPassEngine (through the Router),
backtracking, query-conditioned edge weights, cluster formation, and stub
node boundary behaviour.

Usage:
    export CEREBRAS_API_KEY=your_key_here
    python run.py

    # or inline:
    CEREBRAS_API_KEY=your_key python run.py
"""

import os
import sys
import textwrap
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from contextus import (
    Node, NodeType, Edge, Graph,
    CerebrasClient,
    MultiPassEngine, MultiPassResult,
    Router, RouterResult,
    WeightSystem,
    GraphStore,
)

STORAGE_DIR = Path(__file__).parent / "graphs"


# ---------------------------------------------------------------------------
# Colour helpers (terminal output only)
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
DIM    = "\033[2m"

def header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}{text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")

def ok(text: str)   -> None: print(f"{GREEN}✓ {text}{RESET}")
def warn(text: str) -> None: print(f"{YELLOW}⚠ {text}{RESET}")
def info(text: str) -> None: print(f"{DIM}{text}{RESET}")
def err(text: str)  -> None: print(f"{RED}✗ {text}{RESET}")


# ---------------------------------------------------------------------------
# Build the graphs
# ---------------------------------------------------------------------------

def build_decorators_graph() -> Graph:
    """
    A graph about Python decorators.
    Correct retrieval for 'how does a decorator work' requires traversing
    through: decorator definition → higher-order functions → first-class
    functions (stub — owned by PythonFoundations) + closure scope.

    The First-Class Functions node is a Stub — it is foundational Python
    knowledge that belongs in a separate PythonFoundations graph. The Stub
    preserves the dependency relationship without importing foreign knowledge.
    """
    g = Graph(
        name="PythonDecorators",
        description="Core concepts needed to understand Python decorators.",
    )

    n_dec = g.add_node(Node(
        label="Python Decorator",
        type=NodeType.DEFINITION,
        body=(
            "A decorator is a callable that takes a function as input and returns "
            "a new function (or modified callable) as output. Applied with the @ "
            "syntax above a function definition. e.g. @my_decorator before def foo(): ..."
        ),
        scope="Covers only the definition and syntax of Python decorators. Not how they are implemented internally or what makes them possible.",
        aliases=["decorator", "@decorator"],
    ))

    n_hof = g.add_node(Node(
        label="Higher-Order Function",
        type=NodeType.BEHAVIOR,
        body=(
            "A higher-order function is a function that either accepts another function "
            "as an argument, returns a function as its result, or both. Decorators are "
            "a specific use of higher-order functions."
        ),
        scope="Covers the concept of higher-order functions and their role in decorator mechanics. Not general functional programming.",
    ))

    # First-Class Functions is a Stub — the full definition is owned by the
    # PythonFoundations graph. This node acts as a boundary marker only.
    n_fcf_stub = g.add_node(Node(
        label="First-Class Functions",
        type=NodeType.STUB,
        body=(
            "Functions are first-class objects in Python — they can be passed, "
            "returned, and stored. Full definition in PythonFoundations graph."
        ),
        scope="Stub only. Full definition owned by PythonFoundations graph.",
    ))

    n_clo = g.add_node(Node(
        label="Closure and Scope",
        type=NodeType.BEHAVIOR,
        body=(
            "A closure is a function that remembers the variables from its enclosing "
            "scope even after that scope has finished executing. Decorator wrapper "
            "functions rely on closures to retain access to the original function."
        ),
        scope="Covers closures and lexical scoping as they relate to decorators. Not general variable scoping rules.",
    ))

    n_syn = g.add_node(Node(
        label="@ Syntax Sugar",
        type=NodeType.BEHAVIOR,
        body=(
            "@decorator above def foo() is exactly equivalent to foo = decorator(foo). "
            "The @ symbol is syntactic sugar introduced in PEP 318. It applies the "
            "decorator at function definition time, not at call time."
        ),
        scope="Covers only the @ syntax and its equivalence to explicit decorator application. Not stacking or parameterised decorators.",
    ))

    n_sta = g.add_node(Node(
        label="Stacking Decorators",
        type=NodeType.BEHAVIOR,
        body=(
            "Multiple decorators can be stacked. They are applied bottom-up: "
            "@a @b def foo() is equivalent to foo = a(b(foo)). "
            "The innermost decorator is applied first."
        ),
        scope="Covers stacking multiple decorators only. Not single decorator mechanics.",
    ))

    n_pre = g.add_node(Node(
        label="functools.wraps",
        type=NodeType.PROCEDURE,
        body=(
            "When writing a decorator, use @functools.wraps(original_fn) on the wrapper "
            "function to preserve the original function's __name__, __doc__, and other "
            "metadata. Without it, introspection tools see the wrapper, not the original."
        ),
        scope="Covers functools.wraps usage in decorator implementation only.",
    ))

    n_exc = g.add_node(Node(
        label="Class-Based Decorators",
        type=NodeType.EXCEPTION,
        body=(
            "Decorators don't have to be functions. Any callable works, including class "
            "instances with __call__ defined. Class-based decorators are useful when "
            "the decorator needs to maintain state across calls."
        ),
        scope="Covers class-based decorators as an exception to the function-only mental model. Not class decorators (decorating classes).",
    ))

    # Edges — directed, typed, weighted
    g.add_edge(Edge(source_id=n_dec.id,      target_id=n_hof.id,      relations=["requires", "is_instance_of"], base_weight=0.95))
    g.add_edge(Edge(source_id=n_hof.id,      target_id=n_fcf_stub.id, relations=["depends_on"],                  base_weight=0.95))
    g.add_edge(Edge(source_id=n_hof.id,      target_id=n_clo.id,      relations=["depends_on"],                  base_weight=0.85))
    g.add_edge(Edge(source_id=n_dec.id,      target_id=n_syn.id,      relations=["has_syntax"],                  base_weight=0.80))
    g.add_edge(Edge(source_id=n_syn.id,      target_id=n_sta.id,      relations=["extends_to"],                  base_weight=0.65))
    g.add_edge(Edge(source_id=n_dec.id,      target_id=n_pre.id,      relations=["best_practice_requires"],      base_weight=0.70))
    g.add_edge(Edge(source_id=n_dec.id,      target_id=n_exc.id,      relations=["has_exception"],               base_weight=0.50))

    return g


def build_python_types_graph() -> Graph:
    """
    A second graph about Python's type system.
    Used to test multi-graph routing — some queries need both graphs.
    """
    g = Graph(
        name="PythonTypes",
        description="Core concepts about Python's type system and type hints.",
    )

    n_dyn = g.add_node(Node(
        label="Dynamic Typing",
        type=NodeType.DEFINITION,
        body=(
            "Python is dynamically typed: variables don't have fixed types. "
            "A variable can hold any object and its type is checked at runtime, "
            "not at compile time."
        ),
        scope="Covers Python's dynamic typing model only. Not type hints or static analysis.",
    ))

    n_hin = g.add_node(Node(
        label="Type Hints",
        type=NodeType.BEHAVIOR,
        body=(
            "Type hints (PEP 484) let you annotate variables and function signatures "
            "with expected types: def foo(x: int) -> str. They are not enforced at "
            "runtime by default — they are metadata for static analysis tools."
        ),
        scope="Covers type hint syntax and semantics only. Not runtime enforcement or generics.",
    ))

    n_pro = g.add_node(Node(
        label="Protocol (Structural Subtyping)",
        type=NodeType.DEFINITION,
        body=(
            "A Protocol (PEP 544) defines a structural interface. A class satisfies "
            "a Protocol if it has the required methods/attributes, without needing to "
            "explicitly inherit from it. This is duck typing made explicit."
        ),
        scope="Covers Python Protocols for structural subtyping only. Not ABC or nominal subtyping.",
    ))

    n_gen = g.add_node(Node(
        label="Generics and TypeVar",
        type=NodeType.BEHAVIOR,
        body=(
            "TypeVar allows writing generic functions and classes that work with "
            "multiple types while remaining type-safe: T = TypeVar('T'). "
            "Used to express 'same type in, same type out' relationships."
        ),
        scope="Covers TypeVar and generic type annotations only. Not runtime generics.",
    ))

    g.add_edge(Edge(source_id=n_dyn.id, target_id=n_hin.id, relations=["augmented_by"], base_weight=0.85))
    g.add_edge(Edge(source_id=n_hin.id, target_id=n_pro.id, relations=["enables"],      base_weight=0.75))
    g.add_edge(Edge(source_id=n_hin.id, target_id=n_gen.id, relations=["enables"],      base_weight=0.80))

    return g


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_result(result: RouterResult, cluster_label: int = -1) -> None:
    """Print a RouterResult in the updated multi-pass format."""
    nodes = result.all_nodes()
    edges = result.all_edges()
    node_label = {n.id: n.label for n in nodes}

    graphs_hit = [t.graph_name for t in result.traversals]
    print(f"  Cluster label  : {cluster_label}")
    print(f"  Graphs queried : {graphs_hit}")
    print(f"  Graphs skipped : {result.skipped_graphs}")
    print(f"  Dispatch reason: {result.dispatch_reason}")
    print(f"  Verified       : {GREEN + 'YES' + RESET if result.verified else RED + 'NO' + RESET}")

    # Per-graph multi-pass detail
    if result.traversals:
        print(f"  Passes run per graph:")
        for t in result.traversals:
            bt = t.best.backtrack_count if t.best else 0
            print(
                f"    {t.graph_name}: {t.passes_run} pass(es), "
                f"backtracked: {bt} time(s)"
            )

    # Nodes
    print(f"  Nodes ({len(nodes)}):")
    for n in nodes:
        tag = f"{n.type.value}:{n.subtype}" if n.subtype else n.type.value
        stub_marker = f"  {YELLOW}[STUB — boundary only]{RESET}" if n.is_stub else ""
        print(f"    {DIM}[{tag}]{RESET} {n.label}{stub_marker}")
        print(f"      {DIM}{textwrap.shorten(n.scope, width=80)}{RESET}")

    # Edges — resolve to labels for readability
    print(f"  Edges ({len(edges)}):")
    for e in edges:
        src_label = node_label.get(e.source_id, e.source_id[:8] + "…")
        tgt_label = node_label.get(e.target_id, e.target_id[:8] + "…")
        cw_str = (
            "{" + ", ".join(f"{k}: {v:.3f}" for k, v in sorted(e.cluster_weights.items())) + "}"
            if e.cluster_weights else "{}"
        )
        eff = e.effective_weight(alpha=0.5, cluster_label=-1)
        print(
            f"    {DIM}{src_label} → {tgt_label} "
            f"{e.relations} "
            f"base={e.base_weight:.2f} derived={cw_str} effective={eff:.3f}{RESET}"
        )

    # Verifier notes
    for t in result.traversals:
        if t.best and t.best.verifier_note:
            print(f"  Verifier [{t.graph_name}]: {t.best.verifier_note}")


def print_weight_stats(ws: WeightSystem, graph_name: str) -> None:
    """Print per-edge weight statistics for a graph."""
    stats = ws.edge_stats(graph_name)
    print(f"\n  {BOLD}Edge weights after learning ({graph_name}):{RESET}")
    for s in sorted(stats, key=lambda x: x["effective_weight_a05_global"], reverse=True):
        cw = s["cluster_weights"]
        cw_str = (
            "{" + ", ".join(f"cluster {k}: {v:.3f}" for k, v in sorted(cw.items())) + "}"
            if cw else "{}"
        )
        print(
            f"    {DIM}{s['relations']}{RESET}  "
            f"base={s['base_weight']:.2f}  "
            f"derived={cw_str}  "
            f"effective(α=0.5, global)={s['effective_weight_a05_global']:.3f}"
        )


def print_cluster_stats(ws: WeightSystem) -> None:
    """Print query clustering statistics."""
    stats = ws.cluster_stats()
    print(f"\n  {BOLD}Cluster Stats:{RESET}")
    print(f"    Total queries   : {stats['total_queries']}")
    print(f"    Clusters formed : {stats['cluster_count']}")
    if stats["cluster_count"] > 0:
        for label, queries in stats["queries_per_cluster"].items():
            print(f"    Cluster {label} ({len(queries)} queries):")
            for q in queries:
                print(f"      {DIM}– {q[:70]}{RESET}")
    else:
        info("    (No clusters yet — need more similar queries to form clusters)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        err("CEREBRAS_API_KEY not set. Export it and re-run.")
        sys.exit(1)

    header("Initialising")
    llm = CerebrasClient(api_key=api_key)
    ok("Cerebras client initialised (gpt-oss-120b)")

    # Load graphs from storage, or build and save them on first run
    store = GraphStore(STORAGE_DIR)

    if store.exists("PythonDecorators"):
        g_dec = store.load("PythonDecorators")
        ok(f"Loaded PythonDecorators from storage ({g_dec.node_count()} nodes, {g_dec.edge_count()} edges)")
    else:
        g_dec = build_decorators_graph()
        store.save(g_dec)
        ok(f"Built and saved PythonDecorators ({g_dec.node_count()} nodes, {g_dec.edge_count()} edges)")

    if store.exists("PythonTypes"):
        g_typ = store.load("PythonTypes")
        ok(f"Loaded PythonTypes from storage ({g_typ.node_count()} nodes, {g_typ.edge_count()} edges)")
    else:
        g_typ = build_python_types_graph()
        store.save(g_typ)
        ok(f"Built and saved PythonTypes ({g_typ.node_count()} nodes, {g_typ.edge_count()} edges)")

    # Wire up weight system
    ws = WeightSystem(learning_rate=0.15, min_cluster_size=3)
    ws.register(g_dec)
    ws.register(g_typ)
    ok("WeightSystem initialised (lr=0.15, min_cluster_size=3)")

    # Wire up router (MultiPassEngine is used internally per graph)
    router = Router(llm=llm, max_passes=3, max_depth=8, alpha=0.5)
    router.register(g_dec)
    router.register(g_typ)
    ok("Router initialised with both graphs (max_passes=3)")

    # ----------------------------------------------------------------
    # Query 1 — single graph, multi-hop
    # Expected: decorator + higher-order fn + first-class fn (stub) + closure
    # ----------------------------------------------------------------
    q1 = "How does a Python decorator work internally?"
    header(f"Query 1 — {q1}")
    info("Expected: multi-hop traversal through decorator → HOF → first-class fn (stub) + closure")

    cl1 = ws._clusterer.get_cluster(q1)
    result1 = router.query(q1, cluster_label=cl1)
    print_result(result1, cluster_label=cl1)
    ws.observe_router(result1)

    # ----------------------------------------------------------------
    # Query 2 — shallow, definition only
    # Expected: just the decorator node, maybe syntax sugar
    # ----------------------------------------------------------------
    q2 = "What does the @ symbol mean in Python?"
    header(f"Query 2 — {q2}")
    info("Expected: shallow — decorator definition + @ syntax sugar node only")

    cl2 = ws._clusterer.get_cluster(q2)
    result2 = router.query(q2, cluster_label=cl2)
    print_result(result2, cluster_label=cl2)
    ws.observe_router(result2)

    # ----------------------------------------------------------------
    # Query 3 — cross-graph
    # Expected: router dispatches to both graphs
    # ----------------------------------------------------------------
    q3 = "How do I write a decorator in Python that is properly type-annotated?"
    header(f"Query 3 — {q3}")
    info("Expected: router selects both graphs — decorator mechanics + type hints")

    cl3 = ws._clusterer.get_cluster(q3)
    result3 = router.query(q3, cluster_label=cl3)
    print_result(result3, cluster_label=cl3)
    ws.observe_router(result3)

    # ----------------------------------------------------------------
    # Query 4 — irrelevant
    # Expected: router selects no graphs
    # ----------------------------------------------------------------
    q4 = "What is the boiling point of water at high altitude?"
    header(f"Query 4 — {q4}")
    info("Expected: router dispatches to no graphs")

    cl4 = ws._clusterer.get_cluster(q4)
    result4 = router.query(q4, cluster_label=cl4)
    print_result(result4, cluster_label=cl4)
    ws.observe_router(result4)

    # ----------------------------------------------------------------
    # Weight system — show what was learned
    # ----------------------------------------------------------------
    header("Weight System — learned edge weights")
    info("Edges used in verified traversals accumulate cluster signal toward 1.0")
    info("Sparse signal is expected on first run — clusters form with repeated similar queries")
    print_weight_stats(ws, "PythonDecorators")
    print_weight_stats(ws, "PythonTypes")

    print(f"\n  {BOLD}Observation history:{RESET}")
    print(f"  Total observations: {len(ws.history())}")
    for record in ws.history():
        status = f"{GREEN}verified{RESET}" if record.verified else f"{RED}unverified{RESET}"
        print(
            f"  {DIM}[{record.graph_name}] cluster={record.cluster_label} "
            f"{status} — {len(record.edge_ids)} edges — \"{record.query[:55]}…\"{RESET}"
        )

    # ----------------------------------------------------------------
    # Cluster stats
    # ----------------------------------------------------------------
    header("Cluster Stats")
    print_cluster_stats(ws)

    # Persist graphs so cluster_weights survive across runs
    store.save(g_dec)
    store.save(g_typ)
    ok("Graphs saved to storage (cluster_weights persisted)")

    header("Done")
    ok("End-to-end run complete.")


if __name__ == "__main__":
    main()
