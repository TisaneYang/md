"""
路侧智能体Agent使用示例

该示例展示如何使用RoadsideAgent进行交通场景分析，包括：
1. 基本使用流程
2. 多摄像头场景
3. 监控死角场景
4. 交通指挥指令场景
"""

import os
import sys
import numpy as np
import cv2
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.roadside_agent import RoadsideAgent


def create_test_images():
    """创建测试用的模拟图像"""
    # 创建两个1920x1080的空白图像（模拟摄像头画面）
    image1 = np.ones((1080, 1920, 3), dtype=np.uint8) * 200  # 浅灰色背景
    image2 = np.ones((1080, 1920, 3), dtype=np.uint8) * 180  # 稍深的灰色背景

    # 在图像上添加一些模拟的道路标记
    # 摄像头1：绘制道路
    cv2.rectangle(image1, (400, 0), (1520, 1080), (100, 100, 100), -1)  # 道路
    cv2.line(image1, (960, 0), (960, 1080), (255, 255, 255), 5)  # 中线

    # 摄像头2：绘制道路
    cv2.rectangle(image2, (400, 0), (1520, 1080), (100, 100, 100), -1)  # 道路
    cv2.line(image2, (960, 0), (960, 1080), (255, 255, 255), 5)  # 中线

    # 添加文字标识
    cv2.putText(image1, "Camera 1 - East View", (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.putText(image2, "Camera 2 - West View", (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    return {
        'camera_1': image1,
        'camera_2': image2
    }


def example_basic_usage():
    """示例1：基本使用流程"""
    print("\n" + "="*80)
    print("示例1：基本使用流程")
    print("="*80)

    # 1. 初始化Agent
    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )

    # 2. 准备测试数据
    raw_images = create_test_images()

    # 3. 加载车辆信息（使用template.json的格式）
    vehicle_info = {
        "type": "轿车",
        "color": "白色",
        "discription": "比亚迪秦Plus白色款，绿色牌照新能源汽车",
        "plate": "京A8694A",
        "intention": "直行通过路段",
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

    # 4. 调用Agent分析
    result = agent.analyze(
        raw_images=raw_images,
        vehicle_info=vehicle_info,
        traffic_command=None
    )

    # 5. 查看结果
    print("\n分析结果:")
    print(f"- 车辆摘要: {result['vehicle_summary']}")
    print(f"- 风险等级: {result['risk_level']}")
    print(f"- 置信度: {result['confidence']:.2f}")
    print(f"\n驾驶建议:\n{result['advice']}")

    # 6. 保存带标定框的图像
    if not result['camera_coverage']['in_blind_spot']:
        visible_cameras = result['camera_coverage']['visible_cameras']
        print(f"\n保存带标定框的图像...")
        # 注意：实际的带标定框图像在camera_manager的projections中
        # 这里只是示例，实际使用时需要从agent内部获取


def example_multi_camera():
    """示例2：多摄像头场景"""
    print("\n" + "="*80)
    print("示例2：多摄像头场景 - 车辆在多个摄像头视野内")
    print("="*80)

    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )

    raw_images = create_test_images()

    # 车辆位于两个摄像头之间，都能看到
    vehicle_info = {
        "type": "SUV",
        "color": "黑色",
        "discription": "大型SUV",
        "plate": "京B12345",
        "intention": "左转进入路口",
        "length": 5.0,
        "width": 2.0,
        "height": 1.8,
        "location_x": 10.0,  # 较近的位置
        "location_y": 0.0,   # 中间位置
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": 45.0,  # 转向
        "velocity": 25.0,
        "acceleration": -0.5
    }

    result = agent.analyze(
        raw_images=raw_images,
        vehicle_info=vehicle_info
    )

    print(f"\n可见摄像头数量: {len(result['camera_coverage']['visible_cameras'])}")
    print(f"驾驶建议:\n{result['advice']}")


def example_blind_spot():
    """示例3：监控死角场景"""
    print("\n" + "="*80)
    print("示例3：监控死角场景 - 车辆不在任何摄像头视野内")
    print("="*80)

    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )

    raw_images = create_test_images()

    # 车辆位于摄像头后方（监控死角）
    vehicle_info = {
        "type": "轿车",
        "color": "红色",
        "discription": "小型轿车",
        "plate": "京C99999",
        "intention": "直行",
        "length": 4.0,
        "width": 1.7,
        "height": 1.4,
        "location_x": -15.0,  # 负X方向，在摄像头后方
        "location_y": 0.0,
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": 180.0,
        "velocity": 40.0,
        "acceleration": 0.0
    }

    result = agent.analyze(
        raw_images=raw_images,
        vehicle_info=vehicle_info
    )

    print(f"\n监控死角状态: {result['camera_coverage']['in_blind_spot']}")
    if result['camera_coverage']['blind_spot_info']:
        print(f"盲区描述: {result['camera_coverage']['blind_spot_info']['description']}")
    print(f"\n驾驶建议:\n{result['advice']}")


def example_traffic_command():
    """示例4：交通指挥指令场景"""
    print("\n" + "="*80)
    print("示例4：交通指挥指令场景")
    print("="*80)

    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )

    raw_images = create_test_images()

    vehicle_info = {
        "type": "货车",
        "color": "蓝色",
        "discription": "中型货车",
        "plate": "京D88888",
        "intention": "直行",
        "length": 6.0,
        "width": 2.2,
        "height": 2.5,
        "location_x": 25.0,
        "location_y": 2.0,
        "location_z": 0.0,
        "rotation_row": 0.0,
        "rotation_pitch": 0.0,
        "rotation_yaw": 10.0,
        "velocity": 30.0,
        "acceleration": 0.0
    }

    # 交通指挥者发出指令
    traffic_command = "前方道路施工，请所有车辆减速慢行，注意避让施工人员和设备"

    result = agent.analyze(
        raw_images=raw_images,
        vehicle_info=vehicle_info,
        traffic_command=traffic_command
    )

    print(f"\n交通指令: {traffic_command}")
    print(f"驾驶建议:\n{result['advice']}")


def example_batch_analysis():
    """示例5：批量分析多个场景"""
    print("\n" + "="*80)
    print("示例5：批量分析多个场景")
    print("="*80)

    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )

    # 准备多个场景
    scenarios = []

    # 场景1：正常行驶
    scenarios.append({
        'raw_images': create_test_images(),
        'vehicle_info': {
            "type": "轿车", "color": "白色", "discription": "小轿车",
            "plate": "京A11111", "intention": "直行",
            "length": 4.5, "width": 1.8, "height": 1.5,
            "location_x": 20.0, "location_y": 0.0, "location_z": 0.0,
            "rotation_row": 0.0, "rotation_pitch": 0.0, "rotation_yaw": 0.0,
            "velocity": 50.0, "acceleration": 0.0
        }
    })

    # 场景2：减速行驶
    scenarios.append({
        'raw_images': create_test_images(),
        'vehicle_info': {
            "type": "SUV", "color": "黑色", "discription": "SUV",
            "plate": "京B22222", "intention": "准备右转",
            "length": 5.0, "width": 2.0, "height": 1.8,
            "location_x": 15.0, "location_y": -2.0, "location_z": 0.0,
            "rotation_row": 0.0, "rotation_pitch": 0.0, "rotation_yaw": -15.0,
            "velocity": 20.0, "acceleration": -1.0
        }
    })

    # 批量分析
    results = agent.analyze_batch(scenarios)

    print(f"\n批量分析完成，共处理 {len(results)} 个场景")
    for i, result in enumerate(results):
        if 'error' not in result:
            print(f"\n场景 {i+1}:")
            print(f"  风险等级: {result['risk_level']}")
            print(f"  建议: {result['advice'][:100]}...")


def example_camera_info():
    """示例6：查看摄像头配置信息"""
    print("\n" + "="*80)
    print("示例6：查看摄像头配置信息")
    print("="*80)

    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )

    camera_info = agent.get_camera_info()

    print("\n摄像头配置:")
    for cam_id, info in camera_info['cameras'].items():
        print(f"\n{cam_id}: {info['name']}")
        print(f"  位置: x={info['location']['x']}, y={info['location']['y']}, z={info['location']['z']}")
        print(f"  旋转: pitch={info['rotation']['pitch']}, yaw={info['rotation']['yaw']}, roll={info['rotation']['roll']}")
        print(f"  图像尺寸: {info['image_size']['width']}x{info['image_size']['height']}")

    print(f"\n摄像头关系:\n{camera_info['relationships']}")


if __name__ == '__main__':
    print("\n" + "="*80)
    print("路侧智能体Agent使用示例")
    print("="*80)

    # 检查API密钥
    if not os.environ.get('OPENAI_API_KEY') and not os.environ.get('ANTHROPIC_API_KEY'):
        print("\n警告: 未设置API密钥环境变量")
        print("请设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY")
        print("示例: export OPENAI_API_KEY='your-api-key'")
        print("\n以下示例将跳过LLM调用部分...\n")

    try:
        # 运行示例
        example_basic_usage()
        example_multi_camera()
        example_blind_spot()
        example_traffic_command()
        example_batch_analysis()
        example_camera_info()

        print("\n" + "="*80)
        print("所有示例运行完成！")
        print("="*80)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
