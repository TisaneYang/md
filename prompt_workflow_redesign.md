# RoadsideAgent Prompt / Workflow 重写方案

## 1. 当前问题的根因

现有流程不是单纯“prompt 写得太长”，而是整体状态设计有三个结构性问题：

1. 同一份上下文被重复解释三次
   - `recognize_lane_position`
   - `understand_semantics`
   - `generate_plan`
   - `decompose_tasks`
   这四步里，模型多次重复阅读相同车辆信息、摄像头信息和部分前序结果，token 消耗高，而且前面的小偏差会被后续放大。

2. 中间状态没有“压缩层”
   - `semantic_parse` 直接把自然语言 reasoning、constraints、recommended_action 全部塞给下一步。
   - `plan` 又把 summary、decision_basis、objective 全部塞给 `decompose_tasks`。
   - 后续节点消费的是“原始生成内容”，不是“受控的决策变量”。

3. 任务拆解依赖自由文本而不是受控决策
   - 现在 `decompose_tasks` 主要依据 `plan + semantic_parse + lane_analysis` 做自由生成。
   - 如果 `summary`、`objective` 或 `recommended_action` 表述松散，最后一步就容易偏题、冗余、左右混乱。

4. 可规则化的信息没有前置规则化
   - `scene_type` 是规则判断，这很好。
   - 但像“是否必须干预”“是否优先服从交警”“盲区是否必须保守”“左右方向是否要车端视角翻转”这些仍然交给 LLM 在后面自由发挥。

5. 输出目标混在一起
   - 当前 prompt 同时要求“语义理解 + 风险评估 + 总体规划 + 任务拆解”。
   - 模型会倾向写完整解释，而不是只保留真正会影响下一步的变量。


## 2. 重写目标

重写时建议把目标从“让模型完整思考”改成“让系统逐步收敛到受控决策”：

1. 前面尽量少生成自然语言，多生成短字段。
2. 中间只保留对下一步真正有用的结构化变量。
3. 最后一跳不再重新思考全场景，只把“已定策略”翻译成车辆任务。
4. 规则能决定的事情不用 LLM 再判断。
5. 每一步 schema 必须更窄，禁止大段 reasoning 污染状态。


## 3. 建议的新架构

建议从 7 个节点改成 5 个节点，其中只有 2 个核心 LLM 调用。

### A. `perception_normalize`

职责：
- 清洗输入
- 统一车辆信息
- 生成摄像头可见性摘要
- 明确左右方向转换规则

输出：
- `fact_pack`

推荐 schema：

```json
{
  "vehicle_type": "轿车",
  "vehicle_intent": "直行通过路段",
  "speed_kmh": 45.5,
  "acceleration_mps2": 0.2,
  "in_blind_spot": false,
  "visible_camera_ids": ["cam_front_1"],
  "camera_relation_note": "前视相对而行，路侧左侧等于车端右侧",
  "traffic_command_text": "前方交警指挥靠右减速通行，到路边等待进一步指令。"
}
```

说明：
- 这里只保留客观事实，不保留任何推理语言。

### B. `rule_gate`

职责：
- 用规则做硬约束裁决
- 决定当前属于哪种控制模式

输出：
- `control_policy`

推荐 schema：

```json
{
  "policy_mode": "traffic_command",
  "must_intervene": true,
  "safety_posture": "conservative",
  "needs_lane_reasoning": true,
  "left_right_reference": "vehicle_perspective",
  "hard_constraints": [
    "交通管理指令优先",
    "涉及左右时必须按车端视角表达"
  ]
}
```

说明：
- 这一步尽量不用 LLM。
- `scene_type` 和 `active_skills` 可以并入这里，不需要单独成节点。

### C. `structured_assessment`（LLM 1）

职责：
- 只做“受控场景判断”
- 输出极短、可消费的中间变量
- 不允许大段 reasoning

输入：
- `fact_pack`
- `control_policy`
- 图像

输出：
- `assessment`

推荐 schema：

```json
{
  "scene_summary": "目标车当前正常前进，收到靠右减速等待指令。",
  "risk_level": "medium",
  "primary_goal": "靠右减速通行并进入等待",
  "key_constraints": [
    "右侧通行空间需要确认",
    "动作应平稳，避免激进并线"
  ],
  "maneuver_type": "pull_over_right",
  "lane_change_needed": true,
  "observation_needed": true
}
```

关键约束：
- 不输出长 reasoning。
- `key_constraints` 最多 3 条。
- `scene_summary` 最多 30 字。
- 只保留会影响规划的变量。

### D. `strategy_compiler`（规则 + 小模板；必要时 LLM 2）

职责：
- 根据 `control_policy + assessment` 生成唯一策略骨架
- 决定是否应该走“观察后执行”“立即停车”“保持直行”“靠边等待”等固定模式

输出：
- `strategy`

推荐 schema：

```json
{
  "strategy_id": "pull_over_right_then_wait",
  "summary": "先减速确认右侧安全，再靠右通行并等待。",
  "execution_mode": "traffic_command",
  "task_style": "sequential_vehicle_actions",
  "step_constraints": [
    "先观察后横向动作",
    "每步只能包含单一驾驶动作"
  ]
}
```

建议：
- 这一步尽量规则化，不必让模型自由发挥。
- 可以维护一个 `strategy_id -> task template` 映射表。

### E. `task_realizer`（LLM 2 或纯模板）

职责：
- 严格把 `strategy` 翻译成 1 到 4 步车辆任务
- 不再允许重新判断风险和目标

输入：
- `strategy`
- `assessment`
- 少量必要事实，例如 `vehicle_intent`、`lane_change_needed`

输出：

```json
{
  "tasks": [
    {"description": "平稳减速并观察右侧通行空间。", "time_limit": 6},
    {"description": "确认安全后向右变道靠近路边。", "time_limit": 8},
    {"description": "在路边安全位置停车等待后续指令。", "time_limit": 12}
  ]
}
```

关键点：
- 这一步不能再看到整段 `semantic_parse.reasoning`。
- 也不应该再看到完整的 `camera_coverage` JSON。
- 它只是“翻译器”，不是“第二个规划器”。


## 4. Prompt 层面的重写原则

### 原则 1：把“思考要求”改成“字段定义”

当前 `system_prompt.md` 主要是在告诉模型“你要做哪些任务”。  
重写后应改成：

- 你的角色
- 你必须遵守的优先级
- 每一步允许输出哪些字段
- 哪些字段禁止输出

换句话说，不要写：

- “概括当前场景和车辆驾驶意图”
- “给出风险等级”
- “给出推荐动作”

而要写：

- `scene_summary`: 不超过 30 字，只描述当前状态
- `risk_level`: 只能是 `low|medium|high`
- `primary_goal`: 只能写一个目标

### 原则 2：禁止开放式 reasoning 落盘

现在的 `reasoning` 字段会污染后续步骤。  
建议：

- 中间步骤取消 `reasoning`
- 如果一定要保留调试信息，单独加 `debug_reasoning`
- `debug_reasoning` 不允许进入后续 prompt

### 原则 3：每步只做一个认知任务

例如：

- 识别车道位置：只输出车道相关字段
- 评估策略：只输出策略所需变量
- 生成任务：只输出 tasks

不要在一个 prompt 里同时要求：

- 风险判断
- 干预判断
- 任务拆解

### 原则 4：最后一步不允许重新总结世界

`task_realizer` 的 prompt 应明确写：

- 不要重新分析场景
- 不要重复交通指令背景
- 不要输出依据
- 只根据给定策略输出车辆动作序列


## 5. 建议的新 Prompt 组织方式

当前：
- `system_prompt.md`
- `skill_prompts.json`

建议改为：

1. `base_rules.md`
   - 角色
   - 安全原则
   - 视角约束
   - JSON 输出总原则

2. `assessment_prompt.md`
   - 专门给 `structured_assessment`

3. `task_realizer_prompt.md`
   - 专门给 `task_realizer`

4. `strategy_library.json`
   - 维护 `strategy_id`
   - 每种策略的默认任务骨架
   - 适用条件

5. `policy_rules.py`
   - 交通指令优先
   - 盲区保守
   - 左右翻转
   - 是否必须干预

`skill_prompts.json` 可以保留，但建议从“自由提示词”转为“策略偏置标签”，例如：

```json
{
  "traffic_command": {
    "policy_mode": "traffic_command",
    "safety_posture": "conservative"
  },
  "blind_spot": {
    "policy_mode": "safety_guidance",
    "safety_posture": "conservative"
  }
}
```

也就是说，skill 不再直接扩写 prompt，而是转成受控变量。


## 6. 推荐的新输出结构

现在最终输出里混了很多“对用户友好”和“对系统友好”的字段。  
建议拆成两层：

```json
{
  "decision": {
    "policy_mode": "traffic_command",
    "risk_level": "medium",
    "must_intervene": true,
    "strategy_id": "pull_over_right_then_wait"
  },
  "instruction": {
    "summary": "先减速确认右侧安全，再靠右通行并等待。",
    "tasks": [
      {"description": "平稳减速并观察右侧通行空间。", "time_limit": 6},
      {"description": "确认安全后向右变道靠近路边。", "time_limit": 8},
      {"description": "在路边安全位置停车等待后续指令。", "time_limit": 12}
    ]
  },
  "debug": {
    "scene_type": "traffic_command",
    "visible_cameras": ["cam_front_1"],
    "lane_analysis": {
      "one_way_lane_count": 3,
      "ego_lane_index": 2
    }
  }
}
```

好处：
- `decision` 给系统逻辑消费
- `instruction` 给车端消费
- `debug` 给研发排查

不要再让 `debug` 反向污染生成流程。


## 7. 对现有代码的具体改造建议

### 7.1 Workflow 改造

当前：

```text
perception
-> scene_recognition
-> skill_activation
-> lane_position
-> semantic_understanding
-> planning
-> decompose
```

建议改为：

```text
perception_normalize
-> rule_gate
-> lane_position
-> structured_assessment
-> strategy_compile
-> task_realize
```

如果想再极简一点，可以直接：

```text
perception_normalize
-> rule_gate
-> structured_assessment
-> task_realize
```

其中 `lane_position` 只有在 `needs_lane_reasoning=true` 时才调用。

### 7.2 `AgentState` 改造

建议删除或弱化这些字段：
- `dynamic_system_prompt`
- `reasoning`
- `advice`
- `active_skills`

建议新增：
- `fact_pack`
- `control_policy`
- `assessment`
- `strategy`
- `debug_trace`

### 7.3 `LLMInterface` 改造

建议把接口从“按业务阶段命名”改成“按输出契约命名”：

- `recognize_lane_position`
- `generate_structured_assessment`
- `realize_tasks`

删除：
- `generate_plan`
- 宽泛的 `analyze_scene`

因为 `plan` 这个概念太大，很容易把模型重新带回自由发挥。

### 7.4 Prompt 注入方式改造

当前是把 `system_prompt + scene_type + active_skills` 拼接成超长 system prompt。  
建议改成：

- 固定 `base_rules`
- 每个节点独立的 task prompt
- 通过少量结构化字段传入“场景偏置”

例如：

```python
system_prompt = base_rules + assessment_prompt
user_prompt = render_assessment_input(fact_pack, control_policy)
```

而不是：

```python
system_prompt = system_prompt + scene_type + lots_of_skill_text
```


## 8. 新版 Prompt 示例

### 8.1 `structured_assessment` system prompt

```text
你是路侧协同决策模块。

你的任务不是直接生成车辆任务，而是输出最小化的决策变量。

规则：
1. 只输出合法 JSON。
2. 不要输出解释、前后缀或 markdown。
3. 不要输出长 reasoning。
4. scene_summary 不超过 30 字。
5. key_constraints 最多 3 条，每条不超过 16 字。
6. primary_goal 只能有一个。
7. 如果存在交通管理指令，primary_goal 必须围绕该指令。
8. 涉及左右时，必须按车端视角理解。
```

### 8.2 `task_realizer` system prompt

```text
你是车辆任务翻译模块。

你不会重新分析场景，也不会重新制定策略。
你只根据输入的 strategy 和 constraints 生成车辆可执行任务。

规则：
1. 只输出 {"tasks": [...]}。
2. 任务数量 1 到 4 个。
3. 每个任务只包含一个主要动作。
4. description 必须直接面向车辆执行，不得出现“通知车辆”“发送指令”“监控车辆”。
5. 若需要横向动作，必须先有观察或减速步骤。
6. 若 strategy 明确要求等待，最后一步必须是等待或停车等待。
```


## 9. 为什么这个方案会比现在稳

1. 前面减少自由文本
   - 模型不会在中间产生大段“看似合理但无法稳定复用”的解释。

2. 中间状态更窄
   - 每一步只传决策变量，后一步更不容易跑题。

3. 最后一步不再承担规划责任
   - 它只负责把既定策略翻成动作序列，因此更稳定。

4. 规则与模型职责清晰
   - 交通指令优先、盲区保守、左右视角这些都不该反复让模型“悟”出来。

5. 更容易调试
   - 如果结果错了，可以直接定位是：
     - `fact_pack` 错
     - `control_policy` 错
     - `assessment` 错
     - `strategy` 错
     - `task_realizer` 错


## 10. 推荐落地顺序

建议按下面顺序迭代，而不是一次性全改：

1. 先把中间 `reasoning` 从主流程拿掉
2. 把 `generate_plan` 改成规则化 `strategy_compile`
3. 把 `decompose_tasks` 改成只消费 `strategy + constraints`
4. 再拆 prompt 文件，取消动态 system prompt 的大拼接
5. 最后再决定是否保留 `skill_prompts.json`


## 11. 一句话结论

这次不应该继续优化“更会思考的长 prompt”，而应该把系统改成“前面规则收敛，中间短字段评估，最后受控翻译任务”的窄状态流水线。
