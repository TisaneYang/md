"""
输入处理模块

该模块负责：
- 解析和验证车辆信息
- 处理交通指挥指令
- 协调图像预处理和投影
"""

import json
from typing import Dict, Optional, Any


class InputProcessor:
    """输入数据处理器"""

    def __init__(self):
        """初始化输入处理器"""
        pass

    def parse_vehicle_info(self, vehicle_data: Dict) -> Dict:
        """
        解析和验证车辆信息

        Args:
            vehicle_data: 车辆信息字典或JSON字符串

        Returns:
            标准化的车辆信息字典

        Raises:
            ValueError: 如果必需字段缺失或格式错误
        """
        # 如果是字符串，先解析JSON
        if isinstance(vehicle_data, str):
            vehicle_data = json.loads(vehicle_data)

        # 验证必需字段
        required_fields = [
            'type', 'color', 'plate', 'intention',
            'length', 'width', 'height',
            'location_x', 'location_y', 'location_z',
            'rotation_row', 'rotation_pitch', 'rotation_yaw',
            'velocity', 'acceleration'
        ]

        missing_fields = [field for field in required_fields if field not in vehicle_data]
        if missing_fields:
            raise ValueError(f"车辆信息缺少必需字段: {', '.join(missing_fields)}")

        # 验证数值字段
        numeric_fields = [
            'length', 'width', 'height',
            'location_x', 'location_y', 'location_z',
            'rotation_row', 'rotation_pitch', 'rotation_yaw',
            'velocity', 'acceleration'
        ]

        for field in numeric_fields:
            try:
                vehicle_data[field] = float(vehicle_data[field])
            except (ValueError, TypeError):
                raise ValueError(f"字段 '{field}' 必须是数值类型")

        # 返回标准化的车辆信息
        return {
            'type': str(vehicle_data['type']),
            'color': str(vehicle_data['color']),
            'description': str(vehicle_data.get('discription', '')),  # 注意原始拼写
            'plate': str(vehicle_data['plate']),
            'intention': str(vehicle_data['intention']),
            'length': vehicle_data['length'],
            'width': vehicle_data['width'],
            'height': vehicle_data['height'],
            'location_x': vehicle_data['location_x'],
            'location_y': vehicle_data['location_y'],
            'location_z': vehicle_data['location_z'],
            'rotation_row': vehicle_data['rotation_row'],
            'rotation_pitch': vehicle_data['rotation_pitch'],
            'rotation_yaw': vehicle_data['rotation_yaw'],
            'velocity': vehicle_data['velocity'],
            'acceleration': vehicle_data['acceleration']
        }

    def parse_traffic_command(self, command: Optional[str]) -> Optional[Dict]:
        """
        解析交通指挥指令

        Args:
            command: 自然语言指令字符串

        Returns:
            指令信息字典，如果无指令则返回None
        """
        if not command or not command.strip():
            return None

        return {
            'command': command.strip(),
            'priority': 'highest',  # 交通指挥指令优先级最高
            'type': 'traffic_control'
        }

    def validate_images(self, images: Dict[str, Any]) -> bool:
        """
        验证图像数据

        Args:
            images: 图像字典，key为camera_id，value为图像数组

        Returns:
            验证是否通过

        Raises:
            ValueError: 如果图像数据无效
        """
        if not images:
            raise ValueError("未提供图像数据")

        for camera_id, image in images.items():
            if image is None:
                raise ValueError(f"摄像头 {camera_id} 的图像为空")

            # 检查是否为numpy数组
            if not hasattr(image, 'shape'):
                raise ValueError(f"摄像头 {camera_id} 的图像格式无效")

            # 检查图像维度
            if len(image.shape) != 3 or image.shape[2] != 3:
                raise ValueError(f"摄像头 {camera_id} 的图像必须是3通道彩色图像")

        return True

    def prepare_input(self, vehicle_data: Dict, images: Dict[str, Any],
                     traffic_command: Optional[str] = None) -> Dict:
        """
        准备和整合所有输入数据

        Args:
            vehicle_data: 车辆信息
            images: 原始图像字典
            traffic_command: 可选的交通指挥指令

        Returns:
            整合后的输入数据字典
        """
        # 解析车辆信息
        vehicle_info = self.parse_vehicle_info(vehicle_data)

        # 验证图像
        self.validate_images(images)

        # 解析交通指令
        command_info = self.parse_traffic_command(traffic_command)

        return {
            'vehicle_info': vehicle_info,
            'raw_images': images,
            'traffic_command': command_info
        }

    def format_vehicle_summary(self, vehicle_info: Dict) -> str:
        """
        生成车辆信息的自然语言摘要

        Args:
            vehicle_info: 车辆信息字典

        Returns:
            车辆信息摘要文本
        """
        summary = (
            f"目标车辆：{vehicle_info['color']}{vehicle_info['type']}，"
            f"车牌号{vehicle_info['plate']}。"
        )

        if vehicle_info.get('description'):
            summary += f"{vehicle_info['description']}。"

        summary += (
            f"驾驶意图：{vehicle_info['intention']}。"
            f"当前速度：{vehicle_info['velocity']:.1f} km/h，"
            f"加速度：{vehicle_info['acceleration']:.2f} m/s²。"
        )

        return summary

    def build_fact_pack(
        self,
        vehicle_info: Dict,
        camera_coverage: Dict,
        traffic_command: Optional[Dict],
    ) -> Dict:
        """Build a compact fact pack for downstream structured reasoning."""
        return {
            "vehicle_type": vehicle_info.get("type", ""),
            "vehicle_color": vehicle_info.get("color", ""),
            "vehicle_plate": vehicle_info.get("plate", ""),
            "vehicle_intent": vehicle_info.get("intention", ""),
            "speed_kmh": round(float(vehicle_info.get("velocity", 0.0)), 1),
            "acceleration_mps2": round(float(vehicle_info.get("acceleration", 0.0)), 2),
            "in_blind_spot": bool(camera_coverage.get("in_blind_spot", False)),
            "visible_camera_ids": list(camera_coverage.get("visible_cameras", [])),
            "camera_relation_note": "前视相对而行，涉及左右时按车端视角表达",
            "traffic_command_text": traffic_command.get("command", "") if traffic_command else "",
        }
