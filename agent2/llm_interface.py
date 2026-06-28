"""Hybrid LLM + deterministic helpers for Agent2 workflow."""

from __future__ import annotations

import base64
from datetime import datetime
import io
import json
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

ALLOWED_MANEUVERS = {
    "keep_lane",
    "change_lane_left",
    "change_lane_right",
    "go_straight",
    "turn_left",
    "turn_right",
    "stop",
}

class Agent2LLMInterface:
    """Provide Agent2-facing extraction/planning helpers.

    The first version intentionally prefers deterministic planning rules to
    guarantee stable behavior even when remote model calls are unavailable.
    """

    FORBIDDEN_MANEUVERS = {"observe", "decelerate", "u_turn"}

    def __init__(self, config: Dict[str, Any], image_config: Optional[Dict[str, Any]] = None):
        self.provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-4o-mini")
        self.api_key = config.get("api_key", "")
        self.max_tokens = config.get("max_tokens", 2000)
        self.temperature = config.get("temperature", 0.0)

        self.base_rules_prompt = self._load_prompt(
            ["prompts/base_rules.md", "prompts/system_prompt.md", "prompts/system_prompt.txt"],
            self._default_base_rules(),
        )

        self.image_config = image_config or {}
        self.save_input_images = self.image_config.get("save_input_images", False)
        self.input_images_dir = self.image_config.get("input_images_dir", "debug/input_images/")

        self._init_client()

    @staticmethod
    def _default_base_rules() -> str:
        return (
            "你是一个路侧交通指挥智能体。\n"
            "通用要求：\n"
            "- 只输出用户要求的 JSON 结构，不输出额外解释。\n"
            "- 不确定时要保守，用 `uncertain`/`null`/0 表达信息不足。\n"
            "- 所有左右方向必须按目标车辆视角表达，不使用路侧视角。\n"
            "- 避免编造不存在的事实或观测。\n"
        )
    
    def _init_client(self):
        """Initialize the backing API client."""
        if self.provider == "openai":
            try:
                from openai import OpenAI

                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
            except ImportError:
                self.client = None
                logging.warning("openai 库未安装：将进入离线兜底模式（不调用远程 LLM）。")
        elif self.provider == "anthropic":
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                self.client = None
                logging.warning("anthropic 库未安装：将进入离线兜底模式（不调用远程 LLM）。")
        else:
            raise ValueError(f"不支持的provider: {self.provider}")


    def _load_prompt(self, prompt_candidates: List[str], fallback: str) -> str:
        for path in prompt_candidates:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as file:
                    return file.read()
        return fallback

    def _get_primary_image(self, camera_coverage: Dict[str, Any]) -> Optional[np.ndarray]:
        """Pick the first visible camera image for multi-modal reasoning."""
        if camera_coverage.get("in_blind_spot"):
            return None
        visible_cameras = camera_coverage.get("visible_cameras", [])
        if not visible_cameras:
            return None
        first_camera = visible_cameras[0]
        projection = camera_coverage.get("projections", {}).get(first_camera, {})
        return projection.get("image_with_bbox")
    
    def _extract_json_block(self, text: str) -> Dict[str, Any]:
        """Best-effort JSON extraction from model output."""
        text = text.strip()
        candidates = [text]

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and start < end:
            candidates.append(text[start : end + 1])

        fenced_start = text.find("```json")
        if fenced_start != -1:
            fenced_content = text[fenced_start + 7 :]
            fenced_end = fenced_content.find("```")
            if fenced_end != -1:
                candidates.append(fenced_content[:fenced_end].strip())

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        raise ValueError("模型输出中未找到有效JSON")
    
    def _save_input_image(self, image: np.ndarray, camera_id: str = None):
        """Save images sent to the model for debugging."""
        if not self.save_input_images:
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{timestamp}_{camera_id}.jpg" if camera_id else f"{timestamp}.jpg"
            filepath = os.path.join(self.input_images_dir, filename)
            Image.fromarray(self._bgr_to_rgb(image)).save(filepath, format="JPEG", quality=95)
            print(f"✓ 已保存输入图像: {filepath}")
        except Exception as exc:
            print(f"✗ 保存输入图像失败: {exc}")
    
    @staticmethod
    def _bgr_to_rgb(image: np.ndarray) -> np.ndarray:
        """Convert BGR ndarray to RGB before handing it to PIL."""
        if image.ndim == 3 and image.shape[2] == 3:
            return image[:, :, ::-1]
        return image
    
    def _encode_image(self, image: np.ndarray) -> str:
        """Encode a numpy BGR image into base64 JPEG for the model."""
        pil_image = Image.fromarray(self._bgr_to_rgb(image))
        max_size = self.image_config.get("max_image_size", 1024)
        jpeg_quality = self.image_config.get("jpeg_quality", 85)

        if max(pil_image.size) > max_size:
            ratio = max_size / max(pil_image.size)
            new_size = tuple(int(dim * ratio) for dim in pil_image.size)
            pil_image = pil_image.resize(new_size, Image.LANCZOS)

        buffer = io.BytesIO()
        pil_image.save(buffer, format="JPEG", quality=jpeg_quality)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    def _invoke_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Invoke the configured model and parse a JSON response."""
        if self.client is None:
            raise RuntimeError("LLM client unavailable (missing SDK or not configured).")
        if self.provider == "openai":
            messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            if image is not None:
                base64_image = self._encode_image(image)
                self._save_input_image(image)
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                )
            else:
                messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            raw_response = response.choices[0].message.content
            return self._extract_json_block(raw_response)

        if self.provider == "anthropic":
            content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            if image is not None:
                base64_image = self._encode_image(image)
                self._save_input_image(image)
                content.insert(
                    0,
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image,
                        },
                    },
                )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": content}],
            )
            raw_response = response.content[0].text
            return self._extract_json_block(raw_response)

        raise ValueError(f"不支持的provider: {self.provider}")

    def _compose_system_prompt(self, task_prompt: str) -> str:
        return "\n\n".join([self.base_rules_prompt.strip(), task_prompt.strip()])
    
    def extract_scene_model(
        self,
        camera_coverage: Dict[str, Any],
        vehicle_info: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
        fact_pack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract environment facts that downstream planning can safely consume."""
        image = self._get_primary_image(camera_coverage)
        system_prompt = f"""
你负责抽取环境事实层，而不是直接做规划。

要求：
- 只输出环境事实字段，不输出推理说明。
- 所有左右方向必须按目标车辆视角，不允许使用路侧视角。
- `lane_count` 表示与目标车辆同向的单向车道总数。
- `ego_lane_index` 统一为“从右到左 1-based”；未知填 0。
- `front_gap_status`/`left_gap_status`/`right_gap_status` 只能使用 `clear`、`narrow`、`blocked`、`uncertain`。
- `lane_description` 仅用于可读性，不应替代结构化字段。
- `confidence` 只能是 `low`、`medium`、`high`。
- 无法从图像稳定确认的事实，使用 `uncertain` 或 `null`。
- 下游会基于这些字段直接做策略分支，字段冲突时优先保守，不要臆测。 
"""
        user_prompt = f"""
在图像中，目标车辆被用绿色框线框出，以下描述都针对图中被框出的目标车辆进行，你的输出也应当针对目标车辆。
请基于图像和上下文抽取环境事实，并仅输出 JSON。

事实输入:
{json.dumps(fact_pack, ensure_ascii=False)}

车辆信息:
{json.dumps({
    "intention": vehicle_info.get("intention", ""),
    "velocity": vehicle_info.get("velocity", 0.0),
    "acceleration": vehicle_info.get("acceleration", 0.0),
}, ensure_ascii=False)}

交通指令:
{json.dumps(traffic_command or {}, ensure_ascii=False)}

字段定义与用途（必须严格遵守）:
1) lane_count
- 含义: 与目标车辆行驶方向一致的单向可通行车道总数。
- 取值: 正整数；无法稳定判断填 0。
- 用途: 用于判断目标车辆是否处于最左/最右车道，影响是否允许继续横向机动。

2) ego_lane_index
- 含义: 目标车辆当前车道编号，按车辆前进方向下“从右到左”的顺序，1-based，1号即最靠路侧的车道。
- 取值: 1 到 lane_count；无法稳定判断填 0。
- 用途: 与 lane_count 联合使用；当 ego_lane_index == lane_count 时表示已在最右车道。

3) lane_description
- 含义: 对车道位置的简短描述，例如“位于最右车道”或“位于中间车道”。
- 约束: 不超过 20 字，不要写推理过程。
- 用途: 仅作可读性辅助，不作为核心决策依据。

4) front_gap_status
- 含义: 车辆正前方可通行间隙状态。
- 枚举: "clear" | "narrow" | "blocked" | "uncertain"。
- 判定建议: clear=可平稳前进；narrow=可前进但需明显减速；blocked=基本无法前进；uncertain=看不清或证据不足。
- 用途: 影响是否需要优先减速或停车。

5) left_gap_status
- 含义: 目标车辆左侧相邻通行空间状态。
- 视角: 必须使用车辆视角（不是路侧视角）。
- 枚举: "clear" | "narrow" | "blocked" | "uncertain"。
- 用途: 影响左向变道动作是否可执行。

6) right_gap_status
- 含义: 目标车辆右侧相邻通行空间状态。
- 视角: 必须使用车辆视角（不是路侧视角）。
- 枚举: "clear" | "narrow" | "blocked" | "uncertain"。
- 用途: 影响靠右与右向变道动作，若为 uncertain 则后续应先观察再横向动作。

7) confidence
- 含义: 你对本次 scene_model 抽取结果的置信度。
- 枚举: "low" | "medium" | "high"。
- 用途: 低置信度时系统会更偏向保守兜底。

输出约束:
- 只输出 JSON，不要输出解释。
- 若字段证据不足，优先返回 0/uncertain/null，不要猜测。
"""
        try:
            result = self._invoke_json(
                system_prompt=self._compose_system_prompt(system_prompt.strip()),
                user_prompt=user_prompt.strip(),
                image=image,
            )
            return self._normalize_scene_model(result)
        except Exception as e:
            logging.error(f"Scene context extraction failed: {str(e)}")
            return self._fallback_scene_model(camera_coverage, vehicle_info, traffic_command)

    def build_navigation_context(
        self,
        *,
        scene_model: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
        camera_coverage: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Infer destination/goal in structured form."""
        image = self._get_primary_image(camera_coverage)
        system_prompt = f"""
你是一个路侧交通指挥Agent的**目的地拓扑提取节点**，
你的职责是结合车辆位置、交通指挥指令和场景图像信息，分析交通指挥指令中给出的行驶目的地。

用户给出的输入中会包括：
- 带有标定框的图像。图像中包含了当前的交通场景，绿色的标定框会标注目标车辆的当前所在位置。
- 交通指挥指令。来自交通指挥者的自然语言指令，你应当从指令中推测目标车辆应该以什么位置作为行驶的目的地。
- 场景基础信息。来自上游节点的初步感知结果，包含了车道信息等。

你应当以Json格式输出，包含三个字段：
- "ego_position_desc"，简短描述目标车辆的当前位置，20字以内。
- "destination_position_desc"，根据交通指挥指令，推断车辆的行驶目的地，并对应到图片中相应场景的位置，详细描述，40字左右。
- "route_analysis"，根据目标车辆和目的地的位置，推断车辆要行驶到目的地需要怎样行驶，详细描述。
**route_analysis只需要描述路径，即变道、转向、直行等，不需要描述注意安全、注意观察、注意某辆车等与路径无关的内容。**
"""

        cmd_text = json.dumps(traffic_command, ensure_ascii=False) if traffic_command else "无特定指令"

        user_prompt = f"""
### 1. 交警指挥指令
{cmd_text}

### 2. 场景基础信息
{json.dumps(scene_model, ensure_ascii=False)}

### 3. 图像信息
请参考附带的图像，重点关注绿色标定框内的车辆及其前方的道路拓扑结构。
"""

        try:
            result = self._invoke_json(
                system_prompt=self._compose_system_prompt(system_prompt.strip()),
                user_prompt=user_prompt.strip(),
                image=image,
            )
            return {
                "dest_analysis": result
            }
        except Exception as e:
            # 记录具体错误以便调试
            logging.error(f"Navigation context extraction failed: {str(e)}")
            return {
                "dest_analysis": "Failed to extract."
            }

    def plan_maneuver_sequence(
        self,
        *,
        camera_coverage: Dict[str, Any],
        scene_model: Dict[str, Any],
        navigation_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate topology plan in mermaid + graph schema."""
        image = self._get_primary_image(camera_coverage)
        system_prompt = """
你是一个路侧交通指挥Agent的**拓扑任务构造节点**，
上游节点已完成了场景分析、目的地提取和初步的路径分析，
你的职责是结合场景分析、目的地位置分析、路径分析的结果，推导车辆接下来的拓扑任务结构，提供给车辆进行参考。

用户给出的输入中会包括：
- 当前场景信息，来自上游节点的初步感知结果，包含了车道信息、车辆位置等。
- 路径初步分析，包含了车辆当前位置、目的地位置和初步路径分析结果。
- 当前场景的图像，供你参考。

你的职责是基于场景和路径规划，输出驾驶动作拓扑图。可选动作包括：__ALLOWED_MANEUVERS__。

你应当注意：
- 避免出现违背交通逻辑的规划，例如车辆出现在最右侧（或最左侧）车道，则不能再下发向右（或向左）变道的指令。
- 车辆只有在靠路边行驶时才能下达`stop`指令，`stop`指令是命令车辆长时间停车的，不考虑为了避让、等红灯等其他的刹停行为。
- "go_straight", "turn_left", "turn_right"这三条指令分别对应在十字路口内的导航指令，只能当车辆行驶到十字路口后执行。
- 必须输出可执行且可判定条件的节点信息，每个节点都要给出触发条件与时间/时机约束。
- 你输出的节点数量控制在1~6个，不要太长。

你应当以Json格式输出，且必须严格符合如下结构：
{
    "plan": {
        "mermaid": "flowchart TD; ...",
        "graph": {
            "entry": "N1",
            "nodes": [
                {
                    "id": "N1",
                    "title": "短标题",
                    "action": "keep_lane",
                    "condition": "可判定触发条件",
                    "timing": "执行时机或时间窗口",
                    "detail": "执行细节，至少一句完整说明"
                }
            ],
            "edges": [
                {
                    "from": "N1",
                    "to": "N2",
                    "condition": "边触发条件，分支场景必填可判定条件"
                }
            ]
        }
    }
}

回归示范1（线性）:
{
  "plan": {
    "mermaid": "flowchart TD; N1[保持车道通行] --> N2[右变道准备通过路口] --> N3[通过路口直行]",
    "graph": {
      "entry": "N1",
      "nodes": [
        {"id":"N1","title":"保持车道通行","action":"keep_lane","condition":"前方通行间隙clear","timing":"立即执行并持续3-5秒","detail":"保持当前车道，速度控制在30-35km/h，观察右侧并道空间"},
        {"id":"N2","title":"右变道准备通过路口","action":"change_lane_right","condition":"右侧间隙clear且距路口20-40米","timing":"满足条件后2秒内执行","detail":"单次平稳并入右侧车道，不与相邻车辆抢行"},
        {"id":"N3","title":"通过路口直行","action":"go_straight","condition":"进入路口且前向可通行","timing":"进入路口后立即执行","detail":"沿当前车道通过路口，不做额外横向动作"}
      ],
      "edges": [
        {"from":"N1","to":"N2","condition":"右侧可并道"},
        {"from":"N2","to":"N3","condition":"完成并道并接近路口"}
      ]
    }
  }
}

回归示范2（分支）:
{
  "plan": {
    "mermaid": "flowchart TD; N1[接近路口保持车道] --> N2{信号灯状态}; N2 -->|绿灯| N3[快速直行通过路口]; N2 -->|红灯| N4[右转绕行避免停留]",
    "graph": {
      "entry": "N1",
      "nodes": [
        {"id":"N1","title":"接近路口保持车道","action":"keep_lane","condition":"距路口50米内","timing":"立即执行","detail":"保持当前车道并稳定车速，为路口决策做准备"},
        {"id":"N3","title":"快速直行通过路口","action":"go_straight","condition":"信号灯为绿灯且前向无阻塞","timing":"绿灯窗口内立即执行","detail":"不中途停留，连续通过路口"},
        {"id":"N4","title":"右转绕行避免停留","action":"turn_right","condition":"信号灯为红灯且允许右转","timing":"到达停止线前完成决策并执行","detail":"按右转轨迹通过，避免在路口长时间停留"}
      ],
      "edges": [
        {"from":"N1","to":"N3","condition":"绿灯"},
        {"from":"N1","to":"N4","condition":"红灯且可右转"}
      ]
    }
  }
}
""".replace("__ALLOWED_MANEUVERS__", str(ALLOWED_MANEUVERS))
        user_prompt = f"""
### 1. 当前场景信息
{json.dumps(scene_model, ensure_ascii=False)}

### 2. 目的地路径分析
{json.dumps(navigation_context, ensure_ascii=False)}

### 3. 图像信息
该图像由路侧摄像头拍摄获得，请参考附带的图像，图像中目标车辆被使用绿色框线画出。

请根据以上信息生成拓扑任务结构（mermaid + graph）。
"""

        try:
            result = self._invoke_json(
                system_prompt=self._compose_system_prompt(system_prompt.strip()),
                user_prompt=user_prompt.strip(),
                image=image,
            )
            return result.get("plan", {})
        except Exception as e:
            logging.error(f"Sequence generate failed: {str(e)}")
            return {}

    def validate_output(
        self,
        *,
        camera_coverage: Dict[str, Any],
        plan: Dict[str, Any],
        navigation_context: Dict[str, Any],
        scene_model: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Holistic consistency checks across sequence, tasks and context."""
        issues: List[str] = []
        mermaid = str(plan.get("mermaid", "")).strip()
        graph = plan.get("graph", {})
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges = graph.get("edges", []) if isinstance(graph, dict) else []
        entry = graph.get("entry") if isinstance(graph, dict) else None

        if not mermaid:
            issues.append("缺少 plan.mermaid。")
        elif not mermaid.lower().startswith("flowchart td"):
            issues.append("plan.mermaid 必须以 flowchart TD 开头。")

        if not isinstance(nodes, list) or not nodes:
            issues.append("plan.graph.nodes 不能为空。")

        node_ids = set()
        for item in nodes if isinstance(nodes, list) else []:
            if not isinstance(item, dict):
                issues.append("plan.graph.nodes 中存在非法节点。")
                continue
            node_id = str(item.get("id", "")).strip()
            action = str(item.get("action", "")).strip()
            condition = str(item.get("condition", "")).strip()
            timing = str(item.get("timing", "")).strip()
            detail = str(item.get("detail", "")).strip()
            if not node_id:
                issues.append("存在缺少 id 的节点。")
                continue
            node_ids.add(node_id)
            if action not in ALLOWED_MANEUVERS:
                issues.append(f"节点 {node_id} 的 action 超出词表: {action}")
            if not condition:
                issues.append(f"节点 {node_id} 缺少 condition。")
            if not timing:
                issues.append(f"节点 {node_id} 缺少 timing。")
            if not detail:
                issues.append(f"节点 {node_id} 缺少 detail。")

        if entry and entry not in node_ids:
            issues.append("plan.graph.entry 未在 nodes 中定义。")

        if not isinstance(edges, list):
            issues.append("plan.graph.edges 必须是数组。")
            edges = []
        for edge in edges:
            if not isinstance(edge, dict):
                issues.append("plan.graph.edges 中存在非法边。")
                continue
            src = str(edge.get("from", "")).strip()
            dst = str(edge.get("to", "")).strip()
            cond = str(edge.get("condition", "")).strip()
            if not src or not dst:
                issues.append("存在缺少 from/to 的边。")
                continue
            if src not in node_ids or dst not in node_ids:
                issues.append(f"边 {src}->{dst} 引用了未定义节点。")
            if not cond:
                issues.append(f"边 {src}->{dst} 缺少 condition。")

        lane_count = int(scene_model.get("lane_count", 0) or 0)
        ego_lane = int(scene_model.get("ego_lane_index", 0) or 0)
        if lane_count > 0 and ego_lane == lane_count:
            for item in nodes if isinstance(nodes, list) else []:
                if isinstance(item, dict) and item.get("action") == "change_lane_right":
                    issues.append("车辆已在最右车道，不应继续规划向右变道。")
                    break

        summary = "动作序列与任务语义一致。"
        if issues:
            summary = "发现拓扑规划与约束存在冲突。"

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "validation_summary": summary,
        }

    def _normalize_sequence(self, sequence: List[str]) -> List[str]:
        """Enforce first-version constraints and keep order stable."""
        cleaned = [item for item in sequence if item in ALLOWED_MANEUVERS and item not in self.FORBIDDEN_MANEUVERS]

        # Avoid impossible repetitive lateral actions in v1.
        lateral_count = sum(1 for item in cleaned if item in {"change_lane_left", "change_lane_right"})
        if lateral_count > 2:
            limited: List[str] = []
            kept_lateral = 0
            for item in cleaned:
                if item in {"change_lane_left", "change_lane_right"}:
                    kept_lateral += 1
                    if kept_lateral > 2:
                        continue
                limited.append(item)
            cleaned = limited

        # Keep sequence non-empty.
        if not cleaned:
            cleaned = ["keep_lane", "go_straight"]

        return cleaned
    
    @staticmethod
    def _normalize_status(value: Any, default: str) -> str:
        candidates = {"clear", "narrow", "blocked", "uncertain"}
        value = str(value or "").strip().lower()
        return value if value in candidates else default

    @staticmethod
    def _normalize_confidence(value: Any, default: str) -> str:
        candidates = {"low", "medium", "high"}
        value = str(value or "").strip().lower()
        return value if value in candidates else default
    
    def _normalize_scene_model(self, result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {
            "lane_count": int(result.get("lane_count", 0) or 0),
            "ego_lane_index": int(result.get("ego_lane_index", 0) or 0),
            "lane_description": str(result.get("lane_description", "")).strip(),
            "front_gap_status": self._normalize_status(result.get("front_gap_status"), default="uncertain"),
            "left_gap_status": self._normalize_status(result.get("left_gap_status"), default="uncertain"),
            "right_gap_status": self._normalize_status(result.get("right_gap_status"), default="uncertain"),
            "confidence": self._normalize_confidence(result.get("confidence"), default="low"),
        }
        if not normalized["lane_description"]:
            normalized["lane_description"] = "当前图像信息不足，无法稳定判断具体车道"
        return normalized

    def _fallback_scene_model(
        self,
        camera_coverage: Dict[str, Any],
        vehicle_info: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Conservative deterministic scene model."""
        if camera_coverage.get("in_blind_spot"):
            return {
                "lane_count": 0,
                "ego_lane_index": 0,
                "lane_description": "车辆处于监控盲区，无法稳定判断车道位置",
                "front_gap_status": "uncertain",
                "left_gap_status": "uncertain",
                "right_gap_status": "uncertain",
                "confidence": "low",
            }
        risk = "medium" if traffic_command or vehicle_info.get("velocity", 0.0) >= 35 else "low"
        return {
            "lane_count": 0,
            "ego_lane_index": 0,
            "lane_description": "当前图像信息不足，无法稳定判断具体车道",
            "front_gap_status": "uncertain",
            "left_gap_status": "uncertain",
            "right_gap_status": "uncertain",
            "confidence": "low",
        }
    # @staticmethod
    # def _can_change_right(lane_count: int, ego_lane: int, right_gap: str) -> bool:
    #     if lane_count <= 0 or ego_lane <= 0:
    #         return right_gap == "clear"
    #     return ego_lane < lane_count and right_gap in {"clear", "narrow"}

    # @staticmethod
    # def _can_change_left(lane_count: int, ego_lane: int, left_gap: str) -> bool:
    #     if lane_count <= 0 or ego_lane <= 0:
    #         return left_gap == "clear"
    #     return ego_lane > 1 and left_gap in {"clear", "narrow"}

    # @staticmethod
    # def _task_from_primitive(action: str) -> Dict[str, Any]:
    #     mapping = {
    #         "keep_lane": {"description": "保持当前车道稳定行驶。", "time_limit": 6},
    #         "change_lane_left": {"description": "确认左侧安全后向左变道。", "time_limit": 8},
    #         "change_lane_right": {"description": "确认右侧安全后向右变道。", "time_limit": 8},
    #         "go_straight": {"description": "保持直行通过当前路段。", "time_limit": 8},
    #         "turn_left": {"description": "在路口按规划完成左转。", "time_limit": 10},
    #         "turn_right": {"description": "在路口按规划完成右转。", "time_limit": 10},
    #         "pull_over": {"description": "向右侧路边平稳靠停。", "time_limit": 10},
    #         "stop": {"description": "在安全位置停车并等待。", "time_limit": 12},
    #     }
    #     return mapping.get(action, {"description": "保持当前车道并观察环境。", "time_limit": 6})
