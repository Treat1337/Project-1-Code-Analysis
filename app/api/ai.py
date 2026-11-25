"""
app/api/ai.py — AI/LLM and ML model endpoints.

Extracted from server.py and app/main.py. Preserves:
  POST /api/ai-feedback   (Ollama proxy — from server.py)
  POST /feedback          (Qwen/OpenAI feedback — from app/main.py)
  POST /classify          (CodeClassifier — from app/main.py)
  POST /api/models/predict (all 3 models — from app/main.py)
  POST /learning/trace    (Knowledge tracer — from app/main.py)
  POST /misconceptions/analyze (Misconception detector — from app/main.py)
  GET  /knowledge/search  (Knowledge base search — from app/main.py)
"""
from __future__ import annotations

import re
import time
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

from app.config import QWEN_BASE_URL, QWEN_MODEL
from app.schemas.schemas import (
    ApiAiRequest,
    ClassifyRequest,
    FeedbackRequest,
    KnowledgeTraceRequest,
    MisconceptionRequest,
)

router = APIRouter()


def _extract_plain_text(html_source: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", html_source)
    import html as html_stdlib
    plain = html_stdlib.unescape(re.sub(r"\s+", " ", plain)).strip()
    return plain


# ---------------------------------------------------------------------------
# Ollama proxy (from server.py)
# ---------------------------------------------------------------------------

@router.post("/api/ai-feedback")
def api_ai_feedback(request: ApiAiRequest) -> dict[str, Any]:
    """
    Backend proxy to Ollama at /api/generate.
    Preserved from server.py — logic unchanged.
    """
    ollama_url = f"{QWEN_BASE_URL}/api/generate"
    model_tag = QWEN_MODEL

    plain_desc = _extract_plain_text(request.problem_description)
    if len(plain_desc) > 1500:
        plain_desc = plain_desc[:1500] + "..."

    prompt = (
        "You are an expert programming tutor helping a student understand why their code failed a competitive programming problem.\n"
        "Explain concisely why the solution failed and provide clear, actionable guidance to fix it without revealing the full answer code.\n\n"
        f"### Problem Description:\n{plain_desc}\n\n"
        f"### Verdict: {request.verdict}\n\n"
    )
    if request.failing_input:
        prompt += f"### Failing Input:\n```\n{request.failing_input.strip()[:600]}\n```\n\n"
    if request.expected_output:
        prompt += f"### Expected Output:\n```\n{request.expected_output.strip()[:600]}\n```\n\n"
    if request.actual_output:
        prompt += f"### Actual Output:\n```\n{request.actual_output.strip()[:600]}\n```\n\n"
    if request.stderr:
        prompt += f"### Diagnostics / Stderr:\n```\n{request.stderr.strip()[:800]}\n```\n\n"
    prompt += (
        f"### User Code ({request.language}):\n```{request.language}\n{request.code[:2000]}\n```\n\n"
        "Please provide your explanation structured under these three headings in clean Markdown:\n"
        "### 1. Root Cause\nExplain the underlying logical or runtime error that caused this verdict.\n\n"
        "### 2. Specific Flaw\nPoint out the specific lines of code, faulty conditions, or miscalculations.\n\n"
        "### 3. Actionable Fix\nProvide step-by-step guidance on how to fix the bug (without giving away the full code solution)."
    )

    try:
        response = requests.post(
            ollama_url,
            json={"model": model_tag, "prompt": prompt, "stream": False},
            timeout=60,
        )
    except requests.exceptions.ConnectionError:
        return {
            "available": False,
            "error": f"Could not connect to Ollama at {QWEN_BASE_URL}.",
            "detail": "Ensure Ollama is running (`ollama serve`). Verify at /api/tags.",
        }
    except requests.exceptions.Timeout:
        return {
            "available": False,
            "error": "Ollama request timed out after 60 seconds.",
            "detail": "The local LLM took too long to generate a response. Please try again.",
        }
    except requests.RequestException as exc:
        return {"available": False, "error": f"Ollama request error: {exc}", "detail": str(exc)}

    if response.status_code == 404:
        available_models: list[str] = []
        try:
            tags_resp = requests.get(f"{QWEN_BASE_URL}/api/tags", timeout=5)
            if tags_resp.ok:
                available_models = [m.get("name", "") for m in tags_resp.json().get("models", [])]
        except Exception:
            pass
        return {
            "available": False,
            "error": f"Model '{model_tag}' not found (HTTP 404).",
            "detail": (
                f"Please pull '{model_tag}': ollama pull {model_tag}. "
                f"Available: {', '.join(available_models) if available_models else 'None found'}."
            ),
        }

    if not response.ok:
        return {
            "available": False,
            "error": f"Ollama returned HTTP {response.status_code}.",
            "detail": response.text[:1000],
        }

    try:
        payload = response.json()
        return {"available": True, "response": str(payload.get("response", "")).strip(), "model": model_tag}
    except ValueError as exc:
        return {"available": False, "error": "Ollama returned invalid JSON response.", "detail": str(exc)}


# ---------------------------------------------------------------------------
# LLM feedback (from app/main.py)
# ---------------------------------------------------------------------------

@router.post("/feedback")
def feedback(request: FeedbackRequest) -> dict[str, Any]:
    from app.services.feedback import LLMProviderError, explain
    from app.services.localization import localize_errors
    try:
        return explain(
            request.code,
            request.verdict,
            request.diagnostic,
            static_analysis=request.static_analysis,
            learning_context=request.learning_context,
            model_predictions=request.model_predictions,
            error_location=localize_errors(request.diagnostic, request.static_analysis, []),
        )
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# ML model classification (from app/main.py)
# ---------------------------------------------------------------------------

@router.post("/classify")
def classify(request: ClassifyRequest) -> dict[str, Any]:
    from app.main import classifier
    return classifier.predict(
        request.code,
        request.compiler_message,
        request.problem_description,
        request.sample_input,
        request.sample_output,
    )


@router.post("/api/models/predict")
def predict_models(request: ClassifyRequest) -> dict[str, Any]:
    """Run ASTNN, CodeBERT, and CodeClassifier independently."""
    from app.main import astnn_model, astnn_reason, codebert_model, codebert_reason, classifier
    started = time.monotonic()

    astnn_result = (
        astnn_model.predict(
            request.code,
            request.compiler_message,
            request.problem_description,
            request.sample_input,
            request.sample_output,
        )
        if astnn_model is not None
        else {"available": False, "reason": astnn_reason}
    )
    codebert_result = (
        codebert_model.predict(
            request.code,
            request.compiler_message,
            request.problem_description,
            request.sample_input,
            request.sample_output,
        )
        if codebert_model is not None
        else {"available": False, "reason": codebert_reason}
    )
    classifier_result = classifier.predict(
        request.code,
        request.compiler_message,
        request.problem_description,
        request.sample_input,
        request.sample_output,
    )

    elapsed_ms = round((time.monotonic() - started) * 1000)
    return {
        "astnn": astnn_result,
        "codebert": codebert_result,
        "codeclassifier": classifier_result,
        "model_version": {
            "astnn": "astnn-v1" if astnn_result.get("available") else "unavailable",
            "codebert": "codebert-base-v1" if codebert_result.get("available") else "unavailable",
            "codeclassifier": "tfidf-logreg-v1" if classifier_result.get("available") else "unavailable",
        },
        "pipeline_version": "v1",
        "analysis_time_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# Learning / knowledge endpoints (from app/main.py)
# ---------------------------------------------------------------------------

@router.post("/learning/trace")
def trace_learning(request: KnowledgeTraceRequest) -> dict[str, Any]:
    from app.main import knowledge_tracer
    return knowledge_tracer.predict(
        [attempt.model_dump() for attempt in request.history],
        request.next_test_case_ids,
    )


@router.post("/misconceptions/analyze")
def analyze_misconceptions(request: MisconceptionRequest) -> dict[str, Any]:
    from app.main import misconception_detector
    return misconception_detector.analyze(
        [attempt.model_dump() for attempt in request.attempts]
    )


@router.get("/knowledge/search")
def search_knowledge(q: str, limit: int = 3) -> dict[str, Any]:
    from app.main import knowledge_base
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")
    if not 1 <= limit <= 10:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 10")
    return {"results": knowledge_base.search(q, limit)}
