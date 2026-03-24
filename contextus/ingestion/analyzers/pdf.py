from __future__ import annotations

import os
from pathlib import Path
import tempfile

from ..layout import DocLayoutModelLoader, DocLayoutRemoteClient, NmsProcessor


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
        remote_client: DocLayoutRemoteClient | None = None,
        remote_api_url: str | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.dpi = dpi
        self.model_loader = model_loader or DocLayoutModelLoader()
        self.remote_client = remote_client
        if self.remote_client is None:
            configured_url = remote_api_url or os.environ.get("CONTEXTUS_DOCLAYOUT_API_URL")
            if configured_url:
                self.remote_client = DocLayoutRemoteClient(endpoint_url=configured_url)
        self._model = None
        self._nms = NmsProcessor()

    def analyze(self, file_path: str, max_pages: int | None = None) -> list[dict]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF analysis.") from exc

        if self.remote_client is not None:
            return self._analyze_remote(file_path=file_path, max_pages=max_pages)

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

    def _analyze_remote(self, file_path: str, max_pages: int | None = None) -> list[dict]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF analysis.") from exc

        response = self.remote_client.analyze(file_path)
        pages_payload = response.get("pages")
        if not isinstance(pages_payload, list):
            raise ValueError("Remote DocLayout response must include a 'pages' list.")

        doc = fitz.open(file_path)
        page_limit = min(len(doc), max_pages) if max_pages is not None else len(doc)
        results: list[dict] = []

        try:
            for page_index in range(page_limit):
                page = doc[page_index]
                payload = pages_payload[page_index] if page_index < len(pages_payload) else []
                detections = self._normalize_remote_page_detections(payload)
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

    def _normalize_remote_page_detections(self, payload) -> list[dict]:
        if isinstance(payload, dict):
            items = payload.get("detections", [])
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        detections: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_label = (
                item.get("raw_type")
                or item.get("type")
                or item.get("label_name")
                or item.get("class_name")
                or item.get("label")
            )
            if isinstance(raw_label, (int, float)):
                raise ValueError(
                    "Remote DocLayout detections must include a string label/type, not only numeric class ids."
                )
            if raw_label is None:
                continue
            raw_label_text = str(raw_label).strip().lower()
            if raw_label_text == "abandon":
                continue

            bbox = item.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            detections.append(
                {
                    "type": self.DETECTION_LABEL_MAP.get(raw_label_text, raw_label_text.replace(" ", "_")),
                    "raw_type": raw_label_text,
                    "bbox": [float(v) for v in bbox],
                    "confidence": float(item.get("confidence", item.get("conf", 0.0))),
                }
            )
        return detections
