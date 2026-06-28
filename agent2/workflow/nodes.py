"""LangGraph node implementations for Agent2 workflow."""

from __future__ import annotations

from typing import Any, Dict, List


class Agent2WorkflowNodes:
    """Concrete node handlers for Agent2."""

    def __init__(self, input_processor, camera_manager, llm_interface):
        self.input_processor = input_processor
        self.camera_manager = camera_manager
        self.llm_interface = llm_interface

    def perception_normalize_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw inputs and build objective fact pack."""
        processed_input = self.input_processor.prepare_input(
            vehicle_data=state["vehicle_info"],
            images=state["raw_images"],
            traffic_command=state.get("traffic_command"),
        )
        vehicle_info = processed_input["vehicle_info"]
        command_info = processed_input["traffic_command"]
        vehicle_summary = self.input_processor.format_vehicle_summary(vehicle_info)

        camera_coverage = self.camera_manager.project_vehicle(
            vehicle_info=vehicle_info,
            raw_images=state["raw_images"],
        )
        camera_coverage["relationships"] = self.camera_manager.get_camera_relationships()

        fact_pack = self.input_processor.build_fact_pack(
            vehicle_info=vehicle_info,
            camera_coverage=camera_coverage,
            traffic_command=command_info,
        )

        return {
            "vehicle_info": vehicle_info,
            "traffic_command": command_info,
            "vehicle_summary": vehicle_summary,
            "camera_coverage": camera_coverage,
            "fact_pack": fact_pack,
        }

    def scene_model_extract_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured environment model for destination reasoning."""
        scene_model = self.llm_interface.extract_scene_model(
            camera_coverage=state["camera_coverage"],
            vehicle_info=state["vehicle_info"],
            traffic_command=state.get("traffic_command"),
            fact_pack=state["fact_pack"],
        )

        risk_level = self._derive_risk_level(state["fact_pack"], scene_model)
        should_intervene = bool(state.get("traffic_command")) or risk_level in {"medium", "high"}

        return {
            "scene_model": scene_model,
            "risk_level": risk_level,
            "should_intervene": should_intervene,
        }

    def destination_navigate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Infer destination/goal model from intent + command + scene."""
        navigation_context = self.llm_interface.build_navigation_context(
            camera_coverage=state["camera_coverage"],
            scene_model=state["scene_model"],
            traffic_command=state.get("traffic_command")
        )
        return {"navigation_context": navigation_context}

    def maneuver_sequence_planning_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Plan topology (mermaid + graph) from current-to-goal relation."""
        plan = self.llm_interface.plan_maneuver_sequence(
            camera_coverage=state["camera_coverage"],
            scene_model=state["scene_model"],
            navigation_context=state["navigation_context"],
        )
        return {"plan": plan}

    def output_validation_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate coherence among scene, destination, sequence and tasks."""
        validation_result = self.llm_interface.validate_output(
            camera_coverage=state["camera_coverage"],
            plan=state.get("plan", {}),
            navigation_context=state["navigation_context"],
            scene_model=state["scene_model"],
        )

        if not validation_result.get("is_valid", False):
            validation_result = {
                "is_valid": False,
                "issues": validation_result.get("issues", []),
                "validation_summary": "检测到一致性问题，当前输出不满足拓扑规划约束。",
            }


        return {
            "validation_result": validation_result,
        }

    # def _fallback_sequence(self, scene_model: Dict[str, Any], destination_model: Dict[str, Any]) -> Dict[str, Any]:
    #     sequence: List[str]
    #     if destination_model.get("required_turn") == "right":
    #         sequence = ["turn_right", "go_straight"]
    #     elif destination_model.get("required_turn") == "left":
    #         sequence = ["turn_left", "go_straight"]
    #     else:
    #         sequence = ["keep_lane", "go_straight"]

    #     if destination_model.get("must_stop"):
    #         sequence.append("stop")

    #     return {
    #         "sequence_reason": "使用保守兜底序列以避免不确定场景下的激进机动。",
    #         "sequence": sequence,
    #         "sequence_confidence": "low",
    #     }

    def _fallback_tasks(self, maneuver_sequence: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        for primitive in maneuver_sequence.get("sequence", []):
            if primitive == "change_lane_left":
                tasks.append({"description": "确认左侧安全后向左变道。", "time_limit": 8})
            elif primitive == "change_lane_right":
                tasks.append({"description": "确认右侧安全后向右变道。", "time_limit": 8})
            elif primitive == "turn_left":
                tasks.append({"description": "在路口按规划完成左转。", "time_limit": 10})
            elif primitive == "turn_right":
                tasks.append({"description": "在路口按规划完成右转。", "time_limit": 10})
            elif primitive == "pull_over":
                tasks.append({"description": "平稳靠近右侧路边目标区域。", "time_limit": 10})
            elif primitive == "stop":
                tasks.append({"description": "在安全位置停车并等待。", "time_limit": 12})
            elif primitive == "go_straight":
                tasks.append({"description": "保持直行通过当前路段。", "time_limit": 8})
            else:
                tasks.append({"description": "保持当前车道稳定行驶。", "time_limit": 6})

        if not tasks:
            tasks = [{"description": "保持当前车道并持续观察环境。", "time_limit": 6}]

        return tasks

    @staticmethod
    def _derive_risk_level(fact_pack: Dict[str, Any], scene_model: Dict[str, Any]) -> str:
        if fact_pack.get("in_blind_spot"):
            return "high"
        conflict = scene_model.get("conflict_risk", "medium")
        if conflict in {"low", "medium", "high"}:
            return conflict
        return "medium"
