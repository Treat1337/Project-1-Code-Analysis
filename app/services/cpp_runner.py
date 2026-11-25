"""
app/services/cpp_runner.py — Docker sandbox runner for C++ code.

Renamed from app/services/runner.py with no logic changes.
Backward-compatible re-export kept in runner.py.
"""
# This file is a canonical copy — imported directly by api/judge.py.
# runner.py still re-exports everything for backward compatibility.

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.config import (
    CASE_TIMEOUT_SECONDS,
    COMPILE_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    RUNNER_IMAGE,
    TEMP_DIR,
)


class RunnerUnavailable(RuntimeError):
    pass


class RunnerFailure(RuntimeError):
    pass


def _docker_command() -> str | None:
    import sys
    runner_mod = sys.modules.get("app.services.runner")
    if runner_mod and hasattr(runner_mod, "_docker_command") and runner_mod._docker_command is not _docker_command:
        return runner_mod._docker_command()
    return shutil.which("docker")


def runner_status() -> dict[str, Any]:
    docker = _docker_command()
    if docker is None:
        return {"available": False, "reason": "Docker CLI is not installed"}
    try:
        result = subprocess.run(
            [docker, "image", "inspect", RUNNER_IMAGE],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": f"Could not inspect Docker image: {exc}"}
    if result.returncode:
        return {
            "available": False,
            "reason": f"Runner image '{RUNNER_IMAGE}' is not available; build it using the README",
        }
    return {"available": True, "image": RUNNER_IMAGE}


def analyze_cpp(code: str, test_cases: list[dict[str, str]]) -> dict[str, Any]:
    docker = _docker_command()
    if docker is None:
        raise RunnerUnavailable("Docker is not installed; submitted code was not executed")

    status = runner_status()
    if not status["available"]:
        raise RunnerUnavailable(status["reason"])

    with tempfile.TemporaryDirectory(prefix="code-analysis-", dir=str(TEMP_DIR)) as temp_dir:
        source_path = Path(temp_dir) / "main.cpp"
        source_path.write_text(code, encoding="utf-8")
        try:
            os.chmod(source_path, 0o644)
        except OSError:
            pass

        request = {
            "source": "/input/main.cpp",
            "test_cases": test_cases,
            "case_timeout": CASE_TIMEOUT_SECONDS,
            "compile_timeout": COMPILE_TIMEOUT_SECONDS,
            "max_output_bytes": MAX_OUTPUT_BYTES,
        }
        container_name = f"code-analysis-{uuid.uuid4().hex}"
        command = [
            docker, "run", "--rm", "-i",
            "--name", container_name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=512m",
            "--memory-swap=512m",
            "--cpus=0.5",
            "--user=65534:65534",
            "--tmpfs=/tmp:rw,nosuid,nodev,exec,size=64m",
            "--mount", f"type=bind,source={temp_dir},target=/input,readonly",
            RUNNER_IMAGE,
        ]
        wall_timeout = COMPILE_TIMEOUT_SECONDS + (CASE_TIMEOUT_SECONDS + 1) * len(test_cases) + 5
        try:
            result = subprocess.run(
                command,
                input=json.dumps(request).encode("utf-8"),
                capture_output=True,
                timeout=wall_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            try:
                cleanup = subprocess.run(
                    [docker, "rm", "--force", container_name],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as cleanup_exc:
                raise RunnerFailure(
                    f"Docker runner exceeded wall-clock limit; container cleanup failed: {cleanup_exc}"
                ) from exc
            cleanup_message = (cleanup.stdout + cleanup.stderr).decode("utf-8", errors="replace")
            if cleanup.returncode and "no such container" not in cleanup_message.lower():
                raise RunnerFailure(
                    "Docker runner exceeded wall-clock limit; "
                    f"container cleanup failed: {cleanup_message.strip()}"
                ) from exc
            raise RunnerFailure("Docker runner exceeded its wall-clock limit") from exc
        except OSError as exc:
            raise RunnerFailure(f"Could not start Docker runner: {exc}") from exc

    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()[-2000:]
        message = message or f"Docker exited with status {result.returncode}"
        raise RunnerFailure(message)
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerFailure("Runner returned an invalid response") from exc
    if not isinstance(response, dict) or "verdict" not in response:
        raise RunnerFailure("Runner response is missing its verdict")
    return response


def run_cpp(code: str, stdin: str = "") -> dict[str, Any]:
    result = analyze_cpp(code, [{"stdin": stdin, "expected_stdout": ""}])
    tests = result.get("tests", [])
    test = tests[0] if tests else {}
    return {
        "verdict": result.get("verdict"),
        "stdout": test.get("stdout", ""),
        "stderr": test.get("stderr", "") or result.get("diagnostic", ""),
        "duration_ms": result.get("duration_ms"),
        "diagnostic": result.get("diagnostic", ""),
    }
