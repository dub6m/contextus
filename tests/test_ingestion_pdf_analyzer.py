from __future__ import annotations

from pathlib import Path

import fitz

from contextus.ingestion.analyzers.pdf import PdfLayoutAnalyzer


class FakeRemoteClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def analyze(self, file_path: str):
        self.calls.append(file_path)
        return self.response


def _write_sample_pdf(path: Path, pages: int = 1) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {index + 1}")
    doc.save(path)
    doc.close()


def test_pdf_layout_analyzer_can_use_remote_client(tmp_path):
    source = tmp_path / "sample.pdf"
    _write_sample_pdf(source, pages=2)
    remote = FakeRemoteClient(
        {
            "pages": [
                [
                    {
                        "label": "title",
                        "conf": 0.91,
                        "bbox": [10, 20, 100, 80],
                    },
                    {
                        "label": "isolate_formula",
                        "conf": 0.88,
                        "bbox": [50, 100, 160, 150],
                    },
                ],
                {
                    "detections": [
                        {
                            "type": "table",
                            "confidence": 0.73,
                            "bbox": [30, 40, 200, 260],
                        }
                    ]
                },
            ]
        }
    )
    analyzer = PdfLayoutAnalyzer(remote_client=remote)

    pages = analyzer.analyze(str(source))

    assert remote.calls == [str(source)]
    assert [page["page_number"] for page in pages] == [1, 2]
    assert [item["type"] for item in pages[0]["detections"]] == ["title", "formula"]
    assert pages[1]["detections"][0]["type"] == "table"
    assert pages[0]["page_width"] == 595.0
    assert pages[0]["page_height"] == 842.0


def test_pdf_layout_analyzer_remote_client_requires_string_labels(tmp_path):
    source = tmp_path / "sample.pdf"
    _write_sample_pdf(source, pages=1)
    remote = FakeRemoteClient({"pages": [[{"label": 3, "bbox": [1, 2, 3, 4], "conf": 0.9}]]})
    analyzer = PdfLayoutAnalyzer(remote_client=remote)

    try:
        analyzer.analyze(str(source))
    except ValueError as exc:
        assert "string label/type" in str(exc)
    else:  # pragma: no cover - safety assertion
        raise AssertionError("Expected remote analyzer to reject numeric-only labels.")
