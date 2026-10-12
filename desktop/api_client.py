import json
from typing import Any, Dict, Iterator, Optional, Tuple

import requests

from desktop import config_loader


class ApiError(Exception):
    pass


class BocareApiClient:
    """Thin HTTP client for the BoCare backend. Timeouts come from desktop/config/settings.yml."""

    def __init__(self, base_url: str, timeout: Optional[float] = None):
        settings = config_loader.settings()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.request_timeout_seconds
        self.connect_timeout = settings.connect_timeout_seconds

    def chat(self, message: str, language: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {"message": message, "language": language, "session_id": session_id}
        return self._request("POST", "/chat", json=payload)

    def chat_stream(self, message: str, language: str,
                    session_id: Optional[str] = None) -> Iterator[Tuple[str, Any]]:
        """Yield (event, data) from POST /chat/stream: "triage", "sources", "status", then "done"."""
        payload = {"message": message, "language": language, "session_id": session_id}
        try:
            with requests.post(self.base_url + "/chat/stream", json=payload, stream=True,
                               timeout=(self.connect_timeout, self.timeout)) as response:
                if response.status_code != 200:
                    raise ApiError(f"BoCare API returned {response.status_code}: {response.text[:200]}")
                event, data = None, []
                for line in response.iter_lines(decode_unicode=True):
                    if line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: "):
                        data.append(line[6:])
                    elif not line and event:
                        yield event, json.loads("\n".join(data))
                        event, data = None, []
        except requests.RequestException as exc:
            raise ApiError(f"Cannot reach the BoCare API at {self.base_url} ({exc.__class__.__name__}).") from exc

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        try:
            response = requests.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ApiError(f"Cannot reach the BoCare API at {self.base_url} ({exc.__class__.__name__}).") from exc
        if response.status_code != 200:
            raise ApiError(f"BoCare API returned {response.status_code}: {response.text[:200]}")
        return response.json()
