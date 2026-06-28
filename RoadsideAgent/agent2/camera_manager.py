"""
摄像头管理与投影模块

该模块负责：
- 加载和管理多个摄像头配置
- 将车辆3D位置投影到各摄像头图像平面
- 判断车辆可见性和监控死角
- 绘制标定框
"""

import yaml
import numpy as np
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from PIL import Image
from utils.vehicle_projection import VehicleProjector
from utils.bbox_visualizer import BBoxVisualizer


class CameraManager:
    """摄像头管理器，处理多摄像头投影和可见性判断"""

    def __init__(self, camera_config_path: str, save_images: bool = False, output_dir: str = "debug/camera_images"):
        """
        初始化摄像头管理器

        Args:
            camera_config_path: 摄像头配置文件路径（YAML格式）
            save_images: 是否保存图像
            output_dir: 图像保存的根目录
        """
        self.config_path = camera_config_path
        self.cameras = {}
        self.projectors = {}
        self.visualizers = {}
        self.camera_relationships = []

        # 图像保存配置
        self.save_images = save_images
        self.output_dir = output_dir

        # 如果启用保存，创建目录
        if self.save_images:
            os.makedirs(self.output_dir, exist_ok=True)
            print(f"图像保存已启用，保存路径: {self.output_dir}")

        self._load_config()
        self._initialize_projectors()

    def _load_config(self):
        """加载摄像头配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 加载摄像头配置
        for camera in config.get('cameras', []):
            camera_id = camera['id']
            self.cameras[camera_id] = {
                'name': camera['name'],
                'location': camera['location'],
                'rotation': camera['rotation'],
                'intrinsics': camera['intrinsics'],
                'image_size': camera['image_size']
            }

        # 加载摄像头关系
        self.camera_relationships = config.get('camera_relationships', [])

    def _initialize_projectors(self):
        """为每个摄像头初始化投影器和可视化器"""
        for camera_id, camera_info in self.cameras.items():
            # 创建投影器
            self.projectors[camera_id] = VehicleProjector(camera_info['intrinsics'])

            # 创建可视化器
            self.visualizers[camera_id] = BBoxVisualizer(
                box_color=(0, 255, 0),
                box_thickness=2,
                corner_color=(255, 0, 0),
                corner_radius=3
            )

    def _save_image(self, image: np.ndarray, camera_id: str, has_bbox: bool = False):
        """
        保存图像到指定摄像头的文件夹

        Args:
            image: numpy图像数组 (H, W, 3)
            camera_id: 摄像头ID
            has_bbox: 是否包含标定框
        """
        if not self.save_images:
            return

        try:
            # 为每个摄像头创建子目录
            camera_dir = os.path.join(self.output_dir, camera_id)
            os.makedirs(camera_dir, exist_ok=True)

            # 生成文件名：时间戳_[with_bbox].jpg
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{timestamp}.jpg"
            filepath = os.path.join(camera_dir, filename)

            # OpenCV/CARLA链路中的图像是BGR，转成RGB后再交给PIL保存。
            pil_image = Image.fromarray(self._bgr_to_rgb(image))
            pil_image.save(filepath, format='JPEG', quality=95)

            print(f"✓ 已保存图像: {filepath}")
        except Exception as e:
            print(f"✗ 保存图像失败: {e}")

    @staticmethod
    def _bgr_to_rgb(image: np.ndarray) -> np.ndarray:
        """Convert BGR ndarray to RGB for PIL-based serialization."""
        if image.ndim == 3 and image.shape[2] == 3:
            return image[:, :, ::-1]
        return image

    def project_vehicle(self, vehicle_info: Dict, raw_images: Dict[str, np.ndarray]) -> Dict:
        """
        将车辆投影到所有摄像头，判断可见性并绘制标定框

        Args:
            vehicle_info: 车辆信息字典，包含：
                - location_x, location_y, location_z: 3D位置
                - rotation_pitch, rotation_yaw, rotation_roll: 旋转角度
                - length, width, height: 车辆尺寸
                - type, color, plate, intention等其他属性
            raw_images: 原始图像字典，key为camera_id，value为图像数组

        Returns:
            投影结果字典：
            {
                "visible_cameras": ["camera_1", ...],
                "projections": {
                    "camera_1": {
                        "bbox": (x_min, y_min, x_max, y_max),
                        "corners_2d": [...],
                        "image_with_bbox": np.ndarray
                    }
                },
                "in_blind_spot": False,
                "blind_spot_info": None or {...}
            }
        """
        # 提取车辆位置和姿态信息
        vehicle_location = {
            'x': vehicle_info['location_x'],
            'y': vehicle_info['location_y'],
            'z': vehicle_info['location_z']
        }

        vehicle_rotation = {
            'pitch': vehicle_info['rotation_pitch'],
            'yaw': vehicle_info['rotation_yaw'],
            'roll': vehicle_info['rotation_row']  # 注意：template.json中是rotation_row
        }

        vehicle_dimensions = {
            'length': vehicle_info['length'],
            'width': vehicle_info['width'],
            'height': vehicle_info['height']
        }

        visible_cameras = []
        projections = {}

        # 遍历所有摄像头进行投影
        for camera_id, camera_info in self.cameras.items():
            try:
                # 获取摄像头位姿
                camera_location = camera_info['location']
                camera_rotation = camera_info['rotation']
                image_size = camera_info['image_size']

                # 尝试投影车辆
                projector = self.projectors[camera_id]

                # 获取2D边界框
                bbox = projector.get_vehicle_bbox(
                    camera_location=camera_location,
                    camera_rotation=camera_rotation,
                    vehicle_location=vehicle_location,
                    vehicle_rotation=vehicle_rotation,
                    vehicle_dimensions=vehicle_dimensions,
                    image_width=image_size['width'],
                    image_height=image_size['height'],
                    clip_to_image=True
                )

                # 获取8个角点的2D坐标
                corners_2d = projector.get_vehicle_corners_2d(
                    camera_location=camera_location,
                    camera_rotation=camera_rotation,
                    vehicle_location=vehicle_location,
                    vehicle_rotation=vehicle_rotation,
                    vehicle_dimensions=vehicle_dimensions
                )

                # 在图像上绘制标定框
                if camera_id in raw_images:
                    image = raw_images[camera_id].copy()
                    visualizer = self.visualizers[camera_id]

                    # 绘制3D边界框
                    image_with_bbox = visualizer.draw_3d_bbox(
                        image=image,
                        corners_2d=corners_2d,
                        draw_corners=True
                    )

                    # 也可以绘制2D边界框作为参考
                    image_with_bbox = visualizer.draw_2d_bbox(
                        image=image_with_bbox,
                        bbox=bbox,
                        color=(255, 255, 0),  # 黄色2D框
                        thickness=1
                    )

                    # 保存带标定框的图像
                    self._save_image(image_with_bbox, camera_id, has_bbox=True)
                else:
                    image_with_bbox = None

                # 记录投影成功的摄像头
                visible_cameras.append(camera_id)
                projections[camera_id] = {
                    'bbox': bbox,
                    'corners_2d': corners_2d,
                    'image_with_bbox': image_with_bbox,
                    'camera_name': camera_info['name']
                }

            except ValueError as e:
                # 车辆不在该摄像头视野内，原始图像已经保存
                continue

        # 判断是否在监控死角
        in_blind_spot = len(visible_cameras) == 0
        blind_spot_info = None

        if in_blind_spot:
            blind_spot_info = self.analyze_blind_spot(vehicle_location)

        return {
            'visible_cameras': visible_cameras,
            'projections': projections,
            'in_blind_spot': in_blind_spot,
            'blind_spot_info': blind_spot_info
        }

    def get_camera_relationships(self) -> str:
        """
        获取摄像头之间的关系描述

        Returns:
            摄像头关系的自然语言描述
        """
        if not self.camera_relationships:
            return "摄像头之间无特殊关系配置。"

        descriptions = []
        for rel in self.camera_relationships:
            cameras = rel['cameras']
            rel_type = rel['type']
            description = rel.get('description', '')

            camera_names = [self.cameras[cid]['name'] for cid in cameras if cid in self.cameras]

            desc_text = f"{', '.join(camera_names)}: {description}"
            descriptions.append(desc_text)

        return "\n".join(descriptions)

    def analyze_blind_spot(self, vehicle_location: Dict[str, float]) -> Dict:
        """
        分析车辆在哪个盲区

        Args:
            vehicle_location: 车辆3D位置 {x, y, z}

        Returns:
            盲区分析结果：
            {
                "status": "in_blind_spot",
                "vehicle_position": {...},
                "nearest_camera": "camera_1",
                "distance_to_nearest": 15.5,
                "description": "车辆位于所有摄像头视野之外..."
            }
        """
        # 计算车辆到各摄像头的距离
        distances = {}
        for camera_id, camera_info in self.cameras.items():
            cam_loc = camera_info['location']
            dx = vehicle_location['x'] - cam_loc['x']
            dy = vehicle_location['y'] - cam_loc['y']
            dz = vehicle_location['z'] - cam_loc['z']
            distance = np.sqrt(dx**2 + dy**2 + dz**2)
            distances[camera_id] = distance

        # 找到最近的摄像头
        nearest_camera_id = min(distances, key=distances.get)
        nearest_distance = distances[nearest_camera_id]
        nearest_camera_name = self.cameras[nearest_camera_id]['name']

        # 生成描述
        description = (
            f"车辆位于所有摄像头视野之外（监控死角）。"
            f"最近的摄像头是{nearest_camera_name}，距离约{nearest_distance:.1f}米。"
            f"车辆可能位于摄像头后方等摄像头覆盖范围边界外。"
        )

        return {
            'status': 'in_blind_spot',
            'vehicle_position': vehicle_location,
            'nearest_camera': nearest_camera_id,
            'nearest_camera_name': nearest_camera_name,
            'distance_to_nearest': nearest_distance,
            'description': description
        }

    def get_camera_info(self, camera_id: str) -> Optional[Dict]:
        """
        获取指定摄像头的配置信息

        Args:
            camera_id: 摄像头ID

        Returns:
            摄像头配置信息，如果不存在则返回None
        """
        return self.cameras.get(camera_id)

    def get_all_camera_ids(self) -> List[str]:
        """
        获取所有摄像头ID列表

        Returns:
            摄像头ID列表
        """
        return list(self.cameras.keys())

    def reload_config(self):
        """重新加载摄像头配置（支持动态更新）"""
        self.cameras.clear()
        self.projectors.clear()
        self.visualizers.clear()
        self.camera_relationships.clear()

        self._load_config()
        self._initialize_projectors()
