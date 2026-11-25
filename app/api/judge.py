"""
app/api/judge.py — Code execution endpoints.

Extracted from server.py. Preserves:
  POST /api/run  (single run & submit/run_all modes)

Also preserves from app/main.py:
  POST /analyze   (Docker sandbox runner)
  POST /run       (Docker sandbox run)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from app.config import TEMP_DIR
from app.schemas.schemas import AnalyzeRequest, ApiRunRequest, RunRequest
from app.services.dataset_loader import load_test_cases, valid_problem_id
from app.services.cpp_runner import (
    RunnerFailure,
    RunnerUnavailable,
    analyze_cpp,
    run_cpp,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers (extracted from server.py, logic unchanged)
# ---------------------------------------------------------------------------

def _normalize_output(text: str) -> str:
    if not text:
        return ""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def _is_unmodified_boilerplate(code: str, language: str = "C++") -> tuple[bool, str]:
    if not code or not code.strip():
        return True, "Empty Output"

    lang = language.lower()
    if lang in {"cpp", "c++", "c"}:
        clean = re.sub(r"//.*", "", code)
        clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.S)
    else:
        clean = re.sub(r"#.*", "", code)
        clean = re.sub(r'""".*?"""', "", clean, flags=re.S)
        clean = re.sub(r"'''.*?'''", "", clean, flags=re.S)

    clean_no_ws = re.sub(r"\s+", "", clean).lower()
    if not clean_no_ws:
        return True, "Empty Output"

    starter_signatures = {
        "#include<iostream>usingnamespacestd;intmain(){return0;}",
        "#include<iostream>usingnamespacestd;intmain(){}",
        "#include<bits/stdc++.h>usingnamespacestd;intmain(){return0;}",
        "#include<bits/stdc++.h>intmain(){return0;}",
        "#include<bits/stdc++.h>intmain(){}",
        "usingnamespacestd;intmain(){return0;}",
        "usingnamespacestd;intmain(){}",
        "intmain(){return0;}",
        "intmain(){}",
        'importsysdefmain():passif__name__=="__main__":main()',
        "importsysdefmain():passif__name__=='__main__':main()",
        'defmain():passif__name__=="__main__":main()',
        "defmain():passif__name__=='__main__':main()",
        "defmain():pass",
        "pass",
    }
    if clean_no_ws in starter_signatures:
        return True, "Wrong Answer"
    return False, ""


def _execute_code_single(
    language: str,
    code: str,
    stdin_content: str,
    expected_output: str,
) -> dict[str, Any]:
    """Compile (if C++) and execute code with a 3-second timeout."""
    lang = language.lower()
    started = time.monotonic()

    is_boiler, boiler_verdict = _is_unmodified_boilerplate(code, language)
    if is_boiler:
        return {
            "verdict": boiler_verdict,
            "actual_output": "",
            "expected_output": _normalize_output(expected_output),
            "stderr": "Submission is empty or contains unmodified starter template.",
            "duration_ms": 0,
        }

    with tempfile.TemporaryDirectory(prefix="runner_codenet_", dir=str(TEMP_DIR), ignore_cleanup_errors=True) as temp_dir:
        temp = Path(temp_dir)

        if lang not in {"cpp", "c++", "c", "python", "python3", "py"}:
            return {
                "verdict": "Compilation Error",
                "actual_output": "",
                "expected_output": _normalize_output(expected_output),
                "stderr": f"Unsupported language: {language}",
                "duration_ms": 0,
            }

        if lang in {"cpp", "c++", "c"}:
            compiler = shutil.which("g++")
            if not compiler:
                return {
                    "verdict": "Compilation Error",
                    "actual_output": "",
                    "expected_output": _normalize_output(expected_output),
                    "stderr": "g++ compiler not found in system PATH.",
                    "duration_ms": 0,
                }
            source_file = temp / "main.cpp"
            exe_file = temp / "main.exe"
            source_file.write_text(code, encoding="utf-8")

            try:
                compile_result = subprocess.run(
                    [compiler, "-std=c++17", "-O2", str(source_file), "-o", str(exe_file)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return {
                    "verdict": "Compilation Error",
                    "actual_output": "",
                    "expected_output": _normalize_output(expected_output),
                    "stderr": f"Compilation timed out: {exc}",
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }

            if compile_result.returncode != 0:
                return {
                    "verdict": "Compilation Error",
                    "actual_output": "",
                    "expected_output": _normalize_output(expected_output),
                    "stderr": compile_result.stderr[-4000:],
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            command = [str(exe_file)]
        else:
            source_file = temp / "main.py"
            source_file.write_text(code, encoding="utf-8")
            command = [sys.executable, str(source_file)]

        exec_start = time.monotonic()
        try:
            run_result = subprocess.run(
                command,
                input=stdin_content,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "verdict": "Time Limit Exceeded",
                "actual_output": "",
                "expected_output": _normalize_output(expected_output),
                "stderr": "Time Limit Exceeded: Process exceeded 3.0 seconds.",
                "duration_ms": 3000,
            }
        except Exception as exc:
            return {
                "verdict": "Runtime Error",
                "actual_output": "",
                "expected_output": _normalize_output(expected_output),
                "stderr": f"OS execution error: {exc}",
                "duration_ms": round((time.monotonic() - exec_start) * 1000),
            }

    duration_ms = round((time.monotonic() - exec_start) * 1000)
    actual_norm = _normalize_output(run_result.stdout)
    expected_norm = _normalize_output(expected_output)

    if run_result.returncode != 0:
        verdict = "Runtime Error"
    elif actual_norm == expected_norm:
        verdict = "Accepted"
    else:
        verdict = "Wrong Answer"

    return {
        "verdict": verdict,
        "actual_output": actual_norm,
        "expected_output": expected_norm,
        "stderr": run_result.stderr[-4000:],
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/run")
def api_run(request: ApiRunRequest) -> dict[str, Any]:
    """
    Execute user code against test cases (single run or run_all/submit mode).
    Preserved from server.py — no logic changes.
    """
    test_cases = load_test_cases(request.problem_id) if valid_problem_id(request.problem_id) else []

    if request.run_all:
        if not test_cases:
            return _execute_code_single(
                request.language,
                request.code,
                request.custom_input,
                request.expected_output or "",
            )

        overall_verdict = "Accepted"
        total_duration = 0
        tests_summary: list[dict[str, Any]] = []
        failing_case: Optional[dict[str, Any]] = None

        for idx, case in enumerate(test_cases, start=1):
            res = _execute_code_single(
                request.language,
                request.code,
                case["stdin"],
                case["expected_stdout"],
            )
            total_duration += res["duration_ms"]
            case_verdict = res["verdict"]

            tests_summary.append({
                "case": idx,
                "name": case.get("name", f"Case {idx}"),
                "status": "PASSED" if case_verdict == "Accepted" else case_verdict,
                "stdin": case["stdin"],
                "expected_stdout": res["expected_output"],
                "actual_stdout": res["actual_output"],
                "stderr": res["stderr"],
                "duration_ms": res["duration_ms"],
            })

            if case_verdict != "Accepted" and overall_verdict == "Accepted":
                overall_verdict = case_verdict
                failing_case = res
                failing_case["failing_input"] = case["stdin"]

        return {
            "verdict": overall_verdict,
            "actual_output": failing_case["actual_output"] if failing_case else (tests_summary[0]["actual_stdout"] if tests_summary else ""),
            "expected_output": failing_case["expected_output"] if failing_case else (tests_summary[0]["expected_stdout"] if tests_summary else ""),
            "failing_input": failing_case.get("failing_input", "") if failing_case else "",
            "stderr": failing_case["stderr"] if failing_case else "",
            "duration_ms": total_duration,
            "tests": tests_summary,
            "passed_count": sum(1 for t in tests_summary if t["status"] == "PASSED"),
            "total_count": len(tests_summary),
        }

    # Single test execution (Run button)
    expected_output = request.expected_output or ""
    stdin_input = request.custom_input

    if not expected_output and test_cases:
        match = next((c for c in test_cases if c["stdin"].strip() == stdin_input.strip()), None)
        if match:
            expected_output = match["expected_stdout"]
        elif not stdin_input.strip():
            stdin_input = test_cases[0]["stdin"]
            expected_output = test_cases[0]["expected_stdout"]
        else:
            expected_output = test_cases[0]["expected_stdout"]

    return _execute_code_single(request.language, request.code, stdin_input, expected_output)


@router.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    """Full analysis via Docker sandbox runner (from app/main.py)."""
    from app.services.localization import localize_errors
    from app.services.codenet_retrieval import CodeNetSimilarityIndex
    from app.services.feedback import LLMProviderError, explain
    from app.config import DATASET_DIR

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

    # Lazy import to avoid circular
    from app.main import _model_predictions, similarity_index
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


@router.post("/run")
def run_code(request: RunRequest) -> dict[str, Any]:
    """Run code in Docker sandbox (from app/main.py)."""
    try:
        return run_cpp(request.code, request.stdin)
    except RunnerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RunnerFailure as exc:
        raise HTTPException(status_code=502, detail=f"Sandbox execution failed: {exc}") from exc
