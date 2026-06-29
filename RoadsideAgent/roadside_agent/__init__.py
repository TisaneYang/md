"""RoadsideAgent public API."""

from .camera import RoadsideCameraSensor, RoadsideCameraSpec
from .bench2drive_hook import Bench2DriveRoadsideHook
from .communication import SendResult, VehicleCommandClient, VehicleEndpoint
from .config import RoadsideRuntimeConfig, ServerConfig
from .cloud_vlm_client import build_cloud_vlm_client
from .context import RoadsideContext
from .http_server import create_vehicle_state_server
from .logger import RoadsideLogger
from .manager import RoadsideAgent, RoadsidePerceptionManager
from .projection import ProjectionResult, RoadsideProjector
from .runtime import RoadsideRuntime
from .types import RoadsideBatchInput, RoadsideDecision, RoadsideVehicleObservation, RoadsideVehicleOutput
from .vehicle_registry import VehicleRecord, VehicleRegistry

__all__ = [
    "ProjectionResult",
    "RoadsideAgent",
    "Bench2DriveRoadsideHook",
    "SendResult",
    "VehicleCommandClient",
    "VehicleEndpoint",
    "RoadsideRuntimeConfig",
    "ServerConfig",
    "build_cloud_vlm_client",
    "RoadsideContext",
    "create_vehicle_state_server",
    "RoadsideLogger",
    "RoadsideCameraSensor",
    "RoadsideCameraSpec",
    "RoadsidePerceptionManager",
    "RoadsideProjector",
    "RoadsideRuntime",
    "RoadsideBatchInput",
    "RoadsideDecision",
    "RoadsideVehicleObservation",
    "RoadsideVehicleOutput",
    "VehicleRecord",
    "VehicleRegistry",
]
