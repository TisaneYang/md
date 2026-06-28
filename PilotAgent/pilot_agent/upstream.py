from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .config import UpstreamConfig
from .types import UpstreamCommand


class UpstreamProvider:
    def get_latest(self) -> Optional[UpstreamCommand]:
        raise NotImplementedError


class NullUpstreamProvider(UpstreamProvider):
    def get_latest(self) -> Optional[UpstreamCommand]:
        return None


class FileUpstreamProvider(UpstreamProvider):
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._last_timestamp: Optional[float] = None

    def get_latest(self) -> Optional[UpstreamCommand]:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        command = UpstreamCommand.from_dict(payload)
        if self._last_timestamp == command.timestamp:
            return None
        self._last_timestamp = command.timestamp
        return command


class HttpPollingUpstreamProvider(UpstreamProvider):
    def __init__(self, url: str, timeout_ms: int = 100) -> None:
        self.url = url
        self.timeout = timeout_ms / 1000.0
        self._last_timestamp: Optional[float] = None

    def get_latest(self) -> Optional[UpstreamCommand]:
        try:
            with urllib.request.urlopen(self.url, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        command = UpstreamCommand.from_dict(payload)
        if self._last_timestamp == command.timestamp:
            return None
        self._last_timestamp = command.timestamp
        return command


class InMemoryUpstreamStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Optional[UpstreamCommand] = None

    def put(self, command: UpstreamCommand) -> None:
        with self._lock:
            self._latest = command

    def get(self) -> Optional[UpstreamCommand]:
        with self._lock:
            return self._latest


class InMemoryHttpUpstreamProvider(UpstreamProvider):
    def __init__(self, store: InMemoryUpstreamStore) -> None:
        self.store = store
        self._last_timestamp: Optional[float] = None

    def get_latest(self) -> Optional[UpstreamCommand]:
        command = self.store.get()
        if command is None or self._last_timestamp == command.timestamp:
            return None
        self._last_timestamp = command.timestamp
        return command


def build_upstream_provider(config: UpstreamConfig) -> UpstreamProvider:
    if config.type == "file" and config.path:
        return FileUpstreamProvider(config.path)
    if config.type == "http_polling" and config.url:
        return HttpPollingUpstreamProvider(config.url, config.timeout_ms)
    return NullUpstreamProvider()


def create_upstream_http_server(
    host: str,
    port: int,
    store: InMemoryUpstreamStore,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/upstream":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                store.put(UpstreamCommand.from_dict(payload))
            except Exception as exc:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8"))
                return

            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path != "/latest":
                self.send_response(404)
                self.end_headers()
                return

            command = store.get()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(None if command is None else command.to_dict()).encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
