from __future__ import annotations

from dataclasses import dataclass, field
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
