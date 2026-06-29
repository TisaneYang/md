# Bench2Drive 接入计划

本文只说明需要新增和改动的点，不直接改 Bench2Drive 主流程。

## 新增内容

1. `RoadsideAgent/roadside_agent/projection.py`

   负责目标车辆 3D bbox 到相机 2D bbox 的投影。输入是 CARLA actor 和路侧相机 transform。

2. `RoadsideAgent/roadside_agent/camera.py`

   负责把路侧相机作为独立 world actor 创建。这里不使用 `attach_to=ego_vehicle`，因为路侧相机必须固定在世界坐标中。

3. `RoadsideAgent/roadside_agent/manager.py`

   负责创建相机、读取最新图像、调用投影、绘制绿色 2D 框，并返回结构化感知结果。

4. `RoadsideAgent/config/roadside_cameras.yaml`

   保存路侧相机的绝对位置、姿态、图像尺寸、FOV、投影近裁切面和 bbox 线宽。

## 需要改动 Bench2Drive 的位置

### 方案 A：在 scenario runner 主循环旁接入

在场景初始化完成后创建：

```python
from roadside_agent import RoadsidePerceptionManager, RoadsideAgent

roadside_manager = RoadsidePerceptionManager.from_route_config(
    world=world,
    route_name=config.name,
    config_root="RoadsideAgent/config",
)
roadside_manager.spawn_cameras()
roadside_agent = RoadsideAgent(roadside_manager)
```

在每个 tick 中按配置频率调用：

```python
if roadside_manager.should_sample(tick_index):
    roadside_result = roadside_agent.analyze(
        target_actors=vehicle_registry.active_actor_map(),
    )
```

场景结束时调用：

```python
roadside_manager.destroy()
```

优点：RoadsideAgent 与车端 agent 解耦，不影响 `AgentWrapper.setup_sensors()` 的车载传感器定义。

### 方案 B：在具体 scenario 中接入

每个需要路侧智能体的 scenario 自己创建 `RoadsidePerceptionManager`，并把车辆注册表中的一批 actor 传入。

优点：摄像头位置可以直接跟该 scenario 的触发点、路口位置、事故点绑定。
缺点：多个 scenario 要重复接入生命周期管理。

## 路侧摄像头如何放置

CARLA 传感器创建方式与 Bench2Drive 现有车载相机类似，但差异是第三个参数不能传 `ego_vehicle`：

```python
bp = world.get_blueprint_library().find("sensor.camera.rgb")
bp.set_attribute("image_size_x", "800")
bp.set_attribute("image_size_y", "600")
bp.set_attribute("fov", "90")

transform = carla.Transform(
    carla.Location(x=266.30, y=-307.80, z=5.00),
    carla.Rotation(pitch=-5.71, yaw=180.0, roll=0.0),
)
sensor = world.spawn_actor(bp, transform)
sensor.listen(callback)
```

如果传入 `attach_to=ego_vehicle`，相机会变成车载相机，不符合路侧智能体设定。

## 目标车辆定位与批处理

新版不再要求车辆上报位姿，而是通过车辆编号维护 CARLA actor，再直接读取：

```python
target_transform = vehicle_actor.get_transform()
target_bbox = vehicle_actor.bounding_box
```

其中 `target_bbox.extent` 是半长宽高，`target_bbox.location` 是 bbox 中心相对 actor origin 的本地偏移。新版投影会把这个偏移计入世界角点计算，避免把 actor origin 错当 bbox 中心。

多车辆批处理由 `VehicleRegistry` 维护稳定编号到 actor/state 的映射：

```python
vehicle_registry.upsert_actor(actor, state=state, tick_index=tick_index)
roadside_agent.analyze(target_actors=vehicle_registry.active_actor_map())
```

车辆编号使用 CARLA `actor.id`。每辆车会生成独立带框图，图中标注 `vehicle {actor.id}`。

## 路侧到车辆通信

每个车辆实例在 RoadsideAgent 侧维护一个临时通信地址，当前用 `ip:port` 表示：

```python
vehicle_registry.upsert_actor(
    actor,
    state=state,
    endpoint="127.0.0.1:9101",
    tick_index=tick_index,
)
```

指令下发通过 `VehicleCommandClient` 完成：

```python
command_client = VehicleCommandClient(vehicle_registry.endpoint_map())
roadside_agent = RoadsideAgent(roadside_manager, command_client=command_client)

roadside_agent.send_to_vehicle(
    vehicle_id=str(actor.id),
    message={
        "type": "roadside_command",
        "summary": "slow down and keep lane",
    },
)
```

临时协议为 HTTP JSON POST：

```text
POST http://{ip}:{port}/roadside/message
Content-Type: application/json
```

请求体包含 `vehicle_id` 和 `message`。后续车辆端协议确定后，只需要替换 `VehicleCommandClient` 的底层发送实现。

## 近裁切面处理

只使用相机坐标中 `depth = X > near_clip` 的 bbox 角点参与 2D bbox 计算。

如果可用角点太少，则认为目标当前不适合生成 bbox，返回不可见。这样可以避免车辆部分穿过相机后方时，投影除以接近 0 或负深度造成异常长框。

## 建议暂不改动的内容

- 暂不修改 MindDrive 车端模型。
- 暂不修改 PilotAgent prompt。
- 暂不把 RoadsideAgent 输出直接写入车辆控制。
- 暂不把 RoadsideAgent 做成 Bench2Drive 的 autoagent sensor，因为路侧相机不是车载传感器。

## 当前已确认

1. 目标车辆不是固定某一辆车，RoadsideAgent 后续按多车辆批处理工作。
2. Bench2Drive leaderboard 按 route config 逐个评测，摄像头位姿按 `RouteScenario_{route_id}` 手动配置。
3. 摄像头数量自由配置，不固定 front/rear 模式。
4. 带框图像只给 RoadsideAgent。
5. RoadsideAgent 低频采样，采样间隔写入配置。
6. 车辆稳定编号使用 CARLA `actor.id`。
7. 多车辆视觉输入按车辆拆分，每辆车一张或多张带框图。

## 仍待确认

1. RoadsideAgent 接入 leaderboard evaluator 的具体位置：`_load_and_run_scenario` 中创建，还是封装成单独的 runner hook。
2. 每条 route 的摄像头位姿如何采集和管理：人工测量后写 YAML，还是提供一个辅助脚本从 CARLA 当前 spectator 位姿导出。
3. 车辆端接收指令的 HTTP 路径、消息 schema、确认/重试策略。
