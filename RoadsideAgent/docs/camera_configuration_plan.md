# 路侧摄像头配置规划

## 目标

在已有 Bench2Drive 场景中额外插入一组路侧摄像头，作为 RoadsideAgent 的视觉来源。摄像头不属于 MindDrive 的车载传感器，也不传给 PilotAgent 或 MindDrive。

## 设计结论

1. Bench2Drive leaderboard 按 route config 逐个评测，摄像头配置按 `RouteScenario_{route_id}` 手动预置。
2. 摄像头数量不固定，配置文件中有几个就创建几个。
3. 摄像头使用 CARLA world 绝对坐标，不绑定任何车辆。
4. RoadsideAgent 按配置频率低频运行；相机传感器可以持续缓存最新图像。
5. 多车辆批处理由车辆编号到 actor/state 的注册表维护，RoadsideAgent 每次推理拿一批车辆。

## 配置文件形态

推荐路径：

```text
RoadsideAgent/config/routes/RouteScenario_{route_id}.yaml
```

示例：

```yaml
route_name: "RouteScenario_0"

cameras:
  - id: "roadside_01"
    name: "manual roadside camera 01"
    enabled: true
    location:
      x: 266.30
      y: -307.80
      z: 5.00
    rotation:
      pitch: -5.71
      yaw: 180.00
      roll: 0.00
    image_size:
      width: 800
      height: 600
    fov: 90.0

projection:
  near_clip: 0.10

visualization:
  bbox_thickness: 4

sampling:
  interval_ticks: 10
```

## 配置加载规则

Bench2Drive leaderboard 的 route parser 会把 XML 中的 route `id` 转成 `RouteScenario_{id}`。因此 RoadsideAgent 默认按 route name 找配置：

```python
roadside_manager = RoadsidePerceptionManager.from_route_config(
    world=world,
    route_name=config.name,  # e.g. "RouteScenario_0"
    config_root="RoadsideAgent/config",
)
```

如果某些非 leaderboard 流程确实是按单个 scenario name 运行，可以后续再加 `config/scenarios/{scenario_name}.yaml`。当前 Bench2Drive leaderboard 链路优先 route 级配置。

## 在场景中插入摄像头的方式

Bench2Drive 车载相机通常通过 `AgentWrapper.setup_sensors()` 创建，并传入车辆作为 attach 对象。路侧相机不能走这条逻辑，因为它不是车载相机。

路侧相机应在场景初始化后、仿真 tick 开始前创建：

```python
from pathlib import Path

from roadside_agent import RoadsidePerceptionManager

roadside_manager = RoadsidePerceptionManager.from_route_config(
    world=world,
    route_name=config.name,
    config_root=Path("RoadsideAgent/config"),
)
roadside_manager.spawn_cameras(warmup_ticks=2)
```

底层等价于：

```python
bp = world.get_blueprint_library().find("sensor.camera.rgb")
bp.set_attribute("image_size_x", "800")
bp.set_attribute("image_size_y", "600")
bp.set_attribute("fov", "90")
bp.set_attribute("role_name", "roadside_01")

transform = carla.Transform(
    carla.Location(x=266.30, y=-307.80, z=5.00),
    carla.Rotation(pitch=-5.71, yaw=180.0, roll=0.0),
)
sensor = world.spawn_actor(bp, transform)
```

这里不能传 `attach_to=ego_vehicle`。

## 低频采样

RoadsideAgent 不需要每 tick 都推理。主循环可按 tick 判断：

```python
if roadside_manager.should_sample(tick_index):
    result = roadside_agent.analyze(target_actors=vehicle_registry.active_actor_map())
```

`interval_ticks` 应放在场景摄像头配置中。比如 CARLA 固定步长为 0.05s，`interval_ticks: 10` 约等于 0.5s 触发一次。

## 多车辆批处理

后续 Agent 会收到多车状态并一次性推理，因此需要维护稳定车辆编号：

```python
vehicle_registry.upsert_actor(
    actor=carla_actor,
    state={
        "speed": speed,
        "intention": intention,
    },
    tick_index=tick_index,
)

target_actors = vehicle_registry.active_actor_map()
result = roadside_agent.analyze(target_actors=target_actors)
```

车辆编号使用 CARLA `actor.id`。批处理输出按车辆拆分，每辆车一组带框图；图中标注 `vehicle {actor.id}`。

车辆下发通信地址也挂在同一个车辆记录上，当前用 `ip:port` 暂代：

```python
vehicle_registry.upsert_actor(
    actor=carla_actor,
    state={"speed": speed},
    endpoint="127.0.0.1:9101",
    tick_index=tick_index,
)
```

RoadsideAgent 通过车辆 id 下发消息：

```python
send_result = roadside_agent.send_to_vehicle(
    vehicle_id=str(carla_actor.id),
    message={"type": "roadside_command", "summary": "yield to pedestrian"},
)
```

## 推荐接入点

优先推荐在 scenario runner 的场景生命周期外层接入，而不是逐个 scenario 内部复制代码：

1. 场景 world 和 ego vehicles 创建完成后，创建 `RoadsidePerceptionManager`。
2. 调用 `spawn_cameras()`，让传感器开始缓存图像。
3. 每 tick 或每 N tick，从车辆注册表取当前 active actor map。
4. 调用 `roadside_agent.analyze(target_actors=...)`。
5. 场景结束时调用 `roadside_manager.destroy()`。

如果某些场景摄像头位置强绑定 scenario 内部关键点，也可以在该 scenario 内部构造配置，但要避免每个 scenario 重复实现传感器生命周期。

## 需要手动配置的相机参数

- `location.x/y/z`：CARLA 世界坐标。
- `rotation.pitch/yaw/roll`：相机朝向。
- `image_size.width/height`：图像尺寸。
- `fov`：水平视场角。
- `enabled`：便于临时关闭某个相机，不删配置。

## 尚需确认

1. RoadsideAgent 接入 leaderboard evaluator 的具体位置：`_load_and_run_scenario` 中创建，还是封装成单独的 runner hook。
2. 每条 route 的摄像头位姿如何采集和管理：人工测量后写 YAML，还是提供一个辅助脚本从 CARLA 当前 spectator 位姿导出。
