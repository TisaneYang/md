# RoadsideAgent

新版 RoadsideAgent 现在包含两层：

- 路侧感知层：相机管理、目标车辆投影、绿色 2D 标定框绘制。
- 路侧推理层：批处理多车输入、OpenAI-compatible 模型调用、上下文记忆、可选车辆消息下发。

## 当前实现范围

- 在 CARLA world 中按绝对坐标创建路侧 RGB 摄像头。
- 支持每个场景手动配置任意数量路侧摄像头。
- 从 CARLA 目标车辆 actor 直接读取 `get_transform()` 和 `bounding_box`。
- 将车辆 3D bounding box 投影到路侧相机画面。
- 只绘制一个绿色 2D 框，默认线宽为 4。
- 对车辆跨过相机近裁切面的情况做过滤：只使用深度大于 `near_clip` 的角点计算 2D 框，避免旧式 3D 连线在近裁切面附近拉出异常长线。
- 支持低频采样调度接口，避免每 tick 触发 RoadsideAgent 推理。
- 提供车辆主动上报状态的 HTTP 接口，用于维护可交互车辆白名单。
- 提供车辆编号到 `ip:port` 的通信映射，用于路侧向车辆下发指令。
- 提供与 PilotAgent 对齐的 OpenAI-compatible 多模态推理链路。
- Prompt 设计与 PilotAgent 对齐：职责、规则、目标、输入输出约束放在 system prompt；user prompt 只描述当前环境与输入载荷。
- 模型输出格式为：
  - `global_summary`
  - `vehicle_outputs = [{vehicle_id, should_send, message}]`

## 目录

```text
RoadsideAgent/
├── config/
│   ├── roadside_agent.json
│   ├── roadside_cameras.yaml
│   └── routes/
├── docs/
│   └── integration_plan.md
└── roadside_agent/
    ├── __init__.py
    ├── cloud_vlm_client.py
    ├── camera.py
    ├── communication.py
    ├── config.py
    ├── context.py
    ├── http_server.py
    ├── logger.py
    ├── manager.py
    ├── prompt.py
    ├── projection.py
    ├── runtime.py
    ├── types.py
    ├── vehicle_registry.py
    └── visualization.py
```

## 最小使用方式

在 Bench2Drive 已经完成 `CarlaDataProvider.set_world(...)` 且 ego vehicle 已经 spawn 后：

```python
from pathlib import Path

from roadside_agent import RoadsidePerceptionManager, RoadsideAgent

manager = RoadsidePerceptionManager.from_route_config(
    world=world,
    route_name=config.name,  # e.g. "RouteScenario_0"
    config_root=Path("RoadsideAgent/config"),
)
manager.spawn_cameras()

roadside_agent = RoadsideAgent(manager)

if manager.should_sample(tick_index):
    result = roadside_agent.analyze(target_actor=ego_vehicle)

# result["perception"]["cameras"][camera_id].image_with_bbox 是带绿色 2D 框的 BGR 图像
```

车辆状态上报入口：

```text
POST http://127.0.0.1:8890/vehicles/state
Content-Type: application/json
```

请求体：

```json
{
  "vehicle_id": "123",
  "timestamp": 123.45,
  "endpoint": "127.0.0.1:9101",
  "upstream": {
    "timestamp": 123.45,
    "instruction": ""
  },
  "task_status": "正常巡航中，未收到任务"
}
```

其中：

- `vehicle_id` 使用 CARLA `actor.id`。
- `timestamp` 是心跳字段；只要持续上报，就会被 RoadsideAgent 纳入处理范围。
- `upstream` 和 `task_status` 来自车辆端 PilotAgent。
- `endpoint` 是路侧向车辆下发自然语言建议的临时地址。

Bench2Drive hook 推理前只会处理近期上报过状态的车辆，不再扫描全场所有 `vehicle.*` 作为交互对象。

HTTP server 配置位于 `RoadsideAgent/config/roadside_agent.json`：

```json
{
  "server": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8890,
    "stale_after_seconds": 2.0
  }
}
```

LLM runtime 入口：

```python
from roadside_agent import RoadsideRuntime

runtime = RoadsideRuntime.from_config_path("RoadsideAgent/config/roadside_agent.json")

if manager.should_sample(tick_index):
    perception = manager.perceive_targets(vehicle_registry.active_actor_map())
    decision = runtime.step(
        tick=tick_index,
        timestamp=timestamp,
        route_name="RouteScenario_0",
        scene_description=manager.scene_description,
        perception=perception,
        vehicle_registry=vehicle_registry,
    )
```

路侧下发指令入口：

```python
from roadside_agent import VehicleCommandClient

command_client = VehicleCommandClient(vehicle_registry.endpoint_map())
roadside_agent = RoadsideAgent(manager, command_client=command_client)

send_result = roadside_agent.send_to_vehicle(
    vehicle_id=str(actor_1.id),
    message={
        "type": "roadside_command",
        "summary": "slow down and keep lane",
    },
)
```

临时通信协议是 HTTP JSON POST，默认发送到：

```text
http://{ip}:{port}/roadside/message
```

请求体：

```json
{
  "vehicle_id": "123",
  "message": {
    "type": "roadside_command",
    "summary": "slow down and keep lane"
  }
}
```

## LLM 输出格式

RoadsideRuntime 期望模型返回纯 JSON：

```json
{
  "global_summary": "整体态势总结",
  "vehicle_outputs": [
    {
      "vehicle_id": "123",
      "should_send": true,
      "message": "自然语言建议或任务路线"
    },
    {
      "vehicle_id": "456",
      "should_send": false,
      "message": null
    }
  ]
}
```

其中：

- `global_summary` 是写回上下文的唯一总结字段。
- `should_send=false` 表示本轮不下发该车消息。
- `message` 是自然语言内容，不限制成固定 command schema。

## 多图批处理输入

一次推理处理多辆车。每辆车所有可见相机图像都会附上，不设上限，不可见相机不附。

OpenAI-compatible provider 下，请求中的 user content 采用与 PilotAgent 一致的多模态 block：

- 一段 JSON 文本，包含本轮批处理的结构化输入。
- 若干组 `text + image_url`，每组用文本锚点标明：
  - `vehicle_id`
  - `camera_id`
  - `image_key`

这样模型可以将每张带绿色框的图像与对应车辆绑定起来。

## 路侧相机输出目录

为了检查标定框绘制效果，RoadsidePerceptionManager 现在会在 `RoadsideAgent/output/` 下自动保存每次运行的带框图像。

目录结构如下：

```text
RoadsideAgent/output/
└── RouteScenario_0/
    └── 20260629_153045_123456/
        ├── roadside_01/
        │   ├── tick_000010_frame_000321_vehicle_42_visible.jpg
        │   └── ...
        └── roadside_02/
            └── ...
```

说明：

- 第一层目录是场景名，例如 `RouteScenario_0`。
- 第二层目录是本次运行的时间戳，因此同一场景的多次运行不会互相覆盖。
- 第三层目录按路侧摄像头 `camera_id` 分开保存。
- 每张图都是当前采样帧的 `image_with_bbox`，文件名里包含 `tick`、CARLA sensor `frame`、`vehicle_id`，以及该车在该摄像头下是否可见。

## 与旧版的关键差异

- 旧版目标车定位依赖外部车辆信息 JSON；新版通过车辆编号维护 CARLA actor，再直接读取 actor。
- 旧版同时画 3D 框和 2D 外接框；新版只保留绿色加粗 2D 框。
- 旧版 `get_vehicle_corners_2d()` 会投影所有角点；新版只使用在近裁切面前方的角点计算 bbox。
- 旧版 Agent 链路包含 LLM 多阶段推理；新版目前接入的是一轮批处理 VLM 调用，采用 PilotAgent 风格的 prompt 分层：system prompt 承载职责、规则与输出约束，user prompt 只承载当前环境输入。
- 新版图像标注使用 `vehicle {actor.id}`，每辆车单独生成带框图。

## 尚未擅自决定的业务问题

- RoadsideAgent 接入 leaderboard evaluator 的具体位置。
- 每条 route 的摄像头位姿采集方式。
- 车辆端具体如何将 PilotAgent 的 `upstream` 与 `task_status` 上报到 RoadsideAgent。
