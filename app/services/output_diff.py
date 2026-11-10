import re
from typing import Any


_TOKEN = re.compile(r"\S+")


def compare_output(actual: str, expected: str) -> dict[str, Any]:
    actual_tokens = _TOKEN.findall(actual)
    expected_tokens = _TOKEN.findall(expected)
    first_difference = None
    for index, (actual_token, expected_token) in enumerate(
        zip(actual_tokens, expected_tokens), start=1
    ):
        if actual_token != expected_token:
            first_difference = {
                "token_index": index,
                "actual": actual_token,
                "expected": expected_token,
            }
            break
    if first_difference is None and len(actual_tokens) != len(expected_tokens):
        index = min(len(actual_tokens), len(expected_tokens)) + 1
        first_difference = {
            "token_index": index,
            "actual": actual_tokens[index - 1] if index <= len(actual_tokens) else "<missing>",
            "expected": (
                expected_tokens[index - 1] if index <= len(expected_tokens) else "<missing>"
            ),
        }

    return {
        "actual_token_count": len(actual_tokens),
        "expected_token_count": len(expected_tokens),
        "first_difference": first_difference,
        "matches_ignoring_whitespace": actual_tokens == expected_tokens,
    }


def enrich_test_results(
    requested_tests: list[dict[str, str]], results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        test = requested_tests[index] if index < len(requested_tests) else {}
        item = {**result, "stdin": test.get("stdin", "")}
        if result.get("status") == "WRONG_ANSWER":
            actual = str(result.get("stdout", ""))
            expected = str(result.get("expected_stdout", test.get("expected_stdout", "")))
            item["output_diff"] = compare_output(actual, expected)
        enriched.append(item)
    return enriched
