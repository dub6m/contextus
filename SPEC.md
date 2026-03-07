# Contextus Graph Construction Spec — v0.1

## Overview

This document defines the rules for constructing knowledge graphs in Contextus. It covers node types, atomicity rules per type, edge types, and graph construction principles. It is the source of truth for the auto-graph builder and the rubric for graph quality assessment.

Every rule in this document was derived from working through real source material (a university lecture on recurrence relations) and making explicit decisions about where concept boundaries lie.

---

## Node Types

Eight node types. Every node in every graph is exactly one of these.

| Type | Description |
|------|-------------|
| **Definition** | What something is |
| **Behavior** | How something works or what it does |
| **Constraint** | The conditions under which something holds in the general case |
| **Example** | A concrete instance or analogy demonstrating another node |
| **Relation** | A meaningful transformation or interaction between two concepts that has its own mechanics |
| **Procedure** | A sequence of steps where order matters and each step depends on the previous |
| **Exception** | What happens when a constraint or behavior meets an anomaly and breaks down |
| **Stub** | A lightweight placeholder for a concept owned by another graph |

---

## Definition Rules

**Rule 1 — Independent meaning:**
A Definition node must be independently meaningful. It should convey a complete concept that makes sense without requiring another node to complete its meaning. Fragments that only make sense together belong in the same node.

**Rule 2 — One definition per concept:**
A concept gets exactly one Definition node in a graph. If a new source defines the same concept more completely, merge the new information into the existing node's body. If a new source recaps a concept as a lead-in to new knowledge, ignore the recap and create new nodes for the genuinely new knowledge only, linking them to the existing Definition node.

---

## Behavior Rules

**Rule 1 — Dependency split:**
If understanding how something works requires first understanding how something else works, those are two separate Behavior nodes connected by a `depends_on` edge.

**Rule 2 — Mutually exclusive outcomes:**
If a node describes multiple outcomes that each apply under mutually exclusive conditions, each outcome is a separate Behavior node.

---

## Constraint Rules

**Rule 1 — Complete actionable rule:**
All conditions that together form a single complete actionable rule belong in one Constraint node. Split only if each condition is independently meaningful and applicable without the others.

**Rule 2 — Assumptions are not constraints:**
Simplifying assumptions made within a proof or derivation are not Constraint nodes. They belong in the body of the node they support as context.

---

## Procedure Rules

**Rule 1 — Sequential steps:**
Any sequence of steps where order matters and each step depends on the previous is a Procedure node, regardless of whether the goal is to do something, show something, or derive something.

**Rule 2 — Declarative and sequential are always separate:**
When a concept has both a declarative form and a sequential form, these are always two separate nodes. The declarative form is a Definition node. The sequential form is a Procedure node. They are connected by a `has_procedure` edge from Definition to Procedure.

---

## Example Rules

**Rule 1 — One concept per Example node:**
An Example node demonstrates exactly one other node. If a concrete instance demonstrates multiple distinct concepts, it splits into multiple Example nodes — one per concept demonstrated — each connected by a `demonstrates` edge to the node it illustrates.

**Rule 2 — Concrete vs analogy:**
Example nodes have a subtype — either `concrete` or `analogy`. A concrete example uses the actual mechanics of the concept it demonstrates. An analogy builds intuition through real-world comparison without using the actual mechanics. They are never mixed in the same node.

**Rule 3 — Exercises are represented as solutions:**
Exercises and problems from source material are represented in the graph as their worked solutions, not as questions. The question framing is discarded. The worked solution is a concrete Example node demonstrating whichever concept the exercise was designed to test.

**Rule 4 — Exercises are solved using the graph:**
Exercises from source material are held as pending items during graph construction. After the full document is processed, each exercise is run as a query against the graph. If the traversal is verified, the retrieved subgraph is passed to the LLM as context to generate a worked solution. That solution is stored as the body of a concrete Example node. If the traversal is unverified, the exercise is flagged and no Example node is created until the graph is complete enough to support it.

---

## Relation Rules

**Rule 1 — Interaction with its own mechanics:**
A Relation node is warranted when the transformation or interaction between two concepts has its own mechanics — its own steps, conditions, or properties that aren't captured by either concept alone. If describing how A connects to B requires more than an edge label and more than what's already in A or B's nodes, the interaction has enough substance to be a Relation node.

**Rule 2 — Selective connection:**
A Relation node connects only to the specific nodes from each participating concept whose content is necessary to describe the interaction. Typically this means the Definition nodes of both concepts at minimum, plus any Procedure or Constraint nodes whose mechanics are directly involved. Example nodes of the participating concepts are not connected to the Relation node unless the interaction is only meaningful in a specific instance.

---

## Exception Rules

**Rule 1 — Anomaly of a rule:**
A Constraint node defines the conditions under which something holds in the general case. An Exception node describes what happens when those conditions aren't met or when the general rule produces an unexpected or invalid result. Every Exception node is linked to either a Constraint or Behavior node — it cannot exist without the rule it is an anomaly of.

**Rule 2 — Language signals:**
When source material uses language like "except when", "unless", "however", "this breaks down when", "a special case is", or "note that this doesn't apply if" — that is a signal an Exception node may be warranted.

---

## Stub Rules

**Rule 1 — Minimal body:**
A Stub node body contains exactly: the concept name, one sentence identifying what it is, and a reference to the graph that owns its full definition. Nothing more. Any additional detail belongs in the owning graph.

**Rule 2 — Auto-builder triggers stub creation:**
The auto-builder creates a Stub node when it encounters a concept that fails the central question test — it doesn't serve this graph's central question — but is referenced by nodes that do. The Stub preserves the dependency relationship without importing foreign knowledge into the graph.

---

## Graph Construction Rules

**Rule 1 — One graph per domain:**
One graph per domain. Related documents on the same subject feed into the same graph. Domain boundaries — not document boundaries — determine where one graph ends and another begins.

**Rule 2 — Stubs at domain boundaries only:**
Stub nodes appear only at true domain boundaries, where a concept is referenced but owned by a different domain's graph. Within a domain, all concepts connect directly regardless of which source document introduced them.

**Rule 3 — Central question test:**
Before building a graph, state the central question the domain answers in one sentence. Every concept that directly serves that question belongs in this graph as a full node. Every concept that doesn't gets a Stub.

**Rule 4 — Domain boundary identification:**
Domain boundaries are identified structurally, not by subject label. A domain boundary exists where the primary question being answered changes. Concepts that serve different central questions belong in different graphs regardless of how often they reference each other.

---

## Edge Types

| Edge Type | Meaning |
|-----------|---------|
| `depends_on` | Target must be understood before source |
| `has_procedure` | Source Definition has a corresponding Procedure node |
| `demonstrates` | Source Example illustrates target concept |
| `has_exception` | Target Exception describes anomaly of source Constraint or Behavior |
| `is_case_of` | Source Behavior is one case of target Definition |
| `has_constraint` | Source concept is governed by target Constraint |
| `represents` | Source represents or visualises target concept |
| `constructs` | Source is the act of building target |
| `analyses` | Source provides analysis of target |
| `connects` | Source Relation node connects to a participating concept |
| `proven_by` | Source Definition is proven by target Procedure |
| `is_instance_of` | Source is a specific instance of target |
| `requires` | Source requires target to function correctly |
| `has_syntax` | Source concept has a syntactic form described by target |
| `best_practice_requires` | Best practice for source requires target |
| `has_behavior` | Source concept exhibits behavior described by target |
| `augmented_by` | Source is augmented or extended by target |
| `enables` | Source enables or makes possible target |
| `extends_to` | Source extends or generalises to target |
| `violated_by` | Source constraint or behavior is violated by target Exception |

---

## Schema Notes

- `Example` nodes require a `subtype` field: either `"concrete"` or `"analogy"`
- `Stub` nodes have an intentionally minimal body — body validation is relaxed for Stub nodes
- All other nodes require non-empty `label`, `body`, and `scope`
- `scope` is the most load-bearing field — it is what the traversal engine reads to decide relevance without reading the full body. Write it as a contract: what this node covers and explicitly what it does not cover.

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| v0.1 | 2025 | Initial spec derived from recurrence relations lecture |
