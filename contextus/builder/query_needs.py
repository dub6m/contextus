from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Mapping
import re

from .dependency_resolver import normalize_term_text


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+(?:\.\d+)?")

QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "does",
    "do",
    "for",
    "from",
    "how",
    "if",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
}

NEED_GENERIC_TOKENS = QUERY_STOPWORDS | {
    "answer",
    "claim",
    "context",
    "document",
    "evidence",
    "explain",
    "fact",
    "find",
    "need",
    "proposition",
    "prove",
    "reason",
    "show",
    "support",
}

BOUND_KEYWORDS = {
    "at most",
    "at least",
    "bound",
    "bounded",
    "constant",
    "distance",
    "less than",
    "linear",
    "next",
    "no more",
    "o(n)",
    "position",
    "positions",
    "suffices",
    "within",
}

PROOF_KEYWORDS = {
    "because",
    "contradict",
    "contradiction",
    "follows",
    "hence",
    "proof",
    "show",
    "therefore",
    "thus",
    "why",
}

DEFINITION_KEYWORDS = {"called", "consist", "denote", "define", "definition", "means", "refers"}
PROCEDURE_KEYWORDS = {"algorithm", "call", "compute", "construct", "create", "line", "recursive", "return", "sort"}
SOURCE_KEYWORDS = {"caption", "diagram", "figure", "formula", "shown", "table"}

ROLE_KIND = {
    "assumption": "condition_support",
    "claim": "proof_support",
    "condition": "condition_support",
    "contradiction": "proof_support",
    "definition": "definition_support",
    "formula_support": "source_support",
    "procedure_step": "procedure_support",
    "proof_conclusion": "proof_support",
    "proof_reason": "proof_support",
    "proof_setup": "condition_support",
    "quantity_bound": "bound_support",
    "table_support": "source_support",
    "visual_support": "source_support",
}

KIND_EXPECTED_SUPPORT = {
    "bound_support": ("bound", "constant", "at most", "at least", "within", "suffices", "positions"),
    "complexity_support": ("o(n)", "linear", "constant", "per point", "time", "suffices", "bound", "at most", "positions", "next"),
    "condition_support": ("if", "when", "assume", "condition", "given", "suppose"),
    "definition_support": ("definition", "denote", "means", "called", "consists"),
    "procedure_support": ("algorithm", "compute", "construct", "sort", "call", "return"),
    "proof_support": ("because", "therefore", "hence", "contradict", "proof", "show"),
    "source_support": ("figure", "table", "formula", "caption", "shown"),
}


@dataclass(frozen=True)
class QueryContext:
    original_query: str
    query_type: str
    desired_answer_shape: str
    target_terms: tuple[str, ...] = ()
    important_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class PropositionNeedHint:
    kind: str
    question: str
    target: str = ""
    expected_support: tuple[str, ...] = ()
    anchor_terms: tuple[str, ...] = ()
    confidence: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected_support", tuple(self.expected_support))
        object.__setattr__(self, "anchor_terms", tuple(self.anchor_terms))


@dataclass(frozen=True)
class QueryNeed:
    need_id: str
    core_proposition_id: str
    kind: str
    question: str
    target: str = ""
    expected_support: tuple[str, ...] = ()
    anchor_terms: tuple[str, ...] = ()
    search_questions: tuple[str, ...] = ()
    depth: int = 0
    parent_need_id: str = ""
    status: str = "open"
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected_support", tuple(self.expected_support))
        object.__setattr__(self, "anchor_terms", tuple(self.anchor_terms))
        object.__setattr__(self, "search_questions", tuple(self.search_questions))


@dataclass(frozen=True)
class QueryNeedSupport:
    need_id: str
    proposition_id: str
    element_id: str
    score: float
    semantic_score: float
    matched_terms: tuple[str, ...] = ()
    matched_expectations: tuple[str, ...] = ()
    search_question: str = ""
    reason: str = ""
    status: str = "accepted"

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_terms", tuple(self.matched_terms))
        object.__setattr__(self, "matched_expectations", tuple(self.matched_expectations))


@dataclass(frozen=True)
class QueryNeedTraceStep:
    action: str
    need_id: str = ""
    proposition_id: str = ""
    reason: str = ""
    score: float = 0.0


@dataclass(frozen=True)
class QueryNeedPackage:
    core_proposition_id: str
    core_element_id: str
    query_context: QueryContext
    active_needs: tuple[QueryNeed, ...] = ()
    resolved_needs: tuple[QueryNeed, ...] = ()
    unresolved_needs: tuple[QueryNeed, ...] = ()
    selected_supports: tuple[QueryNeedSupport, ...] = ()
    selected_proposition_ids: tuple[str, ...] = ()
    selected_elements: tuple[str, ...] = ()
    trace: tuple[QueryNeedTraceStep, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_needs", tuple(self.active_needs))
        object.__setattr__(self, "resolved_needs", tuple(self.resolved_needs))
        object.__setattr__(self, "unresolved_needs", tuple(self.unresolved_needs))
        object.__setattr__(self, "selected_supports", tuple(self.selected_supports))
        object.__setattr__(self, "selected_proposition_ids", tuple(self.selected_proposition_ids))
        object.__setattr__(self, "selected_elements", tuple(self.selected_elements))
        object.__setattr__(self, "trace", tuple(self.trace))


def build_query_context(query: str) -> QueryContext:
    original = re.sub(r"\s+", " ", str(query or "")).strip()
    lowered = original.lower()
    if re.search(r"\bhow\s+(?:many|much|long)\b|\b(bound|bounded|limit|maximum|minimum|at most|at least)\b", lowered):
        query_type = "quantity_bound"
        shape = "quantity or bound support"
    elif re.search(r"\bwhy\b|\bexplain\b|\bprove\b|\bjustify\b", lowered):
        query_type = "why_explanation"
        shape = "reason or proof support"
    elif re.search(r"\bwhat\s+(?:is|are|does)\b|\bdefine\b|\bmeaning\b", lowered):
        query_type = "definition"
        shape = "definition or identification"
    elif re.search(r"\bhow\b", lowered):
        query_type = "procedure"
        shape = "procedure or mechanism"
    elif re.search(r"\bwhere\b|\bfigure\b|\btable\b|\bshown\b|\bsource\b", lowered):
        query_type = "source"
        shape = "source, visual, table, or formula support"
    elif re.search(r"\bcompare\b|\bdiffer(?:ence|ent)?\b|\bversus\b|\bvs\b", lowered):
        query_type = "contrast"
        shape = "contrast or disambiguation"
    else:
        query_type = "lookup"
        shape = "direct answer support"
    tokens = _content_tokens(original)
    phrases = _term_phrases(original, max_width=3)
    return QueryContext(
        original_query=original,
        query_type=query_type,
        desired_answer_shape=shape,
        target_terms=tuple(phrases[:8]),
        important_terms=tuple(tokens[:12]),
    )


class QueryNeedResolver:
    def __init__(
        self,
        *,
        max_active_needs: int = 4,
        max_depth: int = 1,
        max_supports_per_need: int = 1,
        min_support_score: float = 0.34,
        max_selected_supports: int = 8,
    ) -> None:
        self.max_active_needs = max(1, int(max_active_needs))
        self.max_depth = max(0, int(max_depth))
        self.max_supports_per_need = max(1, int(max_supports_per_need))
        self.min_support_score = max(0.0, float(min_support_score))
        self.max_selected_supports = max(1, int(max_selected_supports))

    def resolve(
        self,
        *,
        context: QueryContext,
        core_index: int,
        propositions: list[object],
        semantic_score_fn: Callable[[QueryNeed], Mapping[int, float]] | None = None,
    ) -> QueryNeedPackage:
        if core_index < 0 or core_index >= len(propositions):
            raise IndexError("core_index out of range")
        core = propositions[core_index]
        active = self.possible_needs_for_proposition(
            context=context,
            proposition=core,
            depth=0,
            parent_need_id="",
            max_needs=self.max_active_needs,
        )
        trace: list[QueryNeedTraceStep] = [
            QueryNeedTraceStep(
                action="need_created",
                need_id=need.need_id,
                proposition_id=need.core_proposition_id,
                reason=need.reason or need.question,
            )
            for need in active
        ]
        worklist: list[QueryNeed] = list(active)
        resolved: list[QueryNeed] = []
        unresolved: list[QueryNeed] = []
        selected_supports: list[QueryNeedSupport] = []
        selected_proposition_ids: list[str] = []
        selected_elements: list[str] = []
        seen_need_keys = {
            (need.core_proposition_id, need.kind, normalize_term_text(need.target), need.depth)
            for need in active
        }

        while worklist and len(selected_supports) < self.max_selected_supports:
            need = worklist.pop(0)
            semantic_scores = dict(semantic_score_fn(need)) if semantic_score_fn is not None else {}
            candidates: list[QueryNeedSupport] = []
            for index, candidate in enumerate(propositions):
                if index == core_index:
                    continue
                candidate_id = _proposition_id(candidate)
                if candidate_id == need.core_proposition_id:
                    continue
                support = self._score_candidate_support(
                    context=context,
                    need=need,
                    candidate=candidate,
                    semantic_score=float(semantic_scores.get(index, 0.0)),
                    source_distance=abs(_element_index(candidate) - _element_index(core)),
                )
                if support is not None:
                    candidates.append(support)
            candidates.sort(key=lambda item: item.score, reverse=True)
            accepted = [
                candidate
                for candidate in candidates
                if candidate.score >= self.min_support_score
                and (candidate.matched_expectations or candidate.matched_terms or candidate.semantic_score >= 0.55)
            ][: self.max_supports_per_need]
            if not accepted:
                unresolved_need = replace(need, status="unresolved")
                unresolved.append(unresolved_need)
                trace.append(
                    QueryNeedTraceStep(
                        action="need_unresolved",
                        need_id=need.need_id,
                        proposition_id=need.core_proposition_id,
                        reason="no candidate support fulfilled the need",
                    )
                )
                if candidates:
                    best = candidates[0]
                    trace.append(
                        QueryNeedTraceStep(
                            action="candidate_rejected",
                            need_id=need.need_id,
                            proposition_id=best.proposition_id,
                            reason=best.reason,
                            score=round(best.score, 4),
                        )
                    )
                continue

            resolved_need = replace(need, status="resolved")
            resolved.append(resolved_need)
            for support in accepted:
                selected_supports.append(support)
                if support.proposition_id not in selected_proposition_ids:
                    selected_proposition_ids.append(support.proposition_id)
                if support.element_id not in selected_elements:
                    selected_elements.append(support.element_id)
                trace.append(
                    QueryNeedTraceStep(
                        action="need_resolved",
                        need_id=need.need_id,
                        proposition_id=support.proposition_id,
                        reason=support.reason,
                        score=round(support.score, 4),
                    )
                )
                if need.depth >= self.max_depth:
                    continue
                if not self._should_expand_support_need(context=context, parent=need):
                    continue
                support_prop = next(
                    (item for item in propositions if _proposition_id(item) == support.proposition_id),
                    None,
                )
                if support_prop is None:
                    continue
                child_needs = self.possible_needs_for_proposition(
                    context=context,
                    proposition=support_prop,
                    depth=need.depth + 1,
                    parent_need_id=need.need_id,
                    max_needs=1,
                )
                for child in child_needs:
                    key = (child.core_proposition_id, child.kind, normalize_term_text(child.target), child.depth)
                    if key in seen_need_keys:
                        continue
                    if not self._child_need_stays_on_path(parent=need, child=child, context=context):
                        trace.append(
                            QueryNeedTraceStep(
                                action="child_need_skipped",
                                need_id=child.need_id,
                                proposition_id=child.core_proposition_id,
                                reason="child need does not stay on the original query path",
                            )
                        )
                        continue
                    seen_need_keys.add(key)
                    worklist.append(child)
                    trace.append(
                        QueryNeedTraceStep(
                            action="need_created",
                            need_id=child.need_id,
                            proposition_id=child.core_proposition_id,
                            reason=child.reason or child.question,
                        )
                    )

        return QueryNeedPackage(
            core_proposition_id=_proposition_id(core),
            core_element_id=_element_id(core),
            query_context=context,
            active_needs=tuple(active),
            resolved_needs=tuple(resolved),
            unresolved_needs=tuple(unresolved),
            selected_supports=tuple(selected_supports),
            selected_proposition_ids=tuple(selected_proposition_ids),
            selected_elements=tuple(selected_elements),
            trace=tuple(trace),
        )

    def possible_needs_for_proposition(
        self,
        *,
        context: QueryContext,
        proposition: object,
        depth: int,
        parent_need_id: str,
        max_needs: int,
    ) -> list[QueryNeed]:
        explicit = [
            need
            for hint in _possible_need_hints(proposition)
            if (need := self._need_from_hint(context=context, proposition=proposition, hint=hint, depth=depth, parent_need_id=parent_need_id))
            is not None
        ]
        candidates: list[QueryNeed] = []
        candidates.extend(explicit)
        explicit_kinds = {need.kind for need in explicit}
        candidates.extend(
            need
            for need in self._role_needs(context=context, proposition=proposition, depth=depth, parent_need_id=parent_need_id)
            if need.kind not in explicit_kinds
        )
        candidates.extend(
            need
            for need in self._text_needs(context=context, proposition=proposition, depth=depth, parent_need_id=parent_need_id)
            if need.kind not in explicit_kinds
        )

        explicit_need_ids = {need.need_id for need in explicit}
        deduped: dict[tuple[str, str], QueryNeed] = {}
        for need in candidates:
            if need.need_id not in explicit_need_ids and not self._need_is_active_for_query(
                context=context,
                need=need,
            ):
                continue
            key = (need.kind, normalize_term_text(need.target or need.question))
            existing = deduped.get(key)
            if existing is None or len(need.anchor_terms) > len(existing.anchor_terms):
                deduped[key] = need
        ranked = sorted(deduped.values(), key=lambda need: self._need_priority(context, need), reverse=True)
        return ranked[:max_needs]

    def _need_from_hint(
        self,
        *,
        context: QueryContext,
        proposition: object,
        hint: object,
        depth: int,
        parent_need_id: str,
    ) -> QueryNeed | None:
        kind = _clean_kind(_field(hint, "kind"))
        target = _clean_text(_field(hint, "target"))
        question = _clean_text(_field(hint, "question"))
        if not kind or not question:
            return None
        expected = _tuple_text(_field(hint, "expected_support")) or KIND_EXPECTED_SUPPORT.get(kind, ())
        anchors = _tuple_text(_field(hint, "anchor_terms")) or _anchor_terms(target, question, context)
        return self._make_need(
            context=context,
            proposition=proposition,
            kind=kind,
            question=question,
            target=target or question,
            expected_support=expected,
            anchor_terms=anchors,
            depth=depth,
            parent_need_id=parent_need_id,
            reason=_clean_text(_field(hint, "reason")) or "explicit proposition need hint",
        )

    def _role_needs(
        self,
        *,
        context: QueryContext,
        proposition: object,
        depth: int,
        parent_need_id: str,
    ) -> list[QueryNeed]:
        needs: list[QueryNeed] = []
        for index, role in enumerate(_roles(proposition)):
            role_name = _clean_kind(_field(role, "role"))
            kind = ROLE_KIND.get(role_name)
            if not kind:
                continue
            target = _clean_text(_field(role, "value")) or _clean_text(_field(role, "target")) or _proposition_text(proposition)
            if _looks_boundish(target) or (kind == "proof_support" and context.query_type in {"quantity_bound", "why_explanation"} and _looks_boundish(_proposition_text(proposition))):
                kind = "bound_support"
            if context.query_type == "why_explanation" and _looks_complexityish(target + " " + _proposition_text(proposition)):
                kind = "complexity_support"
            expected = KIND_EXPECTED_SUPPORT.get(kind, ())
            anchors = _anchor_terms(target, _proposition_text(proposition), context)
            question = _question_for_need(context=context, kind=kind, target=target)
            needs.append(
                self._make_need(
                    context=context,
                    proposition=proposition,
                    kind=kind,
                    question=question,
                    target=target,
                    expected_support=expected,
                    anchor_terms=anchors,
                    depth=depth,
                    parent_need_id=parent_need_id,
                    reason=f"role {index}:{role_name} suggests {kind}",
                )
            )
        return needs

    def _text_needs(
        self,
        *,
        context: QueryContext,
        proposition: object,
        depth: int,
        parent_need_id: str,
    ) -> list[QueryNeed]:
        text = _proposition_text(proposition)
        needs: list[QueryNeed] = []
        if context.query_type == "definition":
            target = (context.target_terms or _term_phrases(text, max_width=3) or (text,))[0]
            needs.append(
                self._make_need(
                    context=context,
                    proposition=proposition,
                    kind="definition_support",
                    question=_question_for_need(context=context, kind="definition_support", target=target),
                    target=target,
                    expected_support=KIND_EXPECTED_SUPPORT["definition_support"],
                    anchor_terms=_anchor_terms(target, text, context),
                    depth=depth,
                    parent_need_id=parent_need_id,
                    reason="definition query needs source-backed definition support",
                )
            )
        if context.query_type in {"why_explanation", "quantity_bound"} and _looks_boundish(text):
            target = _bound_target(text) or text
            kind = "complexity_support" if _looks_complexityish(text) else "bound_support"
            needs.append(
                self._make_need(
                    context=context,
                    proposition=proposition,
                    kind=kind,
                    question=_question_for_need(context=context, kind=kind, target=target),
                    target=target,
                    expected_support=KIND_EXPECTED_SUPPORT[kind],
                    anchor_terms=_anchor_terms(target, text, context),
                    depth=depth,
                    parent_need_id=parent_need_id,
                    reason=f"text contains {kind} cues",
                )
            )
        if context.query_type == "why_explanation" and not needs:
            target = _best_text_target(text, context)
            needs.append(
                self._make_need(
                    context=context,
                    proposition=proposition,
                    kind="proof_support",
                    question=_question_for_need(context=context, kind="proof_support", target=target),
                    target=target,
                    expected_support=KIND_EXPECTED_SUPPORT["proof_support"],
                    anchor_terms=_anchor_terms(target, text, context),
                    depth=depth,
                    parent_need_id=parent_need_id,
                    reason="why query needs proof support for the core proposition",
                )
            )
        return needs

    def _make_need(
        self,
        *,
        context: QueryContext,
        proposition: object,
        kind: str,
        question: str,
        target: str,
        expected_support: Iterable[str],
        anchor_terms: Iterable[str],
        depth: int,
        parent_need_id: str,
        reason: str,
    ) -> QueryNeed:
        proposition_id = _proposition_id(proposition)
        normalized_target = normalize_term_text(target or question).replace(" ", "_")[:80] or "need"
        need_id = f"qneed:{proposition_id}:{depth}:{kind}:{normalized_target}"
        anchors = tuple(dict.fromkeys(term for term in anchor_terms if term and term not in NEED_GENERIC_TOKENS))[:12]
        expected = tuple(dict.fromkeys(_clean_text(item).lower() for item in expected_support if _clean_text(item)))[:10]
        search_questions = _search_questions(context=context, kind=kind, question=question, target=target, expected=expected, anchors=anchors)
        return QueryNeed(
            need_id=need_id,
            core_proposition_id=proposition_id,
            kind=kind,
            question=question,
            target=target,
            expected_support=expected,
            anchor_terms=anchors,
            search_questions=search_questions,
            depth=depth,
            parent_need_id=parent_need_id,
            reason=reason,
        )

    def _need_is_active_for_query(self, *, context: QueryContext, need: QueryNeed) -> bool:
        if context.query_type == "definition":
            return need.kind in {"definition_support", "source_support"}
        if context.query_type in {"quantity_bound"}:
            return need.kind in {"bound_support", "complexity_support", "proof_support"}
        if context.query_type == "why_explanation":
            return need.kind in {"bound_support", "complexity_support", "condition_support", "proof_support", "procedure_support"}
        if context.query_type == "procedure":
            return need.kind in {"procedure_support", "condition_support", "definition_support", "proof_support"}
        if context.query_type == "source":
            return need.kind in {"source_support", "proof_support", "definition_support"}
        return bool(_overlap(context.important_terms, need.anchor_terms) or need.kind in {"proof_support", "definition_support"})

    def _should_expand_support_need(self, *, context: QueryContext, parent: QueryNeed) -> bool:
        if context.query_type in {"definition", "lookup", "source", "contrast"}:
            return False
        if parent.kind in {"bound_support", "complexity_support", "proof_support", "condition_support"}:
            return True
        return context.query_type == "procedure" and parent.kind == "procedure_support"

    def _need_priority(self, context: QueryContext, need: QueryNeed) -> float:
        score = 0.0
        if context.query_type == "why_explanation" and need.kind in {"complexity_support", "bound_support", "proof_support"}:
            score += 3.0
        if context.query_type == "quantity_bound" and need.kind in {"bound_support", "complexity_support"}:
            score += 3.0
        if context.query_type == "definition" and need.kind == "definition_support":
            score += 3.0
        score += min(2.0, _overlap(context.important_terms, need.anchor_terms) * 2.0)
        score += min(1.0, len(need.anchor_terms) / 8.0)
        return score

    def _score_candidate_support(
        self,
        *,
        context: QueryContext,
        need: QueryNeed,
        candidate: object,
        semantic_score: float,
        source_distance: int,
    ) -> QueryNeedSupport | None:
        text = _candidate_text(candidate)
        tokens = set(_content_tokens(text))
        if not tokens:
            return None
        role_names = {_clean_kind(_field(role, "role")) for role in _roles(candidate)}
        expected = tuple(item for item in need.expected_support if _expectation_matches(item, text, role_names))
        matched_terms = tuple(
            term
            for term in need.anchor_terms
            if _term_matches(term, tokens, text)
        )
        anchor_score = min(1.0, len(matched_terms) / max(1, min(5, len(need.anchor_terms))))
        expected_score = min(1.0, len(expected) / max(1, min(3, len(need.expected_support))))
        query_score = min(1.0, len(set(context.important_terms) & tokens) / max(1, min(4, len(context.important_terms))))
        proximity_score = 1.0 / (1.0 + min(12, source_distance))
        semantic = max(0.0, min(1.0, semantic_score))
        score = (
            semantic * 0.42
            + anchor_score * 0.26
            + expected_score * 0.22
            + query_score * 0.05
            + proximity_score * 0.05
        )
        if expected_score == 0.0 and anchor_score < 0.34 and semantic < 0.55:
            return QueryNeedSupport(
                need_id=need.need_id,
                proposition_id=_proposition_id(candidate),
                element_id=_element_id(candidate),
                score=round(score, 4),
                semantic_score=round(semantic, 4),
                matched_terms=matched_terms,
                matched_expectations=expected,
                search_question=need.search_questions[0] if need.search_questions else need.question,
                reason="candidate shares too little need-specific structure",
                status="rejected",
            )
        reason_parts = []
        if expected:
            reason_parts.append("matches expected support: " + ", ".join(expected[:3]))
        if matched_terms:
            reason_parts.append("matches anchor terms: " + ", ".join(matched_terms[:5]))
        if semantic >= 0.55:
            reason_parts.append(f"semantic probe score {semantic:.2f}")
        return QueryNeedSupport(
            need_id=need.need_id,
            proposition_id=_proposition_id(candidate),
            element_id=_element_id(candidate),
            score=round(score, 4),
            semantic_score=round(semantic, 4),
            matched_terms=matched_terms,
            matched_expectations=expected,
            search_question=need.search_questions[0] if need.search_questions else need.question,
            reason="; ".join(reason_parts) or "candidate is closest available support",
        )

    def _child_need_stays_on_path(self, *, parent: QueryNeed, child: QueryNeed, context: QueryContext) -> bool:
        if child.kind in {"source_support"} and context.query_type != "source":
            return False
        if set(parent.anchor_terms) & set(child.anchor_terms):
            return True
        if set(context.important_terms) & set(child.anchor_terms):
            return True
        if child.kind in {parent.kind, "proof_support", "condition_support"} and parent.kind in {"proof_support", "bound_support", "complexity_support"}:
            return True
        return False


def _field(obj: object, name: str) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name, "")
    return getattr(obj, name, "")


def _roles(proposition: object) -> list[object]:
    roles = _field(proposition, "roles")
    return list(roles) if isinstance(roles, Iterable) and not isinstance(roles, (str, bytes, Mapping)) else []


def _possible_need_hints(proposition: object) -> list[object]:
    hints = _field(proposition, "possible_needs")
    return list(hints) if isinstance(hints, Iterable) and not isinstance(hints, (str, bytes, Mapping)) else []


def _proposition_id(proposition: object) -> str:
    return _clean_text(_field(proposition, "proposition_id"))


def _element_id(proposition: object) -> str:
    return _clean_text(_field(proposition, "element_id"))


def _element_index(proposition: object) -> int:
    try:
        return int(_field(proposition, "element_index"))
    except (TypeError, ValueError):
        return 0


def _proposition_text(proposition: object) -> str:
    return _clean_text(_field(proposition, "text"))


def _candidate_text(proposition: object) -> str:
    parts = [_proposition_text(proposition)]
    for role in _roles(proposition):
        parts.extend([_clean_text(_field(role, "role")), _clean_text(_field(role, "target")), _clean_text(_field(role, "value"))])
    return " ".join(part for part in parts if part)


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_kind(value: object) -> str:
    return re.sub(r"\s+", "_", _clean_text(value).lower())


def _tuple_text(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_clean_text(value),) if _clean_text(value) else ()
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        return tuple(item for item in (_clean_text(item) for item in value) if item)
    return ()


def _content_tokens(text: str) -> tuple[str, ...]:
    tokens = []
    for match in TOKEN_RE.finditer(normalize_term_text(text)):
        token = match.group(0).lower()
        if token and token not in QUERY_STOPWORDS:
            tokens.append(token)
    return tuple(dict.fromkeys(tokens))


def _term_phrases(text: str, *, max_width: int) -> tuple[str, ...]:
    raw_tokens = [match.group(0) for match in TOKEN_RE.finditer(normalize_term_text(text))]
    phrases: list[str] = []
    run: list[str] = []
    for token in raw_tokens:
        lowered = token.lower()
        if lowered in QUERY_STOPWORDS:
            if run:
                phrases.extend(_ngrams(run, max_width=max_width))
                run = []
            continue
        run.append(lowered)
    if run:
        phrases.extend(_ngrams(run, max_width=max_width))
    return tuple(dict.fromkeys(phrases))


def _ngrams(tokens: list[str], *, max_width: int) -> list[str]:
    phrases: list[str] = []
    for width in range(min(max_width, len(tokens)), 0, -1):
        for start in range(0, len(tokens) - width + 1):
            phrase = " ".join(tokens[start : start + width])
            if phrase not in NEED_GENERIC_TOKENS:
                phrases.append(phrase)
    return phrases


def _anchor_terms(target: str, text: str, context: QueryContext) -> tuple[str, ...]:
    terms = []
    terms.extend(_term_phrases(target, max_width=3))
    terms.extend(_content_tokens(target))
    terms.extend(term for term in context.target_terms if term in normalize_term_text(target + " " + text))
    terms.extend(term for term in context.important_terms if term in _content_tokens(target + " " + text))
    for match in re.finditer(r"\b\d+(?:\.\d+)?\b|O\([^)]+\)", text, flags=re.IGNORECASE):
        terms.append(match.group(0).lower())
    return tuple(dict.fromkeys(term for term in terms if term and term not in NEED_GENERIC_TOKENS))


def _question_for_need(*, context: QueryContext, kind: str, target: str) -> str:
    target = target.strip() or "the selected claim"
    if kind == "definition_support":
        return f"What document evidence defines or identifies {target}?"
    if kind == "bound_support":
        return f"What document evidence supports the bound {target}?"
    if kind == "complexity_support":
        return f"What document evidence explains why {target} supports {context.original_query}?"
    if kind == "condition_support":
        return f"What document evidence states the condition needed for {target}?"
    if kind == "procedure_support":
        return f"What document evidence explains the procedure for {target}?"
    if kind == "source_support":
        return f"What source, figure, table, or formula supports {target}?"
    return f"What document evidence explains why {target} holds?"


def _search_questions(
    *,
    context: QueryContext,
    kind: str,
    question: str,
    target: str,
    expected: tuple[str, ...],
    anchors: tuple[str, ...],
) -> tuple[str, ...]:
    probes = [
        question,
        f"What proposition supports {target}?",
        " ".join(part for part in [target, " ".join(expected[:4]), " ".join(anchors[:6])] if part),
        f"{context.original_query} {target}",
    ]
    if kind in {"bound_support", "complexity_support"}:
        probes.append(f"bound constant at most sufficient {target}")
    return tuple(dict.fromkeys(_clean_text(probe) for probe in probes if _clean_text(probe)))[:5]


def _looks_boundish(text: str) -> bool:
    lowered = normalize_term_text(text)
    return bool(
        re.search(r"\b\d+(?:\.\d+)?\b|O\([^)]+\)", text, re.IGNORECASE)
        or any(keyword in lowered for keyword in BOUND_KEYWORDS)
    )


def _looks_complexityish(text: str) -> bool:
    lowered = normalize_term_text(text)
    return bool(re.search(r"O\([^)]+\)", text, re.IGNORECASE) or "linear" in lowered or "time" in lowered)


def _bound_target(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    for pattern in (
        r"(?:at most|at least|no more than|no less than|within)\s+[^.]{1,90}",
        r"O\([^)]+\)\s+[^.]{0,60}",
        r"[^.]{0,80}\bconstant\b[^.]{0,80}",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(0).strip(" ,.;")
    return ""


def _best_text_target(text: str, context: QueryContext) -> str:
    normalized = _clean_text(text)
    for phrase in context.target_terms:
        if phrase in normalize_term_text(normalized):
            return phrase
    chunks = _term_phrases(normalized, max_width=4)
    return chunks[0] if chunks else normalized[:160]


def _expectation_matches(expectation: str, text: str, role_names: set[str]) -> bool:
    expected = normalize_term_text(expectation)
    candidate = normalize_term_text(text)
    if expected in role_names:
        return True
    if expected and expected in candidate:
        return True
    if expected in {"bound", "constant", "positions", "suffices"} and any(keyword in candidate for keyword in BOUND_KEYWORDS):
        return True
    if expected in {"because", "therefore", "proof", "show"} and any(keyword in candidate for keyword in PROOF_KEYWORDS):
        return True
    if expected in {"definition", "denote", "means"} and any(keyword in candidate for keyword in DEFINITION_KEYWORDS):
        return True
    if expected in {"algorithm", "compute", "construct"} and any(keyword in candidate for keyword in PROCEDURE_KEYWORDS):
        return True
    if expected in {"figure", "table", "formula"} and any(keyword in candidate for keyword in SOURCE_KEYWORDS):
        return True
    return False


def _term_matches(term: str, tokens: set[str], text: str) -> bool:
    normalized = normalize_term_text(term)
    if not normalized:
        return False
    if " " in normalized:
        return normalized in normalize_term_text(text)
    return normalized in tokens


def _overlap(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = {normalize_term_text(item) for item in left if normalize_term_text(item)}
    right_set = {normalize_term_text(item) for item in right if normalize_term_text(item)}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / max(1, min(len(left_set), len(right_set)))
