from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Iterable
import math

import numpy as np

from contextus import Edge, Node
from contextus.llm import LLMClient

from .config import BuilderConfig


_EDGE_FALLBACK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="contextus-edge-builder")


class EdgeBuilder:
    """Infers sequential and semantic edges between builder-generated nodes."""

    RELATION_MAP = {
        "DEFINES": "defines",
        "EXTENDS": "extends",
        "CONTRADICTS": "contradicts",
        "REQUIRES": "requires",
        "EXEMPLIFIES": "exemplifies",
        "CAUSES": "causes",
        "CONSTRAINS": "constrains",
        "RELATES_TO": "relates_to",
    }

    def __init__(
        self,
        llm_client: LLMClient,
        config: BuilderConfig | None = None,
        source_document: str | None = None,
    ) -> None:
        """Create an edge builder with cached embedding state."""
        self.llm_client = llm_client
        self.config = config or BuilderConfig()
        self.source_document = source_document or ""
        self._embedder = None
        self.llm_calls = 0

    def build_edges(self, nodes: list[Node]) -> list[Edge]:
        """Build sequential edges plus capped semantic edges for non-adjacent nodes."""
        edges: list[Edge] = []
        for index in range(len(nodes) - 1):
            edges.append(
                Edge(
                    source_id=nodes[index].id,
                    target_id=nodes[index + 1].id,
                    relations=["leads_to"],
                    base_weight=0.5,
                    metadata={
                        "source_document": self.source_document,
                        "kind": "sequential",
                    },
                )
            )

        if len(nodes) < 3:
            return edges

        texts = [self._node_text(node) for node in nodes]
        embeddings = self._embed_texts(texts)
        similarity_matrix = embeddings @ embeddings.T

        semantic_specs = []
        for source_index, source_node in enumerate(nodes):
            candidates: list[tuple[float, int]] = []
            for target_index, target_node in enumerate(nodes):
                if source_index == target_index:
                    continue
                if abs(source_index - target_index) == 1:
                    continue
                similarity = float(similarity_matrix[source_index, target_index])
                if similarity >= self.config.SEMANTIC_EDGE_THRESHOLD:
                    candidates.append((similarity, target_index))
            candidates.sort(key=lambda item: item[0], reverse=True)

            created = 0
            for similarity, target_index in candidates:
                if created >= self.config.MAX_SEMANTIC_EDGES_PER_NODE:
                    break
                semantic_specs.append((source_node, nodes[target_index], similarity))
                created += 1
        futures = [
            (source_node, target_node, similarity, self._submit_relation_classification(source_node, target_node))
            for source_node, target_node, similarity in semantic_specs
        ]
        self.llm_calls += len(futures)
        for source_node, target_node, similarity, future in futures:
            try:
                response = future.result().content.strip().upper()
            except Exception:
                response = ""
            relation = self.RELATION_MAP.get(response, "relates_to")
            edges.append(
                Edge(
                    source_id=source_node.id,
                    target_id=target_node.id,
                    relations=[relation],
                    base_weight=0.7,
                    metadata={
                        "source_document": self.source_document,
                        "kind": "semantic",
                        "similarity": similarity,
                    },
                )
            )
        return edges

    def _node_text(self, node: Node) -> str:
        return f"{node.label}. {node.body}"

    def _embed_texts(self, texts: Iterable[str]) -> np.ndarray:
        model = self._get_embedder()
        embeddings = model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=float)

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is required for edge embeddings.") from exc
        try:
            self._embedder = SentenceTransformer(self.config.EMBEDDING_MODEL, trust_remote_code=True)
        except Exception:
            self._embedder = SentenceTransformer(self.config.EMBEDDING_FALLBACK)
        return self._embedder

    def _relation_prompt(self, source: Node, target: Node) -> tuple[str, str]:
        system = "You are a precise knowledge graph relationship classifier."
        user = (
            "Given these two knowledge graph nodes:\n\n"
            f"Node A:\nLabel: {source.label}\nBody: {source.body}\n\n"
            f"Node B:\nLabel: {target.label}\nBody: {target.body}\n\n"
            "What is the relationship from A to B?\n"
            "Choose the single best option from:\n"
            "DEFINES, EXTENDS, CONTRADICTS, REQUIRES, EXEMPLIFIES, CAUSES, CONSTRAINS, RELATES_TO\n\n"
            "Reply with exactly one word."
        )
        return system, user

    def _submit_relation_classification(self, source: Node, target: Node) -> Future:
        system, user = self._relation_prompt(source, target)
        submit = getattr(self.llm_client, "submit", None)
        if callable(submit):
            return submit(system=system, user=user, temperature=0.0)
        return _EDGE_FALLBACK_EXECUTOR.submit(self.llm_client.complete, system, user, 0.0)

    def _classify_relation(self, source: Node, target: Node) -> str:
        system, user = self._relation_prompt(source, target)
        self.llm_calls += 1
        response = self.llm_client.complete(system=system, user=user, temperature=0.0).content.strip().upper()
        return self.RELATION_MAP.get(response, "relates_to")
