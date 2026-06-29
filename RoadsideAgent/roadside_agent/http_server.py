from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .vehicle_registry import VehicleRegistry


class AdminInstructionStore:
    """Thread-safe store for the latest admin/operator instruction."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._instruction: str = ""
        self._timestamp: float = 0.0
        self._updated: bool = False

    def set_instruction(self, instruction: str, timestamp: Optional[float] = None) -> None:
        with self._lock:
            self._instruction = str(instruction or "")
            self._timestamp = float(timestamp if timestamp is not None else time.time())
            self._updated = True

    def get_instruction(self) -> dict[str, Any]:
        with self._lock:
            return {
                "instruction": self._instruction,
                "timestamp": self._timestamp,
                "has_instruction": bool(self._instruction),
            }

    def peek_and_clear_updated(self) -> bool:
        with self._lock:
            updated = self._updated
            self._updated = False
            return updated


def create_roadside_http_server(
    host: str,
    port: int,
    vehicle_registry: VehicleRegistry,
    admin_store: Optional[AdminInstructionStore] = None,
) -> ThreadingHTTPServer:
    """Create an HTTP server for vehicle state reports and admin instructions."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == "/vehicles/state":
                self._handle_vehicle_state()
            elif self.path == "/admin/instruction":
                self._handle_admin_instruction()
            else:
                self._write_json(404, {"ok": False, "error": "not found"})

        def do_GET(self) -> None:
            if self.path == "/health":
                self._write_json(200, {"ok": True})
            else:
                self._write_json(404, {"ok": False, "error": "not found"})

        def _handle_vehicle_state(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                vehicle_id = str(payload["vehicle_id"])
                timestamp = float(payload["timestamp"])
                endpoint = payload.get("endpoint")
                upstream = payload.get("upstream") or {}
                task_status = payload.get("task_status", "")
                if not isinstance(upstream, dict):
                    raise ValueError("upstream must be a JSON object")
                if endpoint is not None and not isinstance(endpoint, str):
                    raise ValueError("endpoint must be an ip:port string")
                vehicle_registry.upsert_report(
                    vehicle_id=vehicle_id,
                    timestamp=timestamp,
                    upstream=upstream,
                    task_status=str(task_status or ""),
                    endpoint=endpoint,
                )
            except Exception as exc:
                self._write_json(400, {"ok": False, "error": str(exc)})
                return

            self._write_json(200, {"ok": True, "vehicle_id": vehicle_id})

        def _handle_admin_instruction(self) -> None:
            if admin_store is None:
                self._write_json(404, {"ok": False, "error": "admin endpoint disabled"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                instruction = payload.get("instruction", "")
                if not isinstance(instruction, str):
                    raise ValueError("instruction must be a string")
                timestamp = payload.get("timestamp")
                if timestamp is not None:
                    timestamp = float(timestamp)
                admin_store.set_instruction(instruction, timestamp)
            except Exception as exc:
                self._write_json(400, {"ok": False, "error": str(exc)})
                return

            self._write_json(200, {"ok": True})

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


create_vehicle_state_server = create_roadside_http_server
