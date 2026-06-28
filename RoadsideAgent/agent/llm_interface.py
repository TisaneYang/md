"""LLM interface helpers for structured roadside-agent reasoning."""

import base64
import io
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image


class LLMInterface:
    """Multi-modal LLM wrapper with narrow structured JSON helpers."""

    def __init__(self, config: Dict, image_config: Dict = None):
        self.provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-4o-mini")
        self.api_key = config.get("api_key", "")
        self.max_tokens = config.get("max_tokens", 2000)
        self.temperature = config.get("temperature", 0.0)

        self.image_config = image_config or {}
        self.save_input_images = self.image_config.get("save_input_images", False)
        self.input_images_dir = self.image_config.get("input_images_dir", "debug/input_images/")

        if self.save_input_images:
            os.makedirs(self.input_images_dir, exist_ok=True)
            print(f"图像保存已启用，保存路径: {self.input_images_dir}")

        self.base_rules_prompt = self._load_prompt(
            ["prompts/base_rules.md", "prompts/system_prompt.md", "prompts/system_prompt.txt"],
            self._default_base_rules(),
        )
        self.assessment_prompt = self._load_prompt(
            ["prompts/assessment_prompt.md"],
            self._default_assessment_prompt(),
        )
        self.task_realizer_prompt = self._load_prompt(
            ["prompts/task_realizer_prompt.md"],
            self._default_task_realizer_prompt(),
        )
        self.scene_model_prompt = self._load_prompt(
            ["prompts/scene_model_prompt.md"],
            self._default_scene_model_prompt(),
        )
        self._init_client()

    def _load_prompt(self, prompt_candidates: List[str], fallback: str) -> str:
        for path in prompt_candidates:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as file:
                    return file.read()
        return fallback

    def _init_client(self):
        """Initialize the backing API client."""
        if self.provider == "openai":
            try:
                from openai import OpenAI

                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
            except ImportError as exc:
                raise ImportError("请安装openai库: pip install openai") from exc
        elif self.provider == "anthropic":
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError as exc:
                raise ImportError("请安装anthropic库: pip install anthropic") from exc
        else:
            raise ValueError(f"不支持的provider: {self.provider}")

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

    @staticmethod
    def _bgr_to_rgb(image: np.ndarray) -> np.ndarray:
        """Convert BGR ndarray to RGB before handing it to PIL."""
        if image.ndim == 3 and image.shape[2] == 3:
            return image[:, :, ::-1]
        return image

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

    def _invoke_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Invoke the configured model and parse a JSON response."""
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

    def extract_scene_model(
        self,
        camera_coverage: Dict[str, Any],
        vehicle_info: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
        fact_pack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract environment facts that downstream planning can safely consume."""
        image = self._get_primary_image(camera_coverage)
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
- 含义: 目标车辆当前车道编号，按车辆前进方向下“从左到右”的顺序，1-based。
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

7) roadside_pull_over_feasible
- 含义: 当前是否具备“向右靠边并安全停车”的环境条件。
- 取值: true | false | null（信息不足时用 null）。
- 用途: 直接影响是否允许生成靠边停车策略。

8) nearby_agents_summary
- 含义: 周边关键交通参与者摘要（车辆/行人/障碍物），最多 3 条。
- 格式: 每条是短语，如“右前方有慢车”“右侧边缘有行人”。
- 用途: 为后续风险判断提供补充语义，不替代上述结构化字段。

9) conflict_risk
- 含义: 目标车辆在当前环境下发生冲突的总体风险等级。
- 枚举: "low" | "medium" | "high"。
- 用途: high 或 medium 会推动系统进入更保守的干预策略。

10) confidence
- 含义: 你对本次 scene_model 抽取结果的置信度。
- 枚举: "low" | "medium" | "high"。
- 用途: 低置信度时系统会更偏向保守兜底。

输出约束:
- 只输出 JSON，不要输出解释。
- 若字段证据不足，优先返回 0/uncertain/null，不要猜测。
"""
        try:
            result = self._invoke_json(
                system_prompt=self._compose_system_prompt(self.scene_model_prompt),
                user_prompt=user_prompt.strip(),
                image=image,
            )
            return self._normalize_scene_model(result)
        except Exception:
            return self._fallback_scene_model(camera_coverage, vehicle_info, traffic_command)

    def generate_structured_assessment(
        self,
        camera_coverage: Dict[str, Any],
        vehicle_info: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
        fact_pack: Dict[str, Any],
        scene_model: Dict[str, Any],
        control_policy: Dict[str, Any],
        scene_type: str,
    ) -> Dict[str, Any]:
        """Generate a narrow assessment state for strategy compilation."""
        image = self._get_primary_image(camera_coverage)
        user_prompt = f"""
请根据事实输入生成最小化决策状态，并仅输出 JSON。

场景类型:
{scene_type}

事实输入:
{json.dumps(fact_pack, ensure_ascii=False)}

环境模型:
{json.dumps(scene_model, ensure_ascii=False)}

控制策略:
{json.dumps(control_policy, ensure_ascii=False)}

交通指令:
{json.dumps(traffic_command or {}, ensure_ascii=False)}

字段定义与用途（必须严格遵守）:
1) scene_summary
- 含义: 对当前场景决策状态的简短摘要。
- 约束: 不超过 30 字，不要复述全部输入，不要写推理过程。
- 用途: 仅用于人类可读，不作为策略分支主依据。

2) risk_level
- 含义: 当前动作执行风险等级。
- 枚举: "low" | "medium" | "high"。
- 用途: 高风险会推动更保守策略（如减速保持或停车等待）。

3) primary_goal
- 含义: 当前阶段唯一主目标，必须是可执行目标而非解释性文字。
- 约束: 只能有一个目标；存在交通指令时必须与指令目标一致。
- 用途: 作为策略摘要与任务生成的主导目标。

4) key_constraints
- 含义: 影响动作执行的关键约束条件。
- 约束: 数组最多 3 条，每条短句，不超过 16 字。
- 用途: 用于限制任务生成，避免激进或冲突动作。

5) maneuver_type
- 含义: 期望机动类型。
- 枚举: "keep_lane" | "pull_over_right" | "change_lane_left" | "change_lane_right" | "stop_and_wait"。
- 用途: 直接驱动 strategy_id 分支选择，是最关键的控制字段之一。

6) lane_change_needed
- 含义: 为达成 primary_goal 是否需要横向跨车道动作。
- 取值: true | false。
- 用途: true 时后续任务必须包含“先观察/减速再横向动作”的节奏控制。

7) observation_needed
- 含义: 执行主要动作前是否必须先观察确认环境。
- 取值: true | false。
- 用途: true 时后续任务第一步应是观察或减速观察，不应直接横向机动。

8) must_wait
- 含义: 本轮目标是否要求最终进入等待状态（停车等待或原地等待）。
- 取值: true | false。
- 用途: true 时策略与任务末步必须出现“等待/停车等待”语义。

输出约束:
- 只输出 JSON，不要输出解释。
- 若无法确认，保持保守：提高 observation_needed，必要时选择 stop_and_wait。
"""
        try:
            result = self._invoke_json(
                system_prompt=self._compose_system_prompt(self.assessment_prompt),
                user_prompt=user_prompt.strip(),
                image=image,
            )
            return self._normalize_assessment(result, fact_pack, scene_model, traffic_command, control_policy)
        except Exception:
            return self._fallback_assessment(fact_pack, scene_model, traffic_command, control_policy)

    def realize_tasks(
        self,
        strategy: Dict[str, Any],
        assessment: Dict[str, Any],
        scene_model: Dict[str, Any],
        fact_pack: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Translate a chosen strategy into vehicle-executable tasks."""
        user_prompt = f"""
请把既定策略翻译成车辆任务，并仅输出 JSON。

策略:
{json.dumps(strategy, ensure_ascii=False)}

评估状态:
{json.dumps(assessment, ensure_ascii=False)}

环境模型:
{json.dumps({
    "lane_count": scene_model.get("lane_count", 0),
    "ego_lane_index": scene_model.get("ego_lane_index", 0),
    "front_gap_status": scene_model.get("front_gap_status", "uncertain"),
    "left_gap_status": scene_model.get("left_gap_status", "uncertain"),
    "right_gap_status": scene_model.get("right_gap_status", "uncertain"),
    "roadside_pull_over_feasible": scene_model.get("roadside_pull_over_feasible"),
}, ensure_ascii=False)}

事实输入:
{json.dumps({
    "vehicle_intent": fact_pack.get("vehicle_intent", ""),
    "traffic_command_text": fact_pack.get("traffic_command_text", ""),
}, ensure_ascii=False)}

输出格式:
{{
  "tasks": [
    {{"description": "任务描述", "time_limit": 5}}
  ]
}}
"""
        try:
            result = self._invoke_json(
                system_prompt=self._compose_system_prompt(self.task_realizer_prompt),
                user_prompt=user_prompt.strip(),
                image=None,
            )
            return self._normalize_tasks(result.get("tasks", []))
        except Exception:
            return []

    def analyze_scene(
        self,
        camera_coverage: Dict[str, Any],
        vehicle_info: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compatibility wrapper for callers expecting a single-shot interface."""
        fact_pack = {
            "vehicle_type": vehicle_info.get("type", ""),
            "vehicle_color": vehicle_info.get("color", ""),
            "vehicle_plate": vehicle_info.get("plate", ""),
            "vehicle_intent": vehicle_info.get("intention", ""),
            "speed_kmh": round(float(vehicle_info.get("velocity", 0.0)), 1),
            "acceleration_mps2": round(float(vehicle_info.get("acceleration", 0.0)), 2),
            "in_blind_spot": bool(camera_coverage.get("in_blind_spot", False)),
            "visible_camera_ids": list(camera_coverage.get("visible_cameras", [])),
            "camera_relation_note": "前视相对而行，涉及左右时按车端视角表达",
            "traffic_command_text": traffic_command.get("command", "") if traffic_command else "",
        }
        scene_model = self.extract_scene_model(
            camera_coverage=camera_coverage,
            vehicle_info=vehicle_info,
            traffic_command=traffic_command,
            fact_pack=fact_pack,
        )
        control_policy = {
            "policy_mode": "traffic_command" if traffic_command else "observe_only",
            "must_intervene": bool(traffic_command),
            "safety_posture": "conservative" if traffic_command else "balanced",
            "needs_lane_reasoning": not camera_coverage.get("in_blind_spot", False),
            "left_right_reference": "vehicle_perspective",
            "hard_constraints": ["涉及左右时必须按车端视角表达"],
        }
        assessment = self.generate_structured_assessment(
            camera_coverage=camera_coverage,
            vehicle_info=vehicle_info,
            traffic_command=traffic_command,
            fact_pack=fact_pack,
            scene_model=scene_model,
            control_policy=control_policy,
            scene_type="legacy_scene_analysis",
        )
        tasks = self.realize_tasks(
            strategy={
                "strategy_id": "keep_lane_and_observe",
                "summary": "保持当前车道并观察环境。",
                "execution_mode": control_policy["policy_mode"],
                "task_style": "sequential_vehicle_actions",
            },
            assessment=assessment,
            scene_model=scene_model,
            fact_pack=fact_pack,
        )
        return {
            "risk_level": assessment.get("risk_level", "medium"),
            "reasoning": "",
            "advice": assessment.get("primary_goal", "保持谨慎通行"),
            "tasks": tasks,
            "plan": {
                "summary": assessment.get("primary_goal", ""),
                "execution_mode": control_policy["policy_mode"],
            },
            "raw_response": json.dumps(
                {
                    "scene_model": scene_model,
                    "assessment": assessment,
                    "tasks": tasks,
                },
                ensure_ascii=False,
            ),
        }

    def _normalize_scene_model(self, result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {
            "lane_count": int(result.get("lane_count", 0) or 0),
            "ego_lane_index": int(result.get("ego_lane_index", 0) or 0),
            "lane_description": str(result.get("lane_description", "")).strip(),
            "front_gap_status": self._normalize_status(result.get("front_gap_status"), default="uncertain"),
            "left_gap_status": self._normalize_status(result.get("left_gap_status"), default="uncertain"),
            "right_gap_status": self._normalize_status(result.get("right_gap_status"), default="uncertain"),
            "roadside_pull_over_feasible": self._normalize_optional_bool(
                result.get("roadside_pull_over_feasible")
            ),
            "nearby_agents_summary": [
                str(item).strip() for item in result.get("nearby_agents_summary", []) if str(item).strip()
            ][:3],
            "conflict_risk": self._normalize_risk(result.get("conflict_risk"), default="medium"),
            "confidence": self._normalize_confidence(result.get("confidence"), default="low"),
        }
        if not normalized["lane_description"]:
            normalized["lane_description"] = "当前图像信息不足，无法稳定判断具体车道"
        return normalized

    def _normalize_assessment(
        self,
        result: Dict[str, Any],
        fact_pack: Dict[str, Any],
        scene_model: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
        control_policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        summary = str(result.get("scene_summary", "")).strip()
        constraints = [str(item).strip() for item in result.get("key_constraints", []) if str(item).strip()][:3]
        if not constraints:
            constraints = control_policy.get("hard_constraints", [])[:3]

        return {
            "scene_summary": summary[:30] if summary else "基于当前事实生成受控评估。",
            "risk_level": self._normalize_risk(result.get("risk_level"), default="medium"),
            "primary_goal": str(result.get("primary_goal", "")).strip()
            or self._infer_primary_goal(fact_pack, traffic_command),
            "key_constraints": constraints,
            "maneuver_type": self._normalize_maneuver_type(
                result.get("maneuver_type"),
                fact_pack,
                scene_model,
                traffic_command,
            ),
            "lane_change_needed": bool(result.get("lane_change_needed", False)),
            "observation_needed": bool(result.get("observation_needed", True)),
            "must_wait": bool(result.get("must_wait", bool(traffic_command and "等待" in traffic_command.get("command", "")))),
        }

    def _normalize_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_tasks = []
        for task in tasks[:4]:
            description = str(task.get("description", "")).strip()
            if not description:
                continue
            time_limit = int(task.get("time_limit", 5))
            normalized_tasks.append(
                {
                    "description": description,
                    "time_limit": max(1, time_limit),
                }
            )
        return normalized_tasks

    @staticmethod
    def _normalize_status(value: Any, default: str) -> str:
        candidates = {"clear", "narrow", "blocked", "uncertain"}
        value = str(value or "").strip().lower()
        return value if value in candidates else default

    @staticmethod
    def _normalize_risk(value: Any, default: str) -> str:
        candidates = {"low", "medium", "high"}
        value = str(value or "").strip().lower()
        return value if value in candidates else default

    @staticmethod
    def _normalize_confidence(value: Any, default: str) -> str:
        candidates = {"low", "medium", "high"}
        value = str(value or "").strip().lower()
        return value if value in candidates else default

    @staticmethod
    def _normalize_optional_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
        return None

    def _normalize_maneuver_type(
        self,
        maneuver_type: Any,
        fact_pack: Dict[str, Any],
        scene_model: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
    ) -> str:
        candidates = {"keep_lane", "pull_over_right", "change_lane_left", "change_lane_right", "stop_and_wait"}
        maneuver_type = str(maneuver_type or "").strip()
        if maneuver_type in candidates:
            return maneuver_type

        if traffic_command:
            command_text = traffic_command.get("command", "")
            if "靠右" in command_text:
                return "pull_over_right"
            if "停车" in command_text or "停止" in command_text:
                return "stop_and_wait"

        intent = fact_pack.get("vehicle_intent", "")
        if "左" in intent and "变道" in intent:
            return "change_lane_left"
        if "右" in intent and "变道" in intent:
            return "change_lane_right"
        if scene_model.get("roadside_pull_over_feasible") and ("靠边" in intent or "靠右" in intent):
            return "pull_over_right"
        return "keep_lane"

    def _infer_primary_goal(self, fact_pack: Dict[str, Any], traffic_command: Optional[Dict[str, Any]]) -> str:
        if traffic_command:
            return traffic_command.get("command", "优先执行交通管理指令")
        if fact_pack.get("in_blind_spot"):
            return "降低车速并保持环境确认"
        return "在确保安全的前提下保持当前驾驶意图"

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
                "roadside_pull_over_feasible": None,
                "nearby_agents_summary": ["当前无可靠图像，周边环境未知"],
                "conflict_risk": "high",
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
            "roadside_pull_over_feasible": None,
            "nearby_agents_summary": ["周边环境信息不足"],
            "conflict_risk": risk,
            "confidence": "low",
        }

    def _fallback_assessment(
        self,
        fact_pack: Dict[str, Any],
        scene_model: Dict[str, Any],
        traffic_command: Optional[Dict[str, Any]],
        control_policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deterministic assessment when the model is unavailable."""
        risk_level = "low"
        if fact_pack.get("in_blind_spot") or scene_model.get("conflict_risk") == "high":
            risk_level = "high"
        elif traffic_command or fact_pack.get("speed_kmh", 0.0) >= 40 or scene_model.get("conflict_risk") == "medium":
            risk_level = "medium"

        maneuver_type = self._normalize_maneuver_type(None, fact_pack, scene_model, traffic_command)
        return {
            "scene_summary": "基于环境事实生成保守评估。",
            "risk_level": risk_level,
            "primary_goal": self._infer_primary_goal(fact_pack, traffic_command),
            "key_constraints": control_policy.get("hard_constraints", [])[:3],
            "maneuver_type": maneuver_type,
            "lane_change_needed": maneuver_type in {"pull_over_right", "change_lane_left", "change_lane_right"},
            "observation_needed": True,
            "must_wait": bool(traffic_command and "等待" in traffic_command.get("command", "")),
        }

    @staticmethod
    def _default_base_rules() -> str:
        return """你是一个路侧协同智能体。

规则：
1. 安全优先，交通管理指令优先于常规建议。
2. 只输出当前请求要求的 JSON。
3. 不要输出 markdown、解释性前后缀或代码块。
4. 涉及左右时，必须按目标车辆视角理解。
5. 如果信息不足，使用保守结论，不要编造细节。"""

    @staticmethod
    def _default_scene_model_prompt() -> str:
        return """你负责抽取环境事实层，不直接做规划。

要求：
1. 输出最小化环境事实字段。
2. 不要输出 reasoning。
3. gap_status 只能使用 clear、narrow、blocked、uncertain。
4. 如果图像无法支持明确判断，返回 uncertain。"""

    @staticmethod
    def _default_assessment_prompt() -> str:
        return """你负责生成最小化决策状态，而不是直接生成任务。

要求：
1. 只输出合法 JSON。
2. scene_summary 不超过 30 字。
3. key_constraints 最多 3 条。
4. primary_goal 只能有一个。
5. maneuver_type 只能在给定枚举内选择。
6. 不要输出长 reasoning。"""

    @staticmethod
    def _default_task_realizer_prompt() -> str:
        return """你是车辆任务翻译模块。

你不会重新分析场景，也不会重新制定策略。
你只根据输入的 strategy、assessment 和 scene_model 生成车辆可执行任务。

要求：
1. 只输出 {"tasks": [...]}。
2. 任务数量 1 到 4 个。
3. 每个任务只包含一个主要动作。
4. 任务必须直接面向车辆执行。
5. 若需要横向动作，必须先有观察或减速步骤。"""
