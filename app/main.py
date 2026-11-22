from pathlib import Path
from typing import Any
import csv
import html as html_stdlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from html.parser import HTMLParser

import requests
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    AI_API_KEY,
    ASTNN_MODEL_DIR,
    CLASSIFIER_MODEL_PATH,
    CODEBERT_MODEL_DIR,
    DATASET_DIR,
    NEURAL_MODEL_DIR,
    QWEN_ENABLED,
    QWEN_MODEL,
)
from app.models import (
    AnalyzeRequest,
    ClassifyRequest,
    FeedbackRequest,
    KnowledgeTraceRequest,
    MisconceptionRequest,
    RunRequest,
)
from app.services.classifier import CodeClassifier
from app.services.codenet_retrieval import CodeNetSimilarityIndex
from app.services.feedback import LLMProviderError, explain, load_knowledge_base
from app.services.knowledge_tracing import TestCaseInformedKnowledgeTracer
from app.services.localization import localize_errors
from app.services.misconception_detection import MisconceptionPatternDetector
from app.services.retrieval import KnowledgeBase
from app.services.runner import (
    RunnerFailure,
    RunnerUnavailable,
    analyze_cpp,
    run_cpp,
    runner_status,
)


app = FastAPI(
    title="AI Code Analysis for Programming Education",
    description="Analyze C++ against test cases and provide evidence-grounded learning feedback.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CODE_NET_ROOT = Path(
    r"C:\Users\ADMIN\OneDrive\Máy tính\tailieu\2026.1\Project 1\project\Code_Analysis\Dataset\Project_CodeNet"
)
PROBLEM_DESCRIPTIONS = CODE_NET_ROOT / "problem_descriptions"
TEST_IO_DATA = CODE_NET_ROOT / "derived" / "input_output" / "data"
CODE_NET_METADATA = CODE_NET_ROOT / "metadata"
CODE_NET_SOURCE = CODE_NET_ROOT / "data"


class ApiRunRequest(BaseModel):
    problem_id: str
    language: str = "cpp"
    code: str = ""
    custom_input: str = ""


class ApiAiRequest(BaseModel):
    problem_description: str = ""
    code: str = ""
    verdict: str = ""
    failing_input: str = ""
    actual_output: str = ""
    expected_output: str = ""
    model: str = "qwen2.5-coder:3b-instruct-q8_0"
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


def _valid_problem_id(problem_id: str) -> bool:
    return bool(re.fullmatch(r"p\d{5}", problem_id))


def _extract_title(source: str, fallback: str) -> str:
    match = re.search(r"<(?:h1|H1)\b[^>]*>(.*?)</(?:h1|H1)>", source, re.I | re.S)
    if not match:
        return fallback
    title = re.sub(r"<[^>]+>", "", match.group(1))
    return html_stdlib.unescape(title).strip() or fallback


def _sanitize_problem_html(source: str) -> str:
    source = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", source)
    source = re.sub(r"(?is)<iframe\b[^>]*>.*?</iframe>", "", source)
    source = re.sub(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\\s>]*)", "", source, flags=re.I)
    source = re.sub(r"(?is)<meta[^>]*>", "", source)
    return source


def _load_test_cases(problem_id: str) -> list[dict[str, str]]:
    folder = TEST_IO_DATA / problem_id
    if not folder.is_dir():
        return []

    cases: list[dict[str, str]] = []
    input_output = folder / "input.txt"
    output_output = folder / "output.txt"
    if input_output.is_file() and output_output.is_file():
        cases.append({
            "stdin": input_output.read_text(encoding="utf-8", errors="replace"),
            "expected_stdout": output_output.read_text(encoding="utf-8", errors="replace"),
        })

    numbered_inputs = sorted(folder.glob("input_*.txt"))
    for input_path in numbered_inputs:
        suffix = input_path.stem.removeprefix("input")
        suffix = suffix[1:] if suffix.startswith("_") else suffix
        output_path = folder / f"output_{suffix}.txt"
        if not output_path.is_file():
            output_path = folder / f"output{suffix}.txt"
        if output_path.is_file():
            cases.append({
                "stdin": input_path.read_text(encoding="utf-8", errors="replace"),
                "expected_stdout": output_path.read_text(encoding="utf-8", errors="replace"),
            })
    return cases


def _load_accepted_solution(problem_id: str) -> dict[str, str]:
    metadata_path = CODE_NET_METADATA / f"{problem_id}.csv"
    if not metadata_path.is_file():
        return {"available": False, "language": "", "code": "", "submission_id": "", "reason": "Accepted submission metadata not found"}

    with metadata_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.DictReader(handle))

    accepted = [
        row for row in rows
        if str(row.get("status", "")).strip().lower() in {"accepted", "ac"}
    ]
    accepted.sort(key=lambda row: 0 if str(row.get("language", "")).strip().lower() in {"c++", "cpp"} else 1)

    for row in accepted:
        submission_id = str(row.get("submission_id", "")).strip()
        language = str(row.get("language", "")).strip()
        filename_ext = str(row.get("filename_ext", "")).strip().lstrip(".")
        if not submission_id:
            continue
        language_folder = "C++" if language.lower() in {"c++", "cpp"} else language
        source_path = CODE_NET_SOURCE / problem_id / language_folder / f"{submission_id}.{filename_ext or 'txt'}"
        if not source_path.is_file():
            continue
        code = source_path.read_text(encoding="utf-8", errors="replace")
        return {
            "available": True,
            "language": "C++" if language.lower() in {"c++", "cpp"} else language,
            "code": code,
            "submission_id": submission_id,
            "reason": "",
        }
    return {"available": False, "language": "", "code": "", "submission_id": "", "reason": "No accepted source file found"}


@app.get("/api/problems")
@lru_cache(maxsize=1)
def api_problem_list() -> dict[str, object]:
    problem_ids: list[dict[str, str]] = []
    if PROBLEM_DESCRIPTIONS.is_dir():
        for description_path in sorted(PROBLEM_DESCRIPTIONS.glob("p*.html")):
            problem_id = description_path.stem
            if not _valid_problem_id(problem_id):
                continue
            if not (TEST_IO_DATA / problem_id).is_dir():
                continue
            source = description_path.read_text(encoding="utf-8", errors="replace")
            problem_ids.append({
                "problem_id": problem_id,
                "title": _extract_title(source, problem_id),
            })
    return {"problems": problem_ids}


@app.get("/api/problem/{problem_id}")
def api_problem_detail(problem_id: str) -> dict[str, object]:
    if not _valid_problem_id(problem_id):
        raise HTTPException(status_code=404, detail="Invalid problem ID")
    description_path = PROBLEM_DESCRIPTIONS / f"{problem_id}.html"
    if not description_path.is_file():
        raise HTTPException(status_code=404, detail="Problem description not found")
    source = description_path.read_text(encoding="utf-8", errors="replace")
    plain = re.sub(r"<[^>]+>", " ", source)
    plain = html_stdlib.unescape(re.sub(r"\s+", " ", plain)).strip()
    return {
        "problem_id": problem_id,
        "title": _extract_title(source, problem_id),
        "html": _sanitize_problem_html(source),
        "plain_text": plain,
        "test_cases": _load_test_cases(problem_id),
        "accepted_solution": _load_accepted_solution(problem_id),
    }


def _normalize_output(value: str) -> str:
    return value.strip()


def _boilerplate_only(code: str) -> bool:
    normalized = re.sub(r"\s+", "", code).lower()
    if not normalized:
        return True
    cpp_patterns = (
        "#include<bits/stdc++.h>",
        "#include<iostream>",
        "intmain(){}",
        "intmain(){return0;}",
    )
    python_patterns = ("pass", "defsolve(self):pass")
    return all(
        pattern not in normalized
        for pattern in ()
    ) and (
        normalized in cpp_patterns
        or normalized in python_patterns
        or len(normalized) < 20
    )


@app.post("/api/run")
def api_run(request: ApiRunRequest) -> dict[str, object]:
    if not request.code.strip():
        return {
            "verdict": "Empty Output",
            "actual_output": "",
            "expected_output": "",
            "stderr": "Code source is empty.",
        }
    if _boilerplate_only(request.code):
        return {
            "verdict": "Wrong Answer",
            "actual_output": "",
            "expected_output": "",
            "stderr": "Submit an implementation instead of unchanged starter template.",
        }

    test_cases = _load_test_cases(request.problem_id) if _valid_problem_id(request.problem_id) else []
    expected_output = ""
    if test_cases:
        exact = next(
            (case for case in test_cases if case["stdin"].strip() == request.custom_input.strip()),
            None,
        )
        expected_output = (exact or test_cases[0])["expected_stdout"]

    language = request.language.lower()
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="code-run-", ignore_cleanup_errors=True) as temp_dir:
            temp = Path(temp_dir)
            if language in {"cpp", "c++"}:
                compiler = shutil.which("g++")
                if not compiler:
                    return {
                        "verdict": "Compilation Error",
                        "actual_output": "",
                        "expected_output": expected_output,
                        "stderr": "g++ is not installed or not available in PATH.",
                    }
                source = temp / "main.cpp"
                executable = temp / "main.exe"
                source.write_text(request.code, encoding="utf-8")
                compile_result = subprocess.run(
                    [compiler, "-std=c++17", "-O2", str(source), "-o", str(executable)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if compile_result.returncode != 0:
                    return {
                        "verdict": "Compilation Error",
                        "actual_output": "",
                        "expected_output": expected_output,
                        "stderr": compile_result.stderr[-8000:],
                    }
                command = [str(executable)]
            elif language in {"python", "python3", "py"}:
                source = temp / "main.py"
                source.write_text(request.code, encoding="utf-8")
                command = [sys.executable, str(source)]
            else:
                return {
                    "verdict": "Compilation Error",
                    "actual_output": "",
                    "expected_output": expected_output,
                    "stderr": f"Unsupported language: {request.language}",
                }

            try:
                run_result = subprocess.run(
                    command,
                    input=request.custom_input,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return {
                    "verdict": "Time Limit Exceeded",
                    "actual_output": "",
                    "expected_output": expected_output,
                    "stderr": str(exc),
                }
    except subprocess.TimeoutExpired as exc:
        return {
            "verdict": "Time Limit Exceeded",
            "actual_output": "",
            "expected_output": expected_output,
            "stderr": str(exc),
        }
    except OSError as exc:
        return {
            "verdict": "Runtime Error",
            "actual_output": "",
            "expected_output": expected_output,
            "stderr": str(exc),
        }

    actual_output = _normalize_output(run_result.stdout)
    expected_output = _normalize_output(expected_output)
    if run_result.returncode != 0:
        verdict = "Runtime Error"
    elif actual_output == expected_output:
        verdict = "Accepted"
    else:
        verdict = "Wrong Answer"
    return {
        "verdict": verdict,
        "actual_output": actual_output,
        "expected_output": expected_output,
        "stderr": run_result.stderr[-8000:],
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


@app.post("/api/ai-feedback")
def api_ai_feedback(request: ApiAiRequest) -> dict[str, object]:
    prompt = (
        "You are a concise programming tutor. Explain only why the submitted code failed "
        "and suggest a useful fix without revealing the complete solution.\n\n"
        f"Problem: {request.problem_description}\n"
        f"Verdict: {request.verdict}\n"
        f"Failing Input:\n{request.failing_input}\n"
        f"User Output:\n{request.actual_output}\n"
        f"Expected Output:\n{request.expected_output}\n"
        f"User Code:\n{request.code}\n"
    )
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "qwen2.5-coder:3b-instruct-q8_0",
                "prompt": prompt,
                "stream": False,
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        return {
            "available": False,
            "error": (
                "Could not connect to Ollama at http://127.0.0.1:11434. "
                "Check http://127.0.0.1:11434/api/tags and start Ollama with "
                'OLLAMA_ORIGINS="*" ollama serve.'
            ),
            "detail": str(exc),
        }
    if response.status_code == 404:
        return {
            "available": False,
            "error": "Ollama model not found (HTTP 404).",
            "detail": (
                "Pull and verify qwen2.5-coder:3b-instruct-q8_0 with "
                "ollama pull qwen2.5-coder:3b-instruct-q8_0 "
                "and check /api/tags."
            ),
        }
    if not response.ok:
        return {
            "available": False,
            "error": f"Ollama returned HTTP {response.status_code}.",
            "detail": response.text[:2000],
        }
    try:
        payload = response.json()
    except ValueError:
        return {"available": False, "error": "Ollama returned invalid JSON.", "detail": response.text[:2000]}
    return {
        "available": True,
        "response": str(payload.get("response", "")).strip(),
    }


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
    error_location = localize_errors(
        diagnostic,
        static_analysis,
        result.get("tests", []),
    )
    predictions = _model_predictions(request.code, diagnostic)
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
            static_analysis=static_analysis,
            model_predictions=predictions,
            error_location=error_location,
        )
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        **result,
        "feedback": feedback,
        "ml_prediction": predictions,
        "code_retrieval": code_retrieval,
        "error_localization": error_location,
    }


@app.post("/run")
def run_code(request: RunRequest) -> dict[str, object]:
    try:
        return run_cpp(request.code, request.stdin)
    except RunnerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RunnerFailure as exc:
        raise HTTPException(status_code=502, detail=f"Sandbox execution failed: {exc}") from exc


@app.post("/feedback")
def feedback(request: FeedbackRequest) -> dict[str, object]:
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


@app.post("/classify")
def classify(request: ClassifyRequest) -> dict[str, object]:
    return classifier.predict(
        request.code,
        request.compiler_message,
        request.problem_description,
        request.sample_input,
        request.sample_output,
    )


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
