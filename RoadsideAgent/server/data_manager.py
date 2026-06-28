"""
数据缓存管理模块

管理来自多个数据源的缓存：
- 路侧摄像头图片
- 车辆信息
- 交通指挥指令
"""

import threading
from typing import Dict, Optional
import numpy as np


class DataManager:
    """线程安全的数据缓存管理器"""

    def __init__(self):
        self._lock = threading.Lock()
        self._images: Dict[str, np.ndarray] = {}
        self._vehicle_info: Optional[Dict] = None
        self._traffic_command: Optional[str] = None

    def set_image(self, camera_id: str, image: np.ndarray):
        """存储摄像头图片"""
        with self._lock:
            self._images[camera_id] = image

    def get_images(self) -> Dict[str, np.ndarray]:
        """获取所有摄像头图片"""
        with self._lock:
            return self._images.copy()

    def get_image(self, camera_id: str) -> Optional[np.ndarray]:
        """获取指定摄像头图片"""
        with self._lock:
            return self._images.get(camera_id)

    def set_vehicle_info(self, vehicle_info: Dict):
        """存储车辆信息"""
        with self._lock:
            self._vehicle_info = vehicle_info

    def get_vehicle_info(self) -> Optional[Dict]:
        """获取车辆信息"""
        with self._lock:
            return self._vehicle_info

    def set_traffic_command(self, command: str):
        """存储交通指挥指令"""
        with self._lock:
            self._traffic_command = command

    def get_traffic_command(self) -> Optional[str]:
        """获取交通指挥指令"""
        with self._lock:
            return self._traffic_command

    def clear_traffic_command(self):
        """清除交通指挥指令（使用后清除）"""
        with self._lock:
            self._traffic_command = None

    def clear_all(self):
        """清除所有缓存"""
        with self._lock:
            self._images.clear()
            self._vehicle_info = None
            self._traffic_command = None

    def get_status(self) -> Dict:
        """获取缓存状态"""
        with self._lock:
            return {
                "cameras": list(self._images.keys()),
                "has_vehicle_info": self._vehicle_info is not None,
                "has_traffic_command": self._traffic_command is not None
            }

    def get_context_snapshot(self) -> Dict:
        """原子化获取当前分析所需的全部上下文。"""
        with self._lock:
            return {
                "images": self._images.copy(),
                "vehicle_info": self._vehicle_info,
                "traffic_command": self._traffic_command,
            }
