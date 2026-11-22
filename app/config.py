import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = BASE_DIR / "Dataset"
KNOWLEDGE_PATH = DATASET_DIR / "knowledge.json"

RUNNER_IMAGE = os.getenv("RUNNER_IMAGE", "code-analysis-runner:latest")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
QWEN_ENABLED = os.getenv("QWEN_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "http://localhost:11434").rstrip("/")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5-coder:3b-instruct-q8_0")
NEURAL_MODEL_DIR = os.getenv("NEURAL_MODEL_DIR", "").strip()
CODEBERT_MODEL_DIR = os.getenv(
    "CODEBERT_MODEL_DIR",
    str(BASE_DIR / "artifacts" / "code-models" / "codebert"),
).strip()
ASTNN_MODEL_DIR = os.getenv(
    "ASTNN_MODEL_DIR",
    str(BASE_DIR / "artifacts" / "code-models" / "astnn"),
).strip()
CLASSIFIER_MODEL_PATH = Path(
    os.getenv(
        "CLASSIFIER_MODEL_PATH",
        str(BASE_DIR / "artifacts" / "code-models" / "classifier" / "model.joblib"),
    )
)

MAX_CODE_BYTES = 64 * 1024
MAX_TEST_CASES = 10
MAX_INPUT_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
CASE_TIMEOUT_SECONDS = 2.0
COMPILE_TIMEOUT_SECONDS = 15.0
