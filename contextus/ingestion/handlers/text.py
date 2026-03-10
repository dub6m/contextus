from __future__ import annotations

from .base import ElementHandler, HandlerOutput


class TextHandler(ElementHandler):
    def handle(self, page, bbox, scale_x: float, scale_y: float) -> HandlerOutput:
        text = self.extract_text(page, bbox, scale_x, scale_y)
        return HandlerOutput(
            content=text,
            raw_text=text,
            source="pymupdf_text",
            metadata={},
        )
