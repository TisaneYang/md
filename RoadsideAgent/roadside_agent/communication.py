"""Vehicle communication interface for roadside-issued commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib import error, request


@dataclass(frozen=True)
class VehicleEndpoint:
    """Temporary vehicle communication address."""

    host: str
    port: int
    path: str = "/upstream"

    @classmethod
    def from_address(cls, address: str, path: str = "/upstream") -> "VehicleEndpoint":
        """Parse an ``ip:port`` style address."""
        host, port_text = address.rsplit(":", 1)
        return cls(host=host, port=int(port_text), path=path)

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        normalized_path = self.path if self.path.startswith("/") else f"/{self.path}"
        return f"http://{self.address}{normalized_path}"


@dataclass(frozen=True)
class SendResult:
    """Result of one vehicle command send attempt."""

    vehicle_id: str
    endpoint: VehicleEndpoint
    ok: bool
    status_code: Optional[int] = None
    response_body: str = ""
    error: str = ""


class VehicleCommandClient:
    """Send roadside commands to vehicles by vehicle id."""

    def __init__(
        self,
        endpoints: Optional[Mapping[str, VehicleEndpoint | str]] = None,
        timeout_seconds: float = 1.0,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self._endpoints: dict[str, VehicleEndpoint] = {}
        for vehicle_id, endpoint in (endpoints or {}).items():
            self.register_endpoint(vehicle_id, endpoint)

    def register_endpoint(self, vehicle_id: str, endpoint: VehicleEndpoint | str) -> None:
        """Register or update one vehicle communication endpoint."""
        if isinstance(endpoint, str):
            endpoint = VehicleEndpoint.from_address(endpoint)
        self._endpoints[str(vehicle_id)] = endpoint

    def remove_endpoint(self, vehicle_id: str) -> None:
        self._endpoints.pop(str(vehicle_id), None)

    def get_endpoint(self, vehicle_id: str) -> Optional[VehicleEndpoint]:
        return self._endpoints.get(str(vehicle_id))

    def send_message(self, vehicle_id: str, message: Mapping[str, Any] | str) -> SendResult:
        """Send a roadside command/message to the vehicle mapped by ``vehicle_id``."""
        resolved_vehicle_id = str(vehicle_id)
        endpoint = self.get_endpoint(resolved_vehicle_id)
        if endpoint is None:
            return SendResult(
                vehicle_id=resolved_vehicle_id,
                endpoint=VehicleEndpoint(host="", port=0),
                ok=False,
                error=f"no endpoint registered for vehicle {resolved_vehicle_id}",
            )

        import time as _time
        if isinstance(message, str):
            payload = {
                "timestamp": _time.time(),
                "instruction": message,
                "roadside_message": message,
                "source": "roadside",
                "vehicle_id": resolved_vehicle_id,
            }
        else:
            payload = dict(message)
            payload.setdefault("timestamp", _time.time())
            payload.setdefault("source", "roadside")
            payload.setdefault("vehicle_id", resolved_vehicle_id)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            endpoint.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = int(response.status)
                return SendResult(
                    vehicle_id=resolved_vehicle_id,
                    endpoint=endpoint,
                    ok=200 <= status_code < 300,
                    status_code=status_code,
                    response_body=body,
                )
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return SendResult(
                vehicle_id=resolved_vehicle_id,
                endpoint=endpoint,
                ok=False,
                status_code=exc.code,
                response_body=body,
                error=str(exc),
            )
        except Exception as exc:
            return SendResult(
                vehicle_id=resolved_vehicle_id,
                endpoint=endpoint,
                ok=False,
                error=str(exc),
            )
