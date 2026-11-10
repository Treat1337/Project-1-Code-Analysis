from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.config import AI_API_KEY, CLASSIFIER_MODEL_PATH, DATASET_DIR, NEURAL_MODEL_DIR
from app.models import (
    AnalyzeRequest,
    ClassifyRequest,
    FeedbackRequest,
    KnowledgeTraceRequest,
    MisconceptionRequest,
)
from app.services.classifier import CodeClassifier
from app.services.codenet_retrieval import CodeNetSimilarityIndex
from app.services.feedback import LLMProviderError, explain, load_knowledge_base
from app.services.knowledge_tracing import TestCaseInformedKnowledgeTracer
from app.services.localization import localize_errors
from app.services.misconception_detection import MisconceptionPatternDetector
from app.services.retrieval import KnowledgeBase
from app.services.runner import RunnerFailure, RunnerUnavailable, analyze_cpp, runner_status


app = FastAPI(
    title="AI Code Analysis for Programming Education",
    description="Analyze C++ against test cases and provide evidence-grounded learning feedback.",
    version="0.1.0",
)
knowledge_base: KnowledgeBase = load_knowledge_base()
classifier = CodeClassifier(
    DATASET_DIR / "labeled_examples.csv",
    Path(NEURAL_MODEL_DIR) if NEURAL_MODEL_DIR else None,
    CLASSIFIER_MODEL_PATH,
)
similarity_index = CodeNetSimilarityIndex(DATASET_DIR)
knowledge_tracer = TestCaseInformedKnowledgeTracer()
misconception_detector = MisconceptionPatternDetector()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "runner": runner_status(),
        "llm_enabled": bool(AI_API_KEY),
        "classifier": {
            "available": classifier.available,
            "reason": classifier.reason,
        },
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, object]:
    try:
        result = analyze_cpp(
            request.code,
            [test.model_dump() for test in request.test_cases],
        )
    except RunnerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RunnerFailure as exc:
        raise HTTPException(status_code=502, detail=f"Sandbox execution failed: {exc}") from exc

    diagnostic = result.get("diagnostic", "")
    static_analysis = result.get("static_analysis", "")
    code_retrieval: dict[str, object] = {
        "available": False,
        "reason": "A problem_id is required for problem-scoped code retrieval",
    }
    if request.problem_id:
        try:
            code_retrieval = similarity_index.search(
                request.problem_id,
                request.code,
                request.similarity_limit,
            )
        except FileNotFoundError as exc:
            code_retrieval = {
                "available": False,
                "problem_id": request.problem_id,
                "reason": str(exc),
            }
    try:
        feedback = explain(
            request.code,
            result["verdict"],
            diagnostic,
            knowledge_base,
            static_analysis=static_analysis,
        )
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        **result,
        "feedback": feedback,
        "ml_prediction": classifier.predict(request.code, diagnostic),
        "code_retrieval": code_retrieval,
        "error_localization": localize_errors(
            diagnostic,
            static_analysis,
            result.get("tests", []),
        ),
    }


@app.post("/feedback")
def feedback(request: FeedbackRequest) -> dict[str, object]:
    try:
        return explain(
            request.code,
            request.verdict,
            request.diagnostic,
            knowledge_base,
            static_analysis=request.static_analysis,
            learning_context=request.learning_context,
        )
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/classify")
def classify(request: ClassifyRequest) -> dict[str, object]:
    return classifier.predict(request.code, request.compiler_message)


@app.post("/learning/trace")
def trace_learning(request: KnowledgeTraceRequest) -> dict[str, object]:
    return knowledge_tracer.predict(
        [attempt.model_dump() for attempt in request.history],
        request.next_test_case_ids,
    )


@app.post("/misconceptions/analyze")
def analyze_misconceptions(request: MisconceptionRequest) -> dict[str, object]:
    return misconception_detector.analyze(
        [attempt.model_dump() for attempt in request.attempts]
    )


@app.get("/knowledge/search")
def search_knowledge(q: str, limit: int = 3) -> dict[str, object]:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")
    if not 1 <= limit <= 10:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 10")
    return {"results": knowledge_base.search(q, limit)}
