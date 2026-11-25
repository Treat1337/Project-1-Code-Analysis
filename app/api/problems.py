"""
app/api/problems.py — API endpoints for problem listing and details.

Extracted from server.py. Preserves:
  GET /api/problems
  GET /api/problem/{problem_id}

No business logic here — delegates to app.services.dataset_loader.
"""
from __future__ import annotations

import html as html_stdlib
import re
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import (
    CODE_NET_METADATA,
    CODE_NET_SOURCE,
    PROBLEM_DESCRIPTIONS,
    TEST_IO_DATA,
)
from app.services.dataset_loader import (
    load_accepted_solution,
    load_test_cases,
    sanitize_problem_html,
    extract_title,
    valid_problem_id,
)

router = APIRouter()


@router.get("/api/problems")
@lru_cache(maxsize=1)
def api_problem_list() -> dict[str, object]:
    """List all problems that have both a description and test I/O data."""
    if not (PROBLEM_DESCRIPTIONS.is_dir() and TEST_IO_DATA.is_dir()):
        return {"problems": []}

    try:
        available_io_ids = {p.name for p in TEST_IO_DATA.iterdir() if p.is_dir()}
    except OSError:
        available_io_ids = set()

    problem_ids: list[dict[str, str]] = []
    for description_path in sorted(PROBLEM_DESCRIPTIONS.glob("p*.html")):
        problem_id = description_path.stem
        if not valid_problem_id(problem_id):
            continue
        if problem_id not in available_io_ids:
            continue
        try:
            with open(description_path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(2048)
            title = extract_title(head, problem_id)
        except OSError:
            title = problem_id

        problem_ids.append({
            "problem_id": problem_id,
            "title": title,
        })
    return {"problems": problem_ids}


@router.get("/api/problem/{problem_id}")
def api_problem_detail(problem_id: str) -> dict[str, Any]:
    """Return problem description HTML, test cases, and an accepted solution."""
    if not valid_problem_id(problem_id):
        raise HTTPException(status_code=400, detail="Invalid problem ID format (expected pXXXXX)")

    desc_path = PROBLEM_DESCRIPTIONS / f"{problem_id}.html"
    if not desc_path.is_file():
        raise HTTPException(status_code=404, detail=f"Problem description for {problem_id} not found")

    try:
        source_html = desc_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read problem description: {exc}")

    title = extract_title(source_html, problem_id)
    sanitized_html = sanitize_problem_html(source_html)
    plain = re.sub(r"<[^>]+>", " ", sanitized_html)
    plain = html_stdlib.unescape(re.sub(r"\s+", " ", plain)).strip()
    test_cases = load_test_cases(problem_id)
    accepted_solution = load_accepted_solution(problem_id)

    return {
        "problem_id": problem_id,
        "title": title,
        "html": sanitized_html,
        "plain_text": plain,
        "test_cases": test_cases,
        "accepted_solution": accepted_solution,
    }
