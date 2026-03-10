from __future__ import annotations

from pathlib import Path
from typing import Optional
import os
import subprocess
import tempfile


class PptxToPdfConverter:
    def __init__(self, prefer: str = "auto") -> None:
        self.prefer = prefer

    def convert(self, pptx_path: str, out_dir: str | None = None) -> str:
        src = Path(pptx_path)
        if not src.exists():
            raise RuntimeError(f"Source file was not found: {pptx_path}")

        output_dir = Path(out_dir) if out_dir is not None else Path(tempfile.gettempdir())
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / f"{src.stem}.pdf"

        if pdf_path.exists() and pdf_path.stat().st_mtime >= src.stat().st_mtime:
            return str(pdf_path)

        engine = self._choose_engine()
        ok = False
        last_error: Optional[str] = None

        if engine == "powerpoint":
            try:
                self._convert_with_powerpoint(str(src), str(pdf_path))
                ok = pdf_path.exists()
            except Exception as exc:
                last_error = f"PowerPoint export failed: {exc}"

        if not ok:
            try:
                self._convert_with_libreoffice(str(src), str(pdf_path))
                ok = pdf_path.exists()
            except Exception as exc:
                last_error = f"LibreOffice export failed: {exc}"

        if not ok:
            raise RuntimeError(last_error or "PPTX to PDF conversion failed.")
        return str(pdf_path)

    def _choose_engine(self) -> str:
        if self.prefer in {"powerpoint", "libreoffice"}:
            return self.prefer
        if os.name == "nt":
            return "powerpoint"
        return "libreoffice"

    def _convert_with_powerpoint(self, src: str, dst: str) -> None:
        if os.name != "nt":
            raise RuntimeError("PowerPoint automation requires Windows.")
        try:
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RuntimeError("win32com is required for PowerPoint automation.") from exc

        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        powerpoint.Visible = 1
        try:
            presentation = powerpoint.Presentations.Open(src, WithWindow=False)
            presentation.SaveAs(dst, 32)
            presentation.Close()
        finally:
            try:
                powerpoint.Quit()
            except Exception:
                pass

    def _convert_with_libreoffice(self, src: str, dst: str) -> None:
        out_dir = str(Path(dst).parent)
        command = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            src,
            "--outdir",
            out_dir,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "LibreOffice conversion failed.")
