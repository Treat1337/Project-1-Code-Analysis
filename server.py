import csv
import html as html_stdlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from typing import Any, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# 1. Dataset Paths & Configuration (Exact Windows Raw Strings)
# -----------------------------------------------------------------------------
ROOT_DATASET = Path(
    r"C:\Users\ADMIN\OneDrive\Máy tính\tailieu\2026.1\Project 1\project\Code_Analysis\Dataset\Project_CodeNet"
)
PROBLEM_DESCRIPTIONS = Path(
    r"C:\Users\ADMIN\OneDrive\Máy tính\tailieu\2026.1\Project 1\project\Code_Analysis\Dataset\Project_CodeNet\problem_descriptions"
)
TEST_IO_DATA = Path(
    r"C:\Users\ADMIN\OneDrive\Máy tính\tailieu\2026.1\Project 1\project\Code_Analysis\Dataset\Project_CodeNet\derived\input_output\data"
)
CODE_NET_METADATA = ROOT_DATASET / "metadata"
CODE_NET_SOURCE = ROOT_DATASET / "data"

BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = BASE_DIR / "index.html"

# -----------------------------------------------------------------------------
# 2. FastAPI Initialization & CORS Middleware
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Project_CodeNet Code Runner & AI Tutor",
    description="FastAPI backend serving Project_CodeNet dataset, real code execution, and Ollama AI feedback proxy.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# 3. Pydantic Request Models
# -----------------------------------------------------------------------------
class ApiRunRequest(BaseModel):
    problem_id: str
    language: str = "cpp"
    code: str = ""
    custom_input: str = ""
    expected_output: Optional[str] = None
    run_all: bool = False


class ApiAiRequest(BaseModel):
    problem_description: str = ""
    code: str = ""
    verdict: str = ""
    failing_input: str = ""
    actual_output: str = ""
    expected_output: str = ""
    stderr: str = ""
    language: str = "cpp"
    model: str = "qwen2.5-coder:3b-instruct-q8_0"


# -----------------------------------------------------------------------------
# 4. Helper Utilities (HTML Sanitization, Title Extraction, Boilerplate Checks)
# -----------------------------------------------------------------------------
def _valid_problem_id(problem_id: str) -> bool:
    return bool(re.fullmatch(r"p\d{5}", problem_id))


def _extract_title(source: str, fallback: str) -> str:
    match = re.search(r"<(?:h1|H1|title|TITLE)\b[^>]*>(.*?)</(?:h1|H1|title|TITLE)>", source, re.I | re.S)
    if not match:
        return fallback
    clean_title = re.sub(r"<[^>]+>", "", match.group(1))
    clean_title = html_stdlib.unescape(clean_title).strip()
    return clean_title or fallback


def _sanitize_problem_html(source: str) -> str:
    """Strips unsafe scripts, iframes, style/link overrides, inline event handlers, keeping clean math and formatting."""
    source = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", source)
    source = re.sub(r"(?is)<iframe\b[^>]*>.*?</iframe>", "", source)
    source = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", source)
    source = re.sub(r"(?is)<link\b[^>]*>", "", source)
    source = re.sub(r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]*)", "", source, flags=re.I)
    source = re.sub(r"(?is)<meta[^>]*>", "", source)
    # Strip outer html/head/body wrappers if present, keep content
    source = re.sub(r"(?is)<html[^>]*>|</html>|<head[^>]*>.*?</head>|<body[^>]*>|</body>", "", source)
    return source.strip()


def _extract_plain_text(html_source: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", html_source)
    plain = html_stdlib.unescape(re.sub(r"\s+", " ", plain)).strip()
    return plain


def _normalize_output(text: str) -> str:
    """Normalizes CRLF and trailing spaces per line for strict competitive programming comparison."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def _is_unmodified_boilerplate(code: str, language: str = "C++") -> tuple[bool, str]:
    """
    Checks if code is empty or unmodified C++ starter template.
    Returns (is_boilerplate, verdict).
    """
    if not code or not code.strip():
        return True, "Empty Output"

    clean = re.sub(r"//.*", "", code)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.S)
    clean_no_ws = re.sub(r"\s+", "", clean).lower()

    if not clean_no_ws:
        return True, "Empty Output"

    starter_signatures = {
        # C++ minimal starter signatures
        "#include<bits/stdc++.h>usingnamespacestd;intmain(){return0;}",
        "#include<bits/stdc++.h>usingnamespacestd;intmain(){}",
        "#include<bits/stdc++.h>intmain(){return0;}",
        "#include<bits/stdc++.h>intmain(){}",
        "#include<iostream>usingnamespacestd;intmain(){return0;}",
        "#include<iostream>usingnamespacestd;intmain(){}",
        "usingnamespacestd;intmain(){return0;}",
        "usingnamespacestd;intmain(){}",
        "intmain(){return0;}",
        "intmain(){}",
    }

    if clean_no_ws in starter_signatures:
        return True, "Wrong Answer"

    return False, ""


def _load_test_cases(problem_id: str) -> list[dict[str, str]]:
    """Loads input/output test case pairs from derived/input_output/data/{problem_id}/."""
    folder = TEST_IO_DATA / problem_id
    if not folder.is_dir():
        return []

    cases: list[dict[str, str]] = []

    # 1. Base input.txt & output.txt
    in_base = folder / "input.txt"
    out_base = folder / "output.txt"
    if in_base.is_file() and out_base.is_file():
        cases.append({
            "name": "Case 1",
            "stdin": in_base.read_text(encoding="utf-8", errors="replace"),
            "expected_stdout": out_base.read_text(encoding="utf-8", errors="replace"),
        })

    # 2. Numbered input/output files (e.g. input_1.txt, input_2.txt)
    numbered_inputs = sorted(folder.glob("input*.txt"))
    for in_file in numbered_inputs:
        if in_file.name == "input.txt":
            continue
        suffix = in_file.stem.removeprefix("input").lstrip("_")
        out_file = folder / f"output_{suffix}.txt"
        if not out_file.is_file():
            out_file = folder / f"output{suffix}.txt"
        if out_file.is_file():
            cases.append({
                "name": f"Case {len(cases) + 1}",
                "stdin": in_file.read_text(encoding="utf-8", errors="replace"),
                "expected_stdout": out_file.read_text(encoding="utf-8", errors="replace"),
            })

    # 3. Fallback for .in / .out pairs
    if not cases:
        for in_file in sorted(folder.glob("*.in")):
            out_file = in_file.with_suffix(".out")
            if out_file.is_file():
                cases.append({
                    "name": f"Case {len(cases) + 1}",
                    "stdin": in_file.read_text(encoding="utf-8", errors="replace"),
                    "expected_stdout": out_file.read_text(encoding="utf-8", errors="replace"),
                })

    return cases


def _load_accepted_solution(problem_id: str) -> dict[str, Any]:
    """
    Finds 1 real Accepted submission from metadata/{problem_id}.csv
    (preferring C++ or Python, or whatever language is available)
    and reads the actual source code file from data/{problem_id}/...
    """
    csv_path = CODE_NET_METADATA / f"{problem_id}.csv"
    if not csv_path.is_file():
        return {
            "available": False,
            "language": "",
            "code": "",
            "submission_id": "",
            "reason": f"Metadata file {problem_id}.csv not found",
        }

    try:
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        return {
            "available": False,
            "language": "",
            "code": "",
            "submission_id": "",
            "reason": f"Failed to read metadata: {exc}",
        }

    accepted = [
        row for row in rows
        if str(row.get("status", "")).strip().lower() in {"accepted", "ac"}
        and (
            "c++" in str(row.get("language", "")).strip().lower()
            or "cpp" in str(row.get("language", "")).strip().lower()
            or str(row.get("filename_ext", "")).strip().lower() in {".cpp", "cpp", ".cc", "cc", ".cxx", "cxx"}
        )
    ]
    if not accepted:
        return {
            "available": False,
            "language": "C++",
            "code": "",
            "submission_id": "",
            "reason": "No accepted C++ submissions recorded in metadata.",
        }

    prob_data_dir = CODE_NET_SOURCE / problem_id
    if not prob_data_dir.is_dir():
        return {
            "available": False,
            "language": "",
            "code": "",
            "submission_id": "",
            "reason": f"Source directory data/{problem_id} does not exist",
        }

    for row in accepted:
        sub_id = str(row.get("submission_id", "")).strip()
        lang = str(row.get("language", "")).strip()
        ext = str(row.get("filename_ext", "")).strip().lstrip(".")
        if not sub_id:
            continue

        target_dir = prob_data_dir / lang
        if not target_dir.is_dir():
            # Try case-insensitive matching
            for child in prob_data_dir.iterdir():
                if child.is_dir() and child.name.lower() == lang.lower():
                    target_dir = child
                    break

        if not target_dir.is_dir():
            continue

        candidate = target_dir / f"{sub_id}.{ext or 'txt'}"
        if not candidate.is_file():
            # Try finding any file starting with submission_id
            matches = list(target_dir.glob(f"{sub_id}.*"))
            if matches:
                candidate = matches[0]

        if candidate.is_file():
            try:
                code_content = candidate.read_text(encoding="utf-8", errors="replace")
                return {
                    "available": True,
                    "language": lang,
                    "submission_id": sub_id,
                    "filename": candidate.name,
                    "code": code_content,
                    "reason": "",
                }
            except Exception:
                continue

    return {
        "available": False,
        "language": "",
        "code": "",
        "submission_id": "",
        "reason": "No actual source file found on disk for accepted submissions.",
    }


def _execute_code_single(
    problem_id: str,
    language: str,
    code: str,
    stdin_content: str,
    expected_output: str,
) -> dict[str, Any]:
    """Compiles (if C++) and executes code against stdin with a strict 3-second timeout."""
    lang = language.lower()
    started = time.monotonic()

    # Boilerplate / empty check
    is_boiler, boiler_verdict = _is_unmodified_boilerplate(code, language)
    if is_boiler:
        return {
            "verdict": boiler_verdict,
            "actual_output": "",
            "expected_output": _normalize_output(expected_output),
            "stderr": "Submission is empty or contains unmodified starter template.",
            "duration_ms": 0,
        }

    with tempfile.TemporaryDirectory(prefix="runner_codenet_", ignore_cleanup_errors=True) as temp_dir:
        temp = Path(temp_dir)

        if lang not in {"cpp", "c++", "c"}:
            return {
                "verdict": "Compilation Error",
                "actual_output": "",
                "expected_output": _normalize_output(expected_output),
                "stderr": f"Only C++ execution is supported. Received: {language}",
                "duration_ms": 0,
            }

        compiler = shutil.which("g++")
        if not compiler:
            return {
                "verdict": "Compilation Error",
                "actual_output": "",
                "expected_output": _normalize_output(expected_output),
                "stderr": "g++ compiler not found in system PATH.",
                "duration_ms": 0,
            }
        source_file = temp / "temp.cpp"
        exe_file = temp / "temp.exe"
        source_file.write_text(code, encoding="utf-8")

        try:
            compile_result = subprocess.run(
                [compiler, "-O2", str(source_file), "-o", str(exe_file)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "verdict": "Compilation Error",
                "actual_output": "",
                "expected_output": _normalize_output(expected_output),
                "stderr": f"Compilation timed out (10s): {exc}",
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

        # Execution with strict 3-second timeout
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


# -----------------------------------------------------------------------------
# 5. Core API Endpoints
# -----------------------------------------------------------------------------
@app.get("/")
def serve_index() -> FileResponse:
    """Serve index.html at root '/'."""
    if INDEX_HTML_PATH.is_file():
        return FileResponse(INDEX_HTML_PATH)
    raise HTTPException(status_code=404, detail="index.html not found on server")


@app.get("/api/problems")
@lru_cache(maxsize=1)
def api_problems() -> dict[str, Any]:
    """
    Scans available problem IDs (pXXXXX) that exist in BOTH
    problem_descriptions and derived/input_output/data.
    Returns a JSON list of problem IDs and extracted <title> or <h1> names.
    """
    if not (PROBLEM_DESCRIPTIONS.is_dir() and TEST_IO_DATA.is_dir()):
        return {"problems": []}

    available_io_ids = {p.name for p in TEST_IO_DATA.iterdir() if p.is_dir()}
    problem_list: list[dict[str, str]] = []

    for html_path in sorted(PROBLEM_DESCRIPTIONS.glob("p*.html")):
        pid = html_path.stem
        if not _valid_problem_id(pid):
            continue
        if pid not in available_io_ids:
            continue

        try:
            with open(html_path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(2048)
        except OSError:
            continue

        title = _extract_title(head, pid)
        problem_list.append({
            "problem_id": pid,
            "title": title,
        })

    return {"problems": problem_list}


@app.get("/api/problem/{problem_id}")
def api_problem_detail(problem_id: str) -> dict[str, Any]:
    """
    Reads and sanitizes raw HTML from problem_descriptions/{problem_id}.html,
    loads input/output test case pairs from derived/input_output/data/{problem_id}/,
    and retrieves 1 real Accepted submission from metadata/{problem_id}.csv.
    """
    if not _valid_problem_id(problem_id):
        raise HTTPException(status_code=400, detail="Invalid problem ID format (expected pXXXXX)")

    desc_path = PROBLEM_DESCRIPTIONS / f"{problem_id}.html"
    if not desc_path.is_file():
        raise HTTPException(status_code=404, detail=f"Problem description for {problem_id} not found")

    try:
        source_html = desc_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read problem description: {exc}")

    title = _extract_title(source_html, problem_id)
    sanitized_html = _sanitize_problem_html(source_html)
    plain_text = _extract_plain_text(sanitized_html)
    test_cases = _load_test_cases(problem_id)
    accepted_solution = _load_accepted_solution(problem_id)

    return {
        "problem_id": problem_id,
        "title": title,
        "html": sanitized_html,
        "plain_text": plain_text,
        "test_cases": test_cases,
        "accepted_solution": accepted_solution,
    }


@app.post("/api/run")
def api_run(request: ApiRunRequest) -> dict[str, Any]:
    """
    Executes user code against test cases with real subprocess execution.
    NO hardcoded or mock 'Accepted'. Validates boilerplate/starter code.
    """
    test_cases = _load_test_cases(request.problem_id) if _valid_problem_id(request.problem_id) else []

    # If run_all is requested (Submit mode)
    if request.run_all:
        if not test_cases:
            # Fallback to single run if no test cases are on disk
            return _execute_code_single(
                request.problem_id,
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
                request.problem_id,
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
        # Match against loaded test cases
        match = next((c for c in test_cases if c["stdin"].strip() == stdin_input.strip()), None)
        if match:
            expected_output = match["expected_stdout"]
        elif not stdin_input.strip():
            stdin_input = test_cases[0]["stdin"]
            expected_output = test_cases[0]["expected_stdout"]
        else:
            expected_output = test_cases[0]["expected_stdout"]

    return _execute_code_single(
        request.problem_id,
        request.language,
        request.code,
        stdin_input,
        expected_output,
    )


@app.post("/api/ai-feedback")
def api_ai_feedback(request: ApiAiRequest) -> dict[str, Any]:
    """
    Backend proxy routing Ollama calls directly to http://127.0.0.1:11434/api/generate.
    Uses model: 'qwen2.5-coder:3b-instruct-q8_0', stream: false.
    Eliminates browser CORS and HTTP 404 path errors.
    """
    ollama_url = "http://127.0.0.1:11434/api/generate"
    model_tag = "qwen2.5-coder:3b-instruct-q8_0"

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
            json={
                "model": model_tag,
                "prompt": prompt,
                "stream": False,
            },
            timeout=60,
        )
    except requests.exceptions.ConnectionError as exc:
        return {
            "available": False,
            "error": "Could not connect to Ollama at http://127.0.0.1:11434.",
            "detail": (
                "Ollama service is unreachable. Ensure Ollama is running (`ollama serve`). "
                "Verify at http://127.0.0.1:11434/api/tags."
            ),
        }
    except requests.exceptions.Timeout:
        return {
            "available": False,
            "error": "Ollama request timed out after 60 seconds.",
            "detail": "The local LLM took too long to generate a response. Please try again.",
        }
    except requests.RequestException as exc:
        return {
            "available": False,
            "error": f"Ollama request error: {exc}",
            "detail": str(exc),
        }

    if response.status_code == 404:
        # Check installed models
        available_models: list[str] = []
        try:
            tags_resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            if tags_resp.ok:
                available_models = [m.get("name", "") for m in tags_resp.json().get("models", [])]
        except Exception:
            pass

        return {
            "available": False,
            "error": f"Model '{model_tag}' not found (HTTP 404).",
            "detail": (
                f"Please pull '{model_tag}' in your terminal by running: "
                f"ollama pull {model_tag}. "
                f"Currently available models: {', '.join(available_models) if available_models else 'None found'}."
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
        return {
            "available": True,
            "response": str(payload.get("response", "")).strip(),
            "model": model_tag,
        }
    except ValueError as exc:
        return {
            "available": False,
            "error": "Ollama returned invalid JSON response.",
            "detail": str(exc),
        }


# -----------------------------------------------------------------------------
# 6. Main Runner
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI backend on http://127.0.0.1:8000 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
