from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Any

from contextus.llm import LLMClient

from ..handlers import FigureHandler, FormulaHandler, TableHandler, TextHandler
from ..models import ExtractedDocument, ExtractedElement, ExtractedPage


@dataclass
class PreparedNonTextTask:
    page_number: int
    order: int
    element_type: str
    bbox: tuple[float, float, float, float]
    confidence: float | None
    raw_detection_type: str
    handler_kind: str
    prepared: dict[str, Any]
    llm_output: Any = None


class PdfContentExtractor:
    FIGURE_TYPES = {"figure", "image", "chart", "diagram", "flowchart"}

    def __init__(
        self,
        *,
        vision_llm_client: LLMClient | None = None,
        formula_llm_client: LLMClient | None = None,
        non_text_concurrency: int | None = None,
    ) -> None:
        llm_client = vision_llm_client or formula_llm_client
        self.llm_client = llm_client
        self.non_text_concurrency = self._resolve_non_text_concurrency(non_text_concurrency)
        self.text_handler = TextHandler()
        self.table_handler = TableHandler(llm_client=llm_client)
        self.formula_handler = FormulaHandler(llm_client=llm_client)
        self.figure_handler = FigureHandler(llm_client=llm_client)

    def extract(
        self,
        file_path: str,
        analyzed_pages: list[dict],
        *,
        original_source_path: str | None = None,
        converted_from: str | None = None,
        output_dir: str | Path | None = None,
    ) -> ExtractedDocument:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF extraction.") from exc

        asset_dir = None
        if output_dir is not None:
            asset_dir = Path(output_dir) / 'assets'
            asset_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(file_path)
        pages: list[ExtractedPage] = []
        page_states: list[dict[str, Any]] = []
        non_text_tasks: list[PreparedNonTextTask] = []
        dropped_empty_elements = 0
        dropped_duplicate_elements = 0
        rewritten_overlap_elements = 0

        try:
            for page_data in analyzed_pages:
                page_number = int(page_data['page_number'])
                page = doc[page_number - 1]
                page_width = float(page_data.get('page_width', page.rect.width))
                page_height = float(page_data.get('page_height', page.rect.height))
                rendered_width = float(page_data.get('rendered_width') or page.rect.width)
                rendered_height = float(page_data.get('rendered_height') or page.rect.height)
                scale_x = page_width / rendered_width
                scale_y = page_height / rendered_height

                records: list[dict[str, Any]] = []
                detections = sorted(
                    page_data.get('detections', []),
                    key=lambda item: (item['bbox'][1], item['bbox'][0]),
                )
                for order, detection in enumerate(detections, start=1):
                    element_type = str(detection['type']).strip().lower()
                    bbox = tuple(float(v) for v in detection['bbox'])
                    raw_detection_type = str(detection.get('raw_type', element_type))
                    if self._should_parallelize_non_text(element_type):
                        task = PreparedNonTextTask(
                            page_number=page_number,
                            order=order,
                            element_type=element_type,
                            bbox=bbox,
                            confidence=detection.get('confidence'),
                            raw_detection_type=raw_detection_type,
                            handler_kind=self._handler_kind_for(element_type),
                            prepared=self._prepare_non_text_detection(page, element_type, bbox, scale_x, scale_y),
                        )
                        records.append({"task": task})
                        non_text_tasks.append(task)
                        continue

                    output = self._handle_detection(page, element_type, bbox, scale_x, scale_y)
                    records.append(
                        {
                            "page_number": page_number,
                            "order": order,
                            "element_type": element_type,
                            "bbox": bbox,
                            "confidence": detection.get('confidence'),
                            "raw_detection_type": raw_detection_type,
                            "output": output,
                        }
                    )
                page_states.append(
                    {
                        "page_number": page_number,
                        "page_width": page_width,
                        "page_height": page_height,
                        "records": records,
                    }
                )

            self._resolve_non_text_tasks(non_text_tasks)

            for page_state in page_states:
                page_number = int(page_state["page_number"])
                elements: list[ExtractedElement] = []
                for record in page_state["records"]:
                    task = record.get("task")
                    if task is not None:
                        output = task.llm_output or self._fallback_non_text_output(task)
                        element_type = task.element_type
                        bbox = task.bbox
                        order = task.order
                        confidence = task.confidence
                        raw_detection_type = task.raw_detection_type
                    else:
                        output = record["output"]
                        element_type = str(record["element_type"])
                        bbox = tuple(float(v) for v in record["bbox"])
                        order = int(record["order"])
                        confidence = record["confidence"]
                        raw_detection_type = str(record["raw_detection_type"])

                    element = ExtractedElement(
                        type=element_type,
                        page_number=page_number,
                        order=order,
                        bbox=bbox,
                        confidence=confidence,
                        content=output.content,
                        raw_text=output.raw_text,
                        source=output.source,
                        metadata={
                            **output.metadata,
                            'raw_detection_type': raw_detection_type,
                        },
                    )
                    if not self._should_keep_element(element, has_asset=output.asset_bytes is not None):
                        dropped_empty_elements += 1
                        continue
                    if asset_dir is not None and output.asset_bytes is not None:
                        asset_name = f"page-{page_number:04d}-{order:04d}-{element.type}{output.asset_extension or ''}"
                        asset_path = asset_dir / asset_name
                        asset_path.write_bytes(output.asset_bytes)
                        element.asset_path = str(asset_path.relative_to(asset_dir.parent))

                    elements.append(element)

                elements, page_duplicate_drops, page_overlap_rewrites = self._deduplicate_page_elements(elements)
                dropped_duplicate_elements += page_duplicate_drops
                rewritten_overlap_elements += page_overlap_rewrites

                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        width=float(page_state["page_width"]),
                        height=float(page_state["page_height"]),
                        elements=elements,
                    )
                )
        finally:
            doc.close()

        source_path = original_source_path or file_path
        return ExtractedDocument(
            source_name=Path(source_path).name,
            source_path=str(Path(source_path)),
            source_type=Path(source_path).suffix.lower().lstrip('.'),
            processed_path=str(Path(file_path)),
            converted_from=converted_from,
            metadata={
                'pipeline': 'contextus.ingestion',
                'pages_extracted': len(pages),
                'dropped_empty_elements': dropped_empty_elements,
                'dropped_duplicate_elements': dropped_duplicate_elements,
                'rewritten_overlap_elements': rewritten_overlap_elements,
            },
            pages=pages,
        )

    def _resolve_non_text_concurrency(self, value: int | None) -> int:
        candidate = value
        if candidate is None:
            candidate = os.environ.get("CONTEXTUS_NON_TEXT_CONCURRENCY")
        try:
            resolved = int(candidate) if candidate is not None else 10
        except (TypeError, ValueError):
            resolved = 10
        return max(1, resolved)

    def _should_parallelize_non_text(self, element_type: str) -> bool:
        if self.llm_client is None or self.non_text_concurrency <= 1:
            return False
        normalized = (element_type or "").strip().lower()
        return normalized == "table" or normalized == "formula" or normalized in self.FIGURE_TYPES

    def _handler_kind_for(self, element_type: str) -> str:
        normalized = (element_type or "").strip().lower()
        if normalized == "table":
            return "table"
        if normalized == "formula":
            return "formula"
        if normalized in self.FIGURE_TYPES:
            return "figure"
        raise ValueError(f"Unsupported non-text element type: {element_type}")

    def _prepare_non_text_detection(self, page, element_type: str, bbox, scale_x: float, scale_y: float) -> dict[str, Any]:
        handler_kind = self._handler_kind_for(element_type)
        if handler_kind == "table":
            return self.table_handler.prepare_inputs(page, bbox, scale_x, scale_y)
        if handler_kind == "formula":
            return self.formula_handler.prepare_inputs(page, bbox, scale_x, scale_y)
        return self.figure_handler.prepare_inputs(page, bbox, scale_x, scale_y, element_type=element_type)

    def _resolve_non_text_tasks(self, tasks: list[PreparedNonTextTask]) -> None:
        if not tasks:
            return

        with ThreadPoolExecutor(max_workers=self.non_text_concurrency) as executor:
            future_map = {
                executor.submit(self._build_non_text_llm_output, task): task
                for task in tasks
            }
            for future in as_completed(future_map):
                task = future_map[future]
                try:
                    task.llm_output = future.result()
                except Exception:
                    task.llm_output = None

    def _build_non_text_llm_output(self, task: PreparedNonTextTask):
        if task.handler_kind == "table":
            return self.table_handler.build_llm_output(
                raw_text=str(task.prepared["raw_text"]),
                crop=bytes(task.prepared["crop"]),
            )
        if task.handler_kind == "formula":
            return self.formula_handler.build_llm_output(
                raw_text=str(task.prepared["raw_text"]),
                image_bytes=bytes(task.prepared["image_bytes"]),
            )
        return self.figure_handler.build_llm_output(
            raw_text=str(task.prepared["raw_text"]),
            crop=bytes(task.prepared["crop"]),
            element_type=str(task.prepared["element_type"]),
        )

    def _fallback_non_text_output(self, task: PreparedNonTextTask):
        if task.handler_kind == "table":
            return self.table_handler.build_fallback_output(
                page=task.prepared["page"],
                scaled_bbox=task.prepared["scaled_bbox"],
                raw_text=str(task.prepared["raw_text"]),
                crop=bytes(task.prepared["crop"]),
            )
        if task.handler_kind == "formula":
            return self.formula_handler.build_fallback_output(
                raw_text=str(task.prepared["raw_text"]),
                image_bytes=bytes(task.prepared["image_bytes"]),
            )
        return self.figure_handler.build_fallback_output(
            raw_text=str(task.prepared["raw_text"]),
            crop=bytes(task.prepared["crop"]),
            element_type=str(task.prepared["element_type"]),
        )

    def _handle_detection(self, page, element_type: str, bbox, scale_x: float, scale_y: float):
        if element_type in {'text', 'title'}:
            return self.text_handler.handle(page, bbox, scale_x, scale_y)
        if element_type == 'table':
            return self.table_handler.handle(page, bbox, scale_x, scale_y)
        if element_type == 'formula':
            return self.formula_handler.handle(page, bbox, scale_x, scale_y)
        if element_type in self.FIGURE_TYPES:
            return self.figure_handler.handle(page, bbox, scale_x, scale_y, element_type)
        text_output = self.text_handler.handle(page, bbox, scale_x, scale_y)
        text_output.metadata['normalized_from_unknown_type'] = True
        return text_output

    def _should_keep_element(self, element: ExtractedElement, *, has_asset: bool) -> bool:
        element_type = (element.type or "").strip().lower()
        if element_type in self.FIGURE_TYPES:
            return True
        if has_asset:
            return True

        text_content = self._normalized_text(element.content)
        raw_text = self._normalized_text(element.raw_text)

        if element_type in {'text', 'title'}:
            return bool(text_content or raw_text)
        if element_type == 'formula':
            return bool(self._formula_text(element.content) or raw_text)
        if element_type == 'table':
            return bool(raw_text or self._has_table_content(element.content))
        return bool(text_content or raw_text)

    def _formula_text(self, content: Any) -> str:
        if isinstance(content, dict):
            structured = content.get('structured_content')
            if isinstance(structured, dict):
                return self._normalized_text(structured.get('latex') or structured.get('text'))
            return self._normalized_text(content.get('latex') or content.get('text'))
        return self._normalized_text(content)

    def _deduplicate_page_elements(self, elements: list[ExtractedElement]) -> tuple[list[ExtractedElement], int, int]:
        if len(elements) < 2:
            return elements, 0, 0

        original_texts = [self._element_text(element) for element in elements]
        comparable = [self._comparable_text(element) for element in elements]
        drop_indices: set[int] = set()
        insert_before: dict[int, list[ExtractedElement]] = {}
        insert_after: dict[int, list[ExtractedElement]] = {}
        dropped_count = 0
        rewritten_count = 0

        for index, element in enumerate(elements):
            plan = self._overlap_cleanup_plan(elements, original_texts, comparable, index=index)
            if plan is None:
                continue
            drop_indices.add(index)
            dropped_count += 1
            residual = plan["residual"]
            if residual:
                rewritten_count += 1
                rewritten = self._rewrite_text_element(element, residual, source_anchor=str(plan["anchor"]))
                matched_indices = list(plan["matched_indices"])
                if str(plan["anchor"]) == "prefix":
                    target = max(matched_indices)
                    insert_after.setdefault(target, []).append(rewritten)
                else:
                    target = min(matched_indices)
                    insert_before.setdefault(target, []).append(rewritten)

        if not drop_indices:
            return elements, 0, 0

        cleaned: list[ExtractedElement] = []
        for index, element in enumerate(elements):
            cleaned.extend(insert_before.get(index, []))
            if index not in drop_indices:
                cleaned.append(element)
            cleaned.extend(insert_after.get(index, []))

        for order, element in enumerate(cleaned, start=1):
            element.order = order

        return cleaned, dropped_count, rewritten_count

    def _overlap_cleanup_plan(
        self,
        elements: list[ExtractedElement],
        original_texts: list[str],
        comparable: list[str],
        *,
        index: int,
    ) -> dict[str, object] | None:
        element = elements[index]
        if not self._is_textlike(element):
            return None
        candidate = comparable[index]
        original_text = original_texts[index]
        if len(candidate) < 40:
            return None

        matches = self._candidate_matches(elements, comparable, index=index)
        if not matches:
            return None

        options: list[dict[str, object]] = []
        prefix_matches = [match for match in matches if int(match["start"]) == 0]
        if prefix_matches:
            block_end = max(int(match["end"]) for match in matches)
            block_matches = [
                (int(match["start"]), int(match["end"]))
                for match in matches
                if int(match["end"]) <= block_end
            ]
            coverage = self._covered_length(block_matches)
            span_ratio = block_end / len(candidate)
            density = coverage / block_end if block_end else 0.0
            if span_ratio >= 0.35 and density >= 0.45:
                residual = self._prefix_residual(original_text, block_end)
                options.append(
                    {
                        "anchor": "prefix",
                        "residual": residual,
                        "matched_indices": sorted({int(match["other_index"]) for match in matches}),
                        "coverage_ratio": coverage / len(candidate),
                    }
                )

        suffix_matches = [match for match in matches if int(match["end"]) == len(candidate)]
        if suffix_matches:
            block_start = min(int(match["start"]) for match in matches)
            block_matches = [
                (int(match["start"]), int(match["end"]))
                for match in matches
                if int(match["start"]) >= block_start
            ]
            coverage = self._covered_length(block_matches)
            block_length = len(candidate) - block_start
            span_ratio = block_length / len(candidate)
            density = coverage / block_length if block_length else 0.0
            if span_ratio >= 0.35 and density >= 0.45:
                residual = self._suffix_residual(original_text, block_start)
                options.append(
                    {
                        "anchor": "suffix",
                        "residual": residual,
                        "matched_indices": sorted({int(match["other_index"]) for match in matches}),
                        "coverage_ratio": coverage / len(candidate),
                    }
                )

        if not options:
            return None
        options.sort(
            key=lambda option: (
                float(option["coverage_ratio"]),
                1 if not str(option["residual"]).strip() else 0,
            ),
            reverse=True,
        )
        return options[0]

    def _candidate_matches(
        self,
        elements: list[ExtractedElement],
        comparable: list[str],
        *,
        index: int,
    ) -> list[dict[str, int]]:
        candidate = comparable[index]
        element = elements[index]
        matches: list[dict[str, int]] = []
        for other_index, other in enumerate(elements):
            if other_index == index or not self._is_textlike(other):
                continue
            if element.page_number != other.page_number or abs(other.order - element.order) > 3:
                continue
            other_text = comparable[other_index]
            if len(other_text) < 20 or other_text == candidate:
                continue
            start = candidate.find(other_text)
            while start >= 0:
                matches.append(
                    {
                        "start": start,
                        "end": start + len(other_text),
                        "other_index": other_index,
                    }
                )
                start = candidate.find(other_text, start + 1)
        return matches

    def _covered_length(self, spans: list[tuple[int, int]]) -> int:
        if not spans:
            return 0
        total = 0
        current_start, current_end = sorted(spans)[0]
        for start, end in sorted(spans)[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
                continue
            total += current_end - current_start
            current_start, current_end = start, end
        total += current_end - current_start
        return total

    def _prefix_residual(self, text: str, start: int) -> str:
        index = max(0, min(start, len(text)))
        while 0 < index < len(text) and text[index - 1].isalnum() and text[index].isalnum():
            index -= 1
        return self._trim_overlap_residual(text[index:])

    def _suffix_residual(self, text: str, end: int) -> str:
        index = max(0, min(end, len(text)))
        while 0 < index < len(text) and text[index - 1].isalnum() and text[index].isalnum():
            index += 1
        return self._trim_overlap_residual(text[:index])

    def _trim_overlap_residual(self, text: str) -> str:
        return text.strip(" \t\r\n,;:.-")

    def _rewrite_text_element(self, element: ExtractedElement, text: str, *, source_anchor: str) -> ExtractedElement:
        rewritten = replace(element)
        rewritten.content = text
        rewritten.raw_text = text
        rewritten.metadata = {
            **element.metadata,
            "overlap_cleanup": True,
            "overlap_cleanup_anchor": source_anchor,
        }
        return rewritten

    def _has_table_content(self, content: Any) -> bool:
        if not isinstance(content, dict):
            return False
        structured = content.get('structured_content')
        if isinstance(structured, dict):
            headers = structured.get('headers') or []
            rows = structured.get('rows') or []
            markdown = self._normalized_text(structured.get('markdown'))
        else:
            headers = content.get('headers') or []
            rows = content.get('rows') or []
            markdown = self._normalized_text(content.get('markdown'))
        return bool(markdown or any(self._normalized_text(item) for item in headers) or rows)

    def _is_textlike(self, element: ExtractedElement) -> bool:
        return (element.type or "").strip().lower() in {"text", "title"}

    def _comparable_text(self, element: ExtractedElement) -> str:
        return self._element_text(element).casefold()

    def _element_text(self, element: ExtractedElement) -> str:
        return self._normalized_text(element.content) or self._normalized_text(element.raw_text)

    def _normalized_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return " ".join(value.split()).strip()
        if isinstance(value, dict):
            for key in ('raw_text', 'latex', 'text', 'ocr_text', 'markdown', 'literal_description', 'value', 'structured_content'):
                normalized = self._normalized_text(value.get(key))
                if normalized:
                    return normalized
            return ""
        if isinstance(value, list):
            parts = [self._normalized_text(item) for item in value]
            return " ".join(part for part in parts if part).strip()
        return str(value).strip()
