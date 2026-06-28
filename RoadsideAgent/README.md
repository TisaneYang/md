# 路侧智能体 (Roadside Agent)

一个基于多模态大语言模型的路侧交通智能体系统，能够分析路侧摄像头拍摄的交通场景，识别车辆位置和驾驶盲区，并为驾驶员提供安全驾驶建议。

## 功能特性

- **多摄像头管理**: 支持配置和管理多个路侧摄像头，自动判断车辆在哪个摄像头视野内
- **3D到2D投影**: 将车辆3D位置投影到摄像头图像平面，自动绘制标定框
- **监控死角检测**: 识别车辆是否进入监控盲区，提供相应的安全警告
- **场景理解**: 使用多模态LLM分析交通场景，识别潜在风险和驾驶盲区
- **CoT推理**: 采用Chain-of-Thought推理方式，提供完整的分析过程
- **自然语言建议**: 生成清晰、简洁、可执行的驾驶建议
- **交通指挥支持**: 支持接收和处理交通指挥者的自然语言指令

## 系统架构

```
RoadsideAgent/
├── agent/                      # 核心模块
│   ├── roadside_agent.py      # 主Agent类
│   ├── camera_manager.py      # 摄像头管理与投影
│   ├── input_processor.py     # 输入处理
│   ├── llm_interface.py       # LLM接口
│   └── __init__.py
├── utils/                      # 工具模块
│   ├── vehicle_projection.py  # 车辆投影工具
│   ├── bbox_visualizer.py     # 边界框可视化
│   └── __init__.py
├── config/                     # 配置文件
│   ├── agent_config.yaml      # Agent配置
│   └── camera_config.yaml     # 摄像头配置
├── prompts/                    # 提示词模板
│   └── system_prompt.txt      # 系统提示词
├── examples/                   # 使用示例
│   └── agent_usage_example.py
├── test/                       # 测试文件
│   ├── test_projection.py
│   └── example_usage.py
├── template.json              # 车辆信息模板
├── requirements.txt           # 依赖项
└── README.md                  # 本文档
```

## 安装

### 1. 克隆或下载项目

```bash
cd RoadsideAgent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置API密钥

设置环境变量（根据使用的LLM提供商选择）：

```bash
# 使用OpenAI
export OPENAI_API_KEY='your-openai-api-key'

# 或使用Anthropic
export ANTHROPIC_API_KEY='your-anthropic-api-key'
```

## 快速开始

### 基本使用

```python
from agent.roadside_agent import RoadsideAgent
import numpy as np

# 1. 初始化Agent
agent = RoadsideAgent(
    agent_config_path='config/agent_config.yaml',
    camera_config_path='config/camera_config.yaml'
)

# 2. 准备输入数据
raw_images = {
    'camera_1': np.array(...),  # 摄像头1的原始图像
    'camera_2': np.array(...)   # 摄像头2的原始图像
}

vehicle_info = {
    "type": "轿车",
    "color": "白色",
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

# 3. 分析场景
result = agent.analyze(
    raw_images=raw_images,
    vehicle_info=vehicle_info,
    traffic_command=None  # 可选的交通指挥指令
)

# 4. 查看结果
print(f"驾驶建议: {result['advice']}")
print(f"风险等级: {result['risk_level']}")
print(f"置信度: {result['confidence']}")
```

### 运行示例

```bash
python examples/agent_usage_example.py
```

## 配置说明

### 摄像头配置 (camera_config.yaml)

```yaml
cameras:
  - id: "camera_1"
    name: "路口东侧摄像头"
    location: {x: 0.0, y: 10.0, z: 5.0}
    rotation: {pitch: -15.0, yaw: -90.0, roll: 0.0}
    intrinsics: {fx: 1000.0, fy: 1000.0, cx: 960.0, cy: 540.0}
    image_size: {width: 1920, height: 1080}

camera_relationships:
  - cameras: ["camera_1", "camera_2"]
    type: "back_to_back"
    description: "两个摄像头背靠背设置"
```

### Agent配置 (agent_config.yaml)

```yaml
llm:
  provider: "openai"  # 或 "anthropic"
  model: "gpt-4-vision-preview"
  api_key: "${OPENAI_API_KEY}"
  max_tokens: 2000
  temperature: 0.7
```

## 核心功能

### 1. 摄像头管理与投影

系统自动将车辆3D位置投影到各个摄像头的图像平面：

- 读取车辆3D位置和姿态
- 遍历所有摄像头配置
- 使用透视投影计算2D边界框
- 自动绘制标定框
- 判断车辆可见性

### 2. 监控死角检测

当车辆不在任何摄像头视野内时：

- 标记为"监控死角"状态
- 计算车辆到各摄像头的距离
- 推测车辆所在盲区位置
- 生成警告信息和安全建议

### 3. 场景分析与推理

使用多模态LLM进行7步推理：

1. **摄像头覆盖分析**: 判断车辆是否在视野内
2. **观察分析**: 描述图像中看到的内容
3. **场景识别**: 识别交通场景类型
4. **盲区识别**: 识别驾驶员的视野盲区
5. **风险评估**: 分析潜在风险
6. **意图匹配**: 评估驾驶意图与场景匹配度
7. **建议生成**: 生成具体的驾驶建议

### 4. 优先级处理

- **最高优先级**: 交通指挥者指令
- **次优先级**: 紧急安全警告（包括监控死角）
- **常规优先级**: 一般驾驶建议

## 使用场景

### 场景1: 正常行驶

车辆在摄像头视野内，清晰可见，Agent分析场景并提供常规驾驶建议。

### 场景2: 监控死角

车辆进入摄像头覆盖盲区，Agent发出警告并建议谨慎驾驶。

### 场景3: 多摄像头覆盖

车辆同时出现在多个摄像头视野中，Agent选择最佳视角进行分析。

### 场景4: 交通指挥

存在交通指挥指令时，Agent优先执行该指令并提供相关建议。

### 场景5: 遮挡场景

车辆在视野内但被其他物体遮挡，Agent基于可见信息给出建议。

## API参考

### RoadsideAgent

主要方法：

- `__init__(agent_config_path, camera_config_path)`: 初始化Agent
- `analyze(raw_images, vehicle_info, traffic_command=None)`: 分析场景
- `get_camera_info()`: 获取摄像头配置信息
- `reload_config()`: 重新加载配置
- `analyze_batch(scenarios)`: 批量分析多个场景

### 输入格式

**车辆信息** (参考template.json):
```json
{
    "type": "轿车",
    "color": "白色",
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
```

### 输出格式

```python
{
    "camera_coverage": {
        "in_blind_spot": False,
        "visible_cameras": ["camera_1"],
        "blind_spot_info": None
    },
    "vehicle_summary": "目标车辆：白色轿车...",
    "reasoning": "## 推理过程\n...",
    "advice": "建议保持当前速度...",
    "risk_level": "low",
    "confidence": 0.85
}
```

## 性能优化

- 投影计算支持并行处理多个摄像头
- 图像自动压缩以减少LLM token消耗
- 摄像头配置和投影矩阵缓存
- 支持批量分析多个场景

## 扩展性

- 支持动态添加/删除摄像头
- 支持OpenAI和Anthropic两种LLM后端
- 预留接口支持视频流处理
- 支持自定义场景分析规则

## 依赖项

- Python >= 3.8
- numpy >= 1.20.0
- opencv-python >= 4.5.0
- pyyaml >= 6.0
- pillow >= 9.0.0
- openai >= 1.0.0 或 anthropic >= 0.18.0

## 注意事项

1. **API密钥**: 使用前必须设置相应的API密钥环境变量
2. **图像格式**: 输入图像必须是numpy数组，格式为(H, W, 3)的BGR图像
3. **坐标系**: 使用右手坐标系，Z轴向上，X轴为前进方向
4. **角度单位**: 所有旋转角度使用度（degree）
5. **成本控制**: LLM调用会产生费用，建议合理控制调用频率

## 故障排除

### 问题1: 投影失败

**原因**: 车辆在摄像头后方或视野外
**解决**: 检查车辆位置和摄像头配置，确保车辆在合理范围内

### 问题2: LLM调用失败

**原因**: API密钥未设置或无效
**解决**: 检查环境变量设置，确认API密钥有效

### 问题3: 图像格式错误

**原因**: 输入图像格式不正确
**解决**: 确保图像是numpy数组，格式为(H, W, 3)

## 许可证

本项目仅供学习和研究使用。

## 联系方式

如有问题或建议，请提交Issue。
