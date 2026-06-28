# Agent2 设计草图

## 1. 目标

`agent2` 从头设计，不再围绕单一 `strategy_id` 展开，而是采用：

1. 环境事实抽取
2. 目的地建模
3. 空间关系推理
4. 动作原语组合
5. 任务翻译

核心目标：

- 支持多步组合动作
- 明确动作顺序为什么成立
- 避免为每一种组合动作单独定义一个大策略


## 2. 本阶段范围

本阶段只做：

- 定义 `agent2` 的状态 schema
- 定义 workflow 草图
- 统一车道、方位、空间位置的描述方式
- 标清哪些字段必须来自原语词表，哪些字段允许受限自由填充

本阶段不做：

- 代码实现
- prompt 落地
- 规则实现
- 测试实现


## 3. 统一表示规范

这一节是 `agent2` 最重要的基础约定。后续所有 schema 都必须遵守。

### 3.1 车道编号口径

- 一律按目标车辆前进方向理解。
- `lane_index` 一律采用“从左到右，1-based”。
- `lane_count` 表示与目标车辆同向的可通行车道总数。
- 因此：
  - `ego_lane_index == 1` 表示最左车道
  - `ego_lane_index == lane_count` 表示最右车道

### 3.2 左右方位口径

- 一律按目标车辆视角表达左右。
- 禁止使用路侧视角定义 `left` / `right`。
- 所有 `gap_status`、`relative_direction` 都遵守这个规则。

### 3.3 字段类型分类

`agent2` 中的字段分成四类：

1. 原语字段
   - 取值必须来自固定词表
   - 例如动作原语、空间迁移原语

2. 枚举字段
   - 取值必须来自有限集合
   - 例如 `risk_level`、`road_phase`

3. 结构化字段
   - 由多个枚举字段组成
   - 例如空间锚点、拓扑关系、车道对齐要求

4. 受限自由文本
   - 允许自然语言，但只能用于可读性摘要
   - 不允许作为核心规则判断依据

### 3.4 字段设计原则

- 能拆成结构化字段，就不要写成长字符串。
- 能用原语或枚举表达，就不要交给模型自由发挥。
- 自由文本只作为摘要，不作为规则分支依据。


## 4. 原语与自由填充边界

### 4.1 动作原语

以下字段属于动作原语，必须来自固定词表：

- `maneuver_sequence.sequence`

第一版支持的动作原语：

- `keep_lane`
- `change_lane_left`
- `change_lane_right`
- `go_straight`
- `turn_left`
- `turn_right`
- `pull_over`
- `stop`

第一版暂不落实：

- `observe`
- `decelerate`
- `u_turn`



## 5. 首批状态 Schema

建议定义统一状态 `Agent2State`，包含以下主要层级。

### 5.1 输入层

```json
{
  "raw_images": {},
  "vehicle_info": {},
  "traffic_command": null
}
```

### 5.2 基础事实层 `fact_pack`

用途：
- 保存客观输入事实
- 不包含推理语言

```json
{
  "vehicle_type": "轿车",
  "vehicle_color": "白色",
  "vehicle_plate": "京A12345",
  "vehicle_intent": "路口右转后靠边停车",
  "speed_kmh": 28.0,
  "acceleration_mps2": 0.1,
  "in_blind_spot": false,
  "visible_camera_ids": ["cam_front_1"],
  "traffic_command_text": "通过路口后靠右停车等待"
}
```

字段类型：

- 全部为客观事实字段
- 不引入原语

### 5.3 环境结构层 `scene_model`

用途：
- 保存路口、车道、停车空间等结构化环境事实

```json
{
  "is_intersection": true,
  "lane_count": 3,
  "ego_lane_index": 2,
  "lane_description": "位于中间车道",
  "front_gap_status": "clear",
  "left_gap_status": "clear",
  "right_gap_status": "narrow",
  "stop_line_visible": true,
  "confidence": "medium"
}
```

字段类型说明：

- `front_gap_status` / `left_gap_status` / `right_gap_status`
  枚举字段
- `lane_description`
  受限自由文本

### 5.4 位置与目的地联合表示层 `navigation_context`

用途：
- 用一层信息同时讲清楚三件事：
- 车辆当前在哪
- 目的地在哪
- 从当前位置到目的地需要怎样驾驶

```json
{
  "analysis": "【目标车辆在哪】目标车辆当前位于路口前的中间车道，尚未贴近右侧路边。\\n【目的地在哪】目的地位于通过路口后的右侧路边停车区域。\\n【综上，为了驾驶到目的地，需要怎样】车辆需要先向右侧通行路径准备，在路口执行右转，出路口后继续靠近右侧路边，并在目标区域安全停车。",
  "goal_priority": "high"
}
```

字段类型说明：

- `analysis`
  受限自由文本，但内部必须按三段式组织：
  `【目标车辆在哪】`
  `【目的地在哪】`
  `【综上，为了驾驶到目的地，需要怎样】`
- `goal_priority`
  枚举字段

约束：

- 这一层不再要求固定子字段。
- 但分析中必须明确当前位置与目的地的相对空间关系。
- “需要怎样驾驶”应当能直接支持后续动作序列规划。

### 5.7 动作序列层 `maneuver_sequence`

用途：
- 根据 `navigation_context` 输出可执行动作原语序列
- 这里的结果直接交给输出层处理，不再先做字段级直译

```json
{
  "sequence_reason": "目标在路口后右侧路边。车辆当前位于路口前中间车道，因此需要先向右侧完成车道准备，再在路口右转，出路口后靠边停车。",
  "sequence": [
    "change_lane_right",
    "turn_right",
    "pull_over",
    "stop"
  ],
  "sequence_confidence": "medium"
}
```

字段类型说明：

- `sequence`
  动作原语列表
- `sequence_reason`
  受限自由文本
- `sequence_confidence`
  枚举字段

### 5.8 输出层 `tasks`

用途：
- 面向车辆输出带语义的驾驶任务
- 不是把 `sequence` 逐字段翻译成一句句模板，而是结合 `sequence_reason` 组织成连贯指令

```json
{
  "tasks": [
    {
      "description": "先向右侧车道靠拢，为路口右转做准备。",
      "time_limit": 8
    },
    {
      "description": "通过路口时保持右转，进入路口后的右侧道路。",
      "time_limit": 10
    },
    {
      "description": "右转完成后继续靠近右侧路边，并在目标区域安全停车。",
      "time_limit": 12
    }
  ]
}
```

字段类型说明：

- `description`
  受限自由文本
- `time_limit`
  数值字段

### 5.9 验证层 `validation_result`

用途：
- 对 `maneuver_sequence` 与 `tasks` 做整体一致性检查
- 根据整体语义和场景图像判断输出是否合理，而不是只检查单个字段是否对齐

```json
{
  "is_valid": true,
  "issues": [],
  "validation_summary": "动作序列与任务语义一致，能够从当前位置到达路口后右侧目标区域，且不存在在路口内停车的违规描述。"
}
```

字段类型说明：

- `is_valid`
  布尔字段
- `issues`
  受限自由文本列表，用于记录发现的问题
- `validation_summary`
  受限自由文本，用于总结整体判断


## 6. Workflow 草图

建议 `agent2` 第一版 workflow：

```text
perception_normalize
-> scene_model_extract
-> destination_inference
-> navigation_context_build
-> maneuver_sequence_planning
-> task_realization
-> output_validation
```


## 7. 各节点职责

### 7.1 `perception_normalize`

输入：
- `raw_images`
- `vehicle_info`
- `traffic_command`

输出：
- `fact_pack`
- `camera_coverage`

职责：
- 清洗输入
- 规范车辆事实
- 不做推理

### 7.2 `scene_model_extract`

输入：
- `fact_pack`
- 图像

输出：
- `scene_model`

职责：
- 抽取车道、路口、可停车区域、周边参与者等结构信息
- 输出结构化环境层

### 7.3 `destination_inference`

输入：
- `fact_pack`
- `scene_model`
- `traffic_command`

输出：
- `destination_model`

职责：
- 明确阶段性目的地
- 明确目标来源与优先级

### 7.4 `navigation_context_build`

输入：
- `scene_model`
- `destination_model`
- `fact_pack`

输出：
- `navigation_context`

职责：
- 输出三段式自然语言分析
- 明确说明车辆当前在哪、目的地在哪、以及为了到达目的地需要怎样驾驶

### 7.5 `maneuver_sequence_planning`

输入：
- `navigation_context`

输出：
- `maneuver_sequence`

职责：
- 根据当前位置与目的地关系规划动作原语序列
- 必须输出能解释动作顺序成立原因的 `sequence_reason`

限制：
- 第一版禁止输出 `observe`
- 第一版禁止输出 `decelerate`
- 第一版禁止输出 `u_turn`

### 7.6 `task_realization`

输入：
- `maneuver_sequence`
- `navigation_context`

输出：
- `tasks`

职责：
- 根据 `sequence` 和 `sequence_reason` 生成连贯任务描述
- 不做“动作字段到任务字段”的逐项机械翻译

### 7.7 `output_validation`

输入：
- `maneuver_sequence`
- `tasks`
- `navigation_context`
- `scene_model`

输出：
- `validation_result`

职责：
- 从整体上检查当前位置、目标位置、动作序列、任务描述是否一致
- 发现不合理输出时给出问题摘要，并允许后续触发回退或重规划


## 8. 第一版支持范围

优先支持的组合：

1. `keep_lane -> go_straight`
2. `change_lane_left -> go_straight`
3. `change_lane_right -> go_straight`
4. `turn_left -> go_straight`
5. `turn_right -> go_straight`
6. `change_lane_right -> turn_right`
7. `turn_right -> pull_over -> stop`
8. `change_lane_right -> turn_right -> pull_over -> stop`

第一版暂不支持：

1. 任意包含 `u_turn` 的组合
2. 显式包含 `observe` 的组合
3. 显式包含 `decelerate` 的组合
4. 三次以上横向机动的复杂组合


## 9. 与当前 Agent 的关系

`agent2` 与现有 `agent` 并行存在：

- 不复用当前 `strategy_id` 主逻辑
- 不要求兼容当前内部状态结构
- 只在最外层尽量保持输出字段兼容，例如 `risk_level`、`tasks`、`advice`


## 10. 下一步

建议下一步按以下顺序推进：

1. 定义 `agent2/workflow/state.py` 的 TypedDict
2. 定义 `agent2/workflow/graph.py` 的节点连线
3. 设计 `scene_model_extract`、`destination_inference`、`navigation_context_build` 的 prompt schema
4. 再开始最小实现
