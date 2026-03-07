from __future__ import annotations

import json
from pathlib import Path

from .graph import Graph


class GraphStore:
    """
    Manages persistent storage of Graph objects as JSON files.
    Each graph is stored as one file: {storage_dir}/{graph.name}.json

    File names are derived directly from graph.name — no slugification or
    sanitisation. Graph names are assumed to be valid filenames by the caller.

    Parameters
    ----------
    storage_dir : str | Path
        Directory where graph JSON files are stored.
        Created automatically (including any missing parents) if it does not
        exist.
    """

    def __init__(self, storage_dir: str | Path) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}.json"

    # ------------------------------------------------------------------
    # Single-graph operations
    # ------------------------------------------------------------------

    def save(self, graph: Graph) -> Path:
        """
        Serialise graph to JSON and write to storage_dir/{graph.name}.json.
        Overwrites if the file already exists.
        Returns the path written to.
        """
        path = self._path(graph.name)
        path.write_text(graph.to_json(indent=2), encoding="utf-8")
        return path

    def load(self, name: str) -> Graph:
        """
        Load and deserialise a graph by name.
        Raises FileNotFoundError if the graph file does not exist.
        """
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(
                f"No graph named '{name}' found in {self._dir}. "
                f"Expected file: {path}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return Graph.from_dict(data)

    def exists(self, name: str) -> bool:
        """Returns True if a graph with the given name exists in storage."""
        return self._path(name).exists()

    def delete(self, name: str) -> None:
        """
        Delete a graph file by name.
        Raises FileNotFoundError if the graph does not exist.
        """
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(
                f"No graph named '{name}' found in {self._dir}. "
                f"Expected file: {path}"
            )
        path.unlink()

    def list_graphs(self) -> list[str]:
        """
        Returns all graph names currently in storage, sorted alphabetically.
        Names are returned without the .json extension.
        """
        return sorted(p.stem for p in self._dir.glob("*.json"))

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def save_all(self, graphs: list[Graph]) -> list[Path]:
        """
        Save multiple graphs in one call.
        Returns the list of paths written, in the same order as the input.
        """
        return [self.save(g) for g in graphs]

    def load_all(self) -> list[Graph]:
        """
        Load all graphs currently in storage, sorted by name.
        Raises if any file is malformed — does not silently skip.
        """
        return [self.load(name) for name in self.list_graphs()]
