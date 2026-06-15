from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import pickle
import re
from typing import Any, Callable

import numpy as np
from dotenv import load_dotenv

from contextus.builder import (
    BuilderConfig,
    ConsensusKnnPropositionEvidenceAssembler,
    CrossEncoderNliSupportVerifier,
    PropositionNeedHint,
)
from contextus.builder.query_assembly import (
    PropositionQueryTimeEvidenceAssembler,
    PropositionRoleHypothesis,
    QueryAssembledPackage,
    QueryRetrievalPlan,
    QueryRetrievalSubNeed,
    _PropositionDraft,
)
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore
from contextus.llm import CerebrasClient, LLMClient, OpenAIResponsesClient


DEFAULT_EXTRACTIONS = [
    Path("extractions/closest-pair/closest-pair.extraction.json"),
    Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
]


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    document_key: str
    family: str
    prompt: str


def main() -> None:
    load_dotenv(override=True)
    outdir = Path("chunk_runs") / f"query_proposition_prompt_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    outdir.mkdir(parents=True, exist_ok=True)
    documents = {
        safe_stem(document.source_name or path.stem): document
        for path in DEFAULT_EXTRACTIONS
        if path.exists()
        for document in [ExtractionArtifactStore(path.parent).load(path)]
    }
    embedding_cache_path = existing_path(os.environ.get("QUERY_EMBEDDING_CACHE"))
    embedder = CachedEmbeddingBackend(embedding_cache_path) if embedding_cache_path is not None else None
    plan_cache_path = existing_path(os.environ.get("QUERY_RETRIEVAL_PLAN_CACHE"))
    llm_client = make_llm_client()
    assembler = make_assembler(
        llm_client=llm_client,
        embed_texts=embedder if embedder is not None else None,
        cache_only_plans=plan_cache_path is not None,
    )
    proposition_cache_path = existing_path(os.environ.get("QUERY_PROPOSITION_CACHE"))
    if proposition_cache_path is not None:
        warm_proposition_cache(assembler, documents, proposition_cache_path)
    if plan_cache_path is not None and isinstance(assembler, CacheOnlyConsensusAssembler):
        preload_query_plans(assembler, documents, plan_cache_path)

    document_propositions: dict[str, object] = {}
    for document_key, document in documents.items():
        bootstrap = assembler.assemble(document, "__bootstrap_propositions__")
        document_propositions[document_key] = [asdict(proposition) for proposition in bootstrap.propositions]

    selected_cases = prompt_cases()
    case_limit = int(os.environ.get("QUERY_PROMPT_CASE_LIMIT", "0") or "0")
    if case_limit > 0:
        selected_cases = selected_cases[:case_limit]

    cases: list[dict[str, object]] = []
    traces: dict[str, object] = {}
    for case_index, case in enumerate(selected_cases, start=1):
        document = documents.get(case.document_key)
        if document is None:
            continue
        print(f"[{case_index}/{len(selected_cases)}] {case.case_id}", flush=True)
        started = datetime.now()
        result = assembler.assemble(document, case.prompt)
        elapsed = (datetime.now() - started).total_seconds()
        print(f"[{case_index}/{len(selected_cases)}] {case.case_id} done in {elapsed:.2f}s", flush=True)
        traces[case.case_id] = result.to_dict()
        cases.append(
            {
                "case_id": case.case_id,
                "document_key": case.document_key,
                "family": case.family,
                "prompt": case.prompt,
                "assembly_seconds": round(elapsed, 4),
                "package_count": len(result.packages),
                "packages": [
                    package_summary(rank, package)
                    for rank, package in enumerate(result.packages[:5], start=1)
                ],
                "answer_bundle": answer_bundle_summary(result.answer_bundle),
                "dependency_packages": [
                    dependency_package_summary(rank, package)
                    for rank, package in enumerate(result.dependency_packages, start=1)
                ],
                "query_need_packages": [
                    query_need_package_summary(rank, package)
                    for rank, package in enumerate(result.query_need_packages, start=1)
                ],
                "source_traversal_answer_bundle": source_traversal_answer_bundle_summary(
                    result.source_traversal_answer_bundle
                ),
                "source_traversals": source_traversal_summary(result.source_traversals),
                "source_traversal_packages": [
                    package_summary(rank, package)
                    for rank, package in enumerate(result.source_traversal_packages[:8], start=1)
                ],
            }
        )

    diagnostics = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "llm_client": type(llm_client).__name__ if llm_client is not None else None,
        "embedding_cache_path": str(embedding_cache_path) if embedding_cache_path is not None else None,
        "embedding_cache_stats": embedder.stats() if embedder is not None else None,
        "cached_vector_count": len(embedder.vectors) if embedder is not None else None,
        "query_plan_cache": {
            "preloaded": len(assembler._query_plan_cache) if hasattr(assembler, "_query_plan_cache") else None,
            "used": getattr(assembler, "cached_plan_hits", None),
            "missing": getattr(assembler, "cached_plan_misses", None),
        },
        "case_limit": case_limit,
        "assembler": assembler_settings(assembler),
        "documents": {
            document_key: {"proposition_count": len(propositions)}
            for document_key, propositions in document_propositions.items()
        },
    }
    payload = {
        "diagnostics": diagnostics,
        "cases": cases,
        "document_propositions": document_propositions,
        "traces": traces,
    }
    (outdir / "query_prompt_suite.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (outdir / "query_prompt_suite.md").write_text(render_markdown(diagnostics, cases), encoding="utf-8")
    if embedder is not None:
        embedder.save_if_dirty()
    print(
        json.dumps(
            {
                "outdir": str(outdir),
                "case_count": len(cases),
                "relation_geometry": getattr(assembler, "use_relation_geometry", None),
                "embedding_cache_stats": embedder.stats() if embedder is not None else None,
                "query_plan_cache": diagnostics["query_plan_cache"],
                "dependency_packages": {
                    case["case_id"]: {
                        "package_count": len(case.get("dependency_packages", []))
                        if isinstance(case.get("dependency_packages"), list)
                        else 0,
                        "selected_elements": [
                            element
                            for package in case.get("dependency_packages", [])
                            if isinstance(package, dict)
                            for element in package.get("selected_elements", [])
                        ],
                        "unresolved_need_count": sum(
                            int(package.get("unresolved_need_count", 0))
                            for package in case.get("dependency_packages", [])
                            if isinstance(package, dict)
                        ),
                    }
                    for case in cases
                },
                "query_need_packages": {
                    case["case_id"]: {
                        "package_count": len(case.get("query_need_packages", []))
                        if isinstance(case.get("query_need_packages"), list)
                        else 0,
                        "selected_elements": [
                            element
                            for package in case.get("query_need_packages", [])
                            if isinstance(package, dict)
                            for element in package.get("selected_elements", [])
                        ],
                        "resolved_need_count": sum(
                            int(package.get("resolved_need_count", 0))
                            for package in case.get("query_need_packages", [])
                            if isinstance(package, dict)
                        ),
                        "unresolved_need_count": sum(
                            int(package.get("unresolved_need_count", 0))
                            for package in case.get("query_need_packages", [])
                            if isinstance(package, dict)
                        ),
                    }
                    for case in cases
                },
                "top_packages": {
                    case["case_id"]: {
                        "package_id": case["packages"][0]["package_id"] if case["packages"] else None,
                        "core_element_id": case["packages"][0]["core_element_id"] if case["packages"] else None,
                        "score": case["packages"][0]["score"] if case["packages"] else None,
                        "preview": case["packages"][0]["preview"] if case["packages"] else None,
                    }
                    for case in cases
                },
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def make_assembler(
    *,
    llm_client: LLMClient | None,
    embed_texts: Callable[[list[str]], np.ndarray] | None,
    cache_only_plans: bool,
) -> PropositionQueryTimeEvidenceAssembler:
    use_relation_geometry = os.environ.get("QUERY_RELATION_GEOMETRY", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    assembler_cls = CacheOnlyConsensusAssembler if cache_only_plans else ConsensusKnnPropositionEvidenceAssembler
    support_verifier = make_dependency_support_verifier()
    return assembler_cls(
        llm_client=llm_client,
        embed_texts=embed_texts,
        config=BuilderConfig(EMBEDDING_MODEL="all-MiniLM-L6-v2", EMBEDDING_FALLBACK="all-MiniLM-L6-v2"),
        top_k_cores=5,
        proposition_batch_size=int(os.environ.get("QUERY_PROPOSITION_BATCH_SIZE", "6")),
        use_language_map=env_flag("QUERY_LANGUAGE_MAP"),
        use_query_planner=env_flag("QUERY_RETRIEVAL_PLAN"),
        use_role_completion=env_flag("QUERY_ROLE_COMPLETION"),
        query_planner_bridge_slots=int(os.environ.get("QUERY_RETRIEVAL_PLAN_BRIDGE_SLOTS", "1")),
        use_relation_geometry=use_relation_geometry,
        use_dependency_resolver=env_flag("QUERY_DEPENDENCY_RESOLVER"),
        dependency_resolver_depth=int(os.environ.get("QUERY_DEPENDENCY_RESOLVER_DEPTH", "2")),
        dependency_resolver_max_frames=int(os.environ.get("QUERY_DEPENDENCY_RESOLVER_MAX_FRAMES", "32")),
        dependency_support_verifier=support_verifier,
        use_query_need_resolver=env_flag("QUERY_NEED_RESOLVER"),
        query_need_max_depth=int(os.environ.get("QUERY_NEED_RESOLVER_DEPTH", "1")),
        query_need_max_active=int(os.environ.get("QUERY_NEED_RESOLVER_MAX_ACTIVE", "4")),
        query_need_max_supports_per_need=int(os.environ.get("QUERY_NEED_RESOLVER_SUPPORTS_PER_NEED", "1")),
        query_need_min_support_score=float(os.environ.get("QUERY_NEED_RESOLVER_MIN_SCORE", "0.34")),
        query_need_max_selected_supports=int(os.environ.get("QUERY_NEED_RESOLVER_MAX_SUPPORTS", "8")),
    )


def make_dependency_support_verifier() -> object | None:
    if not env_flag("QUERY_DEPENDENCY_NLI"):
        return None
    return CrossEncoderNliSupportVerifier(
        model_name=os.environ.get("QUERY_DEPENDENCY_NLI_MODEL", "cross-encoder/nli-deberta-v3-base"),
        entailment_threshold=float(os.environ.get("QUERY_DEPENDENCY_NLI_ENTAILMENT_THRESHOLD", "0.55")),
        contradiction_ceiling=float(os.environ.get("QUERY_DEPENDENCY_NLI_CONTRADICTION_CEILING", "0.35")),
    )


def make_llm_client() -> LLMClient | None:
    provider = os.environ.get("QUERY_PROPOSITION_LLM", "none").strip().lower()
    if provider in {"none", "cached", "cache", "off"}:
        return None
    if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
        return OpenAIResponsesClient()
    if provider != "openai" and os.environ.get("CEREBRAS_API_KEY"):
        return CerebrasClient()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIResponsesClient()
    return None


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def existing_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip("-") or "document"


class CachedEmbeddingBackend:
    def __init__(self, path: Path) -> None:
        self.path = path
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        self.model_name = str(payload.get("model") or "sentence-transformers/all-MiniLM-L6-v2")
        self.vectors: dict[str, np.ndarray] = dict(payload.get("vectors") or {})
        self.texts: dict[str, str] = dict(payload.get("texts") or {})
        self.calls = 0
        self.requested_texts = 0
        self.hits = 0
        self.misses = 0
        self.missing_text_examples: list[str] = []
        self._fallback = None
        self._dirty = False

    def __call__(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        self.requested_texts += len(texts)
        output: list[np.ndarray | None] = []
        missing: list[str] = []
        missing_positions: list[int] = []
        for index, text in enumerate(texts):
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()
            vector = self.vectors.get(key)
            if vector is None:
                self.misses += 1
                missing.append(text)
                missing_positions.append(index)
                output.append(None)
                if len(self.missing_text_examples) < 10:
                    self.missing_text_examples.append(text[:220])
                continue
            self.hits += 1
            output.append(np.asarray(vector, dtype=float))
        if missing:
            fallback_vectors = self._encode_missing(missing)
            for text, position, vector in zip(missing, missing_positions, fallback_vectors):
                key = hashlib.sha256(text.encode("utf-8")).hexdigest()
                arr = np.asarray(vector, dtype=float)
                self.vectors[key] = arr
                self.texts[key] = text
                output[position] = arr
            self._dirty = True
        return np.vstack([np.asarray(vector, dtype=float) for vector in output if vector is not None])

    def _encode_missing(self, texts: list[str]) -> np.ndarray:
        if self._fallback is None:
            from contextus.builder.query_assembly import _EmbeddingBackend

            self._fallback = _EmbeddingBackend(
                BuilderConfig(EMBEDDING_MODEL="all-MiniLM-L6-v2", EMBEDDING_FALLBACK="all-MiniLM-L6-v2")
            )
        return self._fallback.encode(texts)

    def save_if_dirty(self) -> None:
        if not self._dirty:
            return
        with self.path.open("wb") as handle:
            pickle.dump({"model": self.model_name, "vectors": self.vectors, "texts": self.texts}, handle)

    def stats(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "requested_texts": self.requested_texts,
            "hits": self.hits,
            "misses": self.misses,
            "missing_text_examples": self.missing_text_examples,
        }


class CacheOnlyConsensusAssembler(ConsensusKnnPropositionEvidenceAssembler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.cached_plan_hits = 0
        self.cached_plan_misses = 0

    def _query_retrieval_plan(self, *, signals, propositions, prompt):  # type: ignore[override]
        if not self.use_query_planner:
            return None
        retrieval_map = self._document_retrieval_map(signals=signals, propositions=propositions)
        if not retrieval_map:
            return None
        cache_key = hashlib.sha256(
            "\n".join(["query_retrieval_plan_v2_subneeds", prompt, retrieval_map]).encode("utf-8")
        ).hexdigest()
        cached = self._query_plan_cache.get(cache_key)
        if cached is None:
            self.cached_plan_misses += 1
            return None
        self.cached_plan_hits += 1
        return cached


def warm_proposition_cache(
    assembler: PropositionQueryTimeEvidenceAssembler,
    documents: dict[str, ExtractedDocument],
    proposition_run: Path,
) -> None:
    payload = json.loads(proposition_run.read_text(encoding="utf-8")) if proposition_run.exists() else {}
    cached_by_document = payload.get("document_propositions") if isinstance(payload, dict) else {}
    if not isinstance(cached_by_document, dict):
        cached_by_document = {}

    for document_key, document in documents.items():
        signal_pipeline = assembler._signal_builder.build(document)
        signals = [signal for signal in signal_pipeline.signals if signal.text.strip()]
        raw_propositions = cached_by_document.get(cache_document_key(document_key, document)) or cached_by_document.get(
            document_key
        ) or []
        drafts_by_element: dict[str, list[_PropositionDraft]] = {}
        for raw in raw_propositions if isinstance(raw_propositions, list) else []:
            if not isinstance(raw, dict):
                continue
            element_id = str(raw.get("element_id") or "")
            text = re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()
            if not element_id or not text:
                continue
            roles = [
                PropositionRoleHypothesis(
                    role=str(role.get("role") or "").strip().lower(),
                    target=str(role.get("target") or "").strip(),
                    value=str(role.get("value") or "").strip(),
                    confidence=float(role.get("confidence") or 0.0),
                    reason=str(role.get("reason") or "").strip(),
                )
                for role in raw.get("roles") or []
                if isinstance(role, dict)
            ]
            possible_needs = [
                PropositionNeedHint(
                    kind=str(need.get("kind") or "").strip().lower(),
                    question=str(need.get("question") or "").strip(),
                    target=str(need.get("target") or "").strip(),
                    expected_support=tuple(str(item).strip() for item in need.get("expected_support") or [] if str(item).strip()),
                    anchor_terms=tuple(str(item).strip() for item in need.get("anchor_terms") or [] if str(item).strip()),
                    confidence=float(need.get("confidence") or 0.0),
                    reason=str(need.get("reason") or "").strip(),
                )
                for need in raw.get("possible_needs") or []
                if isinstance(need, dict)
            ]
            drafts_by_element.setdefault(element_id, []).append(
                _PropositionDraft(text=text, roles=roles, possible_needs=possible_needs)
            )

        warmed = 0
        for signal in signals:
            drafts = drafts_by_element.get(signal.element_id)
            if not drafts:
                continue
            assembler._proposition_cache[assembler._proposition_cache_key(signal)] = drafts
            warmed += 1
        print(f"Warmed {warmed} proposition elements for `{document_key}` from {proposition_run}")


def cache_document_key(document_key: str, document: ExtractedDocument) -> str:
    source_name = document.source_name or document_key
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(source_name).stem).strip("-")
    return stem or document_key


def preload_query_plans(
    assembler: CacheOnlyConsensusAssembler,
    documents: dict[str, ExtractedDocument],
    plan_run: Path,
) -> None:
    payload = json.loads(plan_run.read_text(encoding="utf-8")) if plan_run.exists() else {}
    traces = payload.get("query_traces") or payload.get("traces") if isinstance(payload, dict) else {}
    traces = traces if isinstance(traces, dict) else {}
    for case in prompt_cases():
        document = documents.get(case.document_key)
        raw_trace = traces.get(case.case_id)
        plan = plan_from_dict(raw_trace.get("retrieval_plan") if isinstance(raw_trace, dict) else None)
        if document is None or plan is None:
            continue
        pipeline = assembler._signal_builder.build(document)
        signals = [signal for signal in pipeline.signals if signal.text.strip()]
        propositions = assembler._propositions_for_signals(signals)
        retrieval_map = assembler._document_retrieval_map(signals=signals, propositions=propositions)
        if not retrieval_map:
            continue
        cache_key = hashlib.sha256(
            "\n".join(["query_retrieval_plan_v2_subneeds", case.prompt, retrieval_map]).encode("utf-8")
        ).hexdigest()
        assembler._query_plan_cache[cache_key] = plan


def plan_from_dict(raw: object) -> QueryRetrievalPlan | None:
    if not isinstance(raw, dict):
        return None
    return QueryRetrievalPlan(
        interpreted_need=str(raw.get("interpreted_need") or ""),
        query_type=str(raw.get("query_type") or ""),
        source_supported_terms=[str(item) for item in raw.get("source_supported_terms") or []],
        possible_missing_prerequisites=[str(item) for item in raw.get("possible_missing_prerequisites") or []],
        search_forms=[str(item) for item in raw.get("search_forms") or []],
        uncertainties=[str(item) for item in raw.get("uncertainties") or []],
        sub_needs=[
            QueryRetrievalSubNeed(
                need=str(item.get("need") or ""),
                search_terms=[str(term) for term in item.get("search_terms") or []],
                expected_roles=[str(role) for role in item.get("expected_roles") or []],
            )
            for item in raw.get("sub_needs") or []
            if isinstance(item, dict)
        ],
    )


def package_summary(rank: int, package: QueryAssembledPackage) -> dict[str, object]:
    diagnostics = asdict(package.ranking_diagnostics) if package.ranking_diagnostics is not None else {}
    return {
        "rank": rank,
        "package_id": package.package_id,
        "score": round(float(package.score), 4),
        "core_element_id": package.core_element_id,
        "seed_core_element_id": package.seed_core_element_id,
        "element_ids": list(package.element_ids),
        "token_count": package.token_count,
        "score_parts": {
            "legacy": diagnostics.get("legacy_score"),
            "relevance": diagnostics.get("relevance_score"),
            "plan": diagnostics.get("plan_coverage_score"),
            "profile": diagnostics.get("profile_alignment_score"),
            "directness": diagnostics.get("directness_score"),
            "assembly": diagnostics.get("assembly_confidence_score"),
            "roles": diagnostics.get("role_coverage_score"),
            "completion": diagnostics.get("completion_closure_score"),
            "grounding": diagnostics.get("grounding_score"),
            "support": diagnostics.get("support_score"),
            "coherence": diagnostics.get("source_coherence_score"),
            "noise": diagnostics.get("noise_score"),
        },
        "positive_reasons": diagnostics.get("positive_reasons", []),
        "negative_reasons": diagnostics.get("negative_reasons", []),
        "preview": " ".join(package.package_text.split())[:1200],
    }


def answer_bundle_summary(answer_bundle: object) -> dict[str, object] | None:
    if answer_bundle is None:
        return None
    parts = getattr(answer_bundle, "parts", [])
    return {
        "bundle_id": getattr(answer_bundle, "bundle_id", ""),
        "parts": [
            {
                "part_index": index,
                "sub_need": getattr(part, "sub_need", ""),
                "search_terms": list(getattr(part, "search_terms", [])),
                "expected_roles": list(getattr(part, "expected_roles", [])),
                "package": package_summary(index, getattr(part, "package")),
            }
            for index, part in enumerate(parts, start=1)
            if getattr(part, "package", None) is not None
        ],
    }


def dependency_package_summary(rank: int, package: object) -> dict[str, object]:
    return {
        "rank": rank,
        "core_frame_ids": [getattr(frame, "frame_id", "") for frame in getattr(package, "core_frames", [])],
        "selected_frame_ids": [getattr(frame, "frame_id", "") for frame in getattr(package, "selected_frames", [])],
        "selected_elements": list(getattr(package, "selected_elements", [])),
        "resolved_need_count": len(getattr(package, "resolved_needs", [])),
        "unresolved_need_count": len(getattr(package, "unresolved_needs", [])),
        "unresolved_needs": [
            {
                "need_id": getattr(need, "need_id", ""),
                "frame_id": getattr(need, "frame_id", ""),
                "target_path": getattr(need, "target_path", ""),
                "value": getattr(need, "value", ""),
                "reason": getattr(need, "reason", ""),
            }
            for need in getattr(package, "unresolved_needs", [])
        ][:12],
        "cycles": [list(cycle) for cycle in getattr(package, "cycles", [])],
        "trace": [
            {
                "action": getattr(step, "action", ""),
                "need_id": getattr(step, "need_id", ""),
                "frame_ids": list(getattr(step, "frame_ids", [])),
                "reason": getattr(step, "reason", ""),
            }
            for step in getattr(package, "resolution_trace", [])
        ][:16],
    }


def query_need_package_summary(rank: int, package: object) -> dict[str, object]:
    query_context = getattr(package, "query_context", None)
    return {
        "rank": rank,
        "core_proposition_id": getattr(package, "core_proposition_id", ""),
        "core_element_id": getattr(package, "core_element_id", ""),
        "query_context": asdict(query_context) if query_context is not None else {},
        "selected_proposition_ids": list(getattr(package, "selected_proposition_ids", [])),
        "selected_elements": list(getattr(package, "selected_elements", [])),
        "active_need_count": len(getattr(package, "active_needs", [])),
        "resolved_need_count": len(getattr(package, "resolved_needs", [])),
        "unresolved_need_count": len(getattr(package, "unresolved_needs", [])),
        "active_needs": [query_need_summary(need) for need in getattr(package, "active_needs", [])][:12],
        "unresolved_needs": [query_need_summary(need) for need in getattr(package, "unresolved_needs", [])][:12],
        "selected_supports": [
            {
                "need_id": getattr(support, "need_id", ""),
                "proposition_id": getattr(support, "proposition_id", ""),
                "element_id": getattr(support, "element_id", ""),
                "score": round(float(getattr(support, "score", 0.0)), 4),
                "semantic_score": round(float(getattr(support, "semantic_score", 0.0)), 4),
                "matched_terms": list(getattr(support, "matched_terms", [])),
                "matched_expectations": list(getattr(support, "matched_expectations", [])),
                "search_question": getattr(support, "search_question", ""),
                "reason": getattr(support, "reason", ""),
            }
            for support in getattr(package, "selected_supports", [])
        ][:16],
        "trace": [
            {
                "action": getattr(step, "action", ""),
                "need_id": getattr(step, "need_id", ""),
                "proposition_id": getattr(step, "proposition_id", ""),
                "score": round(float(getattr(step, "score", 0.0)), 4),
                "reason": getattr(step, "reason", ""),
            }
            for step in getattr(package, "trace", [])
        ][:24],
    }


def query_need_summary(need: object) -> dict[str, object]:
    return {
        "need_id": getattr(need, "need_id", ""),
        "kind": getattr(need, "kind", ""),
        "question": getattr(need, "question", ""),
        "target": getattr(need, "target", ""),
        "expected_support": list(getattr(need, "expected_support", [])),
        "anchor_terms": list(getattr(need, "anchor_terms", [])),
        "search_questions": list(getattr(need, "search_questions", [])),
        "depth": getattr(need, "depth", 0),
        "parent_need_id": getattr(need, "parent_need_id", ""),
        "status": getattr(need, "status", ""),
        "reason": getattr(need, "reason", ""),
    }


def source_traversal_answer_bundle_summary(answer_bundle: object) -> dict[str, object] | None:
    if answer_bundle is None:
        return None
    parts = getattr(answer_bundle, "parts", [])
    return {
        "bundle_id": getattr(answer_bundle, "bundle_id", ""),
        "prompt": getattr(answer_bundle, "prompt", ""),
        "parts": [
            {
                "part_index": index,
                "part_id": getattr(part, "part_id", ""),
                "role": getattr(part, "role", ""),
                "display_label": getattr(part, "display_label", ""),
                "center_id": getattr(part, "center_id", ""),
                "trace_anchor_element_id": getattr(part, "trace_anchor_element_id", ""),
                "topic_terms": list(getattr(part, "topic_terms", [])),
                "claim_units": list(getattr(part, "claim_units", [])),
                "evidence_element_ids": list(getattr(part, "evidence_element_ids", [])),
                "package": package_summary(index, getattr(part, "package")),
            }
            for index, part in enumerate(parts, start=1)
            if getattr(part, "package", None) is not None
        ],
    }


def source_traversal_summary(source_traversals: object) -> list[dict[str, object]]:
    if not isinstance(source_traversals, list):
        return []
    summaries: list[dict[str, object]] = []
    for trace in source_traversals:
        candidates = list(getattr(trace, "candidates", []))
        summaries.append(
            {
                "anchor_proposition_id": getattr(trace, "anchor_proposition_id", ""),
                "anchor_element_id": getattr(trace, "anchor_element_id", ""),
                "anchor_text_preview": getattr(trace, "anchor_text_preview", ""),
                "accepted_proposition_ids": list(getattr(trace, "accepted_proposition_ids", [])),
                "accepted_element_ids": list(getattr(trace, "accepted_element_ids", [])),
                "centers": list(getattr(trace, "centers", [])),
                "dead_end_reason": getattr(trace, "dead_end_reason", ""),
                "accepted_candidates": [
                    candidate_summary(candidate)
                    for candidate in candidates
                    if getattr(candidate, "action", "") == "accepted"
                ],
                "rejected_candidates": [
                    candidate_summary(candidate)
                    for candidate in candidates
                    if getattr(candidate, "action", "") == "rejected"
                ][:8],
                "deferred_candidates": [
                    candidate_summary(candidate)
                    for candidate in candidates
                    if getattr(candidate, "action", "") == "deferred"
                ][:8],
                "bridge_candidates": [
                    candidate_summary(candidate)
                    for candidate in candidates
                    if getattr(candidate, "action", "") == "bridge"
                ][:8],
            }
        )
    return summaries


def candidate_summary(candidate: object) -> dict[str, object]:
    return {
        "round": getattr(candidate, "round_number", ""),
        "proposition_id": getattr(candidate, "proposition_id", ""),
        "element_id": getattr(candidate, "element_id", ""),
        "center_id": getattr(candidate, "center_id", ""),
        "center_decision": getattr(candidate, "center_decision", ""),
        "relations": list(getattr(candidate, "relation_tags", [])),
        "prompt_similarity": getattr(candidate, "prompt_similarity", ""),
        "state_similarity": getattr(candidate, "state_similarity", ""),
        "novelty": getattr(candidate, "novelty_score", ""),
        "redundancy": getattr(candidate, "redundancy_score", ""),
        "relation": getattr(candidate, "relation_score", ""),
        "role": getattr(candidate, "role_contribution_score", ""),
        "tokens": getattr(candidate, "token_count", ""),
        "reason": getattr(candidate, "reason", ""),
        "answer_contribution": getattr(candidate, "answer_contribution", ""),
        "matched_claim_units": list(getattr(candidate, "matched_claim_units", [])),
        "new_needed_units": list(getattr(candidate, "new_needed_units", [])),
        "foreign_claim_tokens": list(getattr(candidate, "foreign_claim_tokens", [])),
        "frame_continuation": getattr(candidate, "frame_continuation", ""),
        "preview": getattr(candidate, "text_preview", ""),
    }


def assembler_settings(assembler: PropositionQueryTimeEvidenceAssembler) -> dict[str, object]:
    return {
        "kind": type(assembler).__name__,
        "top_k_cores": assembler.top_k_cores,
        "proposition_batch_size": assembler.proposition_batch_size,
        "use_language_map": getattr(assembler, "use_language_map", None),
        "use_query_planner": getattr(assembler, "use_query_planner", None),
        "use_role_completion": getattr(assembler, "use_role_completion", None),
        "use_relation_geometry": getattr(assembler, "use_relation_geometry", None),
        "use_dependency_resolver": getattr(assembler, "use_dependency_resolver", None),
        "dependency_resolver_depth": getattr(assembler, "dependency_resolver_depth", None),
        "dependency_resolver_max_frames": getattr(assembler, "dependency_resolver_max_frames", None),
        "dependency_support_verifier": type(getattr(assembler, "dependency_support_verifier", None)).__name__
        if getattr(assembler, "dependency_support_verifier", None) is not None
        else None,
        "use_query_need_resolver": getattr(assembler, "use_query_need_resolver", None),
        "query_need_max_depth": getattr(assembler, "query_need_max_depth", None),
        "query_need_max_active": getattr(assembler, "query_need_max_active", None),
        "query_need_max_supports_per_need": getattr(assembler, "query_need_max_supports_per_need", None),
        "query_need_min_support_score": getattr(assembler, "query_need_min_support_score", None),
        "query_need_max_selected_supports": getattr(assembler, "query_need_max_selected_supports", None),
        "relation_geometry_weight": getattr(assembler, "relation_geometry_weight", None),
        "relation_family_similarity": getattr(assembler, "relation_family_similarity", None),
        "min_relation_family_size": getattr(assembler, "min_relation_family_size", None),
        "use_source_traversal_audit": getattr(assembler, "use_source_traversal_audit", None),
        "source_traversal_anchor_limit": getattr(assembler, "source_traversal_anchor_limit", None),
        "source_traversal_rounds": getattr(assembler, "source_traversal_rounds", None),
        "source_traversal_accepts_per_round": getattr(assembler, "source_traversal_accepts_per_round", None),
        "source_traversal_candidate_limit": getattr(assembler, "source_traversal_candidate_limit", None),
    }


def render_markdown(diagnostics: dict[str, object], cases: list[dict[str, object]]) -> str:
    lines = ["# Query Proposition Prompt Suite", ""]
    lines.append("Pipeline output only. No automatic content judgment.")
    lines.append("")
    lines.append(f"- Created at: `{diagnostics['created_at']}`")
    lines.append(f"- LLM client: `{diagnostics['llm_client']}`")
    lines.append(f"- Embedding cache: `{diagnostics['embedding_cache_path']}`")
    lines.append(f"- Embedding cache stats: `{diagnostics['embedding_cache_stats']}`")
    lines.append(f"- Query plan cache: `{diagnostics['query_plan_cache']}`")
    lines.append(f"- Assembler: `{diagnostics['assembler']}`")
    lines.append("")
    for case in cases:
        lines.append(f"## {case['case_id']}")
        lines.append("")
        lines.append(f"- Prompt: {case['prompt']}")
        lines.append(f"- Document: `{case['document_key']}`")
        lines.append(f"- Assembly seconds: `{case['assembly_seconds']}`")
        lines.append("")
        for package in case.get("packages", []):
            if not isinstance(package, dict):
                continue
            lines.append(f"### Package {package['rank']}: `{package['package_id']}`")
            lines.append("")
            lines.append(f"- Score: `{package['score']}`")
            lines.append(f"- Core: `{package['core_element_id']}`")
            lines.append(f"- Seed core: `{package['seed_core_element_id']}`")
            lines.append(f"- Tokens: `{package['token_count']}`")
            lines.append(f"- Positive reasons: `{join_list(package.get('positive_reasons'))}`")
            lines.append(f"- Concerns: `{join_list(package.get('negative_reasons'))}`")
            lines.append("")
            lines.append(str(package.get("preview", "")))
            lines.append("")
        dependency_packages = case.get("dependency_packages", [])
        if isinstance(dependency_packages, list) and dependency_packages:
            lines.append("### Dependency Resolver Packages")
            lines.append("")
            for package in dependency_packages:
                if not isinstance(package, dict):
                    continue
                lines.append(f"#### Dependency Package {package.get('rank')}")
                lines.append("")
                lines.append(f"- Core frames: `{join_list(package.get('core_frame_ids'))}`")
                lines.append(f"- Selected frames: `{join_list(package.get('selected_frame_ids'))}`")
                lines.append(f"- Selected elements: `{join_list(package.get('selected_elements'))}`")
                lines.append(f"- Resolved needs: `{package.get('resolved_need_count', 0)}`")
                lines.append(f"- Unresolved needs: `{package.get('unresolved_need_count', 0)}`")
                cycles = package.get("cycles", [])
                if isinstance(cycles, list) and cycles:
                    lines.append(f"- Cycles: `{cycles}`")
                unresolved_needs = package.get("unresolved_needs", [])
                if isinstance(unresolved_needs, list) and unresolved_needs:
                    lines.append("")
                    lines.append("Unresolved:")
                    lines.append("")
                    for need in unresolved_needs[:6]:
                        if not isinstance(need, dict):
                            continue
                        lines.append(
                            f"- `{need.get('need_id', '')}` {need.get('target_path', '')}: "
                            f"{need.get('value', '')} ({need.get('reason', '')})"
                        )
                trace = package.get("trace", [])
                if isinstance(trace, list) and trace:
                    lines.append("")
                    lines.append("Trace preview:")
                    lines.append("")
                    for step in trace[:8]:
                        if not isinstance(step, dict):
                            continue
                        lines.append(
                            f"- `{step.get('action', '')}` `{join_list(step.get('frame_ids'))}`: "
                            f"{step.get('reason', '')}"
                        )
                lines.append("")
        query_need_packages = case.get("query_need_packages", [])
        if isinstance(query_need_packages, list) and query_need_packages:
            lines.append("### Query Need Resolver Packages")
            lines.append("")
            for package in query_need_packages:
                if not isinstance(package, dict):
                    continue
                context = package.get("query_context") if isinstance(package.get("query_context"), dict) else {}
                lines.append(f"#### Query Need Package {package.get('rank')}")
                lines.append("")
                lines.append(f"- Core proposition: `{package.get('core_proposition_id', '')}`")
                lines.append(f"- Core element: `{package.get('core_element_id', '')}`")
                lines.append(f"- Query type: `{context.get('query_type', '')}`")
                lines.append(f"- Desired shape: `{context.get('desired_answer_shape', '')}`")
                lines.append(f"- Selected elements: `{join_list(package.get('selected_elements'))}`")
                lines.append(f"- Active needs: `{package.get('active_need_count', 0)}`")
                lines.append(f"- Resolved needs: `{package.get('resolved_need_count', 0)}`")
                lines.append(f"- Unresolved needs: `{package.get('unresolved_need_count', 0)}`")
                active_needs = package.get("active_needs", [])
                if isinstance(active_needs, list) and active_needs:
                    lines.append("")
                    lines.append("Active needs:")
                    lines.append("")
                    for need in active_needs[:6]:
                        if not isinstance(need, dict):
                            continue
                        lines.append(
                            f"- `{need.get('kind', '')}` {need.get('question', '')} "
                            f"[target: {need.get('target', '')}]"
                        )
                selected_supports = package.get("selected_supports", [])
                if isinstance(selected_supports, list) and selected_supports:
                    lines.append("")
                    lines.append("Selected supports:")
                    lines.append("")
                    for support in selected_supports[:8]:
                        if not isinstance(support, dict):
                            continue
                        lines.append(
                            f"- `{support.get('element_id', '')}` score `{support.get('score', '')}` "
                            f"for `{support.get('need_id', '')}`: {support.get('reason', '')}"
                        )
                unresolved_needs = package.get("unresolved_needs", [])
                if isinstance(unresolved_needs, list) and unresolved_needs:
                    lines.append("")
                    lines.append("Unresolved:")
                    lines.append("")
                    for need in unresolved_needs[:6]:
                        if not isinstance(need, dict):
                            continue
                        lines.append(f"- `{need.get('kind', '')}` {need.get('question', '')}")
                trace = package.get("trace", [])
                if isinstance(trace, list) and trace:
                    lines.append("")
                    lines.append("Trace preview:")
                    lines.append("")
                    for step in trace[:8]:
                        if not isinstance(step, dict):
                            continue
                        lines.append(
                            f"- `{step.get('action', '')}` `{step.get('proposition_id', '')}` "
                            f"score `{step.get('score', '')}`: {step.get('reason', '')}"
                        )
                lines.append("")
        traversal_packages = case.get("source_traversal_packages", [])
        if isinstance(traversal_packages, list) and traversal_packages:
            lines.append("### Source Traversal Packages")
            lines.append("")
            for package in traversal_packages:
                if not isinstance(package, dict):
                    continue
                lines.append(f"#### Traversal Package {package['rank']}: `{package['package_id']}`")
                lines.append("")
                lines.append(f"- Score: `{package['score']}`")
                lines.append(f"- Core: `{package['core_element_id']}`")
                lines.append(f"- Seed core: `{package['seed_core_element_id']}`")
                lines.append(f"- Elements: `{join_list(package.get('element_ids'))}`")
                lines.append(f"- Positive reasons: `{join_list(package.get('positive_reasons'))}`")
                lines.append(f"- Concerns: `{join_list(package.get('negative_reasons'))}`")
                lines.append("")
                lines.append(str(package.get("preview", "")))
                lines.append("")
        traversal_bundle = case.get("source_traversal_answer_bundle")
        if isinstance(traversal_bundle, dict):
            traversal_bundle_parts = traversal_bundle.get("parts", [])
            if isinstance(traversal_bundle_parts, list) and traversal_bundle_parts:
                lines.append("### Source Traversal Answer Bundle")
                lines.append("")
                for raw_part in traversal_bundle_parts:
                    part = raw_part if isinstance(raw_part, dict) else {}
                    package = part.get("package") if isinstance(part.get("package"), dict) else {}
                    lines.append(f"#### Part {part.get('part_index')}: {part.get('display_label')}")
                    lines.append("")
                    lines.append(f"- Role: `{part.get('role', '')}`")
                    lines.append(f"- Center: `{part.get('center_id', '')}`")
                    lines.append(f"- Trace anchor: `{part.get('trace_anchor_element_id', '')}`")
                    lines.append(f"- Topic terms: `{join_list(part.get('topic_terms'))}`")
                    lines.append(f"- Claim units: `{join_list(part.get('claim_units'))}`")
                    lines.append(f"- Evidence elements: `{join_list(part.get('evidence_element_ids'))}`")
                    lines.append(f"- Package: `{package.get('package_id', '')}`")
                    lines.append(f"- Core: `{package.get('core_element_id', '')}`")
                    lines.append(f"- Score: `{package.get('score', '')}`")
                    lines.append("")
                    lines.append(str(package.get("preview", "")))
                    lines.append("")
        traversals = case.get("source_traversals")
        if isinstance(traversals, list) and traversals:
            lines.append("### Source Traversal Audit")
            lines.append("")
            for raw_trace in traversals:
                trace = raw_trace if isinstance(raw_trace, dict) else {}
                lines.append(f"#### Anchor `{trace.get('anchor_element_id', '')}`")
                lines.append("")
                lines.append(f"- Accepted elements: `{join_list(trace.get('accepted_element_ids'))}`")
                lines.append(f"- Dead end: `{trace.get('dead_end_reason', '')}`")
                lines.append("")
                lines.append(str(trace.get("anchor_text_preview", "")))
                lines.append("")
                accepted_candidates = trace.get("accepted_candidates", [])
                if isinstance(accepted_candidates, list) and accepted_candidates:
                    lines.append("Accepted candidates:")
                    lines.append("")
                    for candidate in accepted_candidates:
                        if not isinstance(candidate, dict):
                            continue
                        lines.append(
                            f"- Round {candidate.get('round')}, `{candidate.get('element_id')}` via "
                            f"`{join_list(candidate.get('relations'))}`: {candidate.get('reason')}"
                        )
                        lines.append(f"  {candidate.get('preview', '')}")
                    lines.append("")
                rejected_candidates = trace.get("rejected_candidates", [])
                if isinstance(rejected_candidates, list) and rejected_candidates:
                    lines.append("Rejected candidates:")
                    lines.append("")
                    for candidate in rejected_candidates[:4]:
                        if not isinstance(candidate, dict):
                            continue
                        lines.append(
                            f"- Round {candidate.get('round')}, `{candidate.get('element_id')}` via "
                            f"`{join_list(candidate.get('relations'))}`: {candidate.get('reason')}"
                        )
                    lines.append("")
                bridge_candidates = trace.get("bridge_candidates", [])
                if isinstance(bridge_candidates, list) and bridge_candidates:
                    lines.append("Bridge-only candidates:")
                    lines.append("")
                    for candidate in bridge_candidates[:4]:
                        if not isinstance(candidate, dict):
                            continue
                        lines.append(
                            f"- Round {candidate.get('round')}, `{candidate.get('element_id')}` via "
                            f"`{join_list(candidate.get('relations'))}`: {candidate.get('reason')}"
                        )
                    lines.append("")
                deferred_candidates = trace.get("deferred_candidates", [])
                if isinstance(deferred_candidates, list) and deferred_candidates:
                    lines.append("Deferred candidates:")
                    lines.append("")
                    for candidate in deferred_candidates[:4]:
                        if not isinstance(candidate, dict):
                            continue
                        lines.append(
                            f"- Round {candidate.get('round')}, `{candidate.get('element_id')}` via "
                            f"`{join_list(candidate.get('relations'))}`: {candidate.get('reason')}"
                        )
                    lines.append("")
        bundle = case.get("answer_bundle")
        if not isinstance(bundle, dict):
            continue
        parts = bundle.get("parts", [])
        if not isinstance(parts, list) or not parts:
            continue
        lines.append("### Planner Answer Bundle")
        lines.append("")
        for raw_part in parts:
            part = raw_part if isinstance(raw_part, dict) else {}
            package = part.get("package") if isinstance(part.get("package"), dict) else {}
            lines.append(f"#### Part {part.get('part_index')}: {part.get('sub_need')}")
            lines.append("")
            lines.append(f"- Search terms: `{join_list(part.get('search_terms'))}`")
            lines.append(f"- Expected roles: `{join_list(part.get('expected_roles'))}`")
            lines.append(f"- Package: `{package.get('package_id', '')}`")
            lines.append(f"- Core: `{package.get('core_element_id', '')}`")
            lines.append(f"- Seed core: `{package.get('seed_core_element_id', '')}`")
            lines.append(f"- Score: `{package.get('score', '')}`")
            lines.append("")
            lines.append(str(package.get("preview", "")))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def join_list(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def prompt_cases() -> list[PromptCase]:
    return [
        PromptCase("closest-definition", "closest-pair", "definition", "What is the closest pair problem?"),
        PromptCase(
            "closest-procedure",
            "closest-pair",
            "procedure",
            "How does the divide-and-conquer closest pair algorithm work?",
        ),
        PromptCase(
            "closest-q-r",
            "closest-pair",
            "comparison",
            "How are Q and R used in the recursive closest pair algorithm?",
        ),
        PromptCase(
            "closest-above-three-pairs",
            "closest-pair",
            "reference",
            "What are the above three pairs in the closest pair algorithm?",
        ),
        PromptCase(
            "closest-contradiction",
            "closest-pair",
            "reference",
            "Why does the proof say this contradicts the assumption?",
        ),
        PromptCase(
            "closest-strip-nearby",
            "closest-pair",
            "citation",
            "Why can only nearby points in the strip be closest?",
        ),
        PromptCase(
            "inheritance-punnett",
            "09-Inheritance_fowler_anth1210_24",
            "visual-support",
            "What does the Punnett square illustrate?",
        ),
        PromptCase(
            "inheritance-meiosis-figure",
            "09-Inheritance_fowler_anth1210_24",
            "visual-support",
            "What does the figure show about meiosis producing haploid cells?",
        ),
        PromptCase(
            "inheritance-dna-unwinding",
            "09-Inheritance_fowler_anth1210_24",
            "visual-support",
            "What does the DNA unwinding diagram show?",
        ),
        PromptCase(
            "inheritance-sickle-map",
            "09-Inheritance_fowler_anth1210_24",
            "visual-support",
            "What does the malaria and sickle-cell map imply?",
        ),
        PromptCase(
            "inheritance-mitosis-meiosis",
            "09-Inheritance_fowler_anth1210_24",
            "comparison",
            "How are mitosis and meiosis different?",
        ),
        PromptCase(
            "inheritance-evolution-table",
            "09-Inheritance_fowler_anth1210_24",
            "comparison",
            "How do biological evolution and cultural evolution differ?",
        ),
    ]


if __name__ == "__main__":
    main()
