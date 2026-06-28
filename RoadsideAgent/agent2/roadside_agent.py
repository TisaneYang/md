"""Roadside Agent2 main module."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import yaml

from .camera_manager import CameraManager
from .input_processor import InputProcessor
from .llm_interface import Agent2LLMInterface
from .workflow import build_agent2_workflow
from .workflow.nodes import Agent2WorkflowNodes


class RoadsideAgent2:
    """Primitive-sequence-driven roadside agent implementation."""

    def __init__(
        self,
        agent_config_path: str,
        camera_config_path: str,
        save_images: bool = False,
        output_dir: str = "debug/camera_images",
    ):
        self.agent_config_path = agent_config_path
        self.camera_config_path = camera_config_path
        self.config = self._load_agent_config()

        self.camera_manager = CameraManager(camera_config_path, save_images=save_images, output_dir=output_dir)
        self.input_processor = InputProcessor()
        self.llm_interface = Agent2LLMInterface(self.config["llm"], self.config.get("image_processing", {}))
        self.workflow = build_agent2_workflow(
            Agent2WorkflowNodes(
                input_processor=self.input_processor,
                camera_manager=self.camera_manager,
                llm_interface=self.llm_interface,
            )
        )

        print("Agent2 初始化完成")
        print(f"- 摄像头数量: {len(self.camera_manager.get_all_camera_ids())}")
        print(f"- LLM提供商: {self.config['llm']['provider']}")
        print(f"- 模型: {self.config['llm']['model']}")
        if save_images:
            print(f"- 图像保存: 已启用 ({output_dir})")

    def _load_agent_config(self) -> Dict[str, Any]:
        with open(self.agent_config_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def analyze(
        self,
        raw_images: Dict[str, np.ndarray],
        vehicle_info: Dict[str, Any],
        traffic_command: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze scene and produce Agent2 structured outputs."""
        workflow_state = self.workflow.invoke(
            {
                "raw_images": raw_images,
                "vehicle_info": vehicle_info,
                "traffic_command": traffic_command,
            }
        )

        camera_coverage = workflow_state["camera_coverage"]
        plan = workflow_state.get("plan", {})
        validation_result = workflow_state.get("validation_result", {})

        confidence = self._calculate_confidence(camera_coverage, validation_result)

        return {
            "camera_coverage": {
                "in_blind_spot": camera_coverage.get("in_blind_spot", True),
                "visible_cameras": camera_coverage.get("visible_cameras", []),
                "blind_spot_info": camera_coverage.get("blind_spot_info"),
            },
            "plan": plan,
            "validation_result": validation_result,
            "risk_level": workflow_state.get("risk_level", "medium"),
            "should_intervene": bool(workflow_state.get("should_intervene", False)),
            "confidence": confidence,
        }
        # 方法论
        # 构造
        # 验证

    def _calculate_confidence(self, camera_coverage: Dict[str, Any], validation_result: Dict[str, Any]) -> float:
        confidence = 0.45

        if not camera_coverage.get("in_blind_spot", True):
            confidence += 0.25
            if len(camera_coverage.get("visible_cameras", [])) > 1:
                confidence += 0.1

        confidence += 0.1

        if validation_result.get("is_valid", False):
            confidence += 0.05

        return min(1.0, max(0.0, confidence))

    def get_camera_info(self) -> Dict[str, Any]:
        camera_ids = self.camera_manager.get_all_camera_ids()
        cameras_info = {}

        for camera_id in camera_ids:
            cameras_info[camera_id] = self.camera_manager.get_camera_info(camera_id)

        return {
            "cameras": cameras_info,
            "relationships": self.camera_manager.get_camera_relationships(),
        }

    def reload_config(self):
        self.config = self._load_agent_config()
        self.camera_manager.reload_config()
        self.llm_interface = Agent2LLMInterface(self.config["llm"], self.config.get("image_processing", {}))
        self.workflow = build_agent2_workflow(
            Agent2WorkflowNodes(
                input_processor=self.input_processor,
                camera_manager=self.camera_manager,
                llm_interface=self.llm_interface,
            )
        )
