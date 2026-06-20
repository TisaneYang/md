#!/usr/bin/env bash
set -euo pipefail

# Create a clean conda environment for MindDrive + Bench2Drive closed-loop eval.
#
# Default Linux dev-machine layout:
#   /home/yangtianyu/md/
#   |-- Bench2Drive
#   `-- MindDrive
#
# Usage:
#   cd /home/yangtianyu/md/MindDrive
#   bash adzoo/minddrive/setup_minddrive_env.sh
#
# Useful overrides:
#   ENV_NAME=minddrive_b2d RECREATE=1 bash adzoo/minddrive/setup_minddrive_env.sh
#   CARLA_ROOT=/home/yangtianyu/carla bash adzoo/minddrive/setup_minddrive_env.sh
#   INSTALL_FLASH_ATTN=0 bash adzoo/minddrive/setup_minddrive_env.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINDDRIVE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROJECT_PARENT="$(cd "${MINDDRIVE_ROOT}/.." && pwd)"
LINUX_DEV_ROOT="/home/yangtianyu/md"

ENV_NAME="${ENV_NAME:-minddrive_b2d}"
PYTHON_VERSION="${PYTHON_VERSION:-3.8}"
RECREATE="${RECREATE:-0}"
INSTALL_CUDA_TOOLKIT="${INSTALL_CUDA_TOOLKIT:-1}"
INSTALL_FLASH_ATTN="${INSTALL_FLASH_ATTN:-1}"
CUDA_CHANNEL="${CUDA_CHANNEL:-nvidia/label/cuda-11.8.0}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu118}"
FLASH_ATTN_PACKAGE="${FLASH_ATTN_PACKAGE:-flash-attn}"
MAX_JOBS="${MAX_JOBS:-8}"

echo "MindDrive root: ${MINDDRIVE_ROOT}"
echo "Conda env:      ${ENV_NAME}"
echo "Python:         ${PYTHON_VERSION}"

if ! command -v conda >/dev/null 2>&1; then
    if [ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]; then
        # shellcheck disable=SC1091
        source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    elif [ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]; then
        # shellcheck disable=SC1091
        source "${HOME}/anaconda3/etc/profile.d/conda.sh"
    else
        echo "ERROR: conda not found. Install Miniconda/Anaconda first." >&2
        exit 1
    fi
fi

eval "$(conda shell.bash hook)"

if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    if [ "${RECREATE}" = "1" ]; then
        echo "Removing existing env: ${ENV_NAME}"
        conda env remove -n "${ENV_NAME}" -y
    else
        echo "ERROR: conda env already exists: ${ENV_NAME}" >&2
        echo "Use RECREATE=1 to remove and recreate it, or set ENV_NAME=<new_name>." >&2
        exit 1
    fi
fi

conda create -n "${ENV_NAME}" "python=${PYTHON_VERSION}" -y
conda activate "${ENV_NAME}"

python -m pip install -U "pip<25" setuptools wheel ninja packaging psutil

if [ "${INSTALL_CUDA_TOOLKIT}" = "1" ]; then
    conda install -c "${CUDA_CHANNEL}" cuda-toolkit -y
fi

export CUDA_HOME="${CUDA_HOME:-${CONDA_PREFIX}}"
export PATH="${CUDA_HOME}/bin:${PATH}"
export MAX_JOBS

echo "Installing PyTorch cu118..."
python -m pip install torch torchvision torchaudio --index-url "${TORCH_INDEX_URL}"

TMP_REQ="$(mktemp)"
trap 'rm -f "${TMP_REQ}"' EXIT
grep -Ev '^[[:space:]]*flash[_-]attn([[:space:]]|$|[=<>])' "${MINDDRIVE_ROOT}/requirements.txt" > "${TMP_REQ}"

echo "Installing MindDrive Python requirements except flash-attn..."
python -m pip install -r "${TMP_REQ}"

if [ "${INSTALL_FLASH_ATTN}" = "1" ]; then
    echo "Installing ${FLASH_ATTN_PACKAGE}..."
    python -m pip install "${FLASH_ATTN_PACKAGE}" --no-build-isolation
else
    echo "Skipping flash-attn because INSTALL_FLASH_ATTN=0"
fi

echo "Building and installing MindDrive/MMCV extensions..."
cd "${MINDDRIVE_ROOT}"
python -m pip install -v -e . --no-deps

if [ -z "${CARLA_ROOT:-}" ]; then
    if [ -d "${PROJECT_PARENT}/carla" ]; then
        CARLA_ROOT="${PROJECT_PARENT}/carla"
    elif [ -d "${LINUX_DEV_ROOT}/carla" ]; then
        CARLA_ROOT="${LINUX_DEV_ROOT}/carla"
    elif [ -d "${HOME}/carla" ]; then
        CARLA_ROOT="${HOME}/carla"
    elif [ -d "/home/carla" ]; then
        CARLA_ROOT="/home/carla"
    else
        CARLA_ROOT=""
    fi
fi

if [ -n "${CARLA_ROOT}" ]; then
    CARLA_EGG=""
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

    if [ -n "${CARLA_EGG}" ]; then
        SITE_PACKAGES="$(python - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
        echo "${CARLA_EGG}" > "${SITE_PACKAGES}/carla.pth"
        echo "Configured CARLA egg: ${CARLA_EGG}"
    else
        echo "WARNING: No Python 3 CARLA 0.9.15 egg found under ${CARLA_ROOT}/PythonAPI/carla/dist" >&2
        echo "         Set CARLA_ROOT and rerun, or add the py3 CARLA egg to ${ENV_NAME}/site-packages/carla.pth manually." >&2
    fi
else
    echo "WARNING: CARLA_ROOT not found. You can still set it later when running evaluation." >&2
fi

echo "Validating core imports..."
python - <<'PY'
import torch
import transformers
from transformers import Qwen2Config
from mmcv import Config

print("torch:", torch.__version__, "cuda:", torch.version.cuda, "cuda_available:", torch.cuda.is_available())
print("transformers:", transformers.__version__)
print("Qwen2Config:", Qwen2Config.__name__)
print("mmcv Config:", Config.__name__)
try:
    import carla
    print("carla import: ok")
except Exception as exc:
    print(f"carla import: skipped/failed ({exc})")
PY

echo
echo "Environment is ready."
echo "Next commands:"
echo "  conda activate ${ENV_NAME}"
echo "  cd ${MINDDRIVE_ROOT}"
echo "  bash adzoo/minddrive/run_bench2drive_eval.sh 0"