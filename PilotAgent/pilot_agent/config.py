from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class UpstreamConfig:
    type: str = "file"
    path: Optional[str] = None
    url: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 8765
    timeout_ms: int = 100


@dataclass
class CloudConfig:
    provider: str = "disabled"
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    model: Optional[str] = None
    timeout_ms: int = 800
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextConfig:
    window_size: int = 8
    save_images_in_context: bool = False
    save_environment_summary: bool = True
    image_jpeg_quality: int = 70


@dataclass
class LoggingConfig:
    path: str = "./pilot_logs/pilot_decisions.jsonl"
    enabled: bool = True


@dataclass
class PilotConfig:
    enabled: bool = False
    agent_interval_ticks: int = 10
    upstream: UpstreamConfig = field(default_factory=UpstreamConfig)
    cloud: CloudConfig = field(default_factory=CloudConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_path(cls, path: Optional[str]) -> "PilotConfig":
        if not path:
            return cls()

        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Pilot config does not exist: {config_path}")

        text = config_path.read_text(encoding="utf-8")
        if config_path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("PyYAML is required for YAML pilot config files") from exc
            raw = yaml.safe_load(text) or {}
        else:
            raw = json.loads(text)

        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PilotConfig":
        upstream = UpstreamConfig(**raw.get("upstream", {}))
        cloud_raw = raw.get("cloud", {})
        context = ContextConfig(**raw.get("context", {}))
        logging = LoggingConfig(**raw.get("logging", {}))
        return cls(
            enabled=bool(raw.get("enabled", False)),
            agent_interval_ticks=int(raw.get("agent_interval_ticks", 10)),
            upstream=upstream,
            cloud=CloudConfig(**cloud_raw),
            context=context,
            logging=logging,
        )

