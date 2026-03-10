from __future__ import annotations

from .base import ElementHandler, HandlerOutput


class FigureHandler(ElementHandler):
    def handle(self, page, bbox, scale_x: float, scale_y: float, element_type: str) -> HandlerOutput:
        raw_text = self.extract_text(page, bbox, scale_x, scale_y)
        return HandlerOutput(
            content={
                "format": "figure",
                "figure_type": element_type,
                "ocr_text": raw_text,
                "literal_description": None,
            },
            raw_text=raw_text,
            source="figure_placeholder",
            metadata={
                "needs_review": True,
                "requires_visual_postprocessing": True,
            },
            asset_bytes=self.render_crop(page, bbox, scale_x, scale_y),
            asset_extension=".png",
        )
