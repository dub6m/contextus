from __future__ import annotations

from typing import Any
import json
import re

from contextus import Node, NodeType
from contextus.ingestion.models import ExtractedElement
from contextus.llm import LLMClient

from .preprocessor import ElementPreprocessor


class NodeBuilder:
    """Builds Contextus nodes from contiguous chunks of extracted elements."""

    FALLBACK_SCOPE = "Auto-generated fallback node from document chunk; full semantics need review."

    def __init__(self, llm_client: LLMClient, preprocessor: ElementPreprocessor | None = None) -> None:
        """Create a node builder using the shared builder LLM client."""
        self.llm_client = llm_client
        self.preprocessor = preprocessor or ElementPreprocessor()
        self.llm_calls = 0

    def build_nodes(self, chunks: list[list[ExtractedElement]]) -> list[Node]:
        """Build one node per chunk, falling back to stub nodes on repeated parse failure."""
        nodes: list[Node] = []
        for index, chunk in enumerate(chunks):
            chunk_text = self._chunk_text(chunk)
            metadata = self._chunk_metadata(chunk)
            payload = self._request_node_payload(chunk_text)
            if payload is None:
                nodes.append(self._fallback_node(chunk, index, metadata))
                continue
            try:
                node = Node(
                    label=self._coerce_label(payload.get("label")),
                    type=NodeType(str(payload.get("type", "stub")).strip().lower()),
                    body=self._coerce_body(payload.get("body"), chunk_text),
                    scope=self._coerce_scope(payload.get("scope")),
                    aliases=self._coerce_aliases(payload.get("aliases")),
                    metadata=metadata,
                )
            except Exception:
                node = self._fallback_node(chunk, index, metadata)
            nodes.append(node)
        return nodes

    def _request_node_payload(self, chunk_text: str) -> dict[str, Any] | None:
        system = "You are a precise knowledge graph construction assistant."
        user = (
            "You are building a knowledge graph node from a chunk of document elements.\n\n"
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
        for _ in range(2):
            self.llm_calls += 1
            response = self.llm_client.complete(system=system, user=user, temperature=0.0).content
            payload = self._parse_json_object(response)
            if payload is not None:
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

    def _chunk_text(self, chunk: list[ExtractedElement]) -> str:
        return "\n".join(self.preprocessor.to_text(element) for element in chunk)

    def _chunk_metadata(self, chunk: list[ExtractedElement]) -> dict[str, Any]:
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
