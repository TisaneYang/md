#!/usr/bin/env python3
"""Encode fixed fields with Protobuf enums and retain only item/description text."""

import argparse
import json
from pathlib import Path

import message_fixed_pb2


URGENCY_MAP = {
    "low": message_fixed_pb2.URGENCY_LOW,
    "medium": message_fixed_pb2.URGENCY_MEDIUM,
    "high": message_fixed_pb2.URGENCY_HIGH,
    "urgent": message_fixed_pb2.URGENCY_URGENT,
}

OBSTACLE_TYPE_MAP = {
    "road block": message_fixed_pb2.OBSTACLE_TYPE_ROAD_BLOCK,
    "parking vehicle": message_fixed_pb2.OBSTACLE_TYPE_PARKING_VEHICLE,
    "human": message_fixed_pb2.OBSTACLE_TYPE_HUMAN,
    "others": message_fixed_pb2.OBSTACLE_TYPE_OTHERS,
}

IMPACT_LEVEL_MAP = {
    "none": message_fixed_pb2.IMPACT_LEVEL_NONE,
    "slightly": message_fixed_pb2.IMPACT_LEVEL_SLIGHTLY,
    "medium": message_fixed_pb2.IMPACT_LEVEL_MEDIUM,
    "heavy": message_fixed_pb2.IMPACT_LEVEL_HEAVY,
}

DANGER_TYPE_MAP = {
    "unpredictable pedestrians": message_fixed_pb2.DANGER_TYPE_UNPREDICTABLE_PEDESTRIANS,
    "fast vehicles": message_fixed_pb2.DANGER_TYPE_FAST_VEHICLES,
    "blind spots": message_fixed_pb2.DANGER_TYPE_BLIND_SPOTS,
    "others": message_fixed_pb2.DANGER_TYPE_OTHERS,
}

PRESENT = message_fixed_pb2.PRESENCE_FLAG_PRESENT


def strip_jsonc_comments(jsonc_text):
    """Remove // comments outside strings so JSONC can be parsed as JSON."""
    out = []
    in_str = False
    escaped = False
    i = 0
    n = len(jsonc_text)

    while i < n:
        ch = jsonc_text[i]
        nxt = jsonc_text[i + 1] if i + 1 < n else ""

        if in_str:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            i += 1
            continue

        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            while i < n and jsonc_text[i] != "\n":
                i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def enum_value(mapping, raw_value, field_name):
    key = str(raw_value).strip().lower()
    if key not in mapping:
        raise ValueError(f"Unsupported enum value for {field_name}: {raw_value!r}")
    return mapping[key]


def build_messages_fixed_and_retained(data):
    messages = data.get("messages", [])
    fixed = message_fixed_pb2.MessagesFixed()
    retained_messages = []

    for msg in messages:
        fixed_msg = fixed.messages.add()
        fixed_msg.time = int(msg.get("time", 0))
        fixed_msg.urgency = enum_value(URGENCY_MAP, msg.get("urgency", ""), "urgency")
        fixed_msg.emergency_stop = bool(msg.get("emergency_stop", False))
        if "description" in msg:
            fixed_msg.top_level_description = PRESENT

        retained_msg = {"conflict": [], "obstacles": [], "dangers": [], "tasks": []}

        for conflict in msg.get("conflict", []):
            fixed_conflict = fixed_msg.conflicts.add()
            fixed_conflict.dist = float(conflict.get("dist", 0.0))
            retained_conflict = {}
            if "item" in conflict:
                fixed_conflict.item = PRESENT
                retained_conflict["item"] = conflict["item"]
            retained_msg["conflict"].append(retained_conflict)

        for obstacle in msg.get("obstacles", []):
            fixed_obstacle = fixed_msg.obstacles.add()
            fixed_obstacle.type = enum_value(OBSTACLE_TYPE_MAP, obstacle.get("type", ""), "obstacles.type")
            fixed_obstacle.impact = enum_value(IMPACT_LEVEL_MAP, obstacle.get("impact", ""), "obstacles.impact")
            for position in obstacle.get("position", []):
                fixed_obstacle.position.append(float(position))

            retained_obstacle = {}
            if "description" in obstacle:
                fixed_obstacle.description = PRESENT
                retained_obstacle["description"] = obstacle["description"]
            retained_msg["obstacles"].append(retained_obstacle)

        for danger in msg.get("dangers", []):
            fixed_danger = fixed_msg.dangers.add()
            fixed_danger.type = enum_value(DANGER_TYPE_MAP, danger.get("type", ""), "dangers.type")
            fixed_danger.degree = enum_value(URGENCY_MAP, danger.get("degree", ""), "dangers.degree")
            for position in danger.get("position", []):
                fixed_danger.position.append(float(position))

            retained_danger = {}
            if "description" in danger:
                fixed_danger.description = PRESENT
                retained_danger["description"] = danger["description"]
            retained_msg["dangers"].append(retained_danger)

        for task in msg.get("tasks", []):
            fixed_task = fixed_msg.tasks.add()
            fixed_task.time_limit = int(task.get("time_limit", 0))

            retained_task = {}
            if "description" in task:
                fixed_task.description = PRESENT
                retained_task["description"] = task["description"]
            retained_msg["tasks"].append(retained_task)

        if "description" in msg:
            retained_msg["description"] = msg["description"]

        retained_messages.append(retained_msg)

    retained_json = json.dumps({"messages": retained_messages}, ensure_ascii=False)
    return fixed, retained_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="message_template.json")
    parser.add_argument("--fixed-out", default="proto/out/fixed_fields.pb")
    parser.add_argument("--retained-out", default="proto/out/retained_fields.json")
    parser.add_argument("--mixed-out", default="proto/out/mixed_payload.pb")
    args = parser.parse_args()

    raw_text = Path(args.input).read_text(encoding="utf-8")
    data = json.loads(strip_jsonc_comments(raw_text))

    fixed_msg, retained_json = build_messages_fixed_and_retained(data)
    fixed_bytes = fixed_msg.SerializeToString()

    mixed = message_fixed_pb2.MixedEncodedPayload()
    mixed.fixed_proto = fixed_bytes
    mixed.retained_json = retained_json

    Path(args.fixed_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.retained_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.mixed_out).parent.mkdir(parents=True, exist_ok=True)

    Path(args.fixed_out).write_bytes(fixed_bytes)
    Path(args.retained_out).write_text(retained_json, encoding="utf-8")
    Path(args.mixed_out).write_bytes(mixed.SerializeToString())

    print(f"fixed protobuf bytes: {len(fixed_bytes)} -> {args.fixed_out}")
    print(f"retained json chars: {len(retained_json)} -> {args.retained_out}")
    print(f"mixed payload bytes: {Path(args.mixed_out).stat().st_size} -> {args.mixed_out}")


if __name__ == "__main__":
    main()
