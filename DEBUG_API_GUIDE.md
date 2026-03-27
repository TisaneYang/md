# RoadsideAgent 调试API使用指南

## 概述

本文档介绍RoadsideAgent的调试API功能，该功能用于在Bench2Drive评估过程中自动保存路侧摄像头图像并绘制车辆标定框。

## 功能特性

1. **自动图像保存**：每帧都保存路侧摄像头的原始图像
2. **标定框绘制**：如果车辆在摄像头视野内，自动绘制3D标定框
3. **多摄像头支持**：支持front和rear两个摄像头
4. **独立调试**：不影响正常的评估流程，仅用于调试

## API接口

### POST /debug/save_bbox

接收图像和车辆信息，绘制标定框后保存图像。

**请求参数**：
- `camera_id` (form): 摄像头ID（"front" 或 "rear"）
- `image` (file): 图像文件（JPEG格式）
- `vehicle_info` (form): 车辆信息JSON字符串

**车辆信息格式**：
```json
{
    "type": "sedan",
    "color": "white",
    "discription": "Vehicle description",
    "plate": "ABC123",
    "intention": "straight",
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
```

**响应**：
```json
{
    "status": "success",
    "camera_id": "front",
    "image_shape": [600, 800, 3],
    "visible_cameras": ["front"],
    "in_blind_spot": false,
    "message": "图像已保存到 debug/server_images/"
}
```

## 使用方法

### 1. 启动RoadsideAgent服务器

```bash
cd RoadsideAgent
python server/main.py
```

服务器会在 `http://0.0.0.0:5000` 启动，并自动启用图像保存功能。

### 2. 运行Bench2Drive评估

在leaderboard评估脚本中，调试API会自动被调用（如果RoadsideAgent服务器正在运行）。

```bash
cd leaderboard
bash scripts/run_evaluation_debug.sh
```

### 3. 查看保存的图像

图像会保存在以下目录结构中：

```
RoadsideAgent/debug/server_images/
├── front/
│   ├── 20260308_225130_157217.jpg  # 原始图像
│   ├── 20260308_225130_162345.jpg  # 带标定框的图像
│   └── ...
└── rear/
    ├── 20260308_225130_186624.jpg  # 原始图像
    ├── 20260308_225130_194591.jpg  # 带标定框的图像
    └── ...
```

### 4. 测试调试API

使用提供的测试脚本验证API功能：

```bash
cd RoadsideAgent
python test_debug_api.py
```

## 集成到Leaderboard

调试API已经集成到leaderboard评估流程中：

1. **scenario_manager.py**：添加了 `roadside_debug_callback` 回调函数支持
2. **leaderboard_evaluator.py**：
   - 添加了 `_send_roadside_debug_data()` 方法
   - 在每一帧自动调用该方法发送数据到调试API

### 工作流程

```
每一帧 (20Hz)
    ↓
scenario_manager._tick_scenario()
    ↓
调用 roadside_debug_callback()
    ↓
leaderboard_evaluator._send_roadside_debug_data()
    ↓
获取ego vehicle信息
    ↓
获取front/rear摄像头图像
    ↓
发送到 /debug/save_bbox API
    ↓
RoadsideAgent保存图像和标定框
```

## 配置选项

### 修改图像保存目录

在 `server/main.py` 中修改：

```python
def init_agent():
    global agent
    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml',
        save_images=True,
        output_dir='debug/custom_output_dir'  # 修改这里
    )
```

### 禁用图像保存

在 `server/main.py` 中设置：

```python
def init_agent():
    global agent
    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml',
        save_images=False  # 禁用图像保存
    )
```

## 性能考虑

- 调试API使用异步调用，超时时间为1秒
- 如果API调用失败，会静默忽略，不影响评估流程
- 图像以JPEG格式保存，质量为95%
- 建议在调试完成后禁用图像保存以节省磁盘空间

## 故障排除

### 问题1：服务器无法启动

**错误**：`Address already in use`

**解决**：
```bash
# 查找占用端口的进程
lsof -i:5000

# 杀死进程
kill -9 <PID>
```

### 问题2：图像未保存

**检查**：
1. 确认服务器正在运行
2. 检查 `save_images=True` 是否设置
3. 查看服务器日志是否有错误信息
4. 确认输出目录有写入权限

### 问题3：标定框不正确

**检查**：
1. 确认摄像头位姿配置正确
2. 检查车辆坐标系是否正确
3. 查看 `camera_config.yaml` 中的内参是否准确

## 文件修改清单

### 新增文件
- `RoadsideAgent/test_debug_api.py` - 调试API测试脚本
- `RoadsideAgent/DEBUG_API_GUIDE.md` - 本文档

### 修改文件
1. **RoadsideAgent/agent/camera_manager.py**
   - 添加 `save_images` 和 `output_dir` 参数
   - 添加 `_save_image()` 方法
   - 修改 `project_vehicle()` 自动保存图像

2. **RoadsideAgent/agent/roadside_agent.py**
   - 添加 `save_images` 和 `output_dir` 参数
   - 传递参数到 `CameraManager`

3. **RoadsideAgent/server/main.py**
   - 修改 `init_agent()` 启用图像保存
   - 添加 `/debug/save_bbox` API端点

4. **leaderboard/leaderboard/scenarios/scenario_manager.py**
   - 添加 `roadside_debug_callback` 属性
   - 在 `_tick_scenario()` 中调用回调函数

5. **leaderboard/leaderboard/leaderboard_evaluator.py**
   - 添加 `_send_roadside_debug_data()` 方法
   - 在场景加载时设置回调函数

## 示例代码

### Python客户端示例

```python
import requests
import json
import cv2

# 读取图像
image = cv2.imread('test_image.jpg')
_, img_encoded = cv2.imencode('.jpg', image)

# 准备车辆信息
vehicle_info = {
    'type': 'sedan',
    'color': 'white',
    'plate': 'TEST123',
    'location_x': 20.0,
    'location_y': 0.0,
    'location_z': 0.0,
    # ... 其他字段
}

# 发送请求
files = {'image': ('image.jpg', img_encoded.tobytes(), 'image/jpeg')}
data = {
    'camera_id': 'front',
    'vehicle_info': json.dumps(vehicle_info)
}

response = requests.post(
    'http://0.0.0.0:5000/debug/save_bbox',
    files=files,
    data=data
)

print(response.json())
```

## 参考资料

- [RoadsideAgent README](README.md)
- [Bench2Drive Documentation](../CLAUDE.md)
- [Camera Configuration Guide](config/camera_config.yaml)
