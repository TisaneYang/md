"""
路侧智能体Agent模块

该模块提供路侧交通智能体的核心功能，包括：
- 摄像头管理与车辆投影
- 场景理解与风险分析
- 驾驶决策建议生成
"""

from .roadside_agent import RoadsideAgent
from .camera_manager import CameraManager

__all__ = ['RoadsideAgent', 'CameraManager']
