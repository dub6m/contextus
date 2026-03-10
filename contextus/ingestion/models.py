from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid


BBox = tuple[float, float, float, float]


@dataclass
class ExtractedElement:
    type: str
    page_number: int
    order: int
    bbox: BBox
    confidence: float | None = None
    content: Any = None
    raw_text: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    asset_path: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedElement:
        bbox = tuple(float(v) for v in data["bbox"])
        if len(bbox) != 4:
            raise ValueError("bbox must contain four numeric values.")
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data["type"],
            page_number=int(data["page_number"]),
            order=int(data["order"]),
            bbox=bbox,
            confidence=data.get("confidence"),
            content=data.get("content"),
            raw_text=data.get("raw_text", ""),
            source=data.get("source", ""),
            metadata=data.get("metadata", {}),
            asset_path=data.get("asset_path"),
        )


@dataclass
class ExtractedPage:
    page_number: int
    width: float
    height: float
    elements: list[ExtractedElement] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "elements": [element.to_dict() for element in self.elements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedPage:
        return cls(
            page_number=int(data["page_number"]),
            width=float(data["width"]),
            height=float(data["height"]),
            elements=[ExtractedElement.from_dict(item) for item in data.get("elements", [])],
        )


@dataclass
class ExtractedDocument:
    source_name: str
    source_path: str
    source_type: str
    pages: list[ExtractedPage]
    processed_path: str | None = None
    converted_from: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "processed_path": self.processed_path,
            "converted_from": self.converted_from,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "page_count": len(self.pages),
            "pages": [page.to_dict() for page in self.pages],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @property
    def stem(self) -> str:
        return Path(self.source_name).stem

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedDocument:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            source_name=data["source_name"],
            source_path=data["source_path"],
            source_type=data["source_type"],
            processed_path=data.get("processed_path"),
            converted_from=data.get("converted_from"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            metadata=data.get("metadata", {}),
            pages=[ExtractedPage.from_dict(item) for item in data.get("pages", [])],
        )

    @classmethod
    def from_json(cls, payload: str) -> ExtractedDocument:
        return cls.from_dict(json.loads(payload))
