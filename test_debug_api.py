"""
测试RoadsideAgent调试API

该脚本测试 /debug/save_bbox 接口，验证图像保存和标定框绘制功能
"""

import sys
import json
import numpy as np
import cv2
import requests
import time

sys.path.insert(0, '.')


def test_debug_api():
    """测试调试API"""
    print("\n" + "="*60)
    print("测试RoadsideAgent调试API")
    print("="*60)

    # 创建测试图像（灰色背景）
    test_image = np.ones((600, 800, 3), dtype=np.uint8) * 200

    # 创建车辆信息
    vehicle_info = {
        'type': 'sedan',
        'color': 'white',
        'discription': 'Test vehicle for debug API',
        'plate': 'DEBUG001',
        'intention': 'straight',
        'length': 4.5,
        'width': 1.8,
        'height': 1.5,
        'location_x': 20.0,
        'location_y': 0.0,
        'location_z': 0.0,
        'rotation_row': 0.0,
        'rotation_pitch': 0.0,
        'rotation_yaw': 0.0,
        'velocity': 45.5,
        'acceleration': 0.2
    }

    # 转换图像为JPEG字节
    _, img_encoded = cv2.imencode('.jpg', test_image)
    img_bytes = img_encoded.tobytes()

    # 测试front摄像头
    print("\n[1/2] 测试front摄像头...")
    files = {'image': ('test_front.jpg', img_bytes, 'image/jpeg')}
    data = {
        'camera_id': 'front',
        'vehicle_info': json.dumps(vehicle_info)
    }

    try:
        response = requests.post(
            'http://0.0.0.0:5000/debug/save_bbox',
            files=files,
            data=data,
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✓ 请求成功")
            print(f"  状态: {result['status']}")
            print(f"  摄像头ID: {result['camera_id']}")
            print(f"  图像尺寸: {result['image_shape']}")
            print(f"  可见摄像头: {result['visible_cameras']}")
            print(f"  在盲区: {result['in_blind_spot']}")
            print(f"  消息: {result['message']}")
        else:
            print(f"✗ 请求失败: HTTP {response.status_code}")
            print(f"  响应: {response.text}")
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务器")
        print("  请先启动服务器: cd RoadsideAgent && python server/main.py")
        return False
    except Exception as e:
        print(f"✗ 请求失败: {e}")
        return False

    time.sleep(0.5)

    # 测试rear摄像头
    print("\n[2/2] 测试rear摄像头...")
    files = {'image': ('test_rear.jpg', img_bytes, 'image/jpeg')}
    data = {
        'camera_id': 'rear',
        'vehicle_info': json.dumps(vehicle_info)
    }

    try:
        response = requests.post(
            'http://0.0.0.0:5000/debug/save_bbox',
            files=files,
            data=data,
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✓ 请求成功")
            print(f"  状态: {result['status']}")
            print(f"  摄像头ID: {result['camera_id']}")
            print(f"  图像尺寸: {result['image_shape']}")
            print(f"  可见摄像头: {result['visible_cameras']}")
            print(f"  在盲区: {result['in_blind_spot']}")
            print(f"  消息: {result['message']}")
        else:
            print(f"✗ 请求失败: HTTP {response.status_code}")
            print(f"  响应: {response.text}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
        return False

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60)
    print("\n检查保存的图像:")
    print("  ls -lh debug/server_images/front/")
    print("  ls -lh debug/server_images/rear/")
    print("="*60)

    return True


if __name__ == '__main__':
    success = test_debug_api()
    sys.exit(0 if success else 1)
