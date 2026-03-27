"""
路侧智能体服务端

接收来自路侧摄像头、车端和交通指挥者的数据，
调用Agent生成驾驶建议并推送到车端。
"""

import os
import sys
import io
import yaml
import requests
import numpy as np
import cv2
import asyncio
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.data_manager import DataManager
from agent.roadside_agent import RoadsideAgent

app = FastAPI(title="路侧智能体服务端", version="1.0.0")

# 全局变量
data_manager = DataManager()
agent: Optional[RoadsideAgent] = None
config: Dict = {}
periodic_task: Optional[asyncio.Task] = None
periodic_enabled: bool = False


def load_config(config_path: str = "config/server_config.yaml") -> Dict:
    """加载服务端配置"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {
        "server": {"host": "0.0.0.0", "port": 5000},
        "vehicle": {"ip": "localhost", "port": 8000}
    }


def init_agent():
    """初始化Agent"""
    global agent
    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml',
        save_images=True,  # 启用图像保存用于调试
        output_dir='debug/server_images'
    )


async def periodic_analysis_task():
    """定期分析任务"""
    global periodic_enabled

    # 读取配置
    agent_config_path = 'config/agent_config.yaml'
    with open(agent_config_path, 'r', encoding='utf-8') as f:
        agent_config = yaml.safe_load(f)

    interval = agent_config.get('agent', {}).get('periodic_trigger', {}).get('interval', 3)
    skip_if_no_vehicle = agent_config.get('agent', {}).get('periodic_trigger', {}).get('skip_if_no_vehicle', True)

    print(f"定期分析任务已启动，间隔: {interval}秒")

    while periodic_enabled:
        try:
            await asyncio.sleep(interval)

            if not periodic_enabled:
                break

            # 获取缓存数据
            raw_images = data_manager.get_images()
            vehicle_info = data_manager.get_vehicle_info()
            traffic_command = data_manager.get_traffic_command()

            # 检查是否有必要的数据
            if not raw_images:
                print("[定期分析] 跳过：没有可用的摄像头图片")
                continue

            if skip_if_no_vehicle and not vehicle_info:
                print("[定期分析] 跳过：没有车辆信息")
                continue

            # 调用Agent分析
            print(f"\n[定期分析] 开始分析...")
            result = agent.analyze(
                raw_images=raw_images,
                vehicle_info=vehicle_info,
                traffic_command=traffic_command
            )

            # 发送驾驶建议到车端
            vehicle_ip = config.get("vehicle", {}).get("ip", "localhost")
            vehicle_port = config.get("vehicle", {}).get("port", 8000)

            try:
                resp = requests.post(
                    f"http://{vehicle_ip}:{vehicle_port}/instruct",
                    json={"instruction": result['advice']},
                    timeout=5
                )
                send_status = "success" if resp.status_code == 200 else "failed"
                print(f"[定期分析] 建议已发送到车端: {send_status}")
            except Exception as e:
                print(f"[定期分析] 发送到车端失败: {str(e)}")

        except Exception as e:
            print(f"[定期分析] 分析失败: {str(e)}")

    print("定期分析任务已停止")


# 请求模型
class VehicleInfoRequest(BaseModel):
    type: str
    color: str
    discription: Optional[str] = ""
    plate: str
    intention: str
    length: float
    width: float
    height: float
    location_x: float
    location_y: float
    location_z: float
    rotation_row: float
    rotation_pitch: float
    rotation_yaw: float
    velocity: float
    acceleration: float


class TrafficCommandRequest(BaseModel):
    command: str


# API端点
@app.on_event("startup")
async def startup_event():
    """服务启动时初始化"""
    global config, periodic_enabled, periodic_task
    config = load_config()
    init_agent()

    # 读取agent配置，检查是否启用定期触发
    agent_config_path = 'config/agent_config.yaml'
    with open(agent_config_path, 'r', encoding='utf-8') as f:
        agent_config = yaml.safe_load(f)

    periodic_config = agent_config.get('agent', {}).get('periodic_trigger', {})
    if periodic_config.get('enabled', False):
        periodic_enabled = True
        periodic_task = asyncio.create_task(periodic_analysis_task())
        print(f"定期触发已启用，间隔: {periodic_config.get('interval', 3)}秒")
    else:
        print("定期触发未启用")

    print("服务端启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时清理"""
    global periodic_enabled, periodic_task
    if periodic_task:
        periodic_enabled = False
        await periodic_task
        print("定期分析任务已停止")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "cache_status": data_manager.get_status()}


@app.post("/camera/upload")
async def upload_camera_image(
    camera_id: str = Form(...),
    image: UploadFile = File(...)
):
    """接收摄像头图片"""
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="无法解析图片")

        data_manager.set_image(camera_id, img)
        return {"status": "success", "camera_id": camera_id, "image_shape": img.shape}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CameraPoseUpdate(BaseModel):
    """相机位姿更新请求模型"""
    front: Dict[str, Any]
    rear: Dict[str, Any]


@app.post("/camera/update_poses")
async def update_camera_poses(poses: CameraPoseUpdate):
    """接收并更新相机位姿配置

    Args:
        poses: 包含front和rear相机的位姿信息
            {
                "front": {
                    "location": {"x": float, "y": float, "z": float},
                    "rotation": {"pitch": float, "yaw": float, "roll": float},
                    "intrinsics": {"fx": float, "fy": float, "cx": float, "cy": float},
                    "image_size": {"width": int, "height": int},
                    "fov": float
                },
                "rear": {...}
            }
    """
    try:
        import re

        # 更新配置文件
        camera_config_path = 'config/camera_config.yaml'

        # 读取现有配置文件内容
        with open(camera_config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 更新相机配置（使用正则表达式逐字段替换）
        poses_dict = poses.model_dump()

        for camera_id, pose_data in poses_dict.items():
            # 更新 location
            location = pose_data['location']
            location_pattern = rf'(- id: "{camera_id}".*?location:\s*\n)(.*?)(rotation:)'

            def replace_location(match):
                prefix = match.group(1)
                suffix = match.group(3)
                new_location = f"      x: {location['x']:.2f}\n      y: {location['y']:.2f}\n      z: {location['z']:.2f}\n    "
                return prefix + new_location + suffix

            content = re.sub(location_pattern, replace_location, content, flags=re.DOTALL)

            # 更新 rotation
            rotation = pose_data['rotation']
            rotation_pattern = rf'(- id: "{camera_id}".*?rotation:\s*\n)(.*?)(intrinsics:)'

            def replace_rotation(match):
                prefix = match.group(1)
                suffix = match.group(3)
                new_rotation = f"      pitch: {rotation['pitch']:.2f}\n      yaw: {rotation['yaw']:.2f}\n      roll: {rotation['roll']:.2f}\n    "
                return prefix + new_rotation + suffix

            content = re.sub(rotation_pattern, replace_rotation, content, flags=re.DOTALL)

        # 写回配置文件
        with open(camera_config_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 重新加载Agent的相机配置
        if agent is not None:
            agent.camera_manager.reload_config()

        return {
            "status": "success",
            "message": "相机位姿已更新",
            "updated_cameras": list(poses_dict.keys()),
            "poses": poses_dict
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新相机位姿失败: {str(e)}")


@app.post("/vehicle/info")
async def receive_vehicle_info(request: VehicleInfoRequest):
    """接收车辆信息并触发分析"""
    vehicle_info = request.model_dump()
    data_manager.set_vehicle_info(vehicle_info)

    # 获取缓存数据
    raw_images = data_manager.get_images()
    traffic_command = data_manager.get_traffic_command()

    if not raw_images:
        raise HTTPException(status_code=400, detail="没有可用的摄像头图片")

    # 调用Agent分析
    try:
        result = agent.analyze(
            raw_images=raw_images,
            vehicle_info=vehicle_info,
            traffic_command=traffic_command
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent分析失败: {str(e)}")

    # 发送驾驶建议到车端
    vehicle_ip = config.get("vehicle", {}).get("ip", "localhost")
    vehicle_port = config.get("vehicle", {}).get("port", 8000)

    try:
        resp = requests.post(
            f"http://{vehicle_ip}:{vehicle_port}/instruct",
            json={"instruction": result['advice']},
            timeout=5
        )
        send_status = "success" if resp.status_code == 200 else "failed"
    except Exception as e:
        send_status = f"failed: {str(e)}"

    return {
        "status": "success",
        "advice": result['advice'],
        "risk_level": result['risk_level'],
        "confidence": result['confidence'],
        "send_to_vehicle": send_status
    }


@app.post("/debug/save_bbox")
async def debug_save_bbox(
    camera_id: str = Form(...),
    image: UploadFile = File(...),
    vehicle_info: str = Form(...)
):
    """
    调试API：接收图像和车辆信息，绘制标定框后保存图像

    该API仅用于调试，不进行任何分析或推送操作

    Args:
        camera_id: 摄像头ID
        image: 图像文件
        vehicle_info: 车辆信息JSON字符串

    Returns:
        保存状态和文件路径
    """
    try:
        import json

        # 解析图像
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="无法解析图片")

        # 解析车辆信息
        vehicle_data = json.loads(vehicle_info)

        # 构建raw_images字典
        raw_images = {camera_id: img}

        # 调用camera_manager进行投影和保存
        result = agent.camera_manager.project_vehicle(
            vehicle_info=vehicle_data,
            raw_images=raw_images
        )

        return {
            "status": "success",
            "camera_id": camera_id,
            "image_shape": img.shape,
            "visible_cameras": result['visible_cameras'],
            "in_blind_spot": result['in_blind_spot'],
            "message": "图像已保存到 debug/server_images/"
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"车辆信息JSON解析失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调试保存失败: {str(e)}")


@app.post("/traffic/command")
async def receive_traffic_command(request: TrafficCommandRequest):
    """接收交通指挥指令"""
    data_manager.set_traffic_command(request.command)
    return {"status": "success", "command": request.command}


@app.delete("/traffic/command")
async def clear_traffic_command():
    """清除交通指挥指令"""
    data_manager.clear_traffic_command()
    return {"status": "success", "message": "交通指令已清除"}


@app.post("/periodic/start")
async def start_periodic_analysis():
    """启动定期分析"""
    global periodic_enabled, periodic_task

    if periodic_enabled:
        return {"status": "already_running", "message": "定期分析已在运行"}

    periodic_enabled = True
    periodic_task = asyncio.create_task(periodic_analysis_task())

    return {"status": "success", "message": "定期分析已启动"}


@app.post("/periodic/stop")
async def stop_periodic_analysis():
    """停止定期分析"""
    global periodic_enabled, periodic_task

    if not periodic_enabled:
        return {"status": "not_running", "message": "定期分析未运行"}

    periodic_enabled = False
    if periodic_task:
        await periodic_task

    return {"status": "success", "message": "定期分析已停止"}


@app.get("/periodic/status")
async def get_periodic_status():
    """获取定期分析状态"""
    agent_config_path = 'config/agent_config.yaml'
    with open(agent_config_path, 'r', encoding='utf-8') as f:
        agent_config = yaml.safe_load(f)

    periodic_config = agent_config.get('agent', {}).get('periodic_trigger', {})

    return {
        "enabled": periodic_enabled,
        "config": periodic_config,
        "task_running": periodic_task is not None and not periodic_task.done()
    }


@app.put("/periodic/config")
async def update_periodic_config(
    interval: Optional[int] = None,
    skip_if_no_vehicle: Optional[bool] = None
):
    """更新定期分析配置（不重启任务）"""
    agent_config_path = 'config/agent_config.yaml'

    with open(agent_config_path, 'r', encoding='utf-8') as f:
        agent_config = yaml.safe_load(f)

    if 'agent' not in agent_config:
        agent_config['agent'] = {}
    if 'periodic_trigger' not in agent_config['agent']:
        agent_config['agent']['periodic_trigger'] = {}

    if interval is not None:
        agent_config['agent']['periodic_trigger']['interval'] = interval
    if skip_if_no_vehicle is not None:
        agent_config['agent']['periodic_trigger']['skip_if_no_vehicle'] = skip_if_no_vehicle

    with open(agent_config_path, 'w', encoding='utf-8') as f:
        yaml.dump(agent_config, f, allow_unicode=True, default_flow_style=False)

    return {
        "status": "success",
        "message": "配置已更新（需要重启定期任务才能生效）",
        "config": agent_config['agent']['periodic_trigger']
    }


@app.get("/status")
async def get_status():
    """获取服务状态"""
    return {
        "agent_ready": agent is not None,
        "cache_status": data_manager.get_status(),
        "vehicle_target": f"{config.get('vehicle', {}).get('ip')}:{config.get('vehicle', {}).get('port')}"
    }


if __name__ == "__main__":
    import uvicorn
    config = load_config()
    init_agent()
    uvicorn.run(
        app,
        host=config.get("server", {}).get("host", "0.0.0.0"),
        port=config.get("server", {}).get("port", 5000)
    )
