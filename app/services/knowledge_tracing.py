from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


INITIAL_MASTERY = 0.2
LEARNING_RATE = 0.15
GUESS_RATE = 0.2
SLIP_RATE = 0.1
VERDICT_TO_ERROR = {
    "COMPILE_ERROR": "compile_error",
    "WRONG_ANSWER": "wrong_answer",
    "RUNTIME_ERROR": "runtime_error",
    "TIME_LIMIT_EXCEEDED": "time_limit_exceeded",
}


class TestCaseInformedKnowledgeTracer:
    """A test-case-informed discrete latent-state model, not a trained TIKTOC reproduction."""

    def predict(
        self,
        history: list[dict[str, Any]],
        next_test_case_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        test_observations: dict[int, list[bool]] = defaultdict(list)
        attempt_scores: list[float] = []
        error_counts: Counter[str] = Counter()
        failed_case_counts: Counter[int] = Counter()

        for attempt in history:
            tests = attempt.get("tests", [])
            outcomes = tests
            if outcomes:
                passed_count = 0
                for test in outcomes:
                    case_id = test["case_id"]
                    passed = test["status"] == "PASSED"
                    test_observations[case_id].append(passed)
                    passed_count += int(passed)
                    if not passed:
                        failed_case_counts[case_id] += 1
                attempt_scores.append(passed_count / len(outcomes))
            else:
                passed = attempt["verdict"] == "ACCEPTED"
                attempt_scores.append(float(passed))

            error = VERDICT_TO_ERROR.get(attempt["verdict"])
            if error:
                error_counts[error] += 1

        requested_ids = next_test_case_ids or sorted(test_observations)
        case_predictions: list[dict[str, Any]] = []
        for case_id in requested_ids:
            observations = test_observations.get(case_id, [])
            mastery = self._update_mastery(observations)
            probability = self._probability_correct(mastery)
            case_predictions.append(
                {
                    "case_id": case_id,
                    "pass_probability": round(probability, 4),
                    "observations": len(observations),
                    "mastery_probability": round(mastery, 4),
                }
            )

        if case_predictions:
            overall_probability = self._product(
                item["pass_probability"] for item in case_predictions
            )
        else:
            overall_probability = self._probability_correct(
                self._update_mastery([score >= 1.0 for score in attempt_scores])
            )
        midpoint = max(1, len(attempt_scores) // 2)
        earlier = sum(attempt_scores[:midpoint]) / len(attempt_scores[:midpoint])
        recent = sum(attempt_scores[midpoint:]) / len(attempt_scores[midpoint:]) if len(attempt_scores) > midpoint else earlier
        difference = recent - earlier
        trend = "improving" if difference > 0.1 else "declining" if difference < -0.1 else "stable"

        return {
            "model": "TIKTOC-inspired discrete latent-state tracing",
            "attempt_count": len(history),
            "estimated_next_acceptance_probability": round(overall_probability, 4),
            "test_case_predictions": case_predictions,
            "trend": trend,
            "repeated_errors": sorted(error for error, count in error_counts.items() if count >= 2),
            "repeated_failed_test_cases": sorted(
                case_id for case_id, count in failed_case_counts.items() if count >= 2
            ),
            "note": (
                "Experimental hidden-state baseline based only on the supplied history. It "
                "uses fixed mastery, learning, guess and slip rates; the acceptance estimate "
                "assumes test-case outcomes are independent. It is not a trained or validated "
                "RSSM/TIKTOC model and is not a student ability score."
            ),
        }

    @staticmethod
    def _update_mastery(observations: list[bool]) -> float:
        mastery = INITIAL_MASTERY
        for passed in observations:
            probability_correct = TestCaseInformedKnowledgeTracer._probability_correct(mastery)
            if passed:
                mastery = mastery * (1 - SLIP_RATE) / probability_correct
            else:
                mastery = mastery * SLIP_RATE / (1 - probability_correct)
            mastery += (1 - mastery) * LEARNING_RATE
        return mastery

    @staticmethod
    def _probability_correct(mastery: float) -> float:
        return mastery * (1 - SLIP_RATE) + (1 - mastery) * GUESS_RATE

    @staticmethod
    def _product(values: Any) -> float:
        result = 1.0
        for value in values:
            result *= value
        return result
