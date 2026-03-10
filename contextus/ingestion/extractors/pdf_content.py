from __future__ import annotations

from pathlib import Path

from ..handlers import FigureHandler, FormulaHandler, TableHandler, TextHandler
from ..models import ExtractedDocument, ExtractedElement, ExtractedPage


class PdfContentExtractor:
    FIGURE_TYPES = {"figure", "image", "chart", "diagram", "flowchart"}

    def __init__(self) -> None:
        self.text_handler = TextHandler()
        self.table_handler = TableHandler()
        self.formula_handler = FormulaHandler()
        self.figure_handler = FigureHandler()

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

                elements: list[ExtractedElement] = []
                detections = sorted(
                    page_data.get('detections', []),
                    key=lambda item: (item['bbox'][1], item['bbox'][0]),
                )
                for order, detection in enumerate(detections, start=1):
                    element_type = str(detection['type']).strip().lower()
                    bbox = tuple(float(v) for v in detection['bbox'])
                    output = self._handle_detection(page, element_type, bbox, scale_x, scale_y)

                    element = ExtractedElement(
                        type=element_type,
                        page_number=page_number,
                        order=order,
                        bbox=bbox,
                        confidence=detection.get('confidence'),
                        content=output.content,
                        raw_text=output.raw_text,
                        source=output.source,
                        metadata={
                            **output.metadata,
                            'raw_detection_type': detection.get('raw_type', element_type),
                        },
                    )
                    if asset_dir is not None and output.asset_bytes is not None:
                        asset_name = f"page-{page_number:04d}-{order:04d}-{element.type}{output.asset_extension or ''}"
                        asset_path = asset_dir / asset_name
                        asset_path.write_bytes(output.asset_bytes)
                        element.asset_path = str(asset_path.relative_to(asset_dir.parent))

                    elements.append(element)

                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        width=page_width,
                        height=page_height,
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
            },
            pages=pages,
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
