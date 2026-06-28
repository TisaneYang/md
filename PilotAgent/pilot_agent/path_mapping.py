from __future__ import annotations

import numpy as np


PATH_TO_MODE = {
    "<turn_left>": 0,
    "<turn_right>": 1,
    "<straight>": 2,
    "<lanefollow>": 3,
    "<change_lane_left>": 4,
    "<change_lane_right>": 5,
}

JUNCTION_PATH_ACTIONS = {"<turn_left>", "<turn_right>", "<straight>"}
NON_JUNCTION_PATH_ACTIONS = {"<lanefollow>", "<change_lane_left>", "<change_lane_right>"}


def path_to_ego_fut_cmd(path_action: str) -> np.ndarray:
    if path_action not in PATH_TO_MODE:
        raise ValueError(f"Unsupported Pilot path action: {path_action}")

    command = np.zeros(6)
    command[PATH_TO_MODE[path_action]] = 1
    return command


def is_path_action_allowed(path_action: str, vehicle_position: dict) -> bool:
    is_in_junction = vehicle_position.get("is_in_junction")
    if is_in_junction is None:
        return True
    if is_in_junction:
        return path_action in JUNCTION_PATH_ACTIONS
    if path_action == "<change_lane_left>" and vehicle_position.get("has_left_driving_lane") is False:
        return False
    if path_action == "<change_lane_right>" and vehicle_position.get("has_right_driving_lane") is False:
        return False
    return path_action in NON_JUNCTION_PATH_ACTIONS
