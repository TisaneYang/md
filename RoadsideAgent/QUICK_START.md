# 快速开始指南

本指南帮助您快速上手路侧智能体系统。

## 5分钟快速体验

### 步骤1: 安装依赖

```bash
cd /home/damai/RoadsideAgent
pip install -r requirements.txt
```

### 步骤2: 运行基础测试（无需API密钥）

```bash
python test_basic_functionality.py
```

这将测试：
- ✅ 摄像头管理器
- ✅ 车辆投影功能
- ✅ 监控死角检测
- ✅ 输入处理器
- ✅ 多摄像头场景

测试完成后会生成带标定框的图像：
- `test_output_camera_1.jpg`
- `test_output_camera_2.jpg`

### 步骤3: 配置API密钥（可选，用于完整功能）

如果要使用完整的LLM分析功能，需要配置API密钥：

```bash
# 使用OpenAI
export OPENAI_API_KEY='your-openai-api-key'

# 或使用Anthropic Claude
export ANTHROPIC_API_KEY='your-anthropic-api-key'
```

然后修改 `config/agent_config.yaml` 中的配置：

```yaml
llm:
  provider: "openai"  # 或 "anthropic"
  model: "gpt-4-vision-preview"  # 或 "claude-3-opus-20240229"
  api_key: "${OPENAI_API_KEY}"  # 或 "${ANTHROPIC_API_KEY}"
```

### 步骤4: 运行完整示例

```bash
python examples/agent_usage_example.py
```

## 基本使用示例

### 示例1: 分析单个场景

```python
from agent.roadside_agent import RoadsideAgent
import numpy as np
import cv2

# 1. 初始化Agent
agent = RoadsideAgent(
    agent_config_path='config/agent_config.yaml',
    camera_config_path='config/camera_config.yaml'
)

# 2. 准备图像（从摄像头读取或加载）
image1 = cv2.imread('camera1_frame.jpg')
image2 = cv2.imread('camera2_frame.jpg')

raw_images = {
    'camera_1': image1,
    'camera_2': image2
}

# 3. 准备车辆信息
vehicle_info = {
    "type": "轿车",
    "color": "白色",
    "discription": "比亚迪秦Plus白色款",
    "plate": "京A12345",
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

# 4. 分析场景
result = agent.analyze(
    raw_images=raw_images,
    vehicle_info=vehicle_info
)

# 5. 查看结果
print(f"驾驶建议: {result['advice']}")
print(f"风险等级: {result['risk_level']}")
print(f"置信度: {result['confidence']:.2f}")
```

### 示例2: 处理交通指挥指令

```python
# 添加交通指挥指令
traffic_command = "前方道路施工，请减速慢行并注意避让施工人员"

result = agent.analyze(
    raw_images=raw_images,
    vehicle_info=vehicle_info,
    traffic_command=traffic_command
)

print(f"指令: {traffic_command}")
print(f"建议: {result['advice']}")
```

### 示例3: 批量处理多个场景

```python
scenarios = [
    {
        'raw_images': images1,
        'vehicle_info': vehicle1,
        'traffic_command': None
    },
    {
        'raw_images': images2,
        'vehicle_info': vehicle2,
        'traffic_command': "注意前方路口"
    }
]

results = agent.analyze_batch(scenarios)

for i, result in enumerate(results):
    print(f"场景{i+1}: {result['advice']}")
```

## 配置摄像头

编辑 `config/camera_config.yaml` 添加您的摄像头：

```yaml
cameras:
  - id: "camera_1"
    name: "路口东侧摄像头"
    location:
      x: 0.0      # 摄像头世界坐标X（米）
      y: 10.0     # 摄像头世界坐标Y（米）
      z: 5.0      # 摄像头高度（米）
    rotation:
      pitch: -15.0  # 俯仰角（度）
      yaw: -90.0    # 航向角（度）
      roll: 0.0     # 翻滚角（度）
    intrinsics:
      fx: 1000.0    # 焦距X
      fy: 1000.0    # 焦距Y
      cx: 960.0     # 主点X
      cy: 540.0     # 主点Y
    image_size:
      width: 1920
      height: 1080
```

### 摄像头参数说明

**位置 (location)**:
- `x, y, z`: 摄像头在世界坐标系中的位置（米）
- 坐标系：Z轴向上，X轴为前进方向

**旋转 (rotation)**:
- `pitch`: 俯仰角，负值表示向下看
- `yaw`: 航向角，0度为朝向+X方向
- `roll`: 翻滚角，通常为0

**内参 (intrinsics)**:
- `fx, fy`: 焦距（像素）
- `cx, cy`: 主点坐标（像素）
- 可以从摄像头标定获得

## 车辆信息格式

参考 `template.json`：

```json
{
    "type": "轿车",              // 车辆类型
    "color": "白色",             // 车辆颜色
    "discription": "...",        // 车辆描述
    "plate": "京A12345",         // 车牌号
    "intention": "直行通过路段",  // 驾驶意图
    "length": 4.5,               // 车长（米）
    "width": 1.8,                // 车宽（米）
    "height": 1.5,               // 车高（米）
    "location_x": 20.0,          // 世界坐标X（米）
    "location_y": 0.0,           // 世界坐标Y（米）
    "location_z": 0.0,           // 世界坐标Z（米）
    "rotation_row": 0.0,         // 翻滚角（度）
    "rotation_pitch": 0.0,       // 俯仰角（度）
    "rotation_yaw": 0.0,         // 航向角（度）
    "velocity": 45.5,            // 速度（km/h）
    "acceleration": 0.2          // 加速度（m/s²）
}
```

## 输出结果说明

```python
result = {
    # 摄像头覆盖信息
    "camera_coverage": {
        "in_blind_spot": False,           # 是否在监控死角
        "visible_cameras": ["camera_1"],  # 可见的摄像头列表
        "blind_spot_info": None           # 盲区信息（如果在死角）
    },
    
    # 车辆摘要
    "vehicle_summary": "目标车辆：白色轿车...",
    
    # 完整推理过程（CoT）
    "reasoning": """
    ## 推理过程
    ### 1. 摄像头覆盖分析
    ...
    ### 2. 观察分析
    ...
    """,
    
    # 驾驶建议（自然语言）
    "advice": "建议保持当前速度，注意前方路况...",
    
    # 风险等级
    "risk_level": "low",  # low/medium/high
    
    # 置信度
    "confidence": 0.85,   # 0.0-1.0
    
    # 交通指令（如果有）
    "traffic_command": None
}
```

## 常见场景

### 场景1: 车辆在视野内

```python
# 车辆位置在摄像头前方
vehicle_info = {
    "location_x": 20.0,  # 前方20米
    "location_y": 0.0,
    "location_z": 0.0,
    ...
}

result = agent.analyze(raw_images, vehicle_info)
# result['camera_coverage']['in_blind_spot'] = False
# result['advice'] = "根据场景的具体建议"
```

### 场景2: 车辆在监控死角

```python
# 车辆位置在摄像头后方
vehicle_info = {
    "location_x": -15.0,  # 后方15米
    "location_y": 0.0,
    "location_z": 0.0,
    ...
}

result = agent.analyze(raw_images, vehicle_info)
# result['camera_coverage']['in_blind_spot'] = True
# result['advice'] = "车辆已进入监控盲区，请谨慎驾驶..."
```

### 场景3: 紧急情况

```python
# 高速行驶 + 交通指令
vehicle_info = {
    "velocity": 80.0,  # 80 km/h
    "acceleration": 0.5,
    ...
}

traffic_command = "前方发生事故，请立即减速"

result = agent.analyze(raw_images, vehicle_info, traffic_command)
# result['risk_level'] = "high"
# result['advice'] = "紧急警告：前方发生事故..."
```

## 调试技巧

### 1. 查看摄像头配置

```python
camera_info = agent.get_camera_info()
print(camera_info)
```

### 2. 保存带标定框的图像

```python
# 在camera_manager.project_vehicle()返回的结果中
result = camera_manager.project_vehicle(vehicle_info, raw_images)

for cam_id in result['visible_cameras']:
    image_with_bbox = result['projections'][cam_id]['image_with_bbox']
    cv2.imwrite(f'debug_{cam_id}.jpg', image_with_bbox)
```

### 3. 启用详细日志

在 `config/agent_config.yaml` 中：

```yaml
agent:
  verbose: true
```

### 4. 测试投影功能

```python
from utils.vehicle_projection import VehicleProjector

projector = VehicleProjector(camera_intrinsics)
bbox = projector.get_vehicle_bbox(
    camera_location, camera_rotation,
    vehicle_location, vehicle_rotation,
    vehicle_dimensions
)
print(f"投影边界框: {bbox}")
```

## 故障排除

### 问题1: ModuleNotFoundError

```bash
# 安装缺失的依赖
pip install -r requirements.txt
```

### 问题2: 车辆投影失败

```python
# 检查车辆是否在摄像头视野内
# 确保 location_x > 0（在摄像头前方）
# 调整摄像头的 yaw 角度
```

### 问题3: LLM API调用失败

```bash
# 检查API密钥
echo $OPENAI_API_KEY

# 检查网络连接
# 确认API配额
```

### 问题4: 图像格式错误

```python
# 确保图像是numpy数组
import cv2
image = cv2.imread('image.jpg')  # 正确
# image = Image.open('image.jpg')  # 错误，需要转换

# 转换PIL图像到numpy
import numpy as np
from PIL import Image
pil_image = Image.open('image.jpg')
numpy_image = np.array(pil_image)
```

## 性能优化建议

1. **图像压缩**: 系统会自动压缩图像，无需手动处理
2. **批量处理**: 使用 `analyze_batch()` 处理多个场景
3. **缓存配置**: 避免频繁重新加载配置文件
4. **并行处理**: 投影计算自动并行处理多个摄像头

## 下一步

- 阅读完整文档: `README.md`
- 查看实现细节: `IMPLEMENTATION_SUMMARY.md`
- 运行更多示例: `examples/agent_usage_example.py`
- 自定义配置: 修改 `config/` 目录下的配置文件
- 扩展功能: 参考 `agent/` 目录下的模块代码

## 获取帮助

如有问题，请查看：
1. `README.md` - 完整文档
2. `IMPLEMENTATION_SUMMARY.md` - 实现总结
3. 代码注释 - 每个模块都有详细的文档字符串

祝使用愉快！
