from __future__ import annotations

import threading
from typing import Any, Optional

from .cloud_vlm_client import build_cloud_vlm_client
from .config import PilotConfig
from .context import PilotContext
from .logger import PilotLogger
from .path_mapping import is_path_action_allowed, path_to_ego_fut_cmd
from .types import PilotDecision, UpstreamCommand
from .upstream import (
    InMemoryHttpUpstreamProvider,
    InMemoryUpstreamStore,
    build_upstream_provider,
    create_upstream_http_server,
)


class PilotRuntime:
    def __init__(self, config: PilotConfig) -> None:
        self.config = config
        self.enabled = config.enabled
        self.agent_interval_ticks = max(1, config.agent_interval_ticks)
        self._http_server = None
        if config.upstream.type == "http_push":
            store = InMemoryUpstreamStore()
            self.upstream_provider = InMemoryHttpUpstreamProvider(store)
            self._http_server = create_upstream_http_server(
                config.upstream.host, config.upstream.port, store
            )
            t = threading.Thread(target=self._http_server.serve_forever, daemon=True)
            t.start()
        else:
            self.upstream_provider = build_upstream_provider(config.upstream)
        self.cloud_client = build_cloud_vlm_client(config.cloud)
        self.context = PilotContext(
            window_size=config.context.window_size,
            save_images_in_context=config.context.save_images_in_context,
            save_environment_summary=config.context.save_environment_summary,
            image_jpeg_quality=config.context.image_jpeg_quality,
        )
        self.logger = PilotLogger(config.logging.path, config.logging.enabled)
        self.current_upstream: Optional[UpstreamCommand] = None
        self.last_decision: Optional[PilotDecision] = None
        self.last_error: Optional[str] = None

    @classmethod
    def from_config(cls, path: Optional[str]) -> "PilotRuntime":
        return cls(PilotConfig.from_path(path))

    def should_request_decision(self, tick: int) -> bool:
        return tick % self.agent_interval_ticks == 0

    def step(
        self,
        tick: int,
        timestamp: float,
        images: dict[str, Any],
        ego_speed_mps: float,
        vehicle_position: Optional[dict[str, Any]] = None,
    ) -> Optional[PilotDecision]:
        self.last_error = None
        if not self.enabled:
            return None

        if not self.should_request_decision(tick):
            return self.last_decision

        new_upstream = self.upstream_provider.get_latest()
        if new_upstream is not None:
            self.current_upstream = new_upstream

        if self.current_upstream is None:
            return self.last_decision

        try:
            decision = self.cloud_client.decide(
                upstream=self.current_upstream,
                images=images,
                ego_speed_mps=ego_speed_mps,
                vehicle_position=vehicle_position or {},
                context=self.context.snapshot(),
            )
        except Exception as exc:
            self.last_error = str(exc)
            self.logger.log_tick(
                tick=tick,
                timestamp=timestamp,
                upstream=self.current_upstream,
                decision=None,
                fallback_reason=self.last_error,
            )
            return self.last_decision

        self.last_decision = decision
        self.context.append(
            upstream=self.current_upstream,
            decision=decision,
            vehicle_position=vehicle_position or {},
            images=images if self.config.context.save_images_in_context else None,
        )
        return decision

    def set_upstream(self, command: UpstreamCommand) -> None:
        self.current_upstream = command

    def path_to_ego_fut_cmd(self, path_action: str):
        return path_to_ego_fut_cmd(path_action)

    def is_path_action_allowed(self, path_action: str, vehicle_position: dict[str, Any]) -> bool:
        return is_path_action_allowed(path_action, vehicle_position)

    def model_control(self, decision: Optional[PilotDecision], ego_speed_mps: float) -> Optional[dict[str, Any]]:
        if decision is None:
            return None
        return decision.to_model_control(ego_speed_mps)

    def log_tick(
        self,
        tick: int,
        timestamp: float,
        upstream: Optional[UpstreamCommand],
        decision: Optional[PilotDecision],
        model_debug: Optional[dict[str, Any]] = None,
    ) -> None:
        self.logger.log_tick(
            tick=tick,
            timestamp=timestamp,
            upstream=upstream,
            decision=decision,
            model_debug=model_debug,
            fallback_reason=self.last_error,
        )
