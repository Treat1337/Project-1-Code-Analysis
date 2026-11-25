"""
app/config.py — Centralized configuration for Code Analysis Platform.

All paths are computed from PROJECT_ROOT using pathlib.
No hardcoded Windows absolute paths in business logic modules.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root — always the directory that contains app/
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Dataset paths
# ---------------------------------------------------------------------------
DATASET_DIR: Path = PROJECT_ROOT / "Dataset"
CODE_NET_ROOT: Path = DATASET_DIR / "Project_CodeNet"
PROBLEM_DESCRIPTIONS: Path = CODE_NET_ROOT / "problem_descriptions"
TEST_IO_DATA: Path = CODE_NET_ROOT / "derived" / "input_output" / "data"
CODE_NET_METADATA: Path = CODE_NET_ROOT / "metadata"
CODE_NET_SOURCE: Path = CODE_NET_ROOT / "data"
KNOWLEDGE_PATH: Path = DATASET_DIR / "knowledge.json"

# ---------------------------------------------------------------------------
# Model checkpoints (prefer models/, fallback to artifacts/code-models/)
# ---------------------------------------------------------------------------
MODELS_DIR: Path = PROJECT_ROOT / "models"
_ARTIFACTS_DIR: Path = PROJECT_ROOT / "artifacts" / "code-models"

CODEBERT_MODEL_DIR: Path = Path(
    os.getenv(
        "CODEBERT_MODEL_DIR",
        str(MODELS_DIR / "codebert" if (MODELS_DIR / "codebert" / "model.json").is_file() else _ARTIFACTS_DIR / "codebert"),
    )
).resolve()

ASTNN_MODEL_DIR: Path = Path(
    os.getenv(
        "ASTNN_MODEL_DIR",
        str(MODELS_DIR / "astnn" if (MODELS_DIR / "astnn" / "model.json").is_file() else _ARTIFACTS_DIR / "astnn"),
    )
).resolve()

CLASSIFIER_MODEL_PATH: Path = Path(
    os.getenv(
        "CLASSIFIER_MODEL_PATH",
        str(MODELS_DIR / "classifier" / "model.joblib" if (MODELS_DIR / "classifier" / "model.joblib").is_file() else _ARTIFACTS_DIR / "classifier" / "model.joblib"),
    )
).resolve()

NEURAL_MODEL_DIR: str = os.getenv("NEURAL_MODEL_DIR", "").strip()

# ---------------------------------------------------------------------------
# Temporary files
# ---------------------------------------------------------------------------
TEMP_DIR: Path = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Server / network
# ---------------------------------------------------------------------------
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# ---------------------------------------------------------------------------
# Ollama / LLM
# ---------------------------------------------------------------------------
QWEN_ENABLED: bool = os.getenv("QWEN_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen2.5-coder:3b-instruct-q8_0")

AI_API_KEY: str = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL: str = os.getenv("AI_MODEL", "gpt-4o-mini")

# ---------------------------------------------------------------------------
# Docker runner
# ---------------------------------------------------------------------------
RUNNER_IMAGE: str = os.getenv("RUNNER_IMAGE", "code-analysis-runner:latest")

# ---------------------------------------------------------------------------
# Code execution limits
# ---------------------------------------------------------------------------
MAX_CODE_BYTES: int = 64 * 1024
MAX_TEST_CASES: int = 10
MAX_INPUT_BYTES: int = 16 * 1024
MAX_OUTPUT_BYTES: int = 256 * 1024
CASE_TIMEOUT_SECONDS: float = 2.0
COMPILE_TIMEOUT_SECONDS: float = 15.0

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_DIR: Path = PROJECT_ROOT / "app" / "static"
