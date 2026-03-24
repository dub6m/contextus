from __future__ import annotations

from pathlib import Path
import json
import mimetypes
import os
from urllib import request


class DocLayoutRemoteClient:
    def __init__(
        self,
        endpoint_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.endpoint_url = (
            endpoint_url
            or os.environ.get("CONTEXTUS_DOCLAYOUT_API_URL")
            or ""
        ).strip()
        if not self.endpoint_url:
            raise ValueError("A remote DocLayout endpoint URL is required.")
        self.api_key = api_key or os.environ.get("CONTEXTUS_DOCLAYOUT_API_KEY")
        timeout_value = timeout_seconds
        if timeout_value is None:
            timeout_value = os.environ.get("CONTEXTUS_DOCLAYOUT_TIMEOUT_SECONDS") or "600"
        self.timeout_seconds = float(timeout_value)

    def analyze(self, file_path: str | Path) -> dict[str, object]:
        source = Path(file_path)
        boundary = "----contextus-doclayout-boundary"
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        file_bytes = source.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(
            self.endpoint_url,
            data=body,
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Remote DocLayout response must be a JSON object.")
        return data
