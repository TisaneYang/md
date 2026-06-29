#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash scripts/quick_start.sh <route_id>

Example:
  bash scripts/quick_start.sh 0

Optional environment overrides:
  CARLA_ROOT=/path/to/CARLA_0.9.15
  CKPT=/path/to/Minddrive.pth
  CONFIG=/path/to/minddrive_config.py
  BENCH2DRIVE_ROOT=/path/to/Bench2Drive
  VEHICLE_COMMAND_PORT=9101
  ROADSIDE_SERVER_PORT=8890
  PORT=2000
  TM_PORT=2001
  GPU_RANK=0
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

if [ $# -ne 1 ]; then
    usage >&2
    exit 1
fi

ROUTE_ID="$1"
ROUTE_NAME="RouteScenario_${ROUTE_ID}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUN_EVAL_SCRIPT="${REPO_ROOT}/MindDrive/adzoo/minddrive/run_bench2drive_eval.sh"
PILOT_TEMPLATE="${REPO_ROOT}/PilotAgent/configs/pilot_agent.json"
ROADSIDE_TEMPLATE="${REPO_ROOT}/RoadsideAgent/config/roadside_agent.json"
DEFAULT_TEAM_AGENT="${REPO_ROOT}/PilotAgent/team_code/pilot_minddrive_b2d_agent.py"
DEFAULT_ROUTES="${REPO_ROOT}/Bench2Drive/leaderboard/data/bench2drive220.xml"
ROUTE_CONFIG_PATH="${REPO_ROOT}/RoadsideAgent/config/routes/${ROUTE_NAME}.yaml"

for required_file in \
    "${RUN_EVAL_SCRIPT}" \
    "${PILOT_TEMPLATE}" \
    "${ROADSIDE_TEMPLATE}" \
    "${DEFAULT_TEAM_AGENT}" \
    "${DEFAULT_ROUTES}"; do
    if [ ! -f "${required_file}" ]; then
        echo "ERROR: required file not found: ${required_file}" >&2
        exit 1
    fi
done

if [ ! -f "${ROUTE_CONFIG_PATH}" ]; then
    echo "ERROR: roadside route config not found: ${ROUTE_CONFIG_PATH}" >&2
    echo "Create RoadsideAgent/config/routes/${ROUTE_NAME}.yaml before running quick_start." >&2
    exit 1
fi

VEHICLE_COMMAND_PORT="${VEHICLE_COMMAND_PORT:-9101}"
ROADSIDE_SERVER_PORT="${ROADSIDE_SERVER_PORT:-8890}"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
RUNTIME_DIR="${SCRIPT_DIR}/.runtime/quick_start/${ROUTE_NAME}/${TIMESTAMP}"
mkdir -p "${RUNTIME_DIR}"

export PILOT_TEMPLATE
export ROADSIDE_TEMPLATE
export PILOT_RUNTIME_CONFIG="${RUNTIME_DIR}/pilot_agent.json"
export ROADSIDE_RUNTIME_CONFIG="${RUNTIME_DIR}/roadside_agent.json"
export PILOT_LOG_PATH="${RUNTIME_DIR}/pilot_decisions.jsonl"
export ROADSIDE_LOG_PATH="${RUNTIME_DIR}/roadside_decisions.jsonl"
export ROAD_ENDPOINT="127.0.0.1:${VEHICLE_COMMAND_PORT}"
export ROADSIDE_REPORT_URL="http://127.0.0.1:${ROADSIDE_SERVER_PORT}/vehicles/state"
export VEHICLE_COMMAND_PORT
export ROADSIDE_SERVER_PORT

python3 - <<'PY'
import json
import os
from pathlib import Path

pilot_template = Path(os.environ["PILOT_TEMPLATE"])
roadside_template = Path(os.environ["ROADSIDE_TEMPLATE"])
pilot_runtime = Path(os.environ["PILOT_RUNTIME_CONFIG"])
roadside_runtime = Path(os.environ["ROADSIDE_RUNTIME_CONFIG"])

pilot = json.loads(pilot_template.read_text(encoding="utf-8"))
pilot["enabled"] = True
pilot.setdefault("upstream", {})
pilot["upstream"]["type"] = "http_push"
pilot["upstream"]["host"] = "127.0.0.1"
pilot["upstream"]["port"] = int(os.environ["VEHICLE_COMMAND_PORT"])
pilot.setdefault("logging", {})
pilot["logging"]["path"] = os.environ["PILOT_LOG_PATH"]
pilot["logging"]["enabled"] = True
pilot.setdefault("roadside_report", {})
pilot["roadside_report"]["enabled"] = True
pilot["roadside_report"]["url"] = os.environ["ROADSIDE_REPORT_URL"]
pilot["roadside_report"]["endpoint"] = os.environ["ROAD_ENDPOINT"]
pilot_runtime.write_text(json.dumps(pilot, indent=2) + "\n", encoding="utf-8")

roadside = json.loads(roadside_template.read_text(encoding="utf-8"))
roadside["enabled"] = True
roadside.setdefault("logging", {})
roadside["logging"]["path"] = os.environ["ROADSIDE_LOG_PATH"]
roadside["logging"]["enabled"] = True
roadside.setdefault("server", {})
roadside["server"]["enabled"] = True
roadside["server"]["host"] = "127.0.0.1"
roadside["server"]["port"] = int(os.environ["ROADSIDE_SERVER_PORT"])
roadside_runtime.write_text(json.dumps(roadside, indent=2) + "\n", encoding="utf-8")
PY

export PILOT_AGENT_CONFIG="${PILOT_RUNTIME_CONFIG}"
export ROADSIDE_AGENT_CONFIG="${ROADSIDE_RUNTIME_CONFIG}"
export TEAM_AGENT="${TEAM_AGENT:-${DEFAULT_TEAM_AGENT}}"
export ROUTES="${ROUTES:-${DEFAULT_ROUTES}}"
export CHECKPOINT_ENDPOINT="${CHECKPOINT_ENDPOINT:-${RUNTIME_DIR}/results.json}"
export SAVE_PATH="${SAVE_PATH:-${RUNTIME_DIR}/vis}"

mkdir -p "${SAVE_PATH}"

echo "Quick start route:       ${ROUTE_NAME}"
echo "Bench2Drive routes xml:  ${ROUTES}"
echo "Team agent:              ${TEAM_AGENT}"
echo "Pilot config:            ${PILOT_AGENT_CONFIG}"
echo "Roadside config:         ${ROADSIDE_AGENT_CONFIG}"
echo "Pilot receiver endpoint: http://${ROAD_ENDPOINT}/upstream"
echo "Roadside server:         ${ROADSIDE_REPORT_URL}"
echo "Artifacts dir:           ${RUNTIME_DIR}"

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "WARN: OPENAI_API_KEY is not set. Cloud VLM requests may fail unless your configs use another provider." >&2
fi

exec bash "${RUN_EVAL_SCRIPT}" "${ROUTE_ID}"
