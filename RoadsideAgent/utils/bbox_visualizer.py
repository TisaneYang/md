"""
边界框可视化工具

该模块提供在图像上绘制车辆标定框的功能。
"""

import cv2
import numpy as np
from typing import Tuple, List, Union


class BBoxVisualizer:
    """边界框可视化器"""

    def __init__(self,
                 box_color: Tuple[int, int, int] = (0, 255, 0),
                 box_thickness: int = 2,
                 corner_color: Tuple[int, int, int] = (255, 0, 0),
                 corner_radius: int = 3):
        """
        初始化可视化器

        Args:
            box_color: 边界框颜色 (B, G, R)
            box_thickness: 边界框线条粗细
            corner_color: 角点颜色 (B, G, R)
            corner_radius: 角点半径
        """
        self.box_color = box_color
        self.box_thickness = box_thickness
        self.corner_color = corner_color
        self.corner_radius = corner_radius

    def draw_2d_bbox(self,
                     image: np.ndarray,
                     bbox: Tuple[int, int, int, int],
                     color: Tuple[int, int, int] = None,
                     thickness: int = None) -> np.ndarray:
        """
        在图像上绘制2D边界框

        Args:
            image: 输入图像 (H, W, 3)
            bbox: 边界框坐标 (x_min, y_min, x_max, y_max)
            color: 边界框颜色，如果为None则使用默认颜色
            thickness: 线条粗细，如果为None则使用默认粗细

        Returns:
            绘制了边界框的图像
        """
        img_copy = image.copy()
        x_min, y_min, x_max, y_max = bbox

        color = color if color is not None else self.box_color
        thickness = thickness if thickness is not None else self.box_thickness

        cv2.rectangle(img_copy, (x_min, y_min), (x_max, y_max), color, thickness)

        return img_copy

    def draw_3d_bbox(self,
                     image: np.ndarray,
                     corners_2d: List[Tuple[float, float]],
                     color: Tuple[int, int, int] = None,
                     thickness: int = None,
                     draw_corners: bool = True) -> np.ndarray:
        """
        在图像上绘制3D边界框的投影

        Args:
            image: 输入图像 (H, W, 3)
            corners_2d: 8个角点的2D坐标列表，顺序为:
                        [前右下, 前左下, 后左下, 后右下, 前右上, 前左上, 后左上, 后右上]
            color: 边界框颜色，如果为None则使用默认颜色
            thickness: 线条粗细，如果为None则使用默认粗细
            draw_corners: 是否绘制角点

        Returns:
            绘制了3D边界框的图像
        """
        img_copy = image.copy()

        color = color if color is not None else self.box_color
        thickness = thickness if thickness is not None else self.box_thickness

        # 转换为整数坐标
        corners = [(int(x), int(y)) for x, y in corners_2d]

        # 定义边界框的12条边（连接关系）
        # 底面4条边
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),  # 底面
            (4, 5), (5, 6), (6, 7), (7, 4),  # 顶面
            (0, 4), (1, 5), (2, 6), (3, 7)   # 垂直边
        ]

        # 绘制边
        for start_idx, end_idx in edges:
            cv2.line(img_copy, corners[start_idx], corners[end_idx], color, thickness)

        # 绘制角点
        if draw_corners:
            for corner in corners:
                cv2.circle(img_copy, corner, self.corner_radius, self.corner_color, -1)

        return img_copy

    def draw_multiple_bboxes(self,
                            image: np.ndarray,
                            bboxes: List[Union[Tuple[int, int, int, int], List[Tuple[float, float]]]],
                            bbox_type: str = '2d',
                            colors: List[Tuple[int, int, int]] = None) -> np.ndarray:
        """
        在图像上绘制多个边界框

        Args:
            image: 输入图像 (H, W, 3)
            bboxes: 边界框列表
                    - 如果bbox_type='2d': 每个元素为 (x_min, y_min, x_max, y_max)
                    - 如果bbox_type='3d': 每个元素为8个角点的2D坐标列表
            bbox_type: 边界框类型，'2d' 或 '3d'
            colors: 每个边界框的颜色列表，如果为None则全部使用默认颜色

        Returns:
            绘制了所有边界框的图像
        """
        img_copy = image.copy()

        for i, bbox in enumerate(bboxes):
            color = colors[i] if colors is not None and i < len(colors) else None

            if bbox_type == '2d':
                img_copy = self.draw_2d_bbox(img_copy, bbox, color=color)
            elif bbox_type == '3d':
                img_copy = self.draw_3d_bbox(img_copy, bbox, color=color)
            else:
                raise ValueError(f"不支持的边界框类型: {bbox_type}")

        return img_copy
