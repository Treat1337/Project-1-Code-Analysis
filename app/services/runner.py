"""
app/services/runner.py — Backward-compatible re-export.

Logic đã chuyển vào app/services/cpp_runner.py.
File này giữ nguyên để không làm hỏng import cũ.
"""
from app.services.cpp_runner import (
    RunnerFailure,
    RunnerUnavailable,
    _docker_command,
    analyze_cpp,
    run_cpp,
    runner_status,
)

__all__ = [
    "RunnerFailure",
    "RunnerUnavailable",
    "_docker_command",
    "analyze_cpp",
    "run_cpp",
    "runner_status",
]
