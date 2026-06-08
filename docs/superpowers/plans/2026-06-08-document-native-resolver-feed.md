# Document Native Resolver Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed the dependency resolver from planner-independent document signals so planner-off runs can produce real dependency packages.

**Architecture:** Add a small document-native candidate producer inside the query assembler that converts existing signal/proposition data into `TermCandidate` and `FrameCandidate` records. Keep the resolver itself structured-only: frames prove, document links route, scores only order candidates.

**Tech Stack:** Python, pytest, existing `contextus.builder.query_assembly` and `contextus.builder.dependency_resolver` data models.

---

### Task 1: Tests For Planner-Independent Frames

**Files:**
- Modify: `tests/test_builder_query_assembly.py`

- [ ] Add a focused test showing the resolver receives frames when propositions have no role hypotheses.
- [ ] Assert a core sentence with an unsupported target can resolve through a source sentence that shares the same target and adds structured information.
- [ ] Assert repeated headings/labels do not become support.

### Task 2: Document-Native Candidate Producer

**Files:**
- Modify: `contextus/builder/query_assembly.py`

- [ ] Extend `_dependency_resolver_candidates` to accept `signals`.
- [ ] Add term candidates from `ElementSignalRecord.unique_content_terms`, `formula_symbols`, and exact title/visual labels where available.
- [ ] Add fallback frames from each proposition/signal with grounded `target` and unsupported `value` only when the source has explicit structured signal data.
- [ ] Preserve existing role-hypothesis frames when roles exist.

### Task 3: Link/Route Frames

**Files:**
- Modify: `contextus/builder/query_assembly.py`

- [ ] Create lightweight frames for heading, support/caption, previous/next, list sibling, and source adjacency relations.
- [ ] Use these as resolver routes, not as proof of semantic support.
- [ ] Keep frame count bounded by local, same-section, and same-source constraints.

### Task 4: Wire And Verify

**Files:**
- Modify: `contextus/builder/query_assembly.py`
- Modify: `run_query_proposition_prompt_suite.py` only if reporting needs more detail.

- [ ] Pass `signals` into dependency resolver candidate building.
- [ ] Ensure dependency packages are reported even with planner off.
- [ ] Run focused tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_builder_dependency_resolver.py tests/test_builder_query_assembly.py -q
```

- [ ] Run the planner-off prompt suite:

```powershell
$env:QUERY_PROPOSITION_LLM='none'
$env:QUERY_EMBEDDING_CACHE='chunk_runs\embedding_cache\all-MiniLM-L6-v2_query_package_texts.pkl'
Remove-Item Env:QUERY_RETRIEVAL_PLAN -ErrorAction SilentlyContinue
Remove-Item Env:QUERY_RETRIEVAL_PLAN_CACHE -ErrorAction SilentlyContinue
$env:QUERY_LANGUAGE_MAP='1'
$env:QUERY_ROLE_COMPLETION='1'
$env:QUERY_RELATION_GEOMETRY='1'
$env:QUERY_DEPENDENCY_RESOLVER='1'
$env:QUERY_DEPENDENCY_RESOLVER_DEPTH='2'
$env:QUERY_DEPENDENCY_RESOLVER_MAX_FRAMES='32'
Remove-Item Env:QUERY_DEPENDENCY_NLI -ErrorAction SilentlyContinue
.venv\Scripts\python.exe run_query_proposition_prompt_suite.py
```

### Self-Review

- The plan stays focused on feeding the resolver, not replacing the full package ranker.
- The feed is planner-independent and consumes existing document-native signals.
- The implementation must avoid regex/finite linguistic lists as the resolver's main meaning extractor.
