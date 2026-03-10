from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from .analyzers import PdfLayoutAnalyzer
from .converters import PptxToPdfConverter
from .extractors import PdfContentExtractor
from .models import ExtractedDocument
from .storage import ExtractionArtifactStore


class DocumentExtractionRouter:
    def __init__(
        self,
        *,
        pdf_analyzer: PdfLayoutAnalyzer | None = None,
        pdf_extractor: PdfContentExtractor | None = None,
        pptx_converter: PptxToPdfConverter | None = None,
        artifact_store: ExtractionArtifactStore | None = None,
    ) -> None:
        self.pdf_analyzer = pdf_analyzer or PdfLayoutAnalyzer()
        self.pdf_extractor = pdf_extractor or PdfContentExtractor()
        self.pptx_converter = pptx_converter or PptxToPdfConverter()
        self.artifact_store = artifact_store

    def extract(self, file_path: str, *, max_pages: int | None = None) -> ExtractedDocument:
        return self._extract(file_path=file_path, max_pages=max_pages, output_dir=None)

    def extract_to_directory(
        self,
        file_path: str,
        output_dir: str | Path,
        *,
        max_pages: int | None = None,
    ) -> Path:
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        document = self._extract(file_path=file_path, max_pages=max_pages, output_dir=output_root)
        store = self.artifact_store or ExtractionArtifactStore(output_root)
        return store.save(document, directory=output_root)

    def _extract(
        self,
        *,
        file_path: str,
        max_pages: int | None,
        output_dir: Path | None,
    ) -> ExtractedDocument:
        source = Path(file_path)
        if not source.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")

        suffix = source.suffix.lower()
        if suffix not in {'.pdf', '.pptx'}:
            raise ValueError(f"Unsupported input file type: {suffix}")

        processed_path = source
        converted_from = None
        conversion_dir: str | None = None

        if suffix == '.pptx':
            conversion_dir = tempfile.mkdtemp(prefix='contextus-ingest-')
            processed_path = Path(self.pptx_converter.convert(str(source), out_dir=conversion_dir))
            converted_from = 'pptx'

        try:
            analyzed_pages = self.pdf_analyzer.analyze(str(processed_path), max_pages=max_pages)
            return self.pdf_extractor.extract(
                str(processed_path),
                analyzed_pages,
                original_source_path=str(source),
                converted_from=converted_from,
                output_dir=output_dir,
            )
        finally:
            if conversion_dir is not None:
                shutil.rmtree(conversion_dir, ignore_errors=True)
