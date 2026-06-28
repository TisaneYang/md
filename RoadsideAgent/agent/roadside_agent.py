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
from .workflow import build_agent_workflow
from .workflow.nodes import WorkflowNodes


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
        self.workflow = build_agent_workflow(
            WorkflowNodes(
                input_processor=self.input_processor,
                camera_manager=self.camera_manager,
                llm_interface=self.llm_interface
            )
        )

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
        分析交通场景并生成结构化任务规划

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
                "scene_type": str,
                "fact_pack": {...},
                "scene_model": {...},
                "control_policy": {...},
                "assessment": {...},
                "strategy": {...},
                "advice": str,
                "risk_level": "low/medium/high",
                "tasks": [...],
                "confidence": float
            }

        Raises:
            ValueError: 如果输入数据无效
        """
        print("\n" + "="*60)
        print("开始分析交通场景")
        print("="*60)

        print("\n[1/6] 执行LangGraph工作流...")
        try:
            workflow_state = self.workflow.invoke(
                {
                    'raw_images': raw_images,
                    'vehicle_info': vehicle_info,
                    'traffic_command': traffic_command
                }
            )
        except Exception as e:
            print(f"✗ 工作流执行失败: {e}")
            raise

        camera_coverage = workflow_state['camera_coverage']
        vehicle_info_parsed = workflow_state['vehicle_info']
        vehicle_summary = workflow_state['vehicle_summary']
        traffic_command_parsed = workflow_state.get('traffic_command')

        print(f"✓ 车辆信息: {vehicle_summary}")
        if traffic_command_parsed:
            print(f"✓ 交通指令: {traffic_command_parsed['command']}")
        else:
            print("✓ 无交通指令")

        print("\n[2/6] 感知结果...")
        if camera_coverage['in_blind_spot']:
            print("✗ 车辆不在任何摄像头视野内（监控死角）")
            if camera_coverage.get('blind_spot_info'):
                print(f"  {camera_coverage['blind_spot_info']['description']}")
        else:
            visible_cameras = camera_coverage['visible_cameras']
            print(f"✓ 车辆在 {len(visible_cameras)} 个摄像头视野内")
            for cam_id in visible_cameras:
                cam_name = camera_coverage['projections'][cam_id]['camera_name']
                bbox = camera_coverage['projections'][cam_id]['bbox']
                print(f"  - {cam_name}: bbox={bbox}")

        print("\n[3/6] 规则收敛...")
        print(f"✓ 场景类型: {workflow_state['scene_type']}")
        print(f"✓ 控制模式: {workflow_state['control_policy']['policy_mode']}")

        print("\n[4/6] 环境事实提取...")
        lane_analysis = workflow_state.get("lane_analysis", {})
        print(
            "✓ 车道识别: 单向"
            f"{lane_analysis.get('one_way_lane_count', 0)}车道, 目标车辆位于第"
            f"{lane_analysis.get('ego_lane_index', 0)}车道"
        )
        print(f"✓ 环境冲突风险: {workflow_state['scene_model'].get('conflict_risk', 'medium')}")

        print("\n[5/6] 受控评估与策略编译...")
        print(f"✓ 风险等级: {workflow_state['risk_level']}")
        print(f"✓ 总体策略: {workflow_state['strategy']['summary']}")

        print("\n[6/6] 任务拆解...")
        for index, task in enumerate(workflow_state['tasks'], start=1):
            print(f"  {index}. {task['description']} ({task['time_limit']}s)")

        confidence = self._calculate_confidence(
            camera_coverage,
            {'risk_level': workflow_state['risk_level']}
        )

        result = {
            'camera_coverage': {
                'in_blind_spot': camera_coverage['in_blind_spot'],
                'visible_cameras': camera_coverage['visible_cameras'],
                'blind_spot_info': camera_coverage.get('blind_spot_info')
            },
            'vehicle_summary': vehicle_summary,
            'scene_type': workflow_state['scene_type'],
            'fact_pack': workflow_state.get('fact_pack', {}),
            'control_policy': workflow_state.get('control_policy', {}),
            'scene_model': workflow_state.get('scene_model', {}),
            'lane_analysis': workflow_state.get('lane_analysis', {}),
            'assessment': workflow_state.get('assessment', {}),
            'advice': workflow_state.get('advice', ''),
            'risk_level': workflow_state['risk_level'],
            'strategy': workflow_state.get('strategy', {}),
            'tasks': workflow_state['tasks'],
            'should_intervene': workflow_state['should_intervene'],
            'validation': workflow_state.get('validation', {}),
            'confidence': confidence,
            'traffic_command': traffic_command
        }

        print(f"✓ 分析完成，置信度: {confidence:.2f}")
        print("\n" + "="*60)
        print("分析结果")
        print("="*60)
        print(f"\n{result['advice']}\n")
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
        self.workflow = build_agent_workflow(
            WorkflowNodes(
                input_processor=self.input_processor,
                camera_manager=self.camera_manager,
                llm_interface=self.llm_interface
            )
        )
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
