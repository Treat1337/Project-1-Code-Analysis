"""
app/main.py — FastAPI application factory.

Responsibilities:
  - Initialize FastAPI instance
  - Configure CORS
  - Register all API routers
  - Mount static files
  - Serve index.html at root
  - Initialize global ML model instances at startup

This file merges server.py (port 8000) and the old app/main.py (port 8001)
into a single unified server. All API endpoints are preserved.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    AI_API_KEY,
    ASTNN_MODEL_DIR,
    CLASSIFIER_MODEL_PATH,
    CODEBERT_MODEL_DIR,
    DATASET_DIR,
    NEURAL_MODEL_DIR,
    QWEN_ENABLED,
    QWEN_MODEL,
    STATIC_DIR,
)
from app.services.classifier import CodeClassifier
from app.services.codenet_retrieval import CodeNetSimilarityIndex
from app.services.feedback import LLMProviderError, explain, load_knowledge_base
from app.services.knowledge_tracing import TestCaseInformedKnowledgeTracer
from app.services.misconception_detection import MisconceptionPatternDetector
from app.services.retrieval import KnowledgeBase
from app.services.runner import runner_status

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Code Analysis for Programming Education",
    description=(
        "Unified backend: Project_CodeNet dataset, C++ code execution, "
        "Ollama AI feedback, and ML-based error classification."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global service instances (initialized once at import time)
# ---------------------------------------------------------------------------
knowledge_base: KnowledgeBase = load_knowledge_base()

classifier = CodeClassifier(
    DATASET_DIR / "labeled_examples.csv",
    Path(NEURAL_MODEL_DIR) if NEURAL_MODEL_DIR else None,
    CLASSIFIER_MODEL_PATH,
)

similarity_index = CodeNetSimilarityIndex(DATASET_DIR)
knowledge_tracer = TestCaseInformedKnowledgeTracer()
misconception_detector = MisconceptionPatternDetector()


def _load_optional_neural_model(model_dir: str) -> tuple[Any | None, str]:
    path = Path(model_dir)
    if not (path / "model.json").is_file():
        return None, "Model artifact is not available"
    try:
        from app.services.neural_classifier import TrainedCodeClassifier
        return TrainedCodeClassifier(path), ""
    except (ImportError, OSError, ValueError, KeyError, RuntimeError) as exc:
        return None, f"Could not load model: {exc}"


codebert_model, codebert_reason = _load_optional_neural_model(CODEBERT_MODEL_DIR)
astnn_model, astnn_reason = _load_optional_neural_model(ASTNN_MODEL_DIR)


def _model_predictions(code: str, diagnostic: str) -> dict[str, object]:
    predictions: dict[str, object] = {
        "classifier": classifier.predict(code, diagnostic),
    }
    for name, model, reason in (
        ("codebert", codebert_model, codebert_reason),
        ("astnn", astnn_model, astnn_reason),
    ):
        predictions[name] = (
            model.predict(code, diagnostic)
            if model is not None
            else {"available": False, "reason": reason}
        )
    return predictions


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
from app.api.problems import router as problems_router
from app.api.judge import router as judge_router
from app.api.ai import router as ai_router

app.include_router(problems_router)
app.include_router(judge_router)
app.include_router(ai_router)

# ---------------------------------------------------------------------------
# Static files & root
# ---------------------------------------------------------------------------
# Serve index.html at root
_INDEX_HTML = STATIC_DIR / "index.html"
# Fallback: check project root (old location)
if not _INDEX_HTML.is_file():
    _INDEX_HTML = Path(__file__).resolve().parents[1] / "index.html"


@app.get("/")
def serve_index() -> FileResponse:
    if _INDEX_HTML.is_file():
        return FileResponse(_INDEX_HTML)
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="index.html not found")


# Mount static CSS/JS if the static directory exists
if (STATIC_DIR / "css").is_dir() or (STATIC_DIR / "js").is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "runner": runner_status(),
        "llm_enabled": bool(AI_API_KEY) or QWEN_ENABLED,
        "qwen": {"enabled": QWEN_ENABLED, "model": QWEN_MODEL},
        "classifier": {
            "available": classifier.available,
            "reason": classifier.reason,
        },
        "models": {
            "codebert": {"available": codebert_model is not None, "reason": codebert_reason},
            "astnn": {"available": astnn_model is not None, "reason": astnn_reason},
        },
    }
