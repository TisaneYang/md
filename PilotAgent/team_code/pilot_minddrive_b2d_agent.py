from __future__ import annotations

import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MINDDRIVE_ROOT = REPO_ROOT / "MindDrive"
for path in (REPO_ROOT, MINDDRIVE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from team_code.minddrive_b2d_agent import MinddriveAgent


def get_entry_point():
    return "PilotMinddriveAgent"


class PilotMinddriveAgent(MinddriveAgent):
    """Leaderboard entry point that enables PilotAgent via PILOT_AGENT_CONFIG."""

    pass

