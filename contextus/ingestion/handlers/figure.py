from __future__ import annotations

from typing import Any

from contextus.llm import LLMClient

from .base import ElementHandler, HandlerOutput


class FigureHandler(ElementHandler):
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def handle(self, page, bbox, scale_x: float, scale_y: float, element_type: str) -> HandlerOutput:
        prepared = self.prepare_inputs(page, bbox, scale_x, scale_y, element_type=element_type)
        return self.handle_prepared(**prepared)

    def prepare_inputs(
        self,
        page,
        bbox,
        scale_x: float,
        scale_y: float,
        *,
        element_type: str,
    ) -> dict[str, object]:
        raw_text = self.extract_text(page, bbox, scale_x, scale_y)
        crop = self.render_crop(page, bbox, scale_x, scale_y)
        return {
            "raw_text": raw_text,
            "crop": crop,
            "element_type": element_type,
        }

    def handle_prepared(self, *, raw_text: str, crop: bytes, element_type: str) -> HandlerOutput:
        llm_output = self.build_llm_output(raw_text=raw_text, crop=crop, element_type=element_type)
        if llm_output is not None:
            return llm_output
        return self.build_fallback_output(raw_text=raw_text, crop=crop, element_type=element_type)

    def build_llm_output(self, *, raw_text: str, crop: bytes, element_type: str) -> HandlerOutput | None:
        if self.llm_client is None:
            return None
        llm_result = self._extract_with_llm(crop, raw_text=raw_text, element_type=element_type)
        if llm_result is None:
            return None
        return HandlerOutput(
            content=llm_result["content"],
            raw_text=str(llm_result["raw_text"]),
            source=f"openai_{element_type}_vision",
            metadata={
                "needs_review": bool(llm_result["needs_review"]),
                "transcription_method": type(self.llm_client).__name__,
                "extraction_rationale": llm_result["rationale"],
            },
            asset_bytes=crop,
            asset_extension=".png",
        )

    def build_fallback_output(self, *, raw_text: str, crop: bytes, element_type: str) -> HandlerOutput:
        content = self.build_non_text_payload(
            format="figure",
            figure_type=element_type,
            raw_text=raw_text,
            structured_content=None,
            literal_description=None,
            source_confidence=0.0,
        )
        return HandlerOutput(
            content=content,
            raw_text=raw_text,
            source="figure_placeholder",
            metadata={
                "needs_review": True,
                "requires_visual_postprocessing": True,
            },
            asset_bytes=crop,
            asset_extension=".png",
        )

    def _extract_with_llm(self, image_bytes: bytes, *, raw_text: str, element_type: str) -> dict[str, object] | None:
        try:
            response = self.llm_client.complete_with_image(
                system=self._system_prompt(element_type),
                user=f"Extract this {element_type} and return JSON only.",
                image_bytes=image_bytes,
                mime_type="image/png",
                temperature=0.0,
            ).content
        except NotImplementedError:
            return None
        except Exception:
            return None

        payload = self.parse_json_payload(response)
        if not isinstance(payload, dict):
            return None

        content = self._normalize_llm_content(payload, fallback_raw_text=raw_text, element_type=element_type)
        return {
            "content": content,
            "raw_text": content["raw_text"],
            "needs_review": bool(payload.get("needs_review", False)),
            "rationale": str(payload.get("rationale") or ""),
        }

    def _normalize_llm_content(
        self,
        payload: dict[str, Any],
        *,
        fallback_raw_text: str,
        element_type: str,
    ) -> dict[str, Any]:
        structured = payload.get("structured_content")
        if not isinstance(structured, dict):
            structured = None
        literal_description = self.normalize_text(payload.get("literal_description")) or None
        raw_text = self.normalize_text(payload.get("raw_text")) or fallback_raw_text
        return self.build_non_text_payload(
            format="figure",
            figure_type=element_type,
            raw_text=raw_text,
            structured_content=structured,
            literal_description=literal_description,
            source_confidence=self._coerce_confidence(payload.get("source_confidence")),
        )

    def _system_prompt(self, element_type: str) -> str:
        if element_type == "chart":
            return (
                "You extract a single chart from a cropped document image. "
                "Return strict JSON only using this schema: "
                '{"format":"figure","figure_type":"chart","raw_text":"...","structured_content":{"chart_type":"...","axes":{"x_label":"...","y_label":"..."},"series":[{"name":"...","values":[{"x":"...","y":"..."}]}],"findings":["..."]},"literal_description":null,"source_confidence":0.0,"needs_review":false,"rationale":"..."} '
                "Use structured_content to capture chart type, axes, series, and concise findings. "
                "Set needs_review=true when labels, values, legend mapping, or trends are uncertain."
            )
        if element_type in {"diagram", "flowchart"}:
            return (
                f"You extract a single {element_type} from a cropped document image. "
                "Return strict JSON only using this schema: "
                '{"format":"figure","figure_type":"diagram","raw_text":"...","structured_content":{"nodes":[{"id":"n1","label":"..."}],"edges":[{"source":"n1","target":"n2","label":"..."}],"steps":["..."]},"literal_description":"...","source_confidence":0.0,"needs_review":false,"rationale":"..."} '
                "Use structured_content to capture nodes, edges, and ordered steps when visible. "
                "Use literal_description for the visual layout or any content that does not fit the graph. "
                "Set figure_type to the actual crop type and set needs_review=true if connectivity or labels are uncertain."
            )
        return (
            f"You extract a single {element_type} from a cropped document image. "
            "Return strict JSON only using this schema: "
            '{"format":"figure","figure_type":"image","raw_text":"...","structured_content":null,"literal_description":"...","source_confidence":0.0,"needs_review":false,"rationale":"..."} '
            "Preserve all visible text in raw_text. "
            "Use literal_description for a concrete visual description. "
            "Set figure_type to the actual crop type and use structured_content only if a strong canonical structure is clearly present."
        )
