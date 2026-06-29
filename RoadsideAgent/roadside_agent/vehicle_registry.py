"""Vehicle id to CARLA actor/state registry for batched RoadsideAgent input."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
import time
from typing import Any, Dict, Iterable, Mapping, Optional

from .communication import VehicleEndpoint


@dataclass
class VehicleRecord:
    """Latest known state for one vehicle."""

    vehicle_id: str
    actor: Optional[Any] = None
    state: Dict[str, Any] = field(default_factory=dict)
    endpoint: Optional[VehicleEndpoint] = None
    last_seen_tick: Optional[int] = None
    last_report_timestamp: Optional[float] = None
    last_report_monotonic: Optional[float] = None


class VehicleRegistry:
    """Maintain the mapping from stable vehicle id to actor and summary state."""

    def __init__(self) -> None:
        self._records: Dict[str, VehicleRecord] = {}
        self._lock = RLock()

    def upsert(
        self,
        vehicle_id: str,
        actor: Any,
        state: Optional[Mapping[str, Any]] = None,
        endpoint: Optional[VehicleEndpoint | str] = None,
        tick_index: Optional[int] = None,
    ) -> VehicleRecord:
        parsed_endpoint = VehicleEndpoint.from_address(endpoint) if isinstance(endpoint, str) else endpoint
        with self._lock:
            record = self._records.get(str(vehicle_id))
            if record is None:
                record = VehicleRecord(vehicle_id=str(vehicle_id))
                self._records[record.vehicle_id] = record
            record.actor = actor
            record.state = dict(state or {})
            if parsed_endpoint is not None:
                record.endpoint = parsed_endpoint
            record.last_seen_tick = tick_index
            return record

    def upsert_actor(
        self,
        actor: Any,
        state: Optional[Mapping[str, Any]] = None,
        endpoint: Optional[VehicleEndpoint | str] = None,
        tick_index: Optional[int] = None,
    ) -> VehicleRecord:
        """Register a CARLA actor using actor.id as the stable vehicle id."""
        return self.upsert(
            vehicle_id=str(actor.id),
            actor=actor,
            state=state,
            endpoint=endpoint,
            tick_index=tick_index,
        )

    def upsert_report(
        self,
        vehicle_id: str,
        timestamp: float,
        upstream: Optional[Mapping[str, Any]] = None,
        task_status: str = "",
        endpoint: Optional[VehicleEndpoint | str] = None,
    ) -> VehicleRecord:
        """Register one vehicle that actively reported roadside interaction state."""
        parsed_endpoint = VehicleEndpoint.from_address(endpoint) if isinstance(endpoint, str) else endpoint
        state = {
            "timestamp": float(timestamp),
            "upstream": dict(upstream or {}),
            "task_status": str(task_status or ""),
        }
        with self._lock:
            record = self._records.get(str(vehicle_id))
            if record is None:
                record = VehicleRecord(vehicle_id=str(vehicle_id))
                self._records[record.vehicle_id] = record
            record.state = state
            if parsed_endpoint is not None:
                record.endpoint = parsed_endpoint
            record.last_report_timestamp = float(timestamp)
            record.last_report_monotonic = time.monotonic()
            return record

    def bind_actor(
        self,
        vehicle_id: str,
        actor: Any,
        tick_index: Optional[int] = None,
    ) -> Optional[VehicleRecord]:
        """Bind a reported vehicle id to the current CARLA actor object."""
        with self._lock:
            record = self._records.get(str(vehicle_id))
            if record is None:
                return None
            record.actor = actor
            record.last_seen_tick = tick_index
            return record

    def update_endpoint(self, vehicle_id: str, endpoint: VehicleEndpoint | str) -> VehicleRecord:
        """Update the communication endpoint for an existing vehicle."""
        with self._lock:
            record = self._records[str(vehicle_id)]
            record.endpoint = VehicleEndpoint.from_address(endpoint) if isinstance(endpoint, str) else endpoint
            return record

    def endpoint_map(self) -> Dict[str, VehicleEndpoint]:
        """Return id-to-endpoint map for command clients."""
        with self._lock:
            return {
                vehicle_id: record.endpoint
                for vehicle_id, record in self._records.items()
                if record.endpoint is not None
            }

    def remove(self, vehicle_id: str) -> None:
        with self._lock:
            self._records.pop(str(vehicle_id), None)

    def get(self, vehicle_id: str) -> Optional[VehicleRecord]:
        with self._lock:
            return self._records.get(str(vehicle_id))

    def active_actor_map(self) -> Dict[str, Any]:
        """Return id-to-actor map for batch perception."""
        with self._lock:
            return {
                vehicle_id: record.actor
                for vehicle_id, record in self._records.items()
                if record.actor is not None and getattr(record.actor, "is_alive", True)
            }

    def active_reported_vehicle_ids(self, stale_after_seconds: Optional[float]) -> list[str]:
        """Return vehicle ids that have reported state recently."""
        now = time.monotonic()
        with self._lock:
            vehicle_ids = []
            for vehicle_id, record in self._records.items():
                if record.last_report_monotonic is None:
                    continue
                if stale_after_seconds is not None and now - record.last_report_monotonic > stale_after_seconds:
                    continue
                vehicle_ids.append(vehicle_id)
            return sorted(vehicle_ids, key=str)

    def prune_stale_reports(self, stale_after_seconds: Optional[float]) -> None:
        if stale_after_seconds is None:
            return
        now = time.monotonic()
        with self._lock:
            stale_ids = [
                vehicle_id
                for vehicle_id, record in self._records.items()
                if record.last_report_monotonic is not None
                and now - record.last_report_monotonic > stale_after_seconds
            ]
            for vehicle_id in stale_ids:
                self._records.pop(vehicle_id, None)

    def records(self) -> Iterable[VehicleRecord]:
        with self._lock:
            return list(self._records.values())
