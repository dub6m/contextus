from __future__ import annotations

from typing import Any

from contextus.llm import LLMClient

from .base import ElementHandler, HandlerOutput


class TableHandler(ElementHandler):
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def handle(self, page, bbox, scale_x: float, scale_y: float) -> HandlerOutput:
        prepared = self.prepare_inputs(page, bbox, scale_x, scale_y)
        return self.handle_prepared(**prepared)

    def prepare_inputs(self, page, bbox, scale_x: float, scale_y: float) -> dict[str, object]:
        scaled_bbox = self.scale_bbox(bbox, scale_x, scale_y)
        raw_text = self.extract_text(page, bbox, scale_x, scale_y)
        crop = self.render_crop(page, bbox, scale_x, scale_y)
        return {
            "page": page,
            "scaled_bbox": scaled_bbox,
            "raw_text": raw_text,
            "crop": crop,
        }

    def handle_prepared(
        self,
        *,
        page,
        scaled_bbox: tuple[float, float, float, float],
        raw_text: str,
        crop: bytes,
    ) -> HandlerOutput:
        llm_output = self.build_llm_output(raw_text=raw_text, crop=crop)
        if llm_output is not None:
            return llm_output
        return self.build_fallback_output(page=page, scaled_bbox=scaled_bbox, raw_text=raw_text, crop=crop)

    def build_llm_output(self, *, raw_text: str, crop: bytes) -> HandlerOutput | None:
        if self.llm_client is None:
            return None
        llm_result = self._extract_with_llm(crop, raw_text=raw_text)
        if llm_result is None:
            return None
        return HandlerOutput(
            content=llm_result["content"],
            raw_text=str(llm_result["raw_text"]),
            source="openai_table_vision",
            metadata={
                "needs_review": bool(llm_result["needs_review"]),
                "transcription_method": type(self.llm_client).__name__,
                "extraction_rationale": llm_result["rationale"],
            },
            asset_bytes=crop,
            asset_extension=".png",
        )

    def build_fallback_output(
        self,
        *,
        page,
        scaled_bbox: tuple[float, float, float, float],
        raw_text: str,
        crop: bytes,
    ) -> HandlerOutput:
        rows = self._extract_rows(page, scaled_bbox)

        if rows:
            normalized = self._normalize_rows(rows)
            headers = normalized[0] if normalized else []
            data_rows = normalized[1:] if len(normalized) > 1 else []
            markdown = self._to_markdown(headers, data_rows)
            content = self.build_non_text_payload(
                format="table",
                figure_type="table",
                raw_text=markdown,
                structured_content={
                    "headers": headers,
                    "rows": data_rows,
                    "markdown": markdown,
                },
                literal_description=None,
                source_confidence=0.55,
            )
            return HandlerOutput(
                content=content,
                raw_text=markdown,
                source="pdfplumber_table",
                metadata={"needs_review": False},
                asset_bytes=crop,
                asset_extension=".png",
            )

        content = self.build_non_text_payload(
            format="table",
            figure_type="table",
            raw_text=raw_text,
            structured_content={
                "headers": [],
                "rows": [],
                "markdown": "",
            },
            literal_description=None,
            source_confidence=0.2,
        )
        return HandlerOutput(
            content=content,
            raw_text=raw_text,
            source="pymupdf_table_fallback",
            metadata={"needs_review": True},
            asset_bytes=crop,
            asset_extension=".png",
        )

    def _extract_rows(self, page, bbox: tuple[float, float, float, float]) -> list[list[Any]]:
        try:
            import pdfplumber
        except ImportError:
            return []

        pdf_path = getattr(getattr(page, "parent", None), "name", None)
        if not pdf_path:
            return []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                pdf_page = pdf.pages[page.number]
                cropped = pdf_page.crop(bbox)
                tables = cropped.extract_tables()
        except Exception:
            return []

        if not tables:
            return []
        return tables[0] or []

    def _normalize_rows(self, rows: list[list[Any]]) -> list[list[str]]:
        normalized: list[list[str]] = []
        max_cols = 0
        for row in rows:
            if not isinstance(row, list):
                continue
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            normalized.append(cells)
            max_cols = max(max_cols, len(cells))
        return [row + [""] * (max_cols - len(row)) for row in normalized if max_cols > 0]

    def _to_markdown(self, headers: list[str], rows: list[list[str]]) -> str:
        if not headers:
            return ""
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for row in rows:
            padded = row + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(padded[: len(headers)]) + " |")
        return "\n".join(lines)

    def _extract_with_llm(self, image_bytes: bytes, *, raw_text: str) -> dict[str, object] | None:
        try:
            response = self.llm_client.complete_with_image(
                system=(
                    "You extract a single table from a cropped document image. "
                    "Return strict JSON only. "
                    "Use this schema exactly: "
                    '{"format":"table","figure_type":"table","raw_text":"...","structured_content":{"headers":["..."],"rows":[["..."]],"markdown":"| ... |"},"literal_description":null,"source_confidence":0.0,"needs_review":false,"rationale":"..."} '
                    "Headers must be a flat string list. Rows must contain only data rows, not the header row. "
                    "Preserve visible text faithfully in raw_text. Set needs_review=true if cells, row boundaries, or headers are uncertain."
                ),
                user="Extract this table and return JSON only.",
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

        content = self._normalize_llm_content(payload, fallback_raw_text=raw_text)
        return {
            "content": content,
            "raw_text": content["raw_text"],
            "needs_review": bool(payload.get("needs_review", False)),
            "rationale": str(payload.get("rationale") or ""),
        }

    def _normalize_llm_content(self, payload: dict[str, Any], *, fallback_raw_text: str) -> dict[str, Any]:
        structured = payload.get("structured_content")
        if not isinstance(structured, dict):
            structured = {}
        headers = self._coerce_string_list(structured.get("headers"))
        rows = self._coerce_table_rows(structured.get("rows"))
        markdown = str(structured.get("markdown") or "").strip()
        if not markdown and headers:
            markdown = self._to_markdown(headers, rows)

        raw_text = self.normalize_text(payload.get("raw_text")) or fallback_raw_text
        return self.build_non_text_payload(
            format="table",
            figure_type="table",
            raw_text=raw_text,
            structured_content={
                "headers": headers,
                "rows": rows,
                "markdown": markdown,
            },
            literal_description=None,
            source_confidence=self._coerce_confidence(payload.get("source_confidence")),
        )
