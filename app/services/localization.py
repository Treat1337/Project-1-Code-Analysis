import re
from typing import Any


_COMPILER_LOCATION = re.compile(
    r"(?:^|[\\/])?main\.cpp:(\d+)(?::(\d+))?:\s*"
    r"(fatal error|error|warning|note):\s*(.*)",
    re.IGNORECASE,
)


def localize_errors(
    diagnostic: str,
    static_analysis: str,
    tests: list[dict[str, Any]],
) -> dict[str, Any]:
    compiler_diagnostics = []
    seen: set[tuple[int, int | None, str, str]] = set()
    for evidence, text in (
        ("compiler", diagnostic),
        ("static_analysis", static_analysis),
    ):
        for line in text.splitlines():
            match = _COMPILER_LOCATION.search(line)
            if match is None:
                continue
            source_line = int(match.group(1))
            column = int(match.group(2)) if match.group(2) else None
            severity = match.group(3).lower()
            message = match.group(4).strip()
            key = (source_line, column, severity, message)
            if key in seen:
                continue
            seen.add(key)
            compiler_diagnostics.append(
                {
                    "line": source_line,
                    "column": column,
                    "severity": severity,
                    "message": message,
                    "evidence": evidence,
                }
            )

    failing_tests = [
        {"case": test.get("case", index), "status": test.get("status", "UNKNOWN")}
        for index, test in enumerate(tests, start=1)
        if test.get("status") != "PASSED"
    ]
    return {
        "compiler_diagnostics": compiler_diagnostics,
        "failing_test_cases": failing_tests,
        "note": (
            "Compiler locations point to reported source lines. A failing test identifies "
            "an input that exposes the issue, not the exact source line responsible."
        ),
    }
