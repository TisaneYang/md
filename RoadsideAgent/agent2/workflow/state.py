"""State definitions for Agent2 primitive-sequence workflow."""

from typing import Any, Dict, List, Optional, TypedDict


class Agent2State(TypedDict, total=False):
    """Shared state flowing through the Agent2 workflow."""

    raw_images: Dict[str, Any]
    vehicle_info: Dict[str, Any]
    traffic_command: Optional[str]

    vehicle_summary: str
    camera_coverage: Dict[str, Any]
    fact_pack: Dict[str, Any]

    scene_model: Dict[str, Any]
    destination_model: Dict[str, Any]
    navigation_context: Dict[str, Any]
    plan: Dict[str, Any]

    tasks: List[Dict[str, Any]]
    validation_result: Dict[str, Any]

    advice: str
    risk_level: str
    should_intervene: bool
    confidence: float
