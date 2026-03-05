"""
Contextus — end-to-end integration test.

Graph: Python Decorators (a real multi-hop reasoning target)
  - Understanding what a decorator does requires knowing: functions as
    first-class objects, higher-order functions, closure scope, and the
    @ syntax. A flat RAG system would struggle here because the relevant
    nodes aren't semantically close to every query surface.

Usage:
    export CEREBRAS_API_KEY=your_key_here
    python run.py

    # or inline:
    CEREBRAS_API_KEY=your_key python run.py
"""

import os
import sys
import textwrap

from dotenv import load_dotenv
load_dotenv()

from contextus import (
    Node, NodeType, Edge, Graph,
    CerebrasClient,
    TraversalEngine, TraversalResult,
    Router, RouterResult,
    WeightSystem,
)


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

def build_python_decorators_graph() -> Graph:
    """
    A graph about Python decorators.
    Correct retrieval for 'how does a decorator work' requires traversing
    through: decorator definition → higher-order functions → first-class
    functions → closure scope. A shallow traversal misses the why.
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

    n_fcf = g.add_node(Node(
        label="First-Class Functions",
        type=NodeType.BEHAVIOR,
        body=(
            "In Python, functions are first-class objects. They can be assigned to "
            "variables, passed as arguments, returned from other functions, and stored "
            "in data structures. This is the foundational property that makes decorators possible."
        ),
        scope="Covers Python's first-class function property only. Not closures or scope.",
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
    g.add_edge(Edge(source_id=n_dec.id, target_id=n_hof.id,
                    relations=["requires", "is_instance_of"], base_weight=0.95))
    g.add_edge(Edge(source_id=n_hof.id, target_id=n_fcf.id,
                    relations=["depends_on"], base_weight=0.95))
    g.add_edge(Edge(source_id=n_hof.id, target_id=n_clo.id,
                    relations=["depends_on"], base_weight=0.85))
    g.add_edge(Edge(source_id=n_dec.id, target_id=n_syn.id,
                    relations=["has_syntax"], base_weight=0.80))
    g.add_edge(Edge(source_id=n_syn.id, target_id=n_sta.id,
                    relations=["extends_to"], base_weight=0.65))
    g.add_edge(Edge(source_id=n_dec.id, target_id=n_pre.id,
                    relations=["best_practice_requires"], base_weight=0.70))
    g.add_edge(Edge(source_id=n_dec.id, target_id=n_exc.id,
                    relations=["has_exception"], base_weight=0.50))

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

    g.add_edge(Edge(source_id=n_dyn.id, target_id=n_hin.id,
                    relations=["augmented_by"], base_weight=0.85))
    g.add_edge(Edge(source_id=n_hin.id, target_id=n_pro.id,
                    relations=["enables"], base_weight=0.75))
    g.add_edge(Edge(source_id=n_hin.id, target_id=n_gen.id,
                    relations=["enables"], base_weight=0.80))

    return g


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_result(result: TraversalResult | RouterResult) -> None:
    if isinstance(result, RouterResult):
        nodes = result.all_nodes()
        edges = result.all_edges()
        verified = result.verified
        graphs_hit = [t.graph_name for t in result.traversals]
        print(f"  Graphs queried : {graphs_hit}")
        print(f"  Graphs skipped : {result.skipped_graphs}")
        print(f"  Dispatch reason: {result.dispatch_reason}")
    else:
        nodes = result.nodes
        edges = result.edges
        verified = result.verified
        print(f"  Graph          : {result.graph_name}")

    print(f"  Verified       : {GREEN + 'YES' + RESET if verified else RED + 'NO' + RESET}")
    print(f"  Nodes ({len(nodes)}):")
    for n in nodes:
        print(f"    {DIM}[{n.type.value}]{RESET} {n.label}")
        print(f"      {DIM}{textwrap.shorten(n.scope, width=80)}{RESET}")
    print(f"  Edges ({len(edges)}):")
    for e in edges:
        print(f"    {DIM}{e.source_id[:8]}… → {e.target_id[:8]}… {e.relations} "
              f"(base={e.base_weight:.2f}, derived={e.derived_weight}){RESET}")
    if isinstance(result, TraversalResult) and result.verifier_note:
        print(f"  Verifier note  : {result.verifier_note}")
    if isinstance(result, RouterResult):
        for t in result.traversals:
            if t.verifier_note:
                print(f"  Verifier [{t.graph_name}]: {t.verifier_note}")


def print_weight_stats(ws: WeightSystem, graph_name: str) -> None:
    stats = ws.edge_stats(graph_name)
    print(f"\n  {BOLD}Edge weights after learning ({graph_name}):{RESET}")
    for s in sorted(stats, key=lambda x: x["effective_weight_a05"], reverse=True):
        dw = f"{s['derived_weight']:.3f}" if s['derived_weight'] is not None else "None"
        print(
            f"    {DIM}{s['relations']}{RESET}  "
            f"base={s['base_weight']:.2f}  "
            f"derived={dw}  "
            f"effective(α=0.5)={s['effective_weight_a05']:.3f}"
        )


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

    # Build graphs
    g_dec = build_python_decorators_graph()
    g_typ = build_python_types_graph()
    ok(f"Graph '{g_dec.name}' built — {g_dec.node_count()} nodes, {g_dec.edge_count()} edges")
    ok(f"Graph '{g_typ.name}' built — {g_typ.node_count()} nodes, {g_typ.edge_count()} edges")

    # Wire up weight system
    ws = WeightSystem(learning_rate=0.15)
    ws.register(g_dec)
    ws.register(g_typ)
    ok("WeightSystem initialised (lr=0.15)")

    # Wire up router
    router = Router(llm=llm, max_depth=8, alpha=0.5)
    router.register(g_dec)
    router.register(g_typ)
    ok("Router initialised with both graphs")

    # ----------------------------------------------------------------
    # Query 1 — single graph, multi-hop
    # Expected: decorator + higher-order fn + first-class fn + closure
    # ----------------------------------------------------------------
    header("Query 1 — How does a Python decorator work?")
    info("Expected: multi-hop traversal through decorator → HOF → first-class fn + closure")

    result1 = router.query("How does a Python decorator work internally?")
    print_result(result1)
    ws.observe_router(result1)

    # ----------------------------------------------------------------
    # Query 2 — shallow, definition only
    # Expected: just the decorator node, maybe syntax sugar
    # ----------------------------------------------------------------
    header("Query 2 — What is the @ syntax in Python?")
    info("Expected: shallow — decorator definition + @ syntax sugar node only")

    result2 = router.query("What does the @ symbol mean in Python?")
    print_result(result2)
    ws.observe_router(result2)

    # ----------------------------------------------------------------
    # Query 3 — cross-graph
    # Expected: router dispatches to both graphs
    # ----------------------------------------------------------------
    header("Query 3 — Type-annotating a decorator (cross-graph)")
    info("Expected: router selects both graphs — decorator mechanics + type hints")

    result3 = router.query(
        "How do I write a decorator in Python that is properly type-annotated?"
    )
    print_result(result3)
    ws.observe_router(result3)

    # ----------------------------------------------------------------
    # Query 4 — irrelevant
    # Expected: router selects no graphs (or minimal)
    # ----------------------------------------------------------------
    header("Query 4 — Completely unrelated query")
    info("Expected: router dispatches to no graphs")

    result4 = router.query("What is the boiling point of water at high altitude?")
    print_result(result4)
    ws.observe_router(result4)

    # ----------------------------------------------------------------
    # Weight system — show what was learned
    # ----------------------------------------------------------------
    header("Weight System — learned edge weights")
    info("Edges that appeared in verified traversals trend toward 1.0")
    print_weight_stats(ws, "PythonDecorators")
    print_weight_stats(ws, "PythonTypes")

    print(f"\n  {DIM}Total observations: {len(ws.history())}{RESET}")
    for record in ws.history():
        status = f"{GREEN}verified{RESET}" if record.verified else f"{RED}unverified{RESET}"
        print(f"  {DIM}[{record.graph_name}] {status} — {len(record.edge_ids)} edges — \"{record.query[:50]}…\"{RESET}")

    header("Done")
    ok("End-to-end run complete.")


if __name__ == "__main__":
    main()
