# Vast DocLayout API Contract

`Contextus` can offload PDF layout detection to a remote DocLayout service by setting:

```env
CONTEXTUS_DOCLAYOUT_API_URL=http://<vast-host>:8000/analyze
```

The local analyzer expects the remote service to return JSON shaped like:

```json
{
  "pages": [
    [
      {
        "type": "title",
        "bbox": [10.0, 20.0, 100.0, 80.0],
        "confidence": 0.91
      },
      {
        "type": "isolate_formula",
        "bbox": [50.0, 100.0, 160.0, 150.0],
        "confidence": 0.88
      }
    ],
    {
      "detections": [
        {
          "type": "table",
          "bbox": [30.0, 40.0, 200.0, 260.0],
          "confidence": 0.73
        }
      ]
    }
  ]
}
```

Accepted detection keys:

- `type` or `raw_type` or `label`
- `bbox`
- `confidence` or `conf`

Important rules:

- Labels must be strings, not numeric class ids.
- `bbox` must be `[x0, y0, x1, y1]` in rendered image coordinates.
- The `pages` list must be in document order.
- The local analyzer will map these raw labels:
  - `plain text` -> `text`
  - `title` -> `title`
  - `table` -> `table`
  - `figure` -> `figure`
  - `picture` or `image` -> `image`
  - `chart` -> `chart`
  - `diagram` -> `diagram`
  - `flowchart` -> `flowchart`
  - `formula` or `isolate_formula` -> `formula`
  - `caption`, `figure_caption`, `formula_caption`, `table_caption` -> `text`
- `abandon` detections are ignored.

## Drop-in FastAPI Example

This example returns the shape `Contextus` now accepts.

```python
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import fitz
from fastapi import FastAPI, File, UploadFile
from doclayout_yolo import YOLOv10


app = FastAPI()

MODEL = YOLOv10("doclayout_yolo_docstructbench_imgsz1024.pt")


def _parse_prediction(prediction) -> list[dict]:
    boxes = getattr(prediction, "boxes", None)
    names = getattr(prediction, "names", {})
    if boxes is None:
        return []

    detections: list[dict] = []
    for index in range(len(boxes)):
        class_id = int(boxes.cls[index])
        label = str(names[class_id]).strip().lower()
        if label == "abandon":
            continue
        detections.append(
            {
                "type": label,
                "bbox": [float(value) for value in boxes.xyxy[index].tolist()],
                "confidence": float(boxes.conf[index]),
            }
        )
    return detections


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)) -> dict[str, object]:
    suffix = Path(file.filename or "upload.pdf").suffix.lower() or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = Path(tmp.name)

    pages: list[list[dict]] = []
    try:
        if suffix == ".pdf":
            doc = fitz.open(temp_path)
            try:
                for page in doc:
                    pix = page.get_pixmap(dpi=250)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as page_tmp:
                        page_path = Path(page_tmp.name)
                    try:
                        pix.save(str(page_path))
                        prediction = MODEL.predict(str(page_path), imgsz=1024, conf=0.40)[0]
                    finally:
                        page_path.unlink(missing_ok=True)
                    pages.append(_parse_prediction(prediction))
            finally:
                doc.close()
        else:
            prediction = MODEL.predict(str(temp_path), imgsz=1024, conf=0.40)[0]
            pages.append(_parse_prediction(prediction))
    finally:
        temp_path.unlink(missing_ok=True)

    return {"pages": pages}
```

## Local End-to-End Test

After the Vast service is running:

```env
CONTEXTUS_DOCLAYOUT_API_URL=http://<vast-host>:8000/analyze
OPENAI_API_KEY=...
```

Then run:

```bash
.venv\Scripts\python.exe .\extract.py --file .\contextus\input\closest-pair.pdf --outdir .\extractions\closest-pair-remote
```

If the remote layout path is active, `Contextus` will keep the rest of the extraction local and only offload layout detection to your Vast GPU.
