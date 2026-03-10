from __future__ import annotations

from pathlib import Path


class DocLayoutModelLoader:
    def __init__(
        self,
        repo_id: str = "juliozhao/DocLayout-YOLO-DocStructBench",
        local_dir: str | Path = "./models/DocLayout-YOLO-DocStructBench",
    ) -> None:
        self.repo_id = repo_id
        self.local_dir = Path(local_dir)

    def load(self):
        try:
            from doclayout_yolo import YOLOv10
        except ImportError as exc:
            raise RuntimeError(
                "doclayout_yolo is required for PDF layout analysis. Install the model package first."
            ) from exc

        weights = self._find_local_weights()
        if weights is None:
            try:
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise RuntimeError(
                    "huggingface_hub is required to download DocLayout model weights."
                ) from exc
            model_dir = Path(snapshot_download(repo_id=self.repo_id, local_dir=str(self.local_dir)))
            weights = self._find_weights_in(model_dir)

        if weights is None:
            raise FileNotFoundError("No DocLayout model weights were found.")
        return YOLOv10(str(weights))

    def _find_local_weights(self) -> Path | None:
        return self._find_weights_in(self.local_dir)

    def _find_weights_in(self, directory: str | Path) -> Path | None:
        path = Path(directory)
        if not path.exists():
            return None
        for candidate in path.iterdir():
            if candidate.suffix == ".pt":
                return candidate
        return None
