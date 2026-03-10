from __future__ import annotations

from .base import ElementHandler, HandlerOutput


class FormulaHandler(ElementHandler):
    def handle(self, page, bbox, scale_x: float, scale_y: float) -> HandlerOutput:
        raw_text = self.extract_text(page, bbox, scale_x, scale_y)
        latex = self.simple_text_to_latex(raw_text) or (raw_text if raw_text else None)
        return HandlerOutput(
            content={
                "format": "formula",
                "latex": latex,
                "mathml": None,
            },
            raw_text=raw_text,
            source="pymupdf_formula_text",
            metadata={"needs_review": latex is None},
            asset_bytes=self.render_crop(page, bbox, scale_x, scale_y),
            asset_extension=".png",
        )

    def simple_text_to_latex(self, text: str) -> str | None:
        if not text:
            return None
        value = str(text)
        strong_signals = (
            "=",
            "<=",
            ">=",
            "!=",
            "~",
            "^",
            "/",
            "sqrt",
            "sum",
            "int",
            "\\u221a",
            "\\u2211",
            "\\u222b",
            "\\u2264",
            "\\u2265",
            "\\u2248",
            "\\u2260",
        )
        expanded_value = value.encode('unicode_escape').decode('ascii')
        if not any(token in value or token in expanded_value for token in strong_signals):
            return None
        replacements = {
            "\u2212": "-",
            "\u2013": "-",
            "\u00d7": "*",
            "\u00b7": "\\cdot ",
            "\u00f7": "/",
            "\u2264": "\\leq ",
            "\u2265": "\\geq ",
            "\u2260": "\\neq ",
            "\u2248": "\\approx ",
            "\u2192": "\\to ",
            "\u2190": "\\leftarrow ",
            "\u221e": "\\infty ",
        }
        for source, target in replacements.items():
            value = value.replace(source, target)
        return value.strip()
