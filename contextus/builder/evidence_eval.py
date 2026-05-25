from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import math
import re

from .evidence import EvidenceContextPackage, EvidencePipelineResult


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)?")


@dataclass(frozen=True)
class EvidencePromptCase:
    case_id: str
    document_key: str
    family: str
    prompt: str
    expected_terms: tuple[tuple[str, ...], ...]
    notes: str = ""


@dataclass(frozen=True)
class EvidencePromptHit:
    rank: int
    package_id: str
    handle_id: str
    score: float
    matched_expected_groups: int
    total_expected_groups: int
    core_element_ids: list[str]
    context_element_ids: list[str]
    attachment_types: list[str]
    risk_flags: list[str]
    preview: str


@dataclass(frozen=True)
class RetrievalEvalItem:
    collection_id: str
    item_id: str
    document_key: str
    text: str
    source_element_ids: list[str]
    context_element_ids: list[str] = field(default_factory=list)
    attachment_types: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalEvalHit:
    rank: int
    collection_id: str
    item_id: str
    score: float
    matched_expected_groups: int
    total_expected_groups: int
    source_element_ids: list[str]
    context_element_ids: list[str]
    attachment_types: list[str]
    risk_flags: list[str]
    preview: str


@dataclass(frozen=True)
class RetrievalCollectionEvaluation:
    case: EvidencePromptCase
    collection_id: str
    hit_at_1: bool
    hit_at_3: bool
    best_hit_rank: int | None
    top: list[RetrievalEvalHit]


@dataclass(frozen=True)
class RetrievalComparisonSuiteResult:
    evaluations: list[RetrievalCollectionEvaluation]

    @property
    def summary(self) -> dict[str, object]:
        collection_ids = sorted({item.collection_id for item in self.evaluations})
        by_collection: dict[str, dict[str, object]] = {}
        for collection_id in collection_ids:
            evaluations = [item for item in self.evaluations if item.collection_id == collection_id]
            total = len(evaluations)
            hit_at_1 = sum(1 for item in evaluations if item.hit_at_1)
            hit_at_3 = sum(1 for item in evaluations if item.hit_at_3)
            ranks = [item.best_hit_rank for item in evaluations if item.best_hit_rank is not None]
            by_collection[collection_id] = {
                "case_count": total,
                "hit_at_1": hit_at_1,
                "hit_at_3": hit_at_3,
                "hit_at_3_rate": round(hit_at_3 / total, 4) if total else 0.0,
                "mean_best_hit_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
                "misses": total - hit_at_3,
            }
        pairwise = _pairwise_rank_deltas(self.evaluations)
        return {
            "collection_count": len(collection_ids),
            "case_count": len({item.case.case_id for item in self.evaluations}),
            "collections": by_collection,
            "pairwise_rank_deltas": pairwise,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "evaluations": [asdict(item) for item in self.evaluations],
        }


@dataclass(frozen=True)
class EvidencePromptEvaluation:
    case: EvidencePromptCase
    package_hit_at_1: bool
    package_hit_at_3: bool
    core_hit_at_1: bool
    core_hit_at_3: bool
    package_best_hit_rank: int | None
    core_best_hit_rank: int | None
    package_top: list[EvidencePromptHit]
    core_top: list[EvidencePromptHit]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvidencePromptSuiteResult:
    evaluations: list[EvidencePromptEvaluation]

    @property
    def summary(self) -> dict[str, object]:
        total = len(self.evaluations)
        package_hit_at_1 = sum(1 for item in self.evaluations if item.package_hit_at_1)
        package_hit_at_3 = sum(1 for item in self.evaluations if item.package_hit_at_3)
        core_hit_at_1 = sum(1 for item in self.evaluations if item.core_hit_at_1)
        core_hit_at_3 = sum(1 for item in self.evaluations if item.core_hit_at_3)
        improved = sum(
            1
            for item in self.evaluations
            if _rank_value(item.package_best_hit_rank) < _rank_value(item.core_best_hit_rank)
        )
        regressed = sum(
            1
            for item in self.evaluations
            if _rank_value(item.package_best_hit_rank) > _rank_value(item.core_best_hit_rank)
        )
        return {
            "case_count": total,
            "package_hit_at_1": package_hit_at_1,
            "package_hit_at_3": package_hit_at_3,
            "core_hit_at_1": core_hit_at_1,
            "core_hit_at_3": core_hit_at_3,
            "package_hit_at_3_rate": round(package_hit_at_3 / total, 4) if total else 0.0,
            "core_hit_at_3_rate": round(core_hit_at_3 / total, 4) if total else 0.0,
            "package_improved_rank_count": improved,
            "package_regressed_rank_count": regressed,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "evaluations": [item.to_dict() for item in self.evaluations],
        }


def evaluate_prompt_suite(
    results_by_document_key: dict[str, EvidencePipelineResult],
    prompt_cases: list[EvidencePromptCase],
    *,
    top_k: int = 5,
) -> EvidencePromptSuiteResult:
    evaluations = [
        evaluate_prompt_case(
            results_by_document_key[case.document_key],
            case,
            top_k=top_k,
        )
        for case in prompt_cases
        if case.document_key in results_by_document_key
    ]
    return EvidencePromptSuiteResult(evaluations=evaluations)


def evaluate_retrieval_collections(
    collections_by_id: dict[str, dict[str, list[RetrievalEvalItem]]],
    prompt_cases: list[EvidencePromptCase],
    *,
    top_k: int = 5,
) -> RetrievalComparisonSuiteResult:
    evaluations: list[RetrievalCollectionEvaluation] = []
    for collection_id, items_by_document in collections_by_id.items():
        for case in prompt_cases:
            items = items_by_document.get(case.document_key, [])
            if not items:
                continue
            evaluations.append(
                evaluate_retrieval_collection(
                    items,
                    case,
                    collection_id=collection_id,
                    top_k=top_k,
                )
            )
    return RetrievalComparisonSuiteResult(evaluations=evaluations)


def evaluate_retrieval_collection(
    items: list[RetrievalEvalItem],
    case: EvidencePromptCase,
    *,
    collection_id: str,
    top_k: int = 5,
) -> RetrievalCollectionEvaluation:
    ranked = rank_retrieval_items(items, case.prompt)
    best_hit_rank = _best_item_hit_rank(case, ranked)
    return RetrievalCollectionEvaluation(
        case=case,
        collection_id=collection_id,
        hit_at_1=best_hit_rank == 1,
        hit_at_3=best_hit_rank is not None and best_hit_rank <= 3,
        best_hit_rank=best_hit_rank,
        top=[_retrieval_hit_from_ranked(case, item, rank) for rank, item in enumerate(ranked[:top_k], start=1)],
    )


def rank_retrieval_items(
    items: list[RetrievalEvalItem],
    prompt: str,
) -> list[tuple[RetrievalEvalItem, float]]:
    scorer = _BM25Scorer([item.text for item in items])
    ranked = [(item, scorer.score(prompt, item.text) + _phrase_bonus(prompt, item.text)) for item in items]
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def package_retrieval_items(
    document_key: str,
    result: EvidencePipelineResult,
    *,
    collection_id: str = "evidence_package",
) -> list[RetrievalEvalItem]:
    return [
        RetrievalEvalItem(
            collection_id=collection_id,
            item_id=package.package_id,
            document_key=document_key,
            text=package.package_text,
            source_element_ids=list(package.core_element_ids),
            context_element_ids=list(package.context_element_ids),
            attachment_types=list(package.included_attachment_types),
            risk_flags=list(package.risk_flags),
            metadata={
                "handle_id": package.handle_id,
                "token_count": package.token_count,
                "context_token_count": package.context_token_count,
                "package_scores": dict(package.package_scores),
            },
        )
        for package in result.packages
    ]


def evaluate_prompt_case(
    result: EvidencePipelineResult,
    case: EvidencePromptCase,
    *,
    top_k: int = 5,
) -> EvidencePromptEvaluation:
    package_ranked = rank_packages(result.packages, case.prompt, text_mode="package")
    core_ranked = rank_packages(result.packages, case.prompt, text_mode="core")
    package_top = [
        _hit_from_ranked(case, item, rank, text_mode="package")
        for rank, item in enumerate(package_ranked[:top_k], start=1)
    ]
    core_top = [
        _hit_from_ranked(case, item, rank, text_mode="core")
        for rank, item in enumerate(core_ranked[:top_k], start=1)
    ]
    package_best_hit_rank = _best_hit_rank(case, package_ranked, text_mode="package")
    core_best_hit_rank = _best_hit_rank(case, core_ranked, text_mode="core")
    return EvidencePromptEvaluation(
        case=case,
        package_hit_at_1=package_best_hit_rank == 1,
        package_hit_at_3=package_best_hit_rank is not None and package_best_hit_rank <= 3,
        core_hit_at_1=core_best_hit_rank == 1,
        core_hit_at_3=core_best_hit_rank is not None and core_best_hit_rank <= 3,
        package_best_hit_rank=package_best_hit_rank,
        core_best_hit_rank=core_best_hit_rank,
        package_top=package_top,
        core_top=core_top,
    )


def rank_packages(
    packages: list[EvidenceContextPackage],
    prompt: str,
    *,
    text_mode: str,
) -> list[tuple[EvidenceContextPackage, float]]:
    texts = [_ranking_text(package, text_mode=text_mode) for package in packages]
    scorer = _BM25Scorer(texts)
    ranked = [
        (
            package,
            scorer.score(prompt, text) + _phrase_bonus(prompt, text),
        )
        for package, text in zip(packages, texts)
    ]
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def render_prompt_suite_markdown(result: EvidencePromptSuiteResult) -> str:
    summary = result.summary
    lines = [
        "# Evidence Prompt Evaluation",
        "",
        f"- Cases: `{summary['case_count']}`",
        f"- Package hit@1 / hit@3: `{summary['package_hit_at_1']}` / `{summary['package_hit_at_3']}`",
        f"- Core-only hit@1 / hit@3: `{summary['core_hit_at_1']}` / `{summary['core_hit_at_3']}`",
        f"- Package improved / regressed rank: `{summary['package_improved_rank_count']}` / `{summary['package_regressed_rank_count']}`",
        "",
    ]
    for evaluation in result.evaluations:
        case = evaluation.case
        lines.extend(
            [
                f"## {case.case_id}",
                "",
                f"- Family: `{case.family}`",
                f"- Document: `{case.document_key}`",
                f"- Prompt: {case.prompt}",
                f"- Package best hit rank: `{evaluation.package_best_hit_rank}`",
                f"- Core-only best hit rank: `{evaluation.core_best_hit_rank}`",
                "",
                "### Package Top",
                "",
            ]
        )
        lines.extend(_render_hits(evaluation.package_top))
        lines.extend(["", "### Core-Only Top", ""])
        lines.extend(_render_hits(evaluation.core_top))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_retrieval_comparison_markdown(result: RetrievalComparisonSuiteResult) -> str:
    summary = result.summary
    lines = [
        "# Retrieval Representation Comparison",
        "",
        f"- Cases: `{summary['case_count']}`",
        f"- Collections: `{summary['collection_count']}`",
        "",
        "## Summary",
        "",
    ]
    collections = summary.get("collections", {})
    if isinstance(collections, dict):
        for collection_id, data in collections.items():
            if not isinstance(data, dict):
                continue
            lines.extend(
                [
                    f"### {collection_id}",
                    "",
                    f"- hit@1 / hit@3: `{data.get('hit_at_1')}` / `{data.get('hit_at_3')}`",
                    f"- hit@3 rate: `{data.get('hit_at_3_rate')}`",
                    f"- mean best-hit rank: `{data.get('mean_best_hit_rank')}`",
                    f"- misses: `{data.get('misses')}`",
                    "",
                ]
            )
    pairwise = summary.get("pairwise_rank_deltas", {})
    if isinstance(pairwise, dict) and pairwise:
        lines.extend(["## Pairwise Rank Deltas", ""])
        for pair, data in pairwise.items():
            lines.append(f"- `{pair}`: `{data}`")
        lines.append("")
    by_case: dict[str, list[RetrievalCollectionEvaluation]] = {}
    for evaluation in result.evaluations:
        by_case.setdefault(evaluation.case.case_id, []).append(evaluation)
    lines.extend(["## Cases", ""])
    for case_id, evaluations in by_case.items():
        case = evaluations[0].case
        lines.extend(
            [
                f"### {case_id}",
                "",
                f"- Family: `{case.family}`",
                f"- Document: `{case.document_key}`",
                f"- Prompt: {case.prompt}",
                f"- Failure bucket: `{failure_bucket(evaluations)}`",
                "",
            ]
        )
        for evaluation in sorted(evaluations, key=lambda item: item.collection_id):
            lines.extend(
                [
                    f"#### {evaluation.collection_id}",
                    "",
                    f"- Best hit rank: `{evaluation.best_hit_rank}`",
                    f"- hit@1 / hit@3: `{evaluation.hit_at_1}` / `{evaluation.hit_at_3}`",
                    "",
                ]
            )
            lines.extend(_render_retrieval_hits(evaluation.top[:3]))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def failure_bucket(evaluations: list[RetrievalCollectionEvaluation]) -> str:
    if not evaluations:
        return "not_evaluated"
    any_hit = any(item.hit_at_3 for item in evaluations)
    if not any_hit:
        top_matches = [hit.matched_expected_groups for item in evaluations for hit in item.top[:1]]
        return "retrieval_language_mismatch" if max(top_matches, default=0) == 0 else "representation_miss"
    package = next((item for item in evaluations if item.collection_id == "evidence_package"), None)
    semantic = next((item for item in evaluations if item.collection_id == "semantic_walk_step6"), None)
    if package and semantic:
        if package.hit_at_3 and not semantic.hit_at_3:
            return "package_closure_helped"
        if semantic.hit_at_3 and not package.hit_at_3:
            return "semantic_chunk_helped"
        if _rank_value(package.best_hit_rank) < _rank_value(semantic.best_hit_rank):
            return "package_rank_better"
        if _rank_value(package.best_hit_rank) > _rank_value(semantic.best_hit_rank):
            return "semantic_rank_better"
    return "both_retrieved"


def default_prompt_cases() -> list[EvidencePromptCase]:
    return [
        EvidencePromptCase(
            case_id="closest-definition",
            document_key="closest-pair",
            family="definition",
            prompt="What is the closest pair problem?",
            expected_terms=(("closest pair",), ("points",)),
        ),
        EvidencePromptCase(
            case_id="closest-procedure",
            document_key="closest-pair",
            family="procedure",
            prompt="How does the divide-and-conquer closest pair algorithm work?",
            expected_terms=(("divide", "conquer"), ("recursive", "recursively"), ("closest pair",)),
        ),
        EvidencePromptCase(
            case_id="closest-q-r",
            document_key="closest-pair",
            family="comparison",
            prompt="How are Q and R used in the recursive closest pair algorithm?",
            expected_terms=(("q",), ("r",), ("left half", "right half", "set")),
        ),
        EvidencePromptCase(
            case_id="closest-above-three-pairs",
            document_key="closest-pair",
            family="reference",
            prompt="What are the above three pairs in the closest pair algorithm?",
            expected_terms=(("above three pairs", "three pairs"), ("left half",), ("right half",)),
        ),
        EvidencePromptCase(
            case_id="closest-contradiction",
            document_key="closest-pair",
            family="reference",
            prompt="Why does the proof say this contradicts the assumption?",
            expected_terms=(("contradicts", "contradict"), ("assumption",), ("d(s, t)", "distance")),
        ),
        EvidencePromptCase(
            case_id="closest-strip-nearby",
            document_key="closest-pair",
            family="citation",
            prompt="Why can only nearby points in the strip be closest?",
            expected_terms=(("separated", "rows"), ("distance",), ("boxes", "strip", "z")),
        ),
        EvidencePromptCase(
            case_id="inheritance-punnett",
            document_key="09-Inheritance_fowler_anth1210_24",
            family="visual-support",
            prompt="What does the Punnett square illustrate?",
            expected_terms=(("punnett",), ("alleles", "genes", "gametes"), ("brown", "blue", "eye")),
        ),
        EvidencePromptCase(
            case_id="inheritance-meiosis-figure",
            document_key="09-Inheritance_fowler_anth1210_24",
            family="visual-support",
            prompt="What does the figure show about meiosis producing haploid cells?",
            expected_terms=(("meiosis",), ("haploid",), ("diploid",)),
        ),
        EvidencePromptCase(
            case_id="inheritance-dna-unwinding",
            document_key="09-Inheritance_fowler_anth1210_24",
            family="visual-support",
            prompt="What does the DNA unwinding diagram show?",
            expected_terms=(("dna",), ("unwinding", "strands separate"), ("a t c g", "nucleotides")),
        ),
        EvidencePromptCase(
            case_id="inheritance-sickle-map",
            document_key="09-Inheritance_fowler_anth1210_24",
            family="visual-support",
            prompt="What does the malaria and sickle-cell map imply?",
            expected_terms=(("malaria", "malarial"), ("sickle",), ("africa",)),
        ),
        EvidencePromptCase(
            case_id="inheritance-mitosis-meiosis",
            document_key="09-Inheritance_fowler_anth1210_24",
            family="comparison",
            prompt="How are mitosis and meiosis different?",
            expected_terms=(("mitosis",), ("meiosis",), ("somatic", "haploid", "diploid")),
        ),
        EvidencePromptCase(
            case_id="inheritance-evolution-table",
            document_key="09-Inheritance_fowler_anth1210_24",
            family="comparison",
            prompt="How do biological evolution and cultural evolution differ?",
            expected_terms=(("biological evolution",), ("cultural evolution",), ("variability", "inheritance")),
        ),
    ]


def _ranking_text(package: EvidenceContextPackage, *, text_mode: str) -> str:
    if text_mode == "core":
        return "\n".join(segment.text for segment in package.segments if segment.role == "core")
    if text_mode == "retrieval":
        return package.retrieval_text
    return package.package_text


def _hit_from_ranked(
    case: EvidencePromptCase,
    ranked_item: tuple[EvidenceContextPackage, float],
    rank: int,
    *,
    text_mode: str,
) -> EvidencePromptHit:
    package, score = ranked_item
    text = _ranking_text(package, text_mode=text_mode)
    matched, total = _expected_match_count(text, case.expected_terms)
    preview = " ".join(text.split())
    if len(preview) > 320:
        preview = preview[:317].rstrip() + "..."
    return EvidencePromptHit(
        rank=rank,
        package_id=package.package_id,
        handle_id=package.handle_id,
        score=round(score, 4),
        matched_expected_groups=matched,
        total_expected_groups=total,
        core_element_ids=package.core_element_ids,
        context_element_ids=package.context_element_ids,
        attachment_types=package.included_attachment_types,
        risk_flags=package.risk_flags,
        preview=preview,
    )


def _best_hit_rank(
    case: EvidencePromptCase,
    ranked: list[tuple[EvidenceContextPackage, float]],
    *,
    text_mode: str,
) -> int | None:
    for rank, (package, _score) in enumerate(ranked, start=1):
        matched, total = _expected_match_count(_ranking_text(package, text_mode=text_mode), case.expected_terms)
        if total > 0 and matched == total:
            return rank
    return None


def _expected_match_count(text: str, expected_terms: tuple[tuple[str, ...], ...]) -> tuple[int, int]:
    normalized = _normalize_for_phrase(text)
    matched = 0
    for alternatives in expected_terms:
        if any(_normalize_for_phrase(term) in normalized for term in alternatives):
            matched += 1
    return matched, len(expected_terms)


def _render_hits(hits: list[EvidencePromptHit]) -> list[str]:
    lines = []
    for hit in hits:
        lines.extend(
            [
                f"- Rank `{hit.rank}` score `{hit.score}` expected `{hit.matched_expected_groups}/{hit.total_expected_groups}`",
                f"  - Core: `{hit.core_element_ids}`",
                f"  - Context: `{hit.context_element_ids}` via `{hit.attachment_types}`",
                f"  - Risks: `{hit.risk_flags}`",
                f"  - Preview: {hit.preview}",
            ]
        )
    return lines or ["- No hits."]


def _retrieval_hit_from_ranked(
    case: EvidencePromptCase,
    ranked_item: tuple[RetrievalEvalItem, float],
    rank: int,
) -> RetrievalEvalHit:
    item, score = ranked_item
    matched, total = _expected_match_count(item.text, case.expected_terms)
    preview = " ".join(item.text.split())
    if len(preview) > 320:
        preview = preview[:317].rstrip() + "..."
    return RetrievalEvalHit(
        rank=rank,
        collection_id=item.collection_id,
        item_id=item.item_id,
        score=round(score, 4),
        matched_expected_groups=matched,
        total_expected_groups=total,
        source_element_ids=list(item.source_element_ids),
        context_element_ids=list(item.context_element_ids),
        attachment_types=list(item.attachment_types),
        risk_flags=list(item.risk_flags),
        preview=preview,
    )


def _best_item_hit_rank(
    case: EvidencePromptCase,
    ranked: list[tuple[RetrievalEvalItem, float]],
) -> int | None:
    for rank, (item, _score) in enumerate(ranked, start=1):
        matched, total = _expected_match_count(item.text, case.expected_terms)
        if total > 0 and matched == total:
            return rank
    return None


def _render_retrieval_hits(hits: list[RetrievalEvalHit]) -> list[str]:
    lines = []
    for hit in hits:
        lines.extend(
            [
                f"- Rank `{hit.rank}` score `{hit.score}` expected `{hit.matched_expected_groups}/{hit.total_expected_groups}`",
                f"  - Item: `{hit.item_id}`",
                f"  - Source elements: `{hit.source_element_ids}`",
                f"  - Context: `{hit.context_element_ids}` via `{hit.attachment_types}`",
                f"  - Risks: `{hit.risk_flags}`",
                f"  - Preview: {hit.preview}",
            ]
        )
    return lines or ["- No hits."]


def _pairwise_rank_deltas(evaluations: list[RetrievalCollectionEvaluation]) -> dict[str, dict[str, int]]:
    by_case: dict[str, dict[str, RetrievalCollectionEvaluation]] = {}
    for evaluation in evaluations:
        by_case.setdefault(evaluation.case.case_id, {})[evaluation.collection_id] = evaluation
    collection_ids = sorted({item.collection_id for item in evaluations})
    deltas: dict[str, dict[str, int]] = {}
    for left in collection_ids:
        for right in collection_ids:
            if left >= right:
                continue
            key = f"{left} vs {right}"
            left_better = 0
            right_better = 0
            ties = 0
            for case_evaluations in by_case.values():
                if left not in case_evaluations or right not in case_evaluations:
                    continue
                left_rank = _rank_value(case_evaluations[left].best_hit_rank)
                right_rank = _rank_value(case_evaluations[right].best_hit_rank)
                if left_rank < right_rank:
                    left_better += 1
                elif right_rank < left_rank:
                    right_better += 1
                else:
                    ties += 1
            deltas[key] = {
                f"{left}_better": left_better,
                f"{right}_better": right_better,
                "ties": ties,
            }
    return deltas


def _phrase_bonus(prompt: str, text: str) -> float:
    prompt_terms = set(_content_terms(_tokens(prompt)))
    normalized = _normalize_for_phrase(text)
    bonus = 0.0
    for term in prompt_terms:
        if len(term) >= 4 and term in normalized:
            bonus += 0.35
    return bonus


def _normalize_for_phrase(text: str) -> str:
    return " ".join(_tokens(text.lower()))


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def _content_terms(tokens: list[str]) -> list[str]:
    stopwords = {
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
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "this",
        "to",
        "what",
        "why",
        "with",
    }
    return [token.lower() for token in tokens if token.lower() not in stopwords and len(token) > 1]


def _rank_value(rank: int | None) -> int:
    return rank if rank is not None else 10**9


class _BM25Scorer:
    def __init__(self, documents: list[str]) -> None:
        self._documents = [_content_terms(_tokens(document)) for document in documents]
        self._avg_doc_len = sum(len(document) for document in self._documents) / max(1, len(self._documents))
        document_frequency: Counter[str] = Counter()
        for document in self._documents:
            document_frequency.update(set(document))
        self._idf = {
            term: math.log(1 + (len(self._documents) - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def score(self, query: str, document_text: str) -> float:
        query_terms = _content_terms(_tokens(query))
        document_terms = _content_terms(_tokens(document_text))
        if not query_terms or not document_terms:
            return 0.0
        term_counts = Counter(document_terms)
        k1 = 1.2
        b = 0.75
        score = 0.0
        doc_len = len(document_terms)
        for term in query_terms:
            frequency = term_counts.get(term, 0)
            if frequency <= 0:
                continue
            idf = self._idf.get(term, 0.0)
            numerator = frequency * (k1 + 1)
            denominator = frequency + k1 * (1 - b + b * doc_len / max(1.0, self._avg_doc_len))
            score += idf * numerator / denominator
        return score
