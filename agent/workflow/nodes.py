"""LangGraph node implementations for the redesigned roadside agent workflow."""

from __future__ import annotations

from typing import Any, Dict, List


class WorkflowNodes:
    """Concrete node handlers used by the LangGraph workflow."""

    def __init__(self, input_processor, camera_manager, llm_interface):
        self.input_processor = input_processor
        self.camera_manager = camera_manager
        self.llm_interface = llm_interface

    def perception_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate inputs and normalize core facts."""
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

    def scene_model_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract environment facts needed for downstream planning."""
        scene_model = self.llm_interface.extract_scene_model(
            camera_coverage=state["camera_coverage"],
            vehicle_info=state["vehicle_info"],
            traffic_command=state.get("traffic_command"),
            fact_pack=state["fact_pack"],
        )

        lane_analysis = {
            "one_way_lane_count": scene_model.get("lane_count", 0),
            "ego_lane_index": scene_model.get("ego_lane_index", 0),
            "lane_description": scene_model.get("lane_description", ""),
            "confidence": scene_model.get("confidence", "low"),
        }
        return {
            "scene_model": scene_model,
            "lane_analysis": lane_analysis,
        }

    def rule_gate_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Apply deterministic control policy before model planning."""
        fact_pack = state["fact_pack"]
        scene_model = state.get("scene_model", {})
        traffic_command = state.get("traffic_command")
        intention = fact_pack.get("vehicle_intent", "")

        if traffic_command:
            scene_type = "traffic_command"
            policy_mode = "traffic_command"
        elif fact_pack.get("in_blind_spot"):
            scene_type = "blind_spot"
            policy_mode = "safety_guidance"
        elif any(keyword in intention for keyword in ["左转", "右转", "掉头", "转弯", "merge", "turn"]):
            scene_type = "maneuvering"
            policy_mode = "safety_guidance"
        elif any(keyword in intention for keyword in ["变道", "超车", "并线", "lane"]):
            scene_type = "lane_change"
            policy_mode = "safety_guidance"
        else:
            scene_type = "cruise"
            policy_mode = "observe_only"

        must_intervene = bool(traffic_command) or fact_pack.get("in_blind_spot", False)
        if scene_model.get("conflict_risk") in {"medium", "high"}:
            must_intervene = True

        control_policy = {
            "policy_mode": policy_mode,
            "must_intervene": must_intervene,
            "safety_posture": "conservative"
            if traffic_command or fact_pack.get("in_blind_spot")
            else "balanced",
            "needs_lane_reasoning": not fact_pack.get("in_blind_spot", False),
            "left_right_reference": "vehicle_perspective",
            "hard_constraints": self._build_hard_constraints(fact_pack, scene_model, traffic_command),
        }

        return {
            "scene_type": scene_type,
            "control_policy": control_policy,
            "should_intervene": must_intervene,
        }

    def assessment_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a narrow assessment from facts, policy, and environment model."""
        assessment = self.llm_interface.generate_structured_assessment(
            camera_coverage=state["camera_coverage"],
            vehicle_info=state["vehicle_info"],
            traffic_command=state.get("traffic_command"),
            fact_pack=state["fact_pack"],
            scene_model=state.get("scene_model", {}),
            control_policy=state["control_policy"],
            scene_type=state["scene_type"],
        )
        return {
            "assessment": assessment,
            "risk_level": assessment.get("risk_level", "medium"),
        }

    def strategy_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compile the final strategy deterministically from assessed facts."""
        strategy = self._compile_strategy(
            assessment=state["assessment"],
            control_policy=state["control_policy"],
            scene_model=state.get("scene_model", {}),
            traffic_command=state.get("traffic_command"),
        )
        return {
            "strategy": strategy,
            "advice": strategy.get("summary", ""),
            "should_intervene": state["should_intervene"] or strategy.get("execution_mode") != "observe_only",
        }

    def task_realization_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Translate the chosen strategy into vehicle-executable tasks."""
        tasks = self.llm_interface.realize_tasks(
            strategy=state["strategy"],
            assessment=state["assessment"],
            scene_model=state.get("scene_model", {}),
            fact_pack=state["fact_pack"],
        )
        if not tasks:
            tasks = self._fallback_tasks(state["strategy"], state["assessment"], state.get("scene_model", {}))
        return {"tasks": tasks}

    def validation_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tasks against hard facts and fall back conservatively on conflict."""
        validation = self._validate_tasks(
            tasks=state["tasks"],
            strategy=state["strategy"],
            scene_model=state.get("scene_model", {}),
            control_policy=state["control_policy"],
        )

        tasks = state["tasks"]
        strategy = state["strategy"]
        if not validation["valid"]:
            strategy = self._downgrade_strategy(strategy, state["assessment"], state.get("scene_model", {}))
            tasks = self._fallback_tasks(strategy, state["assessment"], state.get("scene_model", {}))
            validation = {
                "valid": False,
                "fallback_used": True,
                "issues": validation["issues"],
            }

        return {
            "tasks": tasks,
            "strategy": strategy,
            "validation": validation,
            "advice": strategy.get("summary", state.get("advice", "")),
        }

    def _build_hard_constraints(
        self,
        fact_pack: Dict[str, Any],
        scene_model: Dict[str, Any],
        traffic_command: Dict[str, Any] | None,
    ) -> List[str]:
        constraints = ["涉及左右时必须按车端视角表达"]
        if traffic_command:
            constraints.append("交通管理指令优先")
        if fact_pack.get("in_blind_spot"):
            constraints.append("监控盲区内禁止激进机动")
        if scene_model.get("right_gap_status") == "uncertain":
            constraints.append("右侧空间不确定时先观察再横向动作")
        if scene_model.get("roadside_pull_over_feasible") is False:
            constraints.append("当前不适合直接靠路边停车")
        return constraints

    def _compile_strategy(
        self,
        assessment: Dict[str, Any],
        control_policy: Dict[str, Any],
        scene_model: Dict[str, Any],
        traffic_command: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        policy_mode = control_policy.get("policy_mode", "observe_only")
        maneuver_type = assessment.get("maneuver_type", "keep_lane")
        must_wait = assessment.get("must_wait", False)
        risk_level = assessment.get("risk_level", "medium")
        right_gap_status = scene_model.get("right_gap_status", "uncertain")
        roadside_pull_over_feasible = scene_model.get("roadside_pull_over_feasible")

        if maneuver_type == "stop_and_wait":
            strategy_id = "stop_immediately"
            summary = "立即平稳减速并停车等待，持续观察环境变化。"
            policy_mode = "safety_guidance"
        elif traffic_command and maneuver_type == "pull_over_right" and roadside_pull_over_feasible is not False:
            strategy_id = "pull_over_right_then_wait" if must_wait else "pull_over_right"
            summary = "先减速确认右侧安全，再靠右通行并等待。" if must_wait else "先减速确认右侧安全，再靠右通行。"
        elif control_policy.get("must_intervene") and risk_level == "high":
            strategy_id = "slow_down_and_hold"
            summary = "先降低车速并保持当前车道，确认环境后再执行下一动作。"
            policy_mode = "safety_guidance"
        elif (
            maneuver_type == "pull_over_right"
            and right_gap_status == "clear"
            and roadside_pull_over_feasible is not False
        ):
            strategy_id = "pull_over_right_and_stop" if must_wait else "pull_over_right"
            summary = "先观察右侧通行空间，再平稳靠边停车。" if must_wait else "先观察右侧通行空间，再平稳靠右执行目标动作。"
            policy_mode = "safety_guidance"
        elif maneuver_type == "change_lane_left":
            strategy_id = "observe_then_change_lane_left"
            summary = "先确认左侧安全，再平稳向左变道。"
            policy_mode = "safety_guidance"
        elif maneuver_type == "change_lane_right":
            strategy_id = "observe_then_change_lane_right"
            summary = "先确认右侧安全，再平稳向右变道。"
            policy_mode = "safety_guidance"
        elif policy_mode == "observe_only":
            strategy_id = "keep_lane_and_observe"
            summary = "保持当前车道和稳定速度，持续观察周边环境。"
        else:
            strategy_id = "slow_down_and_observe"
            summary = "先降低决策节奏并观察环境，再执行下一步。"
            policy_mode = "safety_guidance"

        return {
            "strategy_id": strategy_id,
            "summary": summary,
            "execution_mode": policy_mode,
            "task_style": "sequential_vehicle_actions",
            "step_constraints": [
                "每个任务只包含一个主要动作",
                "需要横向动作时先观察或减速",
            ],
        }

    def _validate_tasks(
        self,
        tasks: List[Dict[str, Any]],
        strategy: Dict[str, Any],
        scene_model: Dict[str, Any],
        control_policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        issues: List[str] = []
        task_text = " ".join(task.get("description", "") for task in tasks)
        strategy_id = strategy.get("strategy_id", "")

        if scene_model.get("right_gap_status") == "uncertain" and tasks:
            first_task = tasks[0].get("description", "")
            if "向右变道" in first_task or "靠右" in first_task:
                issues.append("右侧空间不确定时，第一步不能直接执行右向横移。")

        if scene_model.get("ego_lane_index", 0) > 0 and scene_model.get("lane_count", 0) > 0:
            if scene_model["ego_lane_index"] == scene_model["lane_count"] and "向右变道" in task_text:
                issues.append("车辆已在最右车道，不应再继续向右变道。")

        if control_policy.get("left_right_reference") == "vehicle_perspective" and "路侧左侧" in task_text:
            issues.append("任务指令不应使用路侧视角描述左右。")

        if strategy_id.endswith("wait") and "等待" not in task_text and "停车" not in task_text:
            issues.append("要求等待的策略，任务序列中缺少等待或停车步骤。")

        if strategy_id == "stop_immediately" and "停车" not in task_text:
            issues.append("紧急停车策略必须包含停车动作。")

        if strategy_id == "pull_over_right_and_stop" and ("靠右" not in task_text or "停车" not in task_text):
            issues.append("靠边停车策略必须同时包含靠右与停车动作。")

        if scene_model.get("roadside_pull_over_feasible") is False and "靠右" in task_text:
            issues.append("环境不支持靠路边停车，不应生成靠右停车任务。")

        return {
            "valid": not issues,
            "fallback_used": False,
            "issues": issues,
        }

    def _downgrade_strategy(
        self,
        strategy: Dict[str, Any],
        assessment: Dict[str, Any],
        scene_model: Dict[str, Any],
    ) -> Dict[str, Any]:
        risk_level = assessment.get("risk_level", "medium")
        if risk_level == "high" or scene_model.get("right_gap_status") == "uncertain":
            return {
                "strategy_id": "slow_down_and_hold",
                "summary": "先减速并保持当前车道，继续确认环境后等待后续动作。",
                "execution_mode": "safety_guidance",
                "task_style": "sequential_vehicle_actions",
                "step_constraints": ["先减速再观察", "避免未经确认的横向动作"],
            }
        return {
            "strategy_id": "keep_lane_and_observe",
            "summary": "保持当前车道并持续观察环境变化。",
            "execution_mode": "observe_only",
            "task_style": "sequential_vehicle_actions",
            "step_constraints": ["避免不必要干预"],
        }

    def _fallback_tasks(
        self,
        strategy: Dict[str, Any],
        assessment: Dict[str, Any],
        scene_model: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        strategy_id = strategy.get("strategy_id", "keep_lane_and_observe")

        if strategy_id == "pull_over_right_then_wait":
            return [
                {"description": "平稳减速并观察右侧通行空间。", "time_limit": 6},
                {"description": "确认安全后向右靠近路边。", "time_limit": 8},
                {"description": "在安全位置停车等待后续指令。", "time_limit": 12},
            ]
        if strategy_id == "pull_over_right":
            return [
                {"description": "平稳减速并观察右侧通行空间。", "time_limit": 6},
                {"description": "确认安全后向右靠近目标位置。", "time_limit": 8},
            ]
        if strategy_id == "pull_over_right_and_stop":
            return [
                {"description": "平稳减速并观察右侧通行空间。", "time_limit": 6},
                {"description": "确认安全后向右靠近路边。", "time_limit": 8},
                {"description": "在路边安全位置停车并保持等待。", "time_limit": 12},
            ]
        if strategy_id == "observe_then_change_lane_left":
            return [
                {"description": "保持稳定速度并观察左侧通行空间。", "time_limit": 5},
                {"description": "确认安全后向左变道。", "time_limit": 8},
            ]
        if strategy_id == "observe_then_change_lane_right":
            return [
                {"description": "保持稳定速度并观察右侧通行空间。", "time_limit": 5},
                {"description": "确认安全后向右变道。", "time_limit": 8},
            ]
        if strategy_id == "slow_down_and_hold":
            return [
                {"description": "平稳降低车速并保持当前车道。", "time_limit": 5},
                {"description": "持续观察车辆周围环境，确认下一步动作。", "time_limit": 8},
            ]
        if strategy_id == "stop_immediately":
            return [
                {"description": "立即平稳减速并保持当前车道。", "time_limit": 4},
                {"description": "在确保安全的前提下尽快停车。", "time_limit": 6},
                {"description": "停车后保持等待并持续观察周边环境。", "time_limit": 12},
            ]

        hold_time = 8 if assessment.get("risk_level") == "high" else 6
        return [
            {"description": "保持当前车道和稳定速度。", "time_limit": 5},
            {"description": "持续观察车辆周围环境变化。", "time_limit": hold_time},
        ]
