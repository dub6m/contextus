<![CDATA[# Contextus

**LLM-guided graph traversal for knowledge retrieval.**

Contextus is a Python library that builds directed, weighted knowledge graphs and uses LLMs to traverse them intelligently. Instead of dumping an entire knowledge base into an LLM's context window, Contextus walks the graph node-by-node — collecting only the minimal subgraph needed to answer a query, then verifying that subgraph for completeness and noise.

---

## How It Works

```
  Query
    │
    ▼
┌────────────┐     ┌────────────────┐     ┌────────────────┐
│   Router   │────▶│   Collector    │────▶│    Verifier     │
│ (dispatch) │     │  (BFS + LLM)   │     │ (quality check) │
└────────────┘     └────────────────┘     └────────────────┘
    │                     │                       │
    │              Walks the graph            Reviews the
    │              node-by-node,              collected subgraph
    ▼              guided by LLM              for completeness
 Multiple                                    and noise
 graphs              │                           │
                     ▼                           ▼
              ┌────────────────┐        ┌────────────────┐
              │ TraversalResult│───────▶│  WeightSystem  │
              │  (subgraph)    │        │  (EMA update)  │
              └────────────────┘        └────────────────┘
```

1. **Graph** — Holds `Node` and `Edge` objects. Nodes are typed (definition, behavior, constraint, example, etc.) and scoped with a one-sentence contract describing exactly what they cover.

2. **Collector** — An LLM-driven BFS agent that starts from an anchor node and expands outward, asking the LLM at each step which neighbors are necessary to answer the query.

3. **Verifier** — A second LLM pass that reviews the collected subgraph and determines if anything is missing or if any nodes are noise.

4. **Router** — Dispatches queries across multiple registered graphs and merges results, deduplicating redundant nodes.

5. **WeightSystem** — Observes traversal outcomes and updates `derived_weight` on edges via Exponential Moving Average (EMA). Uses a three-case signal:
   - **Verified traversal** → reward all edges (`1.0`)
   - **Incomplete graph** (missing nodes, no noise) → skip update (don't penalise good edges for a graph's gaps)
   - **Noisy traversal** → penalise only edges connecting noise nodes (`0.0`), leave the rest alone

---

## Project Structure

```
contextus/
├── pyproject.toml
├── run.py                    # End-to-end integration demo
├── .env                      # API keys (git-ignored)
├── contextus/                # Core package
│   ├── __init__.py
│   ├── node.py               # Node and NodeType
│   ├── edge.py               # Edge with base/derived weights
│   ├── graph.py              # Directed graph container
│   ├── llm.py                # Provider-agnostic LLM interface
│   ├── traversal.py          # Collector + Verifier engine
│   ├── router.py             # Multi-graph dispatcher
│   └── weights.py            # EMA-based weight learning
└── tests/
    ├── test_graph.py
    ├── test_traversal.py
    ├── test_router.py
    └── test_weights.py
```

---

## Installation

```bash
# Clone the repo
git clone https://github.com/<your-username>/contextus.git
cd contextus

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### API Key

Contextus ships with a Cerebras inference client. Set your API key:

```bash
# .env
CEREBRAS_API_KEY=your-key-here
```

Or implement `LLMClient` for any other provider — the traversal engine is provider-agnostic.

---

## Quick Start

```python
from contextus import (
    Node, NodeType, Edge, Graph,
    CerebrasClient, TraversalEngine, WeightSystem,
)

# Build a graph
g = Graph(name="MyGraph", description="A test graph.")
n1 = g.add_node(Node(
    label="Binary Search",
    type=NodeType.DEFINITION,
    body="Binary search finds a target in a sorted array by halving the search space.",
    scope="Covers only the definition. Not implementation or complexity.",
))
n2 = g.add_node(Node(
    label="O(log n) Complexity",
    type=NodeType.BEHAVIOR,
    body="Each step halves the search space, yielding O(log n) time.",
    scope="Covers only time complexity of binary search.",
))
g.add_edge(Edge(source_id=n1.id, target_id=n2.id, relations=["has_behavior"]))

# Traverse
llm = CerebrasClient()
engine = TraversalEngine(graph=g, llm=llm)
result = engine.query("What is the time complexity of binary search?")

print(result.summary())

# Learn from the traversal
ws = WeightSystem()
ws.register(g)
ws.observe(result)
```

---

## Running the Demo

`run.py` builds two example graphs (Python Decorators and Python Types), runs single-graph and multi-graph queries, and demonstrates weight learning across multiple traversals.

```bash
python run.py
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Key Design Decisions

- **Scope fields are load-bearing.** Every node has a `scope` — a one-sentence contract describing exactly what the node covers and doesn't cover. The Collector reads scope first to decide relevance without reading the full body.

- **Two-pass retrieval.** The Collector gathers, the Verifier reviews. This separation means the Collector can be aggressive about inclusion while the Verifier catches noise.

- **Weight learning distinguishes graph gaps from bad traversal.** An unverified result where the graph simply lacks needed nodes doesn't penalise the edges that were traversed — they were the right choices. Only edges leading to genuine noise are penalised.

- **Provider-agnostic LLM interface.** `LLMClient` is an abstract base class. Swap in any provider by implementing `complete()`.

- **Base weights are immutable.** The human-defined `base_weight` is never modified. Learning only affects `derived_weight`, and `effective_weight` blends the two via a configurable alpha.

---

## License

This project is currently unlicensed. All rights reserved.
]]>
