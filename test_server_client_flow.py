"""Integration-style tests for the client -> server -> vehicle flow."""

import asyncio
import unittest
from unittest.mock import patch

import numpy as np

import server.main as server_main
from server.data_manager import DataManager


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeAgent:
    def analyze(self, raw_images, vehicle_info, traffic_command=None):
        has_command = bool(traffic_command)
        return {
            "camera_coverage": {
                "in_blind_spot": False,
                "visible_cameras": list(raw_images.keys()),
                "blind_spot_info": None,
            },
            "vehicle_summary": "测试车辆摘要",
            "scene_type": "traffic_command" if has_command else "cruise",
            "active_skills": ["task_planning"],
            "reasoning": "测试推理",
            "advice": "优先执行交通指令并分步完成任务。" if has_command else "保持稳定行驶并持续观察。",
            "risk_level": "high" if has_command else "medium",
            "plan": {
                "summary": "围绕交通指令组织执行。" if has_command else "保持稳定通行。",
                "objective": traffic_command or "持续通行",
                "execution_mode": "traffic_command" if has_command else "safety_guidance",
            },
            "tasks": [
                {"description": "确认当前环境与目标。", "time_limit": 3},
                {"description": "执行当前规划中的核心动作。", "time_limit": 8},
            ],
            "should_intervene": True,
            "confidence": 0.92,
            "traffic_command": traffic_command,
        }


class ServerClientFlowTests(unittest.TestCase):
    def setUp(self):
        self.pushed_messages = []
        server_main.data_manager = DataManager()
        server_main.agent = FakeAgent()
        server_main.config = {"vehicle": {"ip": "127.0.0.1", "port": 8000}}
        server_main.periodic_task = None
        server_main.periodic_enabled = False

    def _fake_vehicle_post(self, url, json, timeout):
        self.pushed_messages.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(200)

    def _seed_camera_image(self):
        server_main.data_manager.set_image(
            "camera_1",
            np.zeros((64, 64, 3), dtype=np.uint8),
        )

    def _vehicle_info(self):
        return {
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

    def test_camera_then_vehicle_generates_tasks(self):
        with patch.object(server_main.requests, "post", side_effect=self._fake_vehicle_post):
            self._seed_camera_image()

            payload = asyncio.run(
                server_main.receive_vehicle_info(server_main.VehicleInfoRequest(**self._vehicle_info()))
            )
            self.assertEqual(payload["scene_type"], "cruise")
            self.assertEqual(len(payload["tasks"]), 2)
            self.assertEqual(payload["send_to_vehicle"], "success")
            self.assertEqual(len(self.pushed_messages), 1)
            self.assertEqual(self.pushed_messages[0]["json"]["tasks"][0]["description"], "确认当前环境与目标。")

    def test_traffic_command_is_applied_before_vehicle_analysis(self):
        command = "前方交警指挥靠右减速通行"
        with patch.object(server_main.requests, "post", side_effect=self._fake_vehicle_post):
            self._seed_camera_image()
            command_response = asyncio.run(
                server_main.receive_traffic_command(server_main.TrafficCommandRequest(command=command))
            )
            self.assertEqual(command_response["status"], "success")

            payload = asyncio.run(
                server_main.receive_vehicle_info(server_main.VehicleInfoRequest(**self._vehicle_info()))
            )
            self.assertEqual(payload["scene_type"], "traffic_command")
            self.assertEqual(payload["traffic_command"], command)
            self.assertEqual(payload["plan"]["execution_mode"], "traffic_command")
            self.assertEqual(self.pushed_messages[0]["json"]["traffic_command"], command)


if __name__ == "__main__":
    unittest.main()
