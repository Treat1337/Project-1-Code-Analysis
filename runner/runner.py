import json
import os
import signal
import subprocess
import sys
import time
from typing import Any


def main() -> None:
    request = json.load(sys.stdin)
    source = request["source"]
    cases = request["test_cases"]
    case_timeout = float(request["case_timeout"])
    compile_timeout = float(request["compile_timeout"])
    max_output = int(request["max_output_bytes"])

    started = time.monotonic()
    compiled = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            "-pipe",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            source,
            "-o",
            "/tmp/student_program",
        ],
        capture_output=True,
        timeout=compile_timeout,
        check=False,
    )
    if compiled.returncode:
        compiler_output = compiled.stderr or compiled.stdout
        emit(
            {
                "verdict": "COMPILE_ERROR",
                "diagnostic": compiler_output[-max_output:].decode("utf-8", errors="replace"),
                "tests": [],
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        )
        return

    results: list[dict[str, Any]] = []
    verdict = "ACCEPTED"
    diagnostic = ""
    static_analysis = compiled.stderr[-max_output:].decode("utf-8", errors="replace").strip()
    for index, case in enumerate(cases, start=1):
        process = subprocess.Popen(
            ["/tmp/student_program"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(
                input=(case.get("stdin") or "").encode("utf-8"),
                timeout=case_timeout,
            )
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            results.append({"case": index, "status": "TIME_LIMIT_EXCEEDED"})
            verdict = "TIME_LIMIT_EXCEEDED"
            diagnostic = f"Test case {index} exceeded the {case_timeout:g}s time limit"
            break
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        stdout = stdout[:max_output].decode("utf-8", errors="replace")
        stderr = stderr[:max_output].decode("utf-8", errors="replace")
        if process.returncode:
            results.append(
                {
                    "case": index,
                    "status": "RUNTIME_ERROR",
                    "return_code": process.returncode,
                    "stderr": stderr,
                    "stdout": stdout,
                }
            )
            verdict = "RUNTIME_ERROR"
            diagnostic = stderr or f"Program exited with status {process.returncode} on test case {index}"
            break

        expected = case["expected_stdout"]
        passed = stdout.split() == expected.split()
        results.append(
            {
                "case": index,
                "status": "PASSED" if passed else "WRONG_ANSWER",
                "stdout": stdout,
                "expected_stdout": expected,
            }
        )
        if not passed:
            verdict = "WRONG_ANSWER"
            diagnostic = f"Output did not match expected output on test case {index}"
            break

    emit(
        {
            "verdict": verdict,
            "diagnostic": diagnostic,
            "static_analysis": static_analysis,
            "tests": results,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    )


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired:
        emit({"verdict": "TIME_LIMIT_EXCEEDED", "diagnostic": "Compilation timed out", "tests": []})
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Runner error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
