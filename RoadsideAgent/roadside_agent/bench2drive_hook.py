"""Bench2Drive integration hook for RoadsideAgent.

This module keeps the Bench2Drive-side patch small: ScenarioManager only needs
to create the hook, call it once per tick, and destroy it with the scenario.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from .communication import VehicleCommandClient
from .config import RoadsideRuntimeConfig
from .http_server import AdminInstructionStore, create_vehicle_state_server
from .manager import RoadsidePerceptionManager
from .runtime import RoadsideRuntime
from .vehicle_registry import VehicleRegistry


@dataclass
class RoadsideTickRecord:
    """One low-frequency RoadsideAgent execution record."""

    tick_index: int
    result: Dict[str, Any]


class Bench2DriveRoadsideHook:
    """Route-scoped RoadsideAgent runtime for Bench2Drive leaderboard."""

    def __init__(
        self,
        world: Any,
        route_name: str,
        config_root: str | Path,
        warmup_ticks: int = 2,
    ) -> None:
        self.world = world
        self.route_name = str(route_name)
        self.config_root = Path(config_root)
        self.warmup_ticks = int(warmup_ticks)

        self.enabled = False
        self.last_result: Optional[Dict[str, Any]] = None
        self.history: List[RoadsideTickRecord] = []

        self.vehicle_registry = VehicleRegistry()
        self.admin_store = AdminInstructionStore()
        self.perception_manager: Optional[RoadsidePerceptionManager] = None
        self.command_client = VehicleCommandClient()
        self.runtime: Optional[RoadsideRuntime] = None
        self.runtime_config: Optional[RoadsideRuntimeConfig] = None
        self._http_server = None
        self._http_thread: Optional[threading.Thread] = None

    @classmethod
    def create_for_route(
        cls,
        world: Any,
        route_name: str,
        config_root: Optional[str | Path] = None,
    ) -> "Bench2DriveRoadsideHook":
        if config_root is None:
            config_root = Path(__file__).resolve().parents[1] / "config"
        return cls(world=world, route_name=route_name, config_root=config_root)

    def start(self) -> None:
        """Load route-level config and spawn roadside cameras."""
        try:
            self.perception_manager = RoadsidePerceptionManager.from_route_config(
                world=self.world,
                route_name=self.route_name,
                config_root=self.config_root,
            )
        except FileNotFoundError as exc:
            print(f"[RoadsideAgent] disabled: {exc}", flush=True)
            return

        self.perception_manager.spawn_cameras(warmup_ticks=self.warmup_ticks)
        runtime_config_path = self.config_root / "roadside_agent.json"
        self.runtime_config = RoadsideRuntimeConfig.from_path(runtime_config_path)
        self.runtime = RoadsideRuntime(self.runtime_config, command_client=self.command_client)
        self._start_vehicle_state_server()
        self.enabled = True
        print(f"[RoadsideAgent] enabled for {self.route_name}", flush=True)

    def tick(self, tick_index: int) -> None:
        """Run RoadsideAgent on configured low-frequency ticks."""
        if not self.enabled or self.perception_manager is None or self.runtime is None:
            return
        if not self.perception_manager.should_sample(tick_index):
            return

        try:
            self._refresh_registered_vehicle_actors(tick_index)
            perception = self.perception_manager.perceive_targets(
                self.vehicle_registry.active_actor_map(),
            )
            world_snapshot = self.world.get_snapshot()
            timestamp = float(world_snapshot.timestamp.elapsed_seconds)
            admin_instruction = self.admin_store.get_instruction()
            decision = self.runtime.step(
                tick=tick_index,
                timestamp=timestamp,
                route_name=self.route_name,
                scene_description=self.perception_manager.scene_description,
                perception=perception,
                vehicle_registry=self.vehicle_registry,
                admin_instruction=admin_instruction,
            )
            result = {
                "perception": perception,
                "agent_result": None if decision is None else decision.to_dict(),
            }
            self.last_result = result
            self.history.append(RoadsideTickRecord(tick_index=tick_index, result=result))
        except Exception as exc:
            print(f"[RoadsideAgent] tick failed at tick {tick_index}: {exc}", flush=True)

    def destroy(self) -> None:
        """Destroy roadside camera sensors."""
        if self.perception_manager is not None:
            self.perception_manager.destroy()
        self._stop_vehicle_state_server()
        self.enabled = False
        self.perception_manager = None
        self.runtime = None
        self.runtime_config = None

    def _refresh_registered_vehicle_actors(self, tick_index: int) -> None:
        if self.runtime_config is None:
            return

        stale_after = self.runtime_config.server.stale_after_seconds
        self.vehicle_registry.prune_stale_reports(stale_after)
        for vehicle_id in self.vehicle_registry.active_reported_vehicle_ids(stale_after):
            actor = self.world.get_actor(int(vehicle_id))
            if actor is None or not getattr(actor, "is_alive", True):
                continue
            self.vehicle_registry.bind_actor(
                vehicle_id=vehicle_id,
                actor=actor,
                tick_index=tick_index,
            )

    def _start_vehicle_state_server(self) -> None:
        if self.runtime_config is None or not self.runtime_config.server.enabled:
            return
        server_config = self.runtime_config.server
        try:
            self._http_server = create_vehicle_state_server(
                host=server_config.host,
                port=server_config.port,
                vehicle_registry=self.vehicle_registry,
                admin_store=self.admin_store,
            )
        except OSError as exc:
            print(f"[RoadsideAgent] vehicle state server disabled: {exc}", flush=True)
            return
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            daemon=True,
        )
        self._http_thread.start()
        print(
            f"[RoadsideAgent] vehicle state server listening on "
            f"{server_config.host}:{server_config.port}",
            flush=True,
        )

    def _stop_vehicle_state_server(self) -> None:
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=1.0)
            self._http_thread = None
