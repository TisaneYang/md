"""
车辆空间位置坐标到路侧摄像头画面的投影工具

该模块提供将3D空间中的车辆投影到2D摄像头图像平面的功能。
"""

import numpy as np
from typing import Dict, Tuple, List


class VehicleProjector:
    """车辆3D边界框到摄像头2D图像的投影器"""

    def __init__(self, camera_intrinsics: Dict[str, float]):
        """
        初始化投影器

        Args:
            camera_intrinsics: 摄像头内参字典，包含:
                - fx: x方向焦距
                - fy: y方向焦距
                - cx: 主点x坐标
                - cy: 主点y坐标
        """
        self.fx = camera_intrinsics['fx']
        self.fy = camera_intrinsics['fy']
        self.cx = camera_intrinsics['cx']
        self.cy = camera_intrinsics['cy']

        # 构建内参矩阵
        self.K = np.array([
            [self.fx, 0, self.cx],
            [0, self.fy, self.cy],
            [0, 0, 1]
        ])

    @staticmethod
    def euler_to_rotation_matrix(rotation: Dict[str, float]) -> np.ndarray:
        """
        将欧拉角转换为旋转矩阵

        CARLA/UE4坐标系定义：Z轴向上，+X为朝向方向，+Y为右侧
        - yaw: 绕Z轴旋转（航向角，水平面内转向）
        - pitch: 绕Y轴旋转（俯仰角，抬头低头）- CARLA中方向与标准右手系相反
        - roll: 绕X轴旋转（翻滚角，左右倾斜）- CARLA中方向与标准右手系相反

        Args:
            rotation: 欧拉角字典，包含 pitch, yaw, roll (单位：度)

        Returns:
            3x3旋转矩阵
        """
        # CARLA/UE4中pitch和roll的旋转方向与标准右手坐标系相反，需要取反
        pitch = np.radians(-rotation['pitch'])
        yaw = np.radians(rotation['yaw'])
        roll = np.radians(-rotation['roll'])

        # 绕Z轴旋转 (yaw - 航向角)
        Rz = np.array([
            [np.cos(yaw), -np.sin(yaw), 0],
            [np.sin(yaw), np.cos(yaw), 0],
            [0, 0, 1]
        ])

        # 绕Y轴旋转 (pitch - 俯仰角)
        Ry = np.array([
            [np.cos(pitch), 0, np.sin(pitch)],
            [0, 1, 0],
            [-np.sin(pitch), 0, np.cos(pitch)]
        ])

        # 绕X轴旋转 (roll - 翻滚角)
        Rx = np.array([
            [1, 0, 0],
            [0, np.cos(roll), -np.sin(roll)],
            [0, np.sin(roll), np.cos(roll)]
        ])

        # 组合旋转矩阵: 先yaw，再pitch，最后roll (ZYX顺序)
        R = Rz @ Ry @ Rx
        return R

    @staticmethod
    def get_vehicle_corners(vehicle_location: Dict[str, float],
                           vehicle_rotation: Dict[str, float],
                           vehicle_dimensions: Dict[str, float]) -> np.ndarray:
        """
        获取车辆3D边界框的8个角点坐标

        Args:
            vehicle_location: 车辆位置 {x, y, z}
            vehicle_rotation: 车辆旋转 {pitch, yaw, roll}
            vehicle_dimensions: 车辆尺寸 {length, width, height}

        Returns:
            8x3数组，每行是一个角点的世界坐标
        """
        length = vehicle_dimensions['length']
        width = vehicle_dimensions['width']
        height = vehicle_dimensions['height']

        # 在车辆局部坐标系中定义8个角点（车头朝向+X，CARLA坐标系：Y轴朝右）
        # CARLA的location是bounding box的几何中心，所以角点应该以中心为原点
        # Z方向：从 -height/2 到 +height/2
        corners_local = np.array([
            [length/2, width/2, -height/2],      # 前右下（Y正方向是右）
            [length/2, -width/2, -height/2],     # 前左下（Y负方向是左）
            [-length/2, -width/2, -height/2],    # 后左下
            [-length/2, width/2, -height/2],     # 后右下
            [length/2, width/2, height/2],       # 前右上
            [length/2, -width/2, height/2],      # 前左上
            [-length/2, -width/2, height/2],     # 后左上
            [-length/2, width/2, height/2]       # 后右上
        ])

        # 获取旋转矩阵
        R = VehicleProjector.euler_to_rotation_matrix(vehicle_rotation)

        # 旋转角点
        corners_rotated = (R @ corners_local.T).T

        # 平移到世界坐标系
        vehicle_pos = np.array([
            vehicle_location['x'],
            vehicle_location['y'],
            vehicle_location['z']
        ])
        corners_world = corners_rotated + vehicle_pos

        return corners_world

    def world_to_camera(self, points_world: np.ndarray,
                       camera_location: Dict[str, float],
                       camera_rotation: Dict[str, float]) -> np.ndarray:
        """
        将世界坐标系中的点转换到摄像头坐标系

        Args:
            points_world: Nx3数组，世界坐标系中的点
            camera_location: 摄像头位置 {x, y, z}
            camera_rotation: 摄像头旋转 {pitch, yaw, roll}

        Returns:
            Nx3数组，摄像头坐标系中的点
        """
        # 摄像头位置
        camera_pos = np.array([
            camera_location['x'],
            camera_location['y'],
            camera_location['z']
        ])

        # 世界坐标系到摄像头坐标系的旋转矩阵
        R_world_to_cam = VehicleProjector.euler_to_rotation_matrix(camera_rotation).T

        # 平移到摄像头坐标系原点
        points_translated = points_world - camera_pos

        # 旋转到摄像头坐标系
        points_camera = (R_world_to_cam @ points_translated.T).T

        return points_camera

    def project_to_image(self, points_camera: np.ndarray) -> np.ndarray:
        """
        将摄像头坐标系中的点投影到图像平面

        Args:
            points_camera: Nx3数组，摄像头坐标系中的点（X轴为摄像头朝向）

        Returns:
            Nx2数组，图像平面上的像素坐标
        """
        # 标准相机投影：使用Z坐标作为深度（摄像头朝向为+X，需要转换到标准相机坐标系）
        # 标准相机坐标系：Z轴朝前，X轴朝右，Y轴朝下
        # CARLA坐标系：X轴朝前，Y轴朝右，Z轴朝上
        # 转换：camera_standard_x = Y, camera_standard_y = -Z, camera_standard_z = X

        x_standard = points_camera[:, 1]   # 图像x方向（右）- CARLA的Y轴朝右，直接使用
        y_standard = -points_camera[:, 2]  # 图像y方向（下）- CARLA的Z轴朝上，取反得到朝下
        z_standard = points_camera[:, 0]   # 深度方向（前）- CARLA的X轴朝前

        # 投影到归一化平面
        x_normalized = x_standard / z_standard
        y_normalized = y_standard / z_standard

        # 应用内参得到像素坐标
        u = self.fx * x_normalized + self.cx
        v = self.fy * y_normalized + self.cy

        points_pixel = np.column_stack([u, v])

        return points_pixel

    def get_vehicle_bbox(self,
                        camera_location: Dict[str, float],
                        camera_rotation: Dict[str, float],
                        vehicle_location: Dict[str, float],
                        vehicle_rotation: Dict[str, float],
                        vehicle_dimensions: Dict[str, float],
                        image_width: int = None,
                        image_height: int = None,
                        clip_to_image: bool = False) -> Tuple[int, int, int, int]:
        """
        获取车辆在图像中的2D边界框

        Args:
            camera_location: 摄像头位置 {x, y, z}
            camera_rotation: 摄像头旋转 {pitch, yaw, roll}
            vehicle_location: 车辆位置 {x, y, z}
            vehicle_rotation: 车辆旋转 {pitch, yaw, roll}
            vehicle_dimensions: 车辆尺寸 {length, width, height}
            image_width: 图像宽度（用于裁剪边界框）
            image_height: 图像高度（用于裁剪边界框）
            clip_to_image: 是否将边界框裁剪到图像范围内

        Returns:
            (x_min, y_min, x_max, y_max) 边界框坐标
        """
        # 获取车辆8个角点的世界坐标
        corners_world = self.get_vehicle_corners(
            vehicle_location, vehicle_rotation, vehicle_dimensions
        )

        # 转换到摄像头坐标系
        corners_camera = self.world_to_camera(
            corners_world, camera_location, camera_rotation
        )

        # 过滤掉在摄像头后面的点
        valid_mask = corners_camera[:, 0] > 0  # X轴正方向为摄像头朝向
        if not np.any(valid_mask):
            raise ValueError("车辆不在摄像头视野内")

        corners_camera_valid = corners_camera[valid_mask]

        # 投影到图像平面
        corners_2d = self.project_to_image(corners_camera_valid)

        # 计算包围所有投影点的最小边界框
        x_min = int(np.floor(corners_2d[:, 0].min()))
        y_min = int(np.floor(corners_2d[:, 1].min()))
        x_max = int(np.ceil(corners_2d[:, 0].max()))
        y_max = int(np.ceil(corners_2d[:, 1].max()))

        # 如果需要，裁剪到图像范围内
        if clip_to_image and image_width is not None and image_height is not None:
            x_min = max(0, min(x_min, image_width))
            y_min = max(0, min(y_min, image_height))
            x_max = max(0, min(x_max, image_width))
            y_max = max(0, min(y_max, image_height))

        return (x_min, y_min, x_max, y_max)

    def get_vehicle_corners_2d(self,
                              camera_location: Dict[str, float],
                              camera_rotation: Dict[str, float],
                              vehicle_location: Dict[str, float],
                              vehicle_rotation: Dict[str, float],
                              vehicle_dimensions: Dict[str, float]) -> List[Tuple[float, float]]:
        """
        获取车辆8个角点在图像中的投影坐标

        Args:
            camera_location: 摄像头位置 {x, y, z}
            camera_rotation: 摄像头旋转 {pitch, yaw, roll}
            vehicle_location: 车辆位置 {x, y, z}
            vehicle_rotation: 车辆旋转 {pitch, yaw, roll}
            vehicle_dimensions: 车辆尺寸 {length, width, height}

        Returns:
            8个角点的2D坐标列表
        """
        # 获取车辆8个角点的世界坐标
        corners_world = self.get_vehicle_corners(
            vehicle_location, vehicle_rotation, vehicle_dimensions
        )

        # 转换到摄像头坐标系
        corners_camera = self.world_to_camera(
            corners_world, camera_location, camera_rotation
        )

        # 投影到图像平面
        corners_2d = self.project_to_image(corners_camera)

        return [(float(x), float(y)) for x, y in corners_2d]
