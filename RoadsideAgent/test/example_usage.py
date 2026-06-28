"""
车辆投影功能的使用示例
"""

import numpy as np
import cv2
from utils.vehicle_projection import VehicleProjector


def example_basic_usage():
    """基本使用示例"""

    # 1. 定义摄像头内参
    camera_intrinsics = {
        'fx': 1000.0,  # x方向焦距
        'fy': 1000.0,  # y方向焦距
        'cx': 960.0,   # 图像中心x坐标
        'cy': 540.0    # 图像中心y坐标
    }

    # 2. 创建投影器
    projector = VehicleProjector(camera_intrinsics)

    # 3. 定义摄像头位姿（路侧摄像头）
    camera_location = {'x': 0.0, 'y': 10.0, 'z': 5.0}  # 摄像头在道路旁边，高度5米
    camera_rotation = {'pitch': -15.0, 'yaw': -90.0, 'roll': 0.0}  # 俯视角度，朝向道路

    # 4. 定义车辆位姿
    vehicle_location = {'x': 20.0, 'y': 0.0, 'z': 0.0}  # 车辆在道路上
    vehicle_rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}  # 车头朝向+X

    # 5. 定义车辆尺寸
    vehicle_dimensions = {
        'length': 4.5,  # 车长（米）
        'width': 1.8,   # 车宽（米）
        'height': 1.5   # 车高（米）
    }

    # 6. 获取车辆的2D边界框
    try:
        bbox = projector.get_vehicle_bbox(
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            vehicle_location=vehicle_location,
            vehicle_rotation=vehicle_rotation,
            vehicle_dimensions=vehicle_dimensions
        )
        x_min, y_min, x_max, y_max = bbox
        print(f"车辆边界框: ({x_min}, {y_min}) -> ({x_max}, {y_max})")
        print(f"边界框宽度: {x_max - x_min}, 高度: {y_max - y_min}")

    except ValueError as e:
        print(f"投影失败: {e}")

    # 7. 获取车辆8个角点的2D坐标
    corners_2d = projector.get_vehicle_corners_2d(
        camera_location=camera_location,
        camera_rotation=camera_rotation,
        vehicle_location=vehicle_location,
        vehicle_rotation=vehicle_rotation,
        vehicle_dimensions=vehicle_dimensions
    )

    print("\n车辆8个角点的2D坐标:")
    corner_names = ['前右下', '前左下', '后左下', '后右下',
                   '前右上', '前左上', '后左上', '后右上']
    for i, (name, corner) in enumerate(zip(corner_names, corners_2d)):
        print(f"  {name}: ({corner[0]:.2f}, {corner[1]:.2f})")


def example_visualize_on_image():
    """在图像上可视化车辆边界框的示例"""

    # 创建一个空白图像（1920x1080）
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # 摄像头内参
    camera_intrinsics = {
        'fx': 1000.0,
        'fy': 1000.0,
        'cx': 960.0,
        'cy': 540.0
    }

    projector = VehicleProjector(camera_intrinsics)

    # 摄像头位姿
    camera_location = {'x': 0.0, 'y': 10.0, 'z': 5.0}
    camera_rotation = {'pitch': -15.0, 'yaw': -90.0, 'roll': 0.0}

    # 模拟多辆车
    vehicles = [
        {
            'location': {'x': 20.0, 'y': 0.0, 'z': 0.0},
            'rotation': {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0},
            'dimensions': {'length': 4.5, 'width': 1.8, 'height': 1.5},
            'color': (0, 255, 0)  # 绿色
        },
        {
            'location': {'x': 30.0, 'y': -3.5, 'z': 0.0},
            'rotation': {'pitch': 0.0, 'yaw': 5.0, 'roll': 0.0},
            'dimensions': {'length': 5.0, 'width': 2.0, 'height': 1.8},
            'color': (255, 0, 0)  # 蓝色
        },
        {
            'location': {'x': 15.0, 'y': 3.5, 'z': 0.0},
            'rotation': {'pitch': 0.0, 'yaw': -3.0, 'roll': 0.0},
            'dimensions': {'length': 4.0, 'width': 1.7, 'height': 1.4},
            'color': (0, 0, 255)  # 红色
        }
    ]

    # 在图像上绘制每辆车的边界框
    for i, vehicle in enumerate(vehicles):
        try:
            # 获取2D边界框
            bbox = projector.get_vehicle_bbox(
                camera_location=camera_location,
                camera_rotation=camera_rotation,
                vehicle_location=vehicle['location'],
                vehicle_rotation=vehicle['rotation'],
                vehicle_dimensions=vehicle['dimensions']
            )

            x_min, y_min, x_max, y_max = bbox

            # 确保坐标在图像范围内
            x_min = max(0, min(x_min, 1920))
            y_min = max(0, min(y_min, 1080))
            x_max = max(0, min(x_max, 1920))
            y_max = max(0, min(y_max, 1080))

            # 绘制边界框
            cv2.rectangle(image, (x_min, y_min), (x_max, y_max),
                         vehicle['color'], 2)

            # 添加标签
            label = f"Vehicle {i+1}"
            cv2.putText(image, label, (x_min, y_min - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, vehicle['color'], 2)

            # 获取并绘制8个角点
            corners_2d = projector.get_vehicle_corners_2d(
                camera_location=camera_location,
                camera_rotation=camera_rotation,
                vehicle_location=vehicle['location'],
                vehicle_rotation=vehicle['rotation'],
                vehicle_dimensions=vehicle['dimensions']
            )

            # 绘制角点
            for corner in corners_2d:
                x, y = int(corner[0]), int(corner[1])
                if 0 <= x < 1920 and 0 <= y < 1080:
                    cv2.circle(image, (x, y), 3, vehicle['color'], -1)

            print(f"车辆 {i+1} 边界框: ({x_min}, {y_min}) -> ({x_max}, {y_max})")

        except ValueError as e:
            print(f"车辆 {i+1} 投影失败: {e}")

    # 保存结果图像
    cv2.imwrite('vehicle_projection_result.png', image)
    print("\n结果已保存到 vehicle_projection_result.png")


def example_multiple_cameras():
    """多个摄像头视角的示例"""

    camera_intrinsics = {
        'fx': 1000.0,
        'fy': 1000.0,
        'cx': 960.0,
        'cy': 540.0
    }

    projector = VehicleProjector(camera_intrinsics)

    # 定义车辆
    vehicle_location = {'x': 20.0, 'y': 0.0, 'z': 0.0}
    vehicle_rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
    vehicle_dimensions = {'length': 4.5, 'width': 1.8, 'height': 1.5}

    # 定义多个摄像头位置
    cameras = [
        {
            'name': '路侧摄像头1（左侧）',
            'location': {'x': 0.0, 'y': 10.0, 'z': 5.0},
            'rotation': {'pitch': -15.0, 'yaw': -90.0, 'roll': 0.0}
        },
        {
            'name': '路侧摄像头2（右侧）',
            'location': {'x': 0.0, 'y': -10.0, 'z': 5.0},
            'rotation': {'pitch': -15.0, 'yaw': 90.0, 'roll': 0.0}
        },
        {
            'name': '前方摄像头',
            'location': {'x': 40.0, 'y': 0.0, 'z': 6.0},
            'rotation': {'pitch': -20.0, 'yaw': 180.0, 'roll': 0.0}
        }
    ]

    print("同一车辆在不同摄像头视角下的边界框:\n")

    for camera in cameras:
        try:
            bbox = projector.get_vehicle_bbox(
                camera_location=camera['location'],
                camera_rotation=camera['rotation'],
                vehicle_location=vehicle_location,
                vehicle_rotation=vehicle_rotation,
                vehicle_dimensions=vehicle_dimensions
            )
            x_min, y_min, x_max, y_max = bbox
            print(f"{camera['name']}:")
            print(f"  边界框: ({x_min}, {y_min}) -> ({x_max}, {y_max})")
            print(f"  尺寸: {x_max - x_min} x {y_max - y_min}\n")

        except ValueError as e:
            print(f"{camera['name']}: {e}\n")


if __name__ == '__main__':
    print("=" * 60)
    print("示例1: 基本使用")
    print("=" * 60)
    example_basic_usage()

    print("\n" + "=" * 60)
    print("示例2: 在图像上可视化")
    print("=" * 60)
    example_visualize_on_image()

    print("\n" + "=" * 60)
    print("示例3: 多摄像头视角")
    print("=" * 60)
    example_multiple_cameras()
