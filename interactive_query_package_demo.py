from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import hashlib
import numpy as np
from dotenv import load_dotenv

from contextus.builder.config import BuilderConfig
from contextus.builder.query_assembly import (
    ConsensusKnnPropositionEvidenceAssembler,
    PropositionRoleHypothesis,
    QueryAssembledPackage,
    _PropositionDraft,
)
from contextus.ingestion.models import ExtractedDocument
from contextus.ingestion.storage import ExtractionArtifactStore
from contextus.llm import CerebrasClient, LLMClient, LLMRequest, OpenAIResponsesClient


DEFAULT_PROPOSITION_RUN = Path("chunk_runs/query_proposition_assembly_20260524_151159/query_proposition_assembly.json")
DEFAULT_EXTRACTIONS = {
    "closest": Path("extractions/closest-pair/closest-pair.extraction.json"),
    "inheritance": Path("extractions/09-Inheritance_fowler_anth1210_24/09-inheritance_fowler_anth1210_24.extraction.json"),
}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv(override=True)

    parser = argparse.ArgumentParser(description="Run fresh query-time package assembly with cached propositions.")
    parser.add_argument("prompt", nargs="*", help="Prompt to run. If omitted, starts an interactive loop.")
    parser.add_argument(
        "--document",
        choices=["all", *DEFAULT_EXTRACTIONS.keys()],
        default="all",
        help="Document to query. Use all to assemble against both test documents.",
    )
    parser.add_argument("--proposition-run", type=Path, default=DEFAULT_PROPOSITION_RUN)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--full", action="store_true", help="Print full packages instead of previews.")
    parser.add_argument("--answer", action="store_true", help="Generate a grounded answer from the top package.")
    parser.add_argument("--reply-only", action="store_true", help="Only print the grounded answer from the top package.")
    parser.add_argument("--hash-embeddings", action="store_true", help="Use very fast hash embeddings instead of MiniLM.")
    parser.add_argument("--nomic-model", action="store_true", help="Use the heavier configured Nomic embedding model.")
    parser.add_argument("--planner-provider", choices=["openai", "cerebras", "auto", "none"], default="openai")
    args = parser.parse_args()

    documents = load_documents(args.document)
    if not documents:
        raise SystemExit("No extraction documents found.")

    llm_client = make_llm_client(args.planner_provider)
    assembler = ConsensusKnnPropositionEvidenceAssembler(
        llm_client=llm_client,
        embed_texts=fast_embed_texts if args.hash_embeddings else None,
        config=embedding_config(use_nomic=args.nomic_model),
        top_k_cores=5,
        proposition_batch_size=6,
        use_language_map=True,
        use_query_planner=llm_client is not None,
        use_role_completion=True,
        query_planner_bridge_slots=1,
    )
    warm_proposition_cache(assembler, documents, args.proposition_run)

    prompt = " ".join(args.prompt).strip()
    if prompt:
        run_prompt(
            prompt,
            documents,
            assembler,
            llm_client,
            top_k=args.top_k,
            full=args.full,
            answer=args.answer,
            reply_only=args.reply_only,
        )
        return

    print("Fresh query-time package runner")
    print(f"Documents: {', '.join(documents)}")
    print(f"Planner: {type(llm_client).__name__ if llm_client is not None else 'disabled'}")
    print("Type a prompt, or blank/Ctrl+C to exit.")
    while True:
        try:
            prompt = input("\nPrompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not prompt:
            return
        run_prompt(
            prompt,
            documents,
            assembler,
            llm_client,
            top_k=args.top_k,
            full=args.full,
            answer=args.answer,
            reply_only=args.reply_only,
        )


def load_documents(selection: str) -> dict[str, ExtractedDocument]:
    selected = DEFAULT_EXTRACTIONS if selection == "all" else {selection: DEFAULT_EXTRACTIONS[selection]}
    documents: dict[str, ExtractedDocument] = {}
    for key, path in selected.items():
        if path.exists():
            documents[key] = ExtractionArtifactStore(path.parent).load(path)
    return documents


def make_llm_client(provider: str) -> LLMClient | None:
    if provider == "none":
        return None
    if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
        return OpenAIResponsesClient(max_output_tokens=2200)
    if provider == "cerebras" and os.environ.get("CEREBRAS_API_KEY"):
        return CerebrasClient()
    if provider == "auto":
        if os.environ.get("OPENAI_API_KEY"):
            return OpenAIResponsesClient(max_output_tokens=2200)
        if os.environ.get("CEREBRAS_API_KEY"):
            return CerebrasClient()
    return None


def embedding_config(*, use_nomic: bool) -> BuilderConfig:
    if use_nomic:
        return BuilderConfig()
    return BuilderConfig(EMBEDDING_MODEL="all-MiniLM-L6-v2", EMBEDDING_FALLBACK="all-MiniLM-L6-v2")


def warm_proposition_cache(
    assembler: ConsensusKnnPropositionEvidenceAssembler,
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
        document_cache_key = cache_document_key(document_key, document)
        raw_propositions = cached_by_document.get(document_cache_key) or cached_by_document.get(document_key) or []
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
            drafts_by_element.setdefault(element_id, []).append(_PropositionDraft(text=text, roles=roles))

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


def run_prompt(
    prompt: str,
    documents: dict[str, ExtractedDocument],
    assembler: ConsensusKnnPropositionEvidenceAssembler,
    llm_client: LLMClient | None,
    *,
    top_k: int,
    full: bool,
    answer: bool,
    reply_only: bool,
) -> None:
    if not reply_only:
        print(f"\nQuery: {prompt}")
    ranked: list[tuple[float, str, QueryAssembledPackage, Any]] = []
    for document_key, document in documents.items():
        result = assembler.assemble(document, prompt)
        if not result.packages:
            continue
        for rank, package in enumerate(result.packages[: max(1, top_k)], start=1):
            score = float(package.score) - rank * 0.00001
            ranked.append((score, document_key, package, result.retrieval_plan))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if reply_only:
        if not ranked:
            print("No package was assembled for that prompt.")
            return
        print(generate_answer(prompt, ranked[0][2], llm_client))
        return

    for rank, (_score, document_key, package, retrieval_plan) in enumerate(ranked[: max(1, top_k)], start=1):
        print_package(rank, document_key, package, retrieval_plan, full=full)
        if answer and rank == 1:
            print("\nGrounded Answer:")
            print(generate_answer(prompt, package, llm_client))


def print_package(rank: int, document_key: str, package: QueryAssembledPackage, retrieval_plan: Any, *, full: bool) -> None:
    diagnostics = package.ranking_diagnostics
    print("\n" + "=" * 88)
    print(f"Rank {rank} | document={document_key} | package_score={package.score} | core={package.core_element_id}")
    if retrieval_plan is not None:
        print(f"Interpreted need: {retrieval_plan.interpreted_need}")
        if retrieval_plan.sub_needs:
            print("Sub-needs:")
            for sub_need in retrieval_plan.sub_needs[:5]:
                print(f"- {sub_need.need}")
    if diagnostics is not None:
        print(
            "Ranking: "
            f"profile={diagnostics.profile_alignment_score} "
            f"direct={diagnostics.directness_score} "
            f"assembly={diagnostics.assembly_confidence_score} "
            f"plan={diagnostics.plan_coverage_score}"
        )
        if diagnostics.positive_reasons:
            print("Why it ranked well: " + "; ".join(diagnostics.positive_reasons))
        if diagnostics.negative_reasons:
            print("Concerns: " + "; ".join(diagnostics.negative_reasons))
    print("\nPackage:")
    print(package.package_text if full else preview_package_text(package.package_text))


def generate_answer(prompt: str, package: QueryAssembledPackage, llm_client: LLMClient | None) -> str:
    if llm_client is None:
        return "Answer generation unavailable because no planner/LLM client is configured."
    request = LLMRequest(
        system=(
            "Answer the user's question using only the provided source package. "
            "If the package is insufficient, say what is missing. Keep the answer concise and grounded."
        ),
        user="\n".join(["User question:", prompt, "", "Source package:", package.package_text]),
        temperature=0.0,
    )
    response = llm_client.complete_many([request])[0]
    return str(getattr(response, "content", response)).strip()


def fast_embed_texts(texts: list[str]) -> np.ndarray:
    vectors = []
    for text in texts:
        vector = np.zeros(384, dtype=float)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\d+(?:\.\d+)?", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % len(vector)] += 1.0
        norm = float(np.linalg.norm(vector))
        vectors.append(vector / norm if norm else vector)
    return np.asarray(vectors, dtype=float)


def preview_package_text(text: str, *, max_chars: int = 3200) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "\n\n... [preview truncated; rerun with --full]"


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
