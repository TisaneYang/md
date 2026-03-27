"""
基础功能测试脚本

测试路侧智能体的核心功能，不需要LLM API
"""

import sys
import numpy as np
import cv2

sys.path.insert(0, '.')

from agent.camera_manager import CameraManager
from agent.input_processor import InputProcessor


def test_camera_manager():
    """测试摄像头管理器"""
    print("\n" + "="*60)
    print("测试1: 摄像头管理器")
    print("="*60)

    # 初始化摄像头管理器，启用图像保存
    camera_manager = CameraManager('config/camera_config.yaml', save_images=True, output_dir='debug/test_images')

    print(f"✓ 摄像头管理器初始化成功")
    print(f"  摄像头数量: {len(camera_manager.get_all_camera_ids())}")

    # 获取摄像头信息
    camera_ids = camera_manager.get_all_camera_ids()
    for cam_id in camera_ids:
        info = camera_manager.get_camera_info(cam_id)
        print(f"  - {cam_id}: {info['name']}")

    # 测试摄像头关系
    relationships = camera_manager.get_camera_relationships()
    print(f"\n摄像头关系:\n{relationships}")

    return camera_manager


def test_vehicle_projection(camera_manager):
    """测试车辆投影功能"""
    print("\n" + "="*60)
    print("测试2: 车辆投影功能")
    print("="*60)
    
    # 创建测试图像
    raw_images = {
        'camera_1': np.ones((1080, 1920, 3), dtype=np.uint8) * 200,
        'camera_2': np.ones((1080, 1920, 3), dtype=np.uint8) * 180
    }
    
    # 测试车辆信息（在视野内）
    vehicle_info = {
        "type": "轿车",
        "color": "白色",
        "discription": "测试车辆",
        "plate": "京A12345",
        "intention": "直行",
        "length": 4.5,
        "width": 1.8,
        "height": 1.5,
        "location_x": 20.0,
        "location_y": 0.0,
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": 0.0,
        "velocity": 45.5,
        "acceleration": 0.2
    }
    
    # 投影车辆
    result = camera_manager.project_vehicle(vehicle_info, raw_images)
    
    if result['in_blind_spot']:
        print("✗ 车辆在监控死角")
        print(f"  {result['blind_spot_info']['description']}")
    else:
        print(f"✓ 车辆投影成功")
        print(f"  可见摄像头: {result['visible_cameras']}")
        for cam_id in result['visible_cameras']:
            bbox = result['projections'][cam_id]['bbox']
            print(f"  - {cam_id}: bbox={bbox}")
            
            # 保存带标定框的图像
            image_with_bbox = result['projections'][cam_id]['image_with_bbox']
            if image_with_bbox is not None:
                output_path = f'test_output_{cam_id}.jpg'
                cv2.imwrite(output_path, image_with_bbox)
                print(f"    已保存图像: {output_path}")
    
    return result


def test_blind_spot_detection(camera_manager):
    """测试监控死角检测"""
    print("\n" + "="*60)
    print("测试3: 监控死角检测")
    print("="*60)
    
    # 创建测试图像
    raw_images = {
        'camera_1': np.ones((1080, 1920, 3), dtype=np.uint8) * 200,
        'camera_2': np.ones((1080, 1920, 3), dtype=np.uint8) * 180
    }
    
    # 车辆在摄像头后方（监控死角）
    vehicle_info = {
        "type": "轿车",
        "color": "红色",
        "discription": "测试车辆",
        "plate": "京B99999",
        "intention": "直行",
        "length": 4.0,
        "width": 1.7,
        "height": 1.4,
        "location_x": -15.0,  # 负X方向
        "location_y": 0.0,
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": 180.0,
        "velocity": 40.0,
        "acceleration": 0.0
    }
    
    # 投影车辆
    result = camera_manager.project_vehicle(vehicle_info, raw_images)
    
    if result['in_blind_spot']:
        print("✓ 监控死角检测成功")
        blind_spot_info = result['blind_spot_info']
        print(f"  状态: {blind_spot_info['status']}")
        print(f"  最近摄像头: {blind_spot_info['nearest_camera_name']}")
        print(f"  距离: {blind_spot_info['distance_to_nearest']:.1f}米")
        print(f"  描述: {blind_spot_info['description']}")
    else:
        print("✗ 应该检测到监控死角，但车辆仍可见")
    
    return result


def test_input_processor():
    """测试输入处理器"""
    print("\n" + "="*60)
    print("测试4: 输入处理器")
    print("="*60)
    
    processor = InputProcessor()
    
    # 测试车辆信息解析
    vehicle_data = {
        "type": "SUV",
        "color": "黑色",
        "discription": "大型SUV",
        "plate": "京C88888",
        "intention": "左转",
        "length": 5.0,
        "width": 2.0,
        "height": 1.8,
        "location_x": 15.0,
        "location_y": -2.0,
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": -15.0,
        "velocity": 25.0,
        "acceleration": -0.5
    }
    
    parsed_info = processor.parse_vehicle_info(vehicle_data)
    print("✓ 车辆信息解析成功")
    
    # 生成车辆摘要
    summary = processor.format_vehicle_summary(parsed_info)
    print(f"  车辆摘要: {summary}")
    
    # 测试交通指令解析
    command = "前方道路施工，请减速慢行"
    command_info = processor.parse_traffic_command(command)
    print(f"\n✓ 交通指令解析成功")
    print(f"  指令: {command_info['command']}")
    print(f"  优先级: {command_info['priority']}")
    
    return processor


def test_multi_camera_scenario(camera_manager):
    """测试多摄像头场景"""
    print("\n" + "="*60)
    print("测试5: 多摄像头场景")
    print("="*60)
    
    # 创建测试图像
    raw_images = {
        'camera_1': np.ones((1080, 1920, 3), dtype=np.uint8) * 200,
        'camera_2': np.ones((1080, 1920, 3), dtype=np.uint8) * 180
    }
    
    # 车辆位于中间位置，可能被两个摄像头看到
    vehicle_info = {
        "type": "货车",
        "color": "蓝色",
        "discription": "中型货车",
        "plate": "京D77777",
        "intention": "直行",
        "length": 6.0,
        "width": 2.2,
        "height": 2.5,
        "location_x": 10.0,
        "location_y": 0.0,
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": 0.0,
        "velocity": 30.0,
        "acceleration": 0.0
    }
    
    # 投影车辆
    result = camera_manager.project_vehicle(vehicle_info, raw_images)
    
    if not result['in_blind_spot']:
        num_cameras = len(result['visible_cameras'])
        print(f"✓ 车辆在 {num_cameras} 个摄像头视野内")
        for cam_id in result['visible_cameras']:
            cam_name = result['projections'][cam_id]['camera_name']
            bbox = result['projections'][cam_id]['bbox']
            print(f"  - {cam_name}: bbox={bbox}")
    else:
        print("✗ 车辆不在任何摄像头视野内")
    
    return result


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("路侧智能体基础功能测试")
    print("="*60)
    
    try:
        # 测试1: 摄像头管理器
        camera_manager = test_camera_manager()
        
        # 测试2: 车辆投影
        test_vehicle_projection(camera_manager)
        
        # 测试3: 监控死角检测
        test_blind_spot_detection(camera_manager)
        
        # 测试4: 输入处理器
        test_input_processor()
        
        # 测试5: 多摄像头场景
        test_multi_camera_scenario(camera_manager)
        
        print("\n" + "="*60)
        print("所有测试通过！✓")
        print("="*60)
        print("\n提示: 要测试完整的LLM功能，请设置API密钥并运行:")
        print("  python examples/agent_usage_example.py")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
