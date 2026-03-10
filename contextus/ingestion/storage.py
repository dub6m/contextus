from __future__ import annotations

from pathlib import Path
import re

from .models import ExtractedDocument


class ExtractionArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, document: ExtractedDocument, directory: str | Path | None = None) -> Path:
        target_dir = Path(directory) if directory is not None else self.root / self._slug(document.stem)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{self._slug(document.stem)}.extraction.json"
        path.write_text(document.to_json(indent=2), encoding="utf-8")
        return path

    def load(self, path: str | Path) -> ExtractedDocument:
        payload = Path(path).read_text(encoding="utf-8")
        return ExtractedDocument.from_json(payload)

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower()
        return slug or "extraction"
