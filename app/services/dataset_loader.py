"""
app/services/dataset_loader.py — Dataset utilities for CodeNet.

Merged logic from:
  - server.py helpers (_load_test_cases, _load_accepted_solution,
    _valid_problem_id, _extract_title, _sanitize_problem_html)
  - app/services/problem_catalog.py (load_test_cases, load_accepted_solution)

Uses paths from app.config — no hardcoded absolute paths.
Logic is preserved exactly from both source files; server.py variant
is used as the more complete implementation.
"""
from __future__ import annotations

import csv
import html as html_stdlib
import re
from pathlib import Path
from typing import Any

from app.config import (
    CODE_NET_METADATA,
    CODE_NET_SOURCE,
    PROBLEM_DESCRIPTIONS,
    TEST_IO_DATA,
)


# ---------------------------------------------------------------------------
# Problem ID validation
# ---------------------------------------------------------------------------

def valid_problem_id(problem_id: str) -> bool:
    return bool(re.fullmatch(r"p\d{5}", problem_id))


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def extract_title(source: str, fallback: str) -> str:
    match = re.search(
        r"<(?:h1|H1|title|TITLE)\b[^>]*>(.*?)</(?:h1|H1|title|TITLE)>",
        source,
        re.I | re.S,
    )
    if not match:
        return fallback
    clean_title = re.sub(r"<[^>]+>", "", match.group(1))
    clean_title = html_stdlib.unescape(clean_title).strip()
    return clean_title or fallback


def sanitize_problem_html(source: str) -> str:
    """Strip unsafe scripts, iframes, inline event handlers, keeping clean math and formatting."""
    source = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", source)
    source = re.sub(r"(?is)<iframe\b[^>]*>.*?</iframe>", "", source)
    source = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", source)
    source = re.sub(r"(?is)<link\b[^>]*>", "", source)
    source = re.sub(r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]*)", "", source, flags=re.I)
    source = re.sub(r"(?is)<meta[^>]*>", "", source)
    source = re.sub(r"(?is)<html[^>]*>|</html>|<head[^>]*>.*?</head>|<body[^>]*>|</body>", "", source)
    return source.strip()


# ---------------------------------------------------------------------------
# Test cases loader
# ---------------------------------------------------------------------------

def load_test_cases(problem_id: str) -> list[dict[str, str]]:
    """
    Load input/output test case pairs from:
      derived/input_output/data/{problem_id}/
    Returns list of {name, stdin, expected_stdout}.
    """
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

    # 2. Numbered pairs (input_1.txt, input_2.txt, ...)
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


# ---------------------------------------------------------------------------
# Accepted solution loader
# ---------------------------------------------------------------------------

def load_accepted_solution(problem_id: str) -> dict[str, Any]:
    """
    Find one real Accepted C++ submission from metadata/{problem_id}.csv
    and return the source code.
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
    ]
    # Prefer C++
    accepted.sort(
        key=lambda row: 0 if str(row.get("language", "")).strip().lower() in {"c++", "cpp"} else 1
    )

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
            for child in prob_data_dir.iterdir():
                if child.is_dir() and child.name.lower() == lang.lower():
                    target_dir = child
                    break

        if not target_dir.is_dir():
            continue

        candidate = target_dir / f"{sub_id}.{ext or 'txt'}"
        if not candidate.is_file():
            matches = list(target_dir.glob(f"{sub_id}.*"))
            if matches:
                candidate = matches[0]

        if candidate.is_file():
            try:
                return {
                    "available": True,
                    "language": lang,
                    "submission_id": sub_id,
                    "filename": candidate.name,
                    "code": candidate.read_text(encoding="utf-8", errors="replace"),
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
