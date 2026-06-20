#!/usr/bin/env bash
set -euo pipefail

# Run MindDrive on an external Bench2Drive checkout without modifying that checkout.
#
# Expected Linux dev-machine layout:
#   /home/yangtianyu/md/
#   |-- Bench2Drive
#   `-- MindDrive
#
# Usage:
#   cd /home/yangtianyu/md/MindDrive
#   CARLA_ROOT=/home/carla \
#   CKPT=/path/to/minddrive.pth \
#   bash adzoo/minddrive/run_bench2drive_eval.sh [ROUTES_SUBSET]
#
# Optional env overrides:
#   CONFIG, ROUTES, CHECKPOINT_ENDPOINT, SAVE_PATH, PORT, TM_PORT, GPU_RANK,
#   TM_SEED, REPETITIONS, DEBUG_CHALLENGE, RESUME, RECORD_PATH, TEAM_AGENT,
#   TEAM_CONFIG.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINDDRIVE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROJECT_PARENT="$(cd "${MINDDRIVE_ROOT}/.." && pwd)"
LINUX_DEV_ROOT="/home/yangtianyu/md"

if [ -z "${BENCH2DRIVE_ROOT:-}" ]; then
    if [ -d "${PROJECT_PARENT}/Bench2Drive" ]; then
        BENCH2DRIVE_ROOT="${PROJECT_PARENT}/Bench2Drive"
    elif [ -d "${LINUX_DEV_ROOT}/Bench2Drive" ]; then
        BENCH2DRIVE_ROOT="${LINUX_DEV_ROOT}/Bench2Drive"
    else
        BENCH2DRIVE_ROOT="${PROJECT_PARENT}/Bench2Drive"
    fi
fi
BENCH2DRIVE_LEADERBOARD_DIR="${BENCH2DRIVE_ROOT}/leaderboard"
BENCH2DRIVE_SCENARIO_RUNNER_DIR="${BENCH2DRIVE_ROOT}/scenario_runner"

if [ ! -d "${BENCH2DRIVE_LEADERBOARD_DIR}" ] || [ ! -d "${BENCH2DRIVE_SCENARIO_RUNNER_DIR}" ]; then
    echo "ERROR: BENCH2DRIVE_ROOT is invalid: ${BENCH2DRIVE_ROOT}" >&2
    echo "Set BENCH2DRIVE_ROOT=/path/to/Bench2Drive" >&2
    exit 1
fi

if [ -z "${CARLA_ROOT:-}" ]; then
    if [ -d "${PROJECT_PARENT}/carla" ]; then
        export CARLA_ROOT="${PROJECT_PARENT}/carla"
    elif [ -d "${LINUX_DEV_ROOT}/carla" ]; then
        export CARLA_ROOT="${LINUX_DEV_ROOT}/carla"
    elif [ -d "${HOME}/carla" ]; then
        export CARLA_ROOT="${HOME}/carla"
    elif [ -d "/home/carla" ]; then
        export CARLA_ROOT="/home/carla"
    else
        echo "ERROR: CARLA_ROOT is not set and could not be auto-detected." >&2
        echo "Set CARLA_ROOT=/path/to/CARLA_0.9.15" >&2
        exit 1
    fi
fi

if [ ! -x "${CARLA_ROOT}/CarlaUE4.sh" ]; then
    echo "ERROR: CARLA server not found or not executable: ${CARLA_ROOT}/CarlaUE4.sh" >&2
    exit 1
fi

EVAL_WORKDIR="${MINDDRIVE_ROOT}/.bench2drive_eval"
mkdir -p "${EVAL_WORKDIR}"
if [ -e "${EVAL_WORKDIR}/Bench2DriveZoo" ] && [ ! -L "${EVAL_WORKDIR}/Bench2DriveZoo" ]; then
    echo "ERROR: ${EVAL_WORKDIR}/Bench2DriveZoo exists and is not a symlink." >&2
    exit 1
fi
ln -sfn "${MINDDRIVE_ROOT}" "${EVAL_WORKDIR}/Bench2DriveZoo"

CARLA_EGG="${CARLA_EGG:-}"
if [ -z "${CARLA_EGG}" ]; then
    for pattern in \
        "${CARLA_ROOT}"/PythonAPI/carla/dist/carla-0.9.15-py3.8-*.egg \
        "${CARLA_ROOT}"/PythonAPI/carla/dist/carla-0.9.15-py3.7-*.egg \
        "${CARLA_ROOT}"/PythonAPI/carla/dist/carla-0.9.15-py3.*.egg; do
        for egg in ${pattern}; do
            if [ -f "${egg}" ]; then
                CARLA_EGG="${egg}"
                break 2
            fi
        done
    done
fi

if [ -z "${CARLA_EGG}" ]; then
    echo "ERROR: No Python 3 CARLA egg found under ${CARLA_ROOT}/PythonAPI/carla/dist" >&2
    echo "Expected something like carla-0.9.15-py3.7-linux-x86_64.egg for Python 3.8." >&2
    echo "Current dist files:" >&2
    ls -1 "${CARLA_ROOT}/PythonAPI/carla/dist" 2>/dev/null >&2 || true
    exit 1
fi

if [[ "${CARLA_EGG}" == *"py2.7"* ]]; then
    echo "ERROR: Refusing to use Python 2 CARLA egg with Python 3: ${CARLA_EGG}" >&2
    echo "Set CARLA_EGG=/path/to/carla-0.9.15-py3.7-linux-x86_64.egg or reinstall CARLA 0.9.15 PythonAPI." >&2
    exit 1
fi

export CARLA_SERVER="${CARLA_ROOT}/CarlaUE4.sh"
export SCENARIO_RUNNER_ROOT="${BENCH2DRIVE_SCENARIO_RUNNER_DIR}"
export LEADERBOARD_ROOT="${BENCH2DRIVE_LEADERBOARD_DIR}"
export CHALLENGE_TRACK_CODENAME="${CHALLENGE_TRACK_CODENAME:-SENSORS}"
export IS_BENCH2DRIVE="${IS_BENCH2DRIVE:-True}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

export PYTHONPATH="${CARLA_ROOT}/PythonAPI:${CARLA_ROOT}/PythonAPI/carla:${BENCH2DRIVE_LEADERBOARD_DIR}:${BENCH2DRIVE_SCENARIO_RUNNER_DIR}:${EVAL_WORKDIR}:${MINDDRIVE_ROOT}:${PYTHONPATH:-}"
export PYTHONPATH="${CARLA_EGG}:${PYTHONPATH}"

python - <<'PY'
import sys
try:
    import transformers
    from transformers import Qwen2Config
except Exception as exc:
    print("ERROR: MindDrive requires transformers with Qwen2 support.", file=sys.stderr)
    print("Install the pinned dependencies in the active conda env:", file=sys.stderr)
    print("  pip install -U 'transformers==4.45.2' 'peft==0.12.0' sentencepiece", file=sys.stderr)
    print(f"Original import error: {exc}", file=sys.stderr)
    raise SystemExit(1)
print(f"Transformers version: {transformers.__version__}")
PY

PORT="${PORT:-2000}"
TM_PORT="${TM_PORT:-2001}"
GPU_RANK="${GPU_RANK:-0}"
TM_SEED="${TM_SEED:-0}"
REPETITIONS="${REPETITIONS:-1}"
DEBUG_CHALLENGE="${DEBUG_CHALLENGE:-0}"
RESUME="${RESUME:-True}"
RECORD_PATH="${RECORD_PATH:-}"
ROUTES_SUBSET="${1:-${ROUTES_SUBSET:-}}"

TEAM_CONFIG_PROVIDED=0
if [ -n "${TEAM_CONFIG:-}" ]; then
    TEAM_CONFIG_PROVIDED=1
fi

CONFIG="${CONFIG:-${MINDDRIVE_ROOT}/adzoo/minddrive/configs/minddrive_qwen2_05B_infer.py}"
CKPT="${CKPT:-${MINDDRIVE_ROOT}/ckpts/Minddrive.pth}"
ROUTES="${ROUTES:-${BENCH2DRIVE_LEADERBOARD_DIR}/data/bench2drive220.xml}"
CHECKPOINT_ENDPOINT="${CHECKPOINT_ENDPOINT:-${MINDDRIVE_ROOT}/work_dirs/bench2drive_eval/results.json}"
SAVE_PATH="${SAVE_PATH:-${MINDDRIVE_ROOT}/work_dirs/bench2drive_eval/vis}"
TEAM_AGENT="${TEAM_AGENT:-${MINDDRIVE_ROOT}/team_code/minddrive_b2d_agent.py}"
TEAM_CONFIG="${TEAM_CONFIG:-${CONFIG}+${CKPT}}"
export ROUTES CHECKPOINT_ENDPOINT SAVE_PATH TEAM_AGENT TEAM_CONFIG CONFIG CKPT

mkdir -p "$(dirname "${CHECKPOINT_ENDPOINT}")" "${SAVE_PATH}"

if [ ! -f "${CONFIG}" ]; then
    echo "ERROR: CONFIG not found: ${CONFIG}" >&2
    exit 1
fi
if [ "${TEAM_CONFIG_PROVIDED}" = "0" ] && [ ! -f "${CKPT}" ]; then
    echo "ERROR: CKPT not found: ${CKPT}" >&2
    echo "Set CKPT=/path/to/minddrive.pth or provide TEAM_CONFIG=<config.py>+<ckpt.pth>" >&2
    exit 1
fi
if [ ! -f "${TEAM_AGENT}" ]; then
    echo "ERROR: TEAM_AGENT not found: ${TEAM_AGENT}" >&2
    exit 1
fi
if [ ! -f "${ROUTES}" ]; then
    echo "ERROR: ROUTES not found: ${ROUTES}" >&2
    exit 1
fi

echo "Bench2Drive root: ${BENCH2DRIVE_ROOT}"
echo "MindDrive root:    ${MINDDRIVE_ROOT}"
echo "CARLA root:        ${CARLA_ROOT}"
echo "Routes:            ${ROUTES}"
echo "Routes subset:     ${ROUTES_SUBSET:-<all>}"
echo "Team agent:        ${TEAM_AGENT}"
echo "Team config:       ${TEAM_CONFIG}"
echo "Checkpoint JSON:   ${CHECKPOINT_ENDPOINT}"
echo "Save path:         ${SAVE_PATH}"

CUDA_VISIBLE_DEVICES="${GPU_RANK}" python "${LEADERBOARD_ROOT}/leaderboard/leaderboard_evaluator.py" \
    --routes="${ROUTES}" \
    --repetitions="${REPETITIONS}" \
    --track="${CHALLENGE_TRACK_CODENAME}" \
    --checkpoint="${CHECKPOINT_ENDPOINT}" \
    --agent="${TEAM_AGENT}" \
    --agent-config="${TEAM_CONFIG}" \
    --debug="${DEBUG_CHALLENGE}" \
    --record="${RECORD_PATH}" \
    --resume="${RESUME}" \
    --port="${PORT}" \
    --traffic-manager-port="${TM_PORT}" \
    --traffic-manager-seed="${TM_SEED}" \
    --gpu-rank="${GPU_RANK}" \
    $([ -n "${ROUTES_SUBSET}" ] && echo "--routes-subset=${ROUTES_SUBSET}")