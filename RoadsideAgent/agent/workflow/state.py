"""State definitions for the LangGraph-based roadside workflow."""

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state flowing through the LangGraph workflow."""

    raw_images: Dict[str, Any]
    vehicle_info: Dict[str, Any]
    traffic_command: Optional[str]

    vehicle_summary: str
    camera_coverage: Dict[str, Any]
    fact_pack: Dict[str, Any]
    scene_model: Dict[str, Any]
    control_policy: Dict[str, Any]
    scene_type: str
    assessment: Dict[str, Any]
    strategy: Dict[str, Any]
    lane_analysis: Dict[str, Any]
    validation: Dict[str, Any]
    risk_level: str
    should_intervene: bool
    tasks: List[Dict[str, Any]]
    advice: str
    confidence: float
