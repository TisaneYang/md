from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class CloudConfig:
    provider: str = "disabled"
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    model: Optional[str] = None
    timeout_ms: int = 1200
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextConfig:
    window_size: int = 8
    save_images_in_context: bool = False


@dataclass
class LoggingConfig:
    path: str = "./roadside_logs/roadside_decisions.jsonl"
    enabled: bool = True


@dataclass
class ServerConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8890
    stale_after_seconds: float = 2.0


@dataclass
class RoadsideRuntimeConfig:
    enabled: bool = False
    cloud: CloudConfig = field(default_factory=CloudConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    @classmethod
    def from_path(cls, path: Optional[str | Path]) -> "RoadsideRuntimeConfig":
        if not path:
            return cls()

        config_path = Path(path)
        if not config_path.exists():
            return cls()

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RoadsideRuntimeConfig":
        return cls(
            enabled=bool(raw.get("enabled", False)),
            cloud=CloudConfig(**raw.get("cloud", {})),
            context=ContextConfig(**raw.get("context", {})),
            logging=LoggingConfig(**raw.get("logging", {})),
            server=ServerConfig(**raw.get("server", {})),
        )
