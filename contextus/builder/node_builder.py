from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any
import json
import re

from contextus import Node, NodeType
from contextus.ingestion.models import ExtractedElement
from contextus.llm import LLMClient

from .node_candidate import NodeCandidate
from .preprocessor import ElementPreprocessor


_NODE_FALLBACK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="contextus-node-builder")


class NodeBuilder:
    """Builds Contextus nodes from contiguous chunks of extracted elements."""

    FALLBACK_SCOPE = "Auto-generated fallback node from document chunk; full semantics need review."
    MAX_NODE_RETRIES = 2

    def __init__(self, llm_client: LLMClient, preprocessor: ElementPreprocessor | None = None) -> None:
        """Create a node builder using the shared builder LLM client."""
        self.llm_client = llm_client
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.llm_calls = 0

    def build_nodes(self, chunks: list[list[ExtractedElement] | NodeCandidate]) -> list[Node]:
        """Build one node per chunk, falling back to stub nodes on repeated parse failure."""
        prepared = [
            {
                "index": index,
                "chunk": chunk,
                "elements": self._node_elements(chunk),
                "chunk_text": self._chunk_text(chunk),
                "metadata": self._chunk_metadata(chunk),
                "candidate": chunk if isinstance(chunk, NodeCandidate) else None,
            }
            for index, chunk in enumerate(chunks)
        ]
        nodes: list[Node | None] = [None] * len(prepared)
        pending = list(prepared)

        for _ in range(self.MAX_NODE_RETRIES):
            if not pending:
                break
            futures: list[tuple[dict[str, Any], Future]] = []
            for item in pending:
                system, user = self._node_prompt(
                    item["chunk_text"],
                    candidate=item["candidate"],
                )
                futures.append((item, self._submit_node_request(system, user)))
            self.llm_calls += len(futures)

            retry_items: list[dict[str, Any]] = []
            for item, future in futures:
                try:
                    response = future.result()
                    payload = self._parse_json_object(getattr(response, "content", str(response)))
                except Exception:
                    payload = None
                if payload is None:
                    retry_items.append(item)
                    continue
                nodes[item["index"]] = self._node_from_payload(
                    payload=payload,
                    elements=item["elements"],
                    index=item["index"],
                    metadata=item["metadata"],
                    chunk_text=item["chunk_text"],
                )
            pending = retry_items

        for item in pending:
            nodes[item["index"]] = self._fallback_node(item["elements"], item["index"], item["metadata"])
        return [node for node in nodes if node is not None]

    def _node_from_payload(
        self,
        *,
        payload: dict[str, Any],
        elements: list[ExtractedElement],
        index: int,
        metadata: dict[str, Any],
        chunk_text: str,
    ) -> Node:
        try:
            return Node(
                label=self._coerce_label(payload.get("label")),
                type=NodeType(str(payload.get("type", "stub")).strip().lower()),
                body=self._coerce_body(payload.get("body"), chunk_text),
                scope=self._coerce_scope(payload.get("scope")),
                aliases=self._coerce_aliases(payload.get("aliases")),
                metadata=metadata,
            )
        except Exception:
            return self._fallback_node(elements, index, metadata)

    def _submit_node_request(self, system: str, user: str) -> Future:
        submit = getattr(self.llm_client, "submit", None)
        if callable(submit):
            return submit(system=system, user=user, temperature=0.0)
        return _NODE_FALLBACK_EXECUTOR.submit(self.llm_client.complete, system, user, 0.0)

    def _node_prompt(self, chunk_text: str, *, candidate: NodeCandidate | None = None) -> tuple[str, str]:
        system = "You are a precise knowledge graph construction assistant."
        candidate_context = ""
        if candidate is not None:
            candidate_context = (
                f"Candidate title: {candidate.title}\n"
                f"Candidate summary: {candidate.summary}\n"
                f"Quality flags: {json.dumps(candidate.quality_flags, sort_keys=True)}\n\n"
            )
        user = (
            "You are building a knowledge graph node from a chunk of document elements.\n\n"
            f"{candidate_context}"
            f"Chunk content:\n{chunk_text}\n\n"
            "Return a JSON object with exactly these fields:\n"
            "{\n"
            '  "label": "short phrase, max 8 words, uniquely identifies this concept",\n'
            '  "type": "one of: definition, behavior, constraint, example, relation, procedure, exception",\n'
            '  "body": "self-contained atomic statement of the concept, 1-3 sentences, no pronouns that require external context",\n'
            '  "scope": "A single sentence describing what concepts and boundaries this node covers.",\n'
            '  "aliases": ["list", "of", "alternative", "names", "for", "this", "concept"]\n'
            "}\n\n"
            "Return only valid JSON. No markdown, no explanation."
        )
        return system, user

    def _request_node_payload(self, chunk_text: str, *, candidate: NodeCandidate | None = None) -> dict[str, Any] | None:
        system, user = self._node_prompt(chunk_text, candidate=candidate)
        for _ in range(self.MAX_NODE_RETRIES):
            self.llm_calls += 1
            response = self.llm_client.complete(system=system, user=user, temperature=0.0).content
            payload = self._parse_json_object(response)
            if payload is None:
                continue
            return payload
        return None

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception:
            pass
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _fallback_node(self, chunk: list[ExtractedElement], index: int, metadata: dict[str, Any]) -> Node:
        first_text = self.preprocessor.to_text(chunk[0])
        words = [word for word in first_text.split() if word]
        label = " ".join(words[:8]) or f"Chunk {index + 1}"
        return Node(
            label=label,
            type=NodeType.STUB,
            body=first_text,
            scope=self.FALLBACK_SCOPE,
            aliases=[],
            metadata=metadata,
        )

    def _node_elements(self, chunk: list[ExtractedElement] | NodeCandidate) -> list[ExtractedElement]:
        if isinstance(chunk, NodeCandidate):
            return list(chunk.elements)
        return list(chunk)

    def _chunk_text(self, chunk: list[ExtractedElement] | NodeCandidate) -> str:
        if isinstance(chunk, NodeCandidate):
            return chunk.text
        return "\n".join(self.preprocessor.to_text(element) for element in self._node_elements(chunk))

    def _chunk_metadata(self, chunk: list[ExtractedElement] | NodeCandidate) -> dict[str, Any]:
        if isinstance(chunk, NodeCandidate):
            return {
                "source_page_numbers": list(chunk.source_page_numbers),
                "source_element_ids": list(chunk.source_element_ids),
                "chunk_size": len(chunk.elements),
                "node_candidate_id": chunk.candidate_id,
                "node_candidate_index": chunk.candidate_index,
                "node_candidate_title": chunk.title,
                "node_candidate_summary": chunk.summary,
                "node_candidate_quality_flags": dict(chunk.quality_flags),
                "source_element_types": list(chunk.element_types),
                **chunk.metadata,
            }
        return {
            "source_page_numbers": sorted({element.page_number for element in chunk}),
            "source_element_ids": [element.id for element in chunk],
            "chunk_size": len(chunk),
        }

    def _coerce_label(self, value: Any) -> str:
        label = str(value or "").strip()
        if label:
            return label
        raise ValueError("Node label is required.")

    def _coerce_body(self, value: Any, fallback: str) -> str:
        body = str(value or "").strip()
        return body or fallback

    def _coerce_scope(self, value: Any) -> str:
        scope = str(value or "").strip()
        if scope:
            return scope
        raise ValueError("Node scope is required.")

    def _coerce_aliases(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        aliases = []
        for item in value:
            alias = str(item).strip()
            if alias:
                aliases.append(alias)
        return aliases
