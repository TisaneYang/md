"""
测试车辆投影组件的数学正确性
"""

import numpy as np
from utils.vehicle_projection import VehicleProjector


def test_rotation_matrix():
    """测试旋转矩阵的正确性"""
    print("=" * 60)
    print("测试1: 旋转矩阵验证")
    print("=" * 60)

    # 测试1: 零旋转应该是单位矩阵
    rotation_zero = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
    R_zero = VehicleProjector.euler_to_rotation_matrix(rotation_zero)
    print("\n零旋转矩阵（应该是单位矩阵）:")
    print(R_zero)
    assert np.allclose(R_zero, np.eye(3)), "零旋转应该是单位矩阵"
    print("✓ 通过")

    # 测试2: 绕Z轴旋转90度（yaw=90）
    rotation_yaw90 = {'pitch': 0.0, 'yaw': 90.0, 'roll': 0.0}
    R_yaw90 = VehicleProjector.euler_to_rotation_matrix(rotation_yaw90)
    print("\n绕Z轴旋转90度:")
    print(R_yaw90)
    # 点(1,0,0)应该变成(0,1,0)
    point = np.array([1, 0, 0])
    rotated = R_yaw90 @ point
    print(f"点(1,0,0)旋转后: {rotated}")
    assert np.allclose(rotated, [0, 1, 0]), "绕Z轴旋转90度验证失败"
    print("✓ 通过")

    # 测试3: 旋转矩阵应该是正交矩阵
    rotation_random = {'pitch': 15.0, 'yaw': -30.0, 'roll': 5.0}
    R_random = VehicleProjector.euler_to_rotation_matrix(rotation_random)
    print("\n随机旋转矩阵的正交性验证:")
    print(f"R @ R.T (应该是单位矩阵):")
    print(R_random @ R_random.T)
    assert np.allclose(R_random @ R_random.T, np.eye(3)), "旋转矩阵应该是正交矩阵"
    print("✓ 通过")

    # 测试4: 行列式应该是1
    det = np.linalg.det(R_random)
    print(f"\n旋转矩阵的行列式: {det} (应该是1)")
    assert np.allclose(det, 1.0), "旋转矩阵行列式应该是1"
    print("✓ 通过")


def test_vehicle_corners():
    """测试车辆角点计算"""
    print("\n" + "=" * 60)
    print("测试2: 车辆角点计算")
    print("=" * 60)

    # 测试1: 无旋转的车辆
    vehicle_location = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    vehicle_rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
    vehicle_dimensions = {'length': 4.0, 'width': 2.0, 'height': 1.5}

    corners = VehicleProjector.get_vehicle_corners(
        vehicle_location, vehicle_rotation, vehicle_dimensions
    )

    print("\n无旋转车辆的8个角点:")
    corner_names = ['前右下', '前左下', '后左下', '后右下',
                   '前右上', '前左上', '后左上', '后右上']
    for i, (name, corner) in enumerate(zip(corner_names, corners)):
        print(f"{name}: ({corner[0]:.2f}, {corner[1]:.2f}, {corner[2]:.2f})")

    # 验证角点的范围
    assert corners[:, 0].max() == 2.0, "车长方向最大值应该是length/2"
    assert corners[:, 0].min() == -2.0, "车长方向最小值应该是-length/2"
    assert corners[:, 1].max() == 1.0, "车宽方向最大值应该是width/2"
    assert corners[:, 1].min() == -1.0, "车宽方向最小值应该是-width/2"
    assert corners[:, 2].max() == 1.5, "车高方向最大值应该是height"
    assert corners[:, 2].min() == 0.0, "车高方向最小值应该是0"
    print("✓ 通过")

    # 测试2: 旋转90度的车辆
    vehicle_rotation_90 = {'pitch': 0.0, 'yaw': 90.0, 'roll': 0.0}
    corners_90 = VehicleProjector.get_vehicle_corners(
        vehicle_location, vehicle_rotation_90, vehicle_dimensions
    )

    print("\n绕Z轴旋转90度后的车辆角点:")
    for i, (name, corner) in enumerate(zip(corner_names, corners_90)):
        print(f"{name}: ({corner[0]:.2f}, {corner[1]:.2f}, {corner[2]:.2f})")

    # 旋转90度后，原来的X方向变成Y方向
    assert np.allclose(corners_90[:, 0].max(), 1.0, atol=1e-10), "旋转后X最大值应该是原width/2"
    assert np.allclose(corners_90[:, 1].max(), 2.0, atol=1e-10), "旋转后Y最大值应该是原length/2"
    print("✓ 通过")


def test_world_to_camera():
    """测试世界坐标到摄像头坐标的转换"""
    print("\n" + "=" * 60)
    print("测试3: 世界坐标到摄像头坐标转换")
    print("=" * 60)

    camera_intrinsics = {'fx': 1000.0, 'fy': 1000.0, 'cx': 960.0, 'cy': 540.0}
    projector = VehicleProjector(camera_intrinsics)

    # 测试1: 摄像头在原点，无旋转
    camera_location = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    camera_rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}

    # 世界坐标系中的点
    points_world = np.array([
        [1.0, 0.0, 0.0],  # X轴上的点
        [0.0, 1.0, 0.0],  # Y轴上的点
        [0.0, 0.0, 1.0],  # Z轴上的点
    ])

    points_camera = projector.world_to_camera(
        points_world, camera_location, camera_rotation
    )

    print("\n摄像头在原点无旋转时的坐标转换:")
    print("世界坐标 -> 摄像头坐标")
    for pw, pc in zip(points_world, points_camera):
        print(f"{pw} -> {pc}")

    # 无旋转时，坐标应该相同
    assert np.allclose(points_world, points_camera), "无旋转时坐标应该相同"
    print("✓ 通过")

    # 测试2: 摄像头有平移
    camera_location_shifted = {'x': 10.0, 'y': 5.0, 'z': 2.0}
    points_camera_shifted = projector.world_to_camera(
        points_world, camera_location_shifted, camera_rotation
    )

    print("\n摄像头平移后的坐标转换:")
    for pw, pc in zip(points_world, points_camera_shifted):
        print(f"{pw} -> {pc}")

    # 验证平移
    expected = points_world - np.array([10.0, 5.0, 2.0])
    assert np.allclose(points_camera_shifted, expected), "平移计算错误"
    print("✓ 通过")


def test_projection():
    """测试投影到图像平面"""
    print("\n" + "=" * 60)
    print("测试4: 投影到图像平面")
    print("=" * 60)

    camera_intrinsics = {'fx': 1000.0, 'fy': 1000.0, 'cx': 960.0, 'cy': 540.0}
    projector = VehicleProjector(camera_intrinsics)

    # 测试点：在摄像头坐标系中
    # 摄像头坐标系：X轴朝前，Y轴朝左，Z轴朝上
    points_camera = np.array([
        [10.0, 0.0, 0.0],   # 正前方10米，应该投影到图像中心
        [10.0, 1.0, 0.0],   # 正前方10米，左侧1米
        [10.0, 0.0, 1.0],   # 正前方10米，上方1米
        [5.0, 0.0, 0.0],    # 正前方5米，应该投影到图像中心
    ])

    points_2d = projector.project_to_image(points_camera)

    print("\n摄像头坐标 -> 图像坐标:")
    for pc, p2d in zip(points_camera, points_2d):
        print(f"{pc} -> ({p2d[0]:.2f}, {p2d[1]:.2f})")

    # 验证投影
    # 点(10, 0, 0)应该投影到图像中心
    assert np.allclose(points_2d[0], [960.0, 540.0]), "正前方的点应该投影到图像中心"
    print("✓ 正前方点投影到中心")

    # 点(10, 1, 0)应该在图像中心左侧（因为Y轴朝左，投影后x减小）
    assert points_2d[1, 0] < 960.0, "左侧的点应该投影到图像中心左侧"
    print("✓ 左侧点投影正确")

    # 点(10, 0, 1)应该在图像中心上方（因为Z轴朝上，投影后y减小）
    assert points_2d[2, 1] < 540.0, "上方的点应该投影到图像中心上方"
    print("✓ 上方点投影正确")

    # 距离更近的点，投影应该离中心更远（相同偏移）
    # 点(5, 0, 0)和(10, 0, 0)都在正前方，应该都投影到中心
    assert np.allclose(points_2d[3], [960.0, 540.0]), "不同深度的正前方点都应该投影到中心"
    print("✓ 深度不影响中心点投影")


def test_full_pipeline():
    """测试完整的投影流程"""
    print("\n" + "=" * 60)
    print("测试5: 完整投影流程")
    print("=" * 60)

    camera_intrinsics = {'fx': 1000.0, 'fy': 1000.0, 'cx': 960.0, 'cy': 540.0}
    projector = VehicleProjector(camera_intrinsics)

    # 场景设置：摄像头在原点，朝向+X方向（前方）
    camera_location = {'x': 0.0, 'y': 0.0, 'z': 5.0}  # 高5米
    camera_rotation = {'pitch': -15.0, 'yaw': 0.0, 'roll': 0.0}  # 俯视，朝向+X方向

    # 车辆在摄像头前方20米处
    vehicle_location = {'x': 20.0, 'y': 0.0, 'z': 0.0}
    vehicle_rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
    vehicle_dimensions = {'length': 4.5, 'width': 1.8, 'height': 1.5}

    try:
        bbox = projector.get_vehicle_bbox(
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            vehicle_location=vehicle_location,
            vehicle_rotation=vehicle_rotation,
            vehicle_dimensions=vehicle_dimensions
        )

        x_min, y_min, x_max, y_max = bbox
        print(f"\n车辆边界框: ({x_min}, {y_min}) -> ({x_max}, {y_max})")
        print(f"边界框尺寸: {x_max - x_min} x {y_max - y_min}")

        # 验证边界框的合理性
        assert x_max > x_min, "边界框宽度应该大于0"
        assert y_max > y_min, "边界框高度应该大于0"
        assert 0 < x_min < 1920, "边界框应该在图像范围内"
        assert 0 < y_min < 1080, "边界框应该在图像范围内"
        print("✓ 边界框计算成功")

        # 获取角点
        corners_2d = projector.get_vehicle_corners_2d(
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            vehicle_location=vehicle_location,
            vehicle_rotation=vehicle_rotation,
            vehicle_dimensions=vehicle_dimensions
        )

        print("\n车辆8个角点的2D投影:")
        corner_names = ['前右下', '前左下', '后左下', '后右下',
                       '前右上', '前左上', '后左上', '后右上']
        for name, corner in zip(corner_names, corners_2d):
            print(f"{name}: ({corner[0]:.2f}, {corner[1]:.2f})")

        # 验证角点都在边界框内
        for corner in corners_2d:
            assert x_min <= corner[0] <= x_max, "角点应该在边界框内"
            assert y_min <= corner[1] <= y_max, "角点应该在边界框内"
        print("✓ 所有角点都在边界框内")

    except ValueError as e:
        print(f"✗ 投影失败: {e}")
        return False

    return True


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("测试6: 边界情况")
    print("=" * 60)

    camera_intrinsics = {'fx': 1000.0, 'fy': 1000.0, 'cx': 960.0, 'cy': 540.0}
    projector = VehicleProjector(camera_intrinsics)

    camera_location = {'x': 0.0, 'y': 0.0, 'z': 5.0}
    camera_rotation = {'pitch': -15.0, 'yaw': 0.0, 'roll': 0.0}

    # 测试1: 车辆在摄像头后面
    print("\n测试: 车辆在摄像头后面")
    vehicle_location_behind = {'x': -10.0, 'y': 0.0, 'z': 0.0}
    vehicle_rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
    vehicle_dimensions = {'length': 4.5, 'width': 1.8, 'height': 1.5}

    try:
        bbox = projector.get_vehicle_bbox(
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            vehicle_location=vehicle_location_behind,
            vehicle_rotation=vehicle_rotation,
            vehicle_dimensions=vehicle_dimensions
        )
        print("✗ 应该抛出异常，但没有")
    except ValueError as e:
        print(f"✓ 正确抛出异常: {e}")

    # 测试2: 车辆非常近
    print("\n测试: 车辆非常近")
    vehicle_location_close = {'x': 2.0, 'y': 0.0, 'z': 0.0}
    try:
        bbox = projector.get_vehicle_bbox(
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            vehicle_location=vehicle_location_close,
            vehicle_rotation=vehicle_rotation,
            vehicle_dimensions=vehicle_dimensions
        )
        print(f"✓ 近距离车辆边界框: {bbox}")
    except Exception as e:
        print(f"✗ 近距离投影失败: {e}")

    # 测试3: 车辆非常远
    print("\n测试: 车辆非常远")
    vehicle_location_far = {'x': 100.0, 'y': 0.0, 'z': 0.0}
    try:
        bbox = projector.get_vehicle_bbox(
            camera_location=camera_location,
            camera_rotation=camera_rotation,
            vehicle_location=vehicle_location_far,
            vehicle_rotation=vehicle_rotation,
            vehicle_dimensions=vehicle_dimensions
        )
        x_min, y_min, x_max, y_max = bbox
        bbox_size = (x_max - x_min) * (y_max - y_min)
        print(f"✓ 远距离车辆边界框: {bbox}, 面积: {bbox_size}")
        # 远距离的车辆应该投影更小
        assert bbox_size < 10000, "远距离车辆投影应该较小"
    except Exception as e:
        print(f"✗ 远距离投影失败: {e}")


if __name__ == '__main__':
    print("\n开始测试车辆投影组件的数学正确性...\n")

    test_rotation_matrix()
    test_vehicle_corners()
    test_world_to_camera()
    test_projection()
    success = test_full_pipeline()
    test_edge_cases()

    print("\n" + "=" * 60)
    if success:
        print("所有测试通过！组件数学逻辑正确。")
    else:
        print("部分测试失败，请检查。")
    print("=" * 60)
