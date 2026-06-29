# RoadsideAgent Bench2Drive 嵌入说明

## 嵌入原则

RoadsideAgent 不嵌入 `team_code`，因为它不是车端控制 agent，也不应成为 MindDrive 的车载传感器。它作为 route 级旁路系统挂在 Bench2Drive leaderboard 的 `ScenarioManager` 中。

Bench2Drive 侧只改一个文件：

```text
Bench2Drive/leaderboard/leaderboard/scenarios/scenario_manager.py
```

RoadsideAgent 侧的集成逻辑集中在：

```text
RoadsideAgent/roadside_agent/bench2drive_hook.py
```

## 生命周期

### 1. 场景加载

`ScenarioManager.load_scenario()` 中，原有车端传感器创建完成后调用：

```python
self._setup_roadside_agent()
```

hook 会使用当前 route name 加载配置：

```text
RoadsideAgent/config/routes/{RouteScenario_x}.yaml
```

如果配置不存在，RoadsideAgent 自动禁用，不影响原评测流程。

### 2. 每 tick 触发

`ScenarioManager._tick_scenario()` 中，世界 tick、actor state 更新、ego agent 控制、scenario tree tick 完成后调用：

```python
self._tick_roadside_agent()
```

hook 内部先判断 `sampling.interval_ticks`，只有到低频采样点才执行：

1. 从 `VehicleRegistry` 读取近期通过 `/vehicles/state` 上报过状态的车辆。
2. 用 `vehicle_id` 解析对应 CARLA actor，并绑定到注册表。
3. 只对这些可交互车辆做路侧相机投影和图像标框。
4. 调用 RoadsideRuntime 批处理推理。
5. 对 `should_send=true` 的车辆，按其上报的 endpoint 下发自然语言建议。
6. 将结果保存到 hook 的 `last_result` 和 `history`，作为后续 Agent context 的来源。

### 3. 场景结束

`ScenarioManager.stop_scenario()` 和 `cleanup()` 都会调用：

```python
self._cleanup_roadside_agent()
```

用于销毁路侧 camera sensors，避免传感器泄漏到下一条 route。

## 触发链路

```text
LeaderboardEvaluator
  -> RouteScenario(world, config)
  -> ScenarioManager.load_scenario(...)
      -> AgentWrapper.setup_sensors(ego)          # 原 MindDrive/PilotAgent 车端链路
      -> Bench2DriveRoadsideHook.start()          # 新 RoadsideAgent 路侧链路
  -> ScenarioManager.run_scenario()
      -> _tick_scenario()
          -> world.tick()
          -> CarlaDataProvider.on_carla_tick()
          -> ego agent run_step()
          -> ego.apply_control()
          -> scenario_tree.tick_once()
          -> Bench2DriveRoadsideHook.tick()
```

## 与 PilotAgent 的区别

PilotAgent 通过 `team_code` 继承 MindDrive agent，因此每 tick 跟随 ego agent 的 `run_step()` 被触发。

RoadsideAgent 是路侧系统，关注多车辆和 world-fixed cameras，所以挂在 `ScenarioManager` 的 route tick 旁路，不参与 ego control 的同步传感器校验，也不修改 MindDrive 输出。
