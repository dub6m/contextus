from __future__ import annotations

from typing import Any

from .base import ElementHandler, HandlerOutput


class TableHandler(ElementHandler):
    def handle(self, page, bbox, scale_x: float, scale_y: float) -> HandlerOutput:
        scaled_bbox = self.scale_bbox(bbox, scale_x, scale_y)
        rows = self._extract_rows(page, scaled_bbox)
        crop = self.render_crop(page, bbox, scale_x, scale_y)

        if rows:
            normalized = self._normalize_rows(rows)
            markdown = self._to_markdown(normalized)
            return HandlerOutput(
                content={
                    "format": "table",
                    "headers": normalized[0] if normalized else [],
                    "rows": normalized,
                    "markdown": markdown,
                },
                raw_text=markdown,
                source="pdfplumber_table",
                metadata={"needs_review": False},
                asset_bytes=crop,
                asset_extension=".png",
            )

        text = self.extract_text(page, bbox, scale_x, scale_y)
        return HandlerOutput(
            content={
                "format": "table",
                "headers": [],
                "rows": [],
                "markdown": "",
                "fallback_text": text,
            },
            raw_text=text,
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

    def _to_markdown(self, rows: list[list[str]]) -> str:
        if not rows:
            return ""
        header = rows[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in rows[1:]:
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[: len(header)]) + " |")
        return "\n".join(lines)
