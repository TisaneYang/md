"""
路侧智能体Agent主模块

该模块整合所有子模块，提供完整的路侧交通智能体功能。
"""

import yaml
from typing import Dict, Optional, Any
import numpy as np

from .camera_manager import CameraManager
from .input_processor import InputProcessor
from .llm_interface import LLMInterface


class RoadsideAgent:
    """路侧交通智能体主类"""

    def __init__(self, agent_config_path: str, camera_config_path: str,
                 save_images: bool = False, output_dir: str = "debug/camera_images"):
        """
        初始化路侧智能体

        Args:
            agent_config_path: Agent配置文件路径
            camera_config_path: 摄像头配置文件路径
            save_images: 是否保存图像
            output_dir: 图像保存的根目录
        """
        self.agent_config_path = agent_config_path
        self.camera_config_path = camera_config_path

        # 加载Agent配置
        self.config = self._load_agent_config()

        # 初始化各模块
        self.camera_manager = CameraManager(camera_config_path, save_images=save_images, output_dir=output_dir)
        self.input_processor = InputProcessor()
        self.llm_interface = LLMInterface(self.config['llm'], self.config.get('image_processing', {}))

        print(f"路侧智能体初始化完成")
        print(f"- 摄像头数量: {len(self.camera_manager.get_all_camera_ids())}")
        print(f"- LLM提供商: {self.config['llm']['provider']}")
        print(f"- 模型: {self.config['llm']['model']}")
        if save_images:
            print(f"- 图像保存: 已启用 ({output_dir})")

    def _load_agent_config(self) -> Dict:
        """加载Agent配置文件"""
        with open(self.agent_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config

    def analyze(self, raw_images: Dict[str, np.ndarray],
               vehicle_info: Dict,
               traffic_command: Optional[str] = None) -> Dict:
        """
        分析交通场景并生成驾驶建议

        这是Agent的主要接口，执行完整的分析流程：
        1. 输入处理和验证
        2. 车辆投影到摄像头
        3. 判断可见性
        4. 场景分析（如果可见）或盲区处理（如果不可见）
        5. LLM推理和建议生成

        Args:
            raw_images: 原始图像字典，key为camera_id，value为图像数组
            vehicle_info: 车辆信息字典（参考template.json格式）
            traffic_command: 可选的交通指挥指令（自然语言）

        Returns:
            分析结果字典：
            {
                "camera_coverage": {
                    "in_blind_spot": bool,
                    "visible_cameras": [...],
                    "projections": {...}
                },
                "vehicle_summary": str,
                "reasoning": str,
                "advice": str,
                "risk_level": "low/medium/high",
                "confidence": float
            }

        Raises:
            ValueError: 如果输入数据无效
        """
        print("\n" + "="*60)
        print("开始分析交通场景")
        print("="*60)

        # 步骤1: 输入处理
        print("\n[1/5] 处理输入数据...")
        try:
            processed_input = self.input_processor.prepare_input(
                vehicle_data=vehicle_info,
                images=raw_images,
                traffic_command=traffic_command
            )
            vehicle_info_parsed = processed_input['vehicle_info']
            traffic_command_parsed = processed_input['traffic_command']

            vehicle_summary = self.input_processor.format_vehicle_summary(vehicle_info_parsed)
            print(f"✓ 车辆信息: {vehicle_summary}")

            if traffic_command_parsed:
                print(f"✓ 交通指令: {traffic_command_parsed['command']}")
            else:
                print("✓ 无交通指令")

        except Exception as e:
            print(f"✗ 输入处理失败: {e}")
            raise

        # 步骤2: 车辆投影
        print("\n[2/5] 投影车辆到摄像头...")
        try:
            camera_coverage = self.camera_manager.project_vehicle(
                vehicle_info=vehicle_info_parsed,
                raw_images=raw_images
            )

            if camera_coverage['in_blind_spot']:
                print("✗ 车辆不在任何摄像头视野内（监控死角）")
                print(f"  {camera_coverage['blind_spot_info']['description']}")
            else:
                visible_cameras = camera_coverage['visible_cameras']
                print(f"✓ 车辆在 {len(visible_cameras)} 个摄像头视野内")
                for cam_id in visible_cameras:
                    cam_name = camera_coverage['projections'][cam_id]['camera_name']
                    bbox = camera_coverage['projections'][cam_id]['bbox']
                    print(f"  - {cam_name}: bbox={bbox}")

        except Exception as e:
            print(f"✗ 投影失败: {e}")
            raise

        # 步骤3: 摄像头关系说明
        print("\n[3/5] 分析摄像头配置...")
        camera_relationships = self.camera_manager.get_camera_relationships()
        camera_coverage['relationships'] = camera_relationships
        print(f"摄像头关系:\n{camera_relationships}")

        # 步骤4: LLM分析
        print("\n[4/5] 调用LLM进行场景分析...")
        try:
            llm_result = self.llm_interface.analyze_scene(
                camera_coverage=camera_coverage,
                vehicle_info=vehicle_info_parsed,
                traffic_command=traffic_command_parsed
            )

            print(f"✓ LLM分析完成")
            print(f"  风险等级: {llm_result['risk_level']}")

        except Exception as e:
            print(f"✗ LLM分析失败: {e}")
            raise

        # 步骤5: 整合结果
        print("\n[5/5] 整合分析结果...")

        # 计算置信度
        confidence = self._calculate_confidence(camera_coverage, llm_result)

        result = {
            'camera_coverage': {
                'in_blind_spot': camera_coverage['in_blind_spot'],
                'visible_cameras': camera_coverage['visible_cameras'],
                'blind_spot_info': camera_coverage.get('blind_spot_info')
            },
            'vehicle_summary': vehicle_summary,
            'reasoning': llm_result['reasoning'],
            'advice': llm_result['advice'],
            'risk_level': llm_result['risk_level'],
            'confidence': confidence,
            'traffic_command': traffic_command
        }

        print(f"✓ 分析完成，置信度: {confidence:.2f}")
        print("\n" + "="*60)
        print("分析结果")
        print("="*60)
        print(f"\n{llm_result['advice']}\n")
        print("="*60)

        return result

    def _calculate_confidence(self, camera_coverage: Dict, llm_result: Dict) -> float:
        """
        计算分析结果的置信度

        Args:
            camera_coverage: 摄像头覆盖信息
            llm_result: LLM分析结果

        Returns:
            置信度分数 (0.0-1.0)
        """
        confidence = 0.5  # 基础置信度

        # 如果车辆可见，增加置信度
        if not camera_coverage['in_blind_spot']:
            confidence += 0.3

            # 如果在多个摄像头中可见，进一步增加
            num_visible = len(camera_coverage['visible_cameras'])
            if num_visible > 1:
                confidence += 0.1

        # 根据风险等级调整
        if llm_result['risk_level'] == 'high':
            confidence += 0.1  # 高风险情况下，建议更明确
        elif llm_result['risk_level'] == 'low':
            confidence += 0.05

        # 限制在0-1范围内
        confidence = min(1.0, max(0.0, confidence))

        return confidence

    def get_camera_info(self) -> Dict:
        """
        获取摄像头配置信息

        Returns:
            摄像头信息字典
        """
        camera_ids = self.camera_manager.get_all_camera_ids()
        cameras_info = {}

        for cam_id in camera_ids:
            cameras_info[cam_id] = self.camera_manager.get_camera_info(cam_id)

        return {
            'cameras': cameras_info,
            'relationships': self.camera_manager.get_camera_relationships()
        }

    def reload_config(self):
        """重新加载配置（支持动态更新）"""
        print("重新加载配置...")
        self.config = self._load_agent_config()
        self.camera_manager.reload_config()
        self.llm_interface = LLMInterface(self.config['llm'], self.config.get('image_processing', {}))
        print("配置重新加载完成")

    def analyze_batch(self, scenarios: list) -> list:
        """
        批量分析多个场景

        Args:
            scenarios: 场景列表，每个场景包含 raw_images, vehicle_info, traffic_command

        Returns:
            分析结果列表
        """
        results = []

        for i, scenario in enumerate(scenarios):
            print(f"\n处理场景 {i+1}/{len(scenarios)}...")
            try:
                result = self.analyze(
                    raw_images=scenario['raw_images'],
                    vehicle_info=scenario['vehicle_info'],
                    traffic_command=scenario.get('traffic_command')
                )
                results.append(result)
            except Exception as e:
                print(f"场景 {i+1} 分析失败: {e}")
                results.append({'error': str(e)})

        return results
