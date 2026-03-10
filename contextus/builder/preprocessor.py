from __future__ import annotations

from contextus.ingestion.models import ExtractedElement
import re


class ElementPreprocessor:
    """Converts extracted elements into canonical natural language strings."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def to_text(self, element: ExtractedElement) -> str:
        """Return a non-empty natural language representation of one element."""
        if element.id in self._cache:
            return self._cache[element.id]

        text = ""
        element_type = (element.type or "").strip().lower()
        content = element.content
        raw_text = (element.raw_text or "").strip()

        if element_type in {"text", "title"}:
            if isinstance(content, str) and content.strip():
                text = content.strip()
            else:
                text = raw_text
        elif element_type == "formula":
            latex = ""
            if isinstance(content, dict):
                latex = str(content.get("latex") or "").strip()
            readable = self._latex_to_readable(latex or raw_text)
            text = f"Formula: {readable}" if readable else ""
        elif element_type == "table":
            text = self._table_to_text(content)
        elif element_type in {"figure", "image", "chart", "diagram", "flowchart"}:
            figure_type = self._figure_type(element)
            ocr_text = self._figure_text(element)
            text = f"Figure ({figure_type}): {ocr_text or 'no text content'}"

        if not text.strip():
            text = f"Element of type {element.type} on page {element.page_number}"

        text = " ".join(text.split()).strip()
        self._cache[element.id] = text
        return text

    def _latex_to_readable(self, latex: str) -> str:
        latex = (latex or "").strip()
        if not latex:
            return ""

        def replace_frac(match: re.Match[str]) -> str:
            return f"{match.group(1)} divided by {match.group(2)}"

        previous = None
        current = latex
        while previous != current:
            previous = current
            current = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", replace_frac, current)

        replacements = {
            "\\sum": "sum of",
            "\\int": "integral of",
            "^": " to the power of ",
            "_": " subscript ",
            "{": " ",
            "}": " ",
            "\\": " ",
        }
        for source, target in replacements.items():
            current = current.replace(source, target)

        current = re.sub(r"\s+", " ", current)
        return current.strip()

    def _table_to_text(self, content: object) -> str:
        if not isinstance(content, dict):
            return ""

        headers = content.get("headers") or []
        rows = content.get("rows") or []
        normalized_headers = [str(item).strip() for item in headers if str(item).strip()]
        normalized_rows = [
            [str(cell).strip() for cell in row]
            for row in rows
            if isinstance(row, list)
        ]

        data_rows = normalized_rows
        if normalized_headers and normalized_rows and normalized_rows[0] == normalized_headers:
            data_rows = normalized_rows[1:]
        preview_rows = data_rows[:3]

        header_text = ", ".join(normalized_headers) if normalized_headers else "unknown columns"
        row_summaries: list[str] = []
        for row in preview_rows:
            if normalized_headers:
                pairs = []
                for index, value in enumerate(row[: len(normalized_headers)]):
                    if value:
                        pairs.append(f"{normalized_headers[index]}={value}")
                if pairs:
                    row_summaries.append(", ".join(pairs))
                    continue
            row_summaries.append(" | ".join(value for value in row if value))

        if row_summaries:
            return f"Table with columns {header_text}. First rows show: {'; '.join(row_summaries)}."
        return f"Table with columns {header_text}."

    def _figure_type(self, element: ExtractedElement) -> str:
        if isinstance(element.content, dict):
            value = str(element.content.get("figure_type") or "").strip()
            if value:
                return value
        value = str(element.metadata.get("figure_type") or "").strip()
        if value:
            return value
        return element.type

    def _figure_text(self, element: ExtractedElement) -> str:
        if isinstance(element.content, dict):
            value = str(element.content.get("ocr_text") or "").strip()
            if value:
                return value
        return (element.raw_text or "").strip()
