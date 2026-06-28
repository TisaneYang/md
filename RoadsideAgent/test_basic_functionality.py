"""Basic regression tests for the LangGraph-based roadside workflow."""

import unittest

import numpy as np

from agent.input_processor import InputProcessor
from agent.workflow import build_agent_workflow
from agent.workflow.nodes import WorkflowNodes


class FakeCameraManager:
    def project_vehicle(self, vehicle_info, raw_images):
        return {
            "visible_cameras": list(raw_images.keys()),
            "projections": {
                camera_id: {
                    "bbox": (10, 10, 20, 20),
                    "corners_2d": [],
                    "image_with_bbox": image,
                    "camera_name": camera_id,
                }
                for camera_id, image in raw_images.items()
            },
            "in_blind_spot": False,
            "blind_spot_info": None,
        }

    def get_camera_relationships(self):
        return "测试环境中的摄像头互补覆盖。"


class FakeLLMInterface:
    def extract_scene_model(
        self,
        camera_coverage,
        vehicle_info,
        traffic_command,
        fact_pack,
    ):
        return {
            "lane_count": 3,
            "ego_lane_index": 2,
            "lane_description": "位于中间车道",
            "front_gap_status": "clear",
            "left_gap_status": "clear",
            "right_gap_status": "clear",
            "roadside_pull_over_feasible": True,
            "nearby_agents_summary": ["前方车流平稳"],
            "conflict_risk": "medium" if traffic_command else "low",
            "confidence": "medium",
        }

    def generate_structured_assessment(
        self,
        camera_coverage,
        vehicle_info,
        traffic_command,
        fact_pack,
        scene_model,
        control_policy,
        scene_type,
    ):
        if traffic_command:
            command_text = traffic_command.get("command", "")
            if "停" in command_text:
                return {
                    "scene_summary": "收到停车等待指令",
                    "risk_level": "high",
                    "primary_goal": "立即减速停车并等待",
                    "key_constraints": ["交通管理指令优先", "优先停车避险"],
                    "maneuver_type": "stop_and_wait",
                    "lane_change_needed": False,
                    "observation_needed": True,
                    "must_wait": True,
                }
            return {
                "scene_summary": "收到靠右等待指令",
                "risk_level": "high",
                "primary_goal": "靠右减速并等待",
                "key_constraints": ["交通管理指令优先"],
                "maneuver_type": "pull_over_right",
                "lane_change_needed": True,
                "observation_needed": True,
                "must_wait": True,
            }
        return {
            "scene_summary": "正常直行场景",
            "risk_level": "low",
            "primary_goal": "保持当前驾驶意图",
            "key_constraints": ["保持稳定通行"],
            "maneuver_type": "keep_lane",
            "lane_change_needed": False,
            "observation_needed": True,
            "must_wait": False,
        }

    def realize_tasks(
        self,
        strategy,
        assessment,
        scene_model,
        fact_pack,
    ):
        if strategy["strategy_id"] == "stop_immediately":
            return [
                {"description": "立即平稳减速并保持当前车道。", "time_limit": 4},
                {"description": "在确保安全的前提下尽快停车。", "time_limit": 6},
                {"description": "停车后保持等待并持续观察周边环境。", "time_limit": 12},
            ]
        if strategy["strategy_id"] == "pull_over_right_then_wait":
            return [
                {"description": "平稳减速并观察右侧通行空间。", "time_limit": 6},
                {"description": "确认安全后向右靠近路边。", "time_limit": 8},
                {"description": "在安全位置停车等待后续指令。", "time_limit": 12},
            ]
        return [
            {"description": "保持当前车道和稳定速度。", "time_limit": 5},
            {"description": "持续观察周边环境变化。", "time_limit": 8},
        ]


class WorkflowBasicTests(unittest.TestCase):
    def setUp(self):
        self.workflow = build_agent_workflow(
            WorkflowNodes(
                input_processor=InputProcessor(),
                camera_manager=FakeCameraManager(),
                llm_interface=FakeLLMInterface(),
            )
        )
        self.raw_images = {"camera_1": np.zeros((64, 64, 3), dtype=np.uint8)}
        self.vehicle_info = {
            "type": "轿车",
            "color": "白色",
            "discription": "测试车辆",
            "plate": "TEST123",
            "intention": "直行通过路段",
            "length": 4.5,
            "width": 1.8,
            "height": 1.5,
            "location_x": 20.0,
            "location_y": 0.0,
            "location_z": 0.0,
            "rotation_row": 0.0,
            "rotation_pitch": 0.0,
            "rotation_yaw": 0.0,
            "velocity": 30.0,
            "acceleration": 0.2,
        }

    def test_workflow_generates_tasks_without_command(self):
        result = self.workflow.invoke(
            {
                "raw_images": self.raw_images,
                "vehicle_info": self.vehicle_info,
                "traffic_command": None,
            }
        )

        self.assertEqual(result["scene_type"], "cruise")
        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["should_intervene"])
        self.assertGreaterEqual(len(result["tasks"]), 2)
        self.assertEqual(result["lane_analysis"]["one_way_lane_count"], 3)
        self.assertEqual(result["strategy"]["strategy_id"], "keep_lane_and_observe")

    def test_workflow_prioritizes_traffic_command(self):
        result = self.workflow.invoke(
            {
                "raw_images": self.raw_images,
                "vehicle_info": self.vehicle_info,
                "traffic_command": "前方交警指挥靠右减速通行",
            }
        )

        self.assertEqual(result["scene_type"], "traffic_command")
        self.assertTrue(result["should_intervene"])
        self.assertEqual(result["strategy"]["execution_mode"], "traffic_command")
        self.assertEqual(result["strategy"]["strategy_id"], "pull_over_right_then_wait")
        self.assertGreaterEqual(len(result["tasks"]), 3)

    def test_workflow_supports_stop_immediately_strategy(self):
        result = self.workflow.invoke(
            {
                "raw_images": self.raw_images,
                "vehicle_info": self.vehicle_info,
                "traffic_command": "前方临时管制，请立即停车等待指令",
            }
        )

        self.assertEqual(result["scene_type"], "traffic_command")
        self.assertEqual(result["strategy"]["strategy_id"], "stop_immediately")
        self.assertEqual(result["strategy"]["execution_mode"], "safety_guidance")
        self.assertTrue(any("停车" in task["description"] for task in result["tasks"]))


if __name__ == "__main__":
    unittest.main()
