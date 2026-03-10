from __future__ import annotations

from pathlib import Path
import tempfile

from ..layout import DocLayoutModelLoader, NmsProcessor


class PdfLayoutAnalyzer:
    DETECTION_LABEL_MAP = {
        "plain text": "text",
        "text": "text",
        "title": "title",
        "table": "table",
        "table_caption": "text",
        "figure": "figure",
        "figure_caption": "text",
        "picture": "image",
        "image": "image",
        "chart": "chart",
        "diagram": "diagram",
        "flowchart": "flowchart",
        "formula": "formula",
        "isolate_formula": "formula",
        "formula_caption": "text",
        "caption": "text",
    }

    def __init__(
        self,
        confidence_threshold: float = 0.40,
        iou_threshold: float = 0.70,
        dpi: int = 250,
        model_loader: DocLayoutModelLoader | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.dpi = dpi
        self.model_loader = model_loader or DocLayoutModelLoader()
        self._model = None
        self._nms = NmsProcessor()

    def analyze(self, file_path: str, max_pages: int | None = None) -> list[dict]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF analysis.") from exc

        if self._model is None:
            self._model = self.model_loader.load()

        doc = fitz.open(file_path)
        page_limit = min(len(doc), max_pages) if max_pages is not None else len(doc)
        results: list[dict] = []

        try:
            for page_index in range(page_limit):
                page = doc[page_index]
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    temp_path = Path(temp_file.name)
                try:
                    pixmap = page.get_pixmap(dpi=self.dpi)
                    pixmap.save(str(temp_path))
                    predictions = self._model.predict(
                        str(temp_path),
                        imgsz=1024,
                        conf=self.confidence_threshold,
                    )
                    detections = self._collect_detections(predictions)
                finally:
                    temp_path.unlink(missing_ok=True)

                detections = self._nms.deduplicate(detections, iou_threshold=self.iou_threshold)
                detections.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
                results.append(
                    {
                        "page_number": page_index + 1,
                        "page_width": float(page.rect.width),
                        "page_height": float(page.rect.height),
                        "rendered_width": int(page.rect.width * self.dpi / 72),
                        "rendered_height": int(page.rect.height * self.dpi / 72),
                        "detections": detections,
                    }
                )
        finally:
            doc.close()

        return results

    def _collect_detections(self, predictions) -> list[dict]:
        if not predictions:
            return []
        page = predictions[0]
        boxes = getattr(page, "boxes", None)
        if boxes is None:
            return []

        names = getattr(page, "names", {})
        detections: list[dict] = []
        for index in range(len(boxes)):
            class_id = int(boxes.cls[index])
            raw_label = str(names[class_id]).strip().lower()
            if raw_label == "abandon":
                continue
            detections.append(
                {
                    "type": self.DETECTION_LABEL_MAP.get(raw_label, raw_label.replace(" ", "_")),
                    "raw_type": raw_label,
                    "bbox": [float(v) for v in boxes.xyxy[index].tolist()],
                    "confidence": float(boxes.conf[index]),
                }
            )
        return detections
