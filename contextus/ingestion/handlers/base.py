from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any


@dataclass
class HandlerOutput:
    content: Any
    raw_text: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    asset_bytes: bytes | None = None
    asset_extension: str | None = None


class ElementHandler:
    @staticmethod
    def build_non_text_payload(
        *,
        format: str,
        figure_type: str,
        raw_text: str,
        structured_content: Any,
        literal_description: str | None,
        source_confidence: float | None,
    ) -> dict[str, Any]:
        return {
            "format": format,
            "figure_type": figure_type,
            "raw_text": (raw_text or "").strip(),
            "structured_content": structured_content,
            "literal_description": literal_description,
            "source_confidence": ElementHandler._coerce_confidence(source_confidence),
        }

    @staticmethod
    def scale_bbox(
        bbox: list[float] | tuple[float, float, float, float],
        scale_x: float,
        scale_y: float,
    ) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = bbox
        return (x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y)

    @staticmethod
    def extract_text(page, bbox, scale_x: float, scale_y: float) -> str:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for text extraction.") from exc

        rect = fitz.Rect(*ElementHandler.scale_bbox(bbox, scale_x, scale_y))
        text = page.get_text("text", clip=rect)
        return " ".join(text.split()).strip()

    @staticmethod
    def render_crop(page, bbox, scale_x: float, scale_y: float, zoom: float = 2.0) -> bytes:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for figure cropping.") from exc

        rect = fitz.Rect(*ElementHandler.scale_bbox(bbox, scale_x, scale_y))
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)
        return pixmap.tobytes("png")

    @staticmethod
    def parse_json_payload(text: str) -> dict[str, Any] | None:
        candidate = (text or "").strip()
        if not candidate:
            return None
        if candidate.startswith("```"):
            lines = [line for line in candidate.splitlines() if not line.strip().startswith("```")]
            candidate = "\n".join(lines).strip()

        for attempt in (candidate, ElementHandler._extract_outer_json_object(candidate)):
            if not attempt:
                continue
            try:
                payload = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @staticmethod
    def normalize_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return " ".join(value.split()).strip()
        if isinstance(value, list):
            parts = [ElementHandler.normalize_text(item) for item in value]
            return " ".join(part for part in parts if part).strip()
        if isinstance(value, dict):
            for key in (
                "raw_text",
                "text",
                "latex",
                "markdown",
                "literal_description",
                "value",
            ):
                normalized = ElementHandler.normalize_text(value.get(key))
                if normalized:
                    return normalized
            return ""
        return str(value).strip()

    @staticmethod
    def _extract_outer_json_object(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return ""
        return text[start:end + 1]

    @staticmethod
    def _coerce_confidence(value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, result))

    @staticmethod
    def _coerce_string_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(item).strip() for item in values if str(item).strip()]

    @staticmethod
    def _coerce_table_rows(values: Any) -> list[list[str]]:
        if not isinstance(values, list):
            return []
        rows: list[list[str]] = []
        for row in values:
            if not isinstance(row, list):
                continue
            rows.append([str(cell).strip() for cell in row])
        return rows
