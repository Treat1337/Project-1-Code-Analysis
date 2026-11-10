import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
from pydantic import ValidationError

from app.models import AnalyzeRequest, FeedbackRequest, KnowledgeTraceRequest
from app.services.classifier import CodeClassifier
from app.services.codenet_retrieval import CodeNetSimilarityIndex
from app.services.knowledge_tracing import TestCaseInformedKnowledgeTracer
from app.services.localization import localize_errors
from app.services.misconception_detection import MisconceptionPatternDetector
from app.services.problem_catalog import (
    _StatementParser,
    extract_sample_test_cases,
    load_derived_test_cases,
    load_problem,
)
from app.services.retrieval import KnowledgeBase
from app.services.runner import RunnerUnavailable, analyze_cpp
from scripts.prepare_codenet_dataset import export_dataset


class RetrievalTests(unittest.TestCase):
    def test_retrieves_relevant_document(self) -> None:
        kb = KnowledgeBase(
            [
                {"title": "Lỗi runtime", "content": "Truy cập mảng ngoài phạm vi gây runtime error."},
                {"title": "Tối ưu", "content": "Độ phức tạp O(n log n) giúp giảm thời gian."},
            ]
        )
        results = kb.search("runtime truy cập mảng", limit=1)
        self.assertEqual(results[0]["title"], "Lỗi runtime")

    def test_codenet_search_is_scoped_to_problem_and_returns_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir)
            metadata = dataset / "Project_CodeNet" / "metadata"
            data = dataset / "Project_CodeNet" / "data"
            metadata.mkdir(parents=True)

            for problem_id, rows in {
                "p00001": [
                    ("s000000001", "Accepted", "int main(){int sum=0; sum+=1; return sum;}"),
                    ("s000000002", "Wrong Answer", "int main(){int product=1; product*=2; return product;}"),
                ],
                "p00002": [
                    ("s000000003", "Accepted", "int main(){return 0;}"),
                ],
            }.items():
                problem_dir = data / problem_id / "C++"
                problem_dir.mkdir(parents=True)
                metadata_lines = [
                    "submission_id,problem_id,language,filename_ext,status"
                ]
                for submission_id, status, code in rows:
                    (problem_dir / f"{submission_id}.cpp").write_text(code, encoding="utf-8")
                    metadata_lines.append(
                        f"{submission_id},{problem_id},C++,cpp,{status}"
                    )
                (metadata / f"{problem_id}.csv").write_text(
                    "\n".join(metadata_lines) + "\n",
                    encoding="utf-8",
                )

            result = CodeNetSimilarityIndex(dataset).search(
                "p00001",
                "int main(){int sum=0; sum+=1; return sum;}",
            )

        self.assertTrue(result["available"])
        self.assertEqual(result["problem_id"], "p00001")
        self.assertEqual(
            {reference["problem_id"] for reference in result["results"]},
            {"p00001"},
        )
        self.assertEqual(result["results"][0]["submission_id"], "s000000001")
        self.assertEqual(result["results"][0]["verdict"], "ACCEPTED")
        self.assertEqual(
            {reference["verdict"] for reference in result["nearest_by_verdict"]},
            {"ACCEPTED", "WRONG_ANSWER"},
        )

    def test_localization_separates_compiler_lines_from_failing_tests(self) -> None:
        result = localize_errors(
            "/input/main.cpp:8:4: error: expected ';' before '}' token",
            "main.cpp:9:2: warning: unused variable 'value'",
            [{"case": 2, "status": "WRONG_ANSWER"}],
        )

        self.assertEqual(result["compiler_diagnostics"][0]["line"], 8)
        self.assertEqual(result["compiler_diagnostics"][0]["column"], 4)
        self.assertEqual(result["compiler_diagnostics"][1]["evidence"], "static_analysis")
        self.assertEqual(result["failing_test_cases"], [{"case": 2, "status": "WRONG_ANSWER"}])


class ProblemStatementTests(unittest.TestCase):
    def test_loads_input_output_from_derived_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir)
            data_dir = (
                dataset
                / "Project_CodeNet"
                / "derived"
                / "input_output"
                / "data"
                / "p00001"
            )
            data_dir.mkdir(parents=True)
            (data_dir / "input.txt").write_text("1 2\n", encoding="utf-8")
            (data_dir / "output.txt").write_text("3\n", encoding="utf-8")
            description_dir = dataset / "Project_CodeNet" / "problem_descriptions"
            description_dir.mkdir(parents=True)
            (description_dir / "p00001.html").write_text(
                "<h1>Problem</h1><h2>Sample Input 1</h2><pre>9</pre>"
                "<h2>Output for the Sample Input 1</h2><pre>9</pre>",
                encoding="utf-8",
            )

            with patch("app.services.problem_catalog.DATASET_DIR", dataset):
                problem = load_problem("p00001")

        self.assertEqual(
            problem.sample_test_cases,
            [{"stdin": "1 2\n", "expected_stdout": "3\n"}],
        )

    def test_missing_derived_input_output_returns_no_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.problem_catalog.DATASET_DIR", Path(temp_dir)
            ):
                cases = load_derived_test_cases("p00001")

        self.assertEqual(cases, [])

    def test_extracts_problem_title_and_sample_sections(self) -> None:
        parser = _StatementParser()
        parser.feed(
            "<h1>Sample problem</h1><h2>Sample Input 1</h2><pre>4\n</pre>"
            "<h2>Output for the Sample Input 1</h2><pre>16\n</pre>"
        )

        self.assertEqual(parser.title_parts, ["Sample problem"])
        self.assertEqual(
            parser.sections,
            [
                ("Sample Input 1", "4"),
                ("Output for the Sample Input 1", "16"),
            ],
        )
        self.assertEqual(
            extract_sample_test_cases(parser.sections),
            [{"stdin": "4", "expected_stdout": "16"}],
        )

    def test_extracts_samples_with_and_without_the_article(self) -> None:
        cases = extract_sample_test_cases(
            [
                ("Sample Input 2", "10"),
                ("Output for Sample Input 2", "100"),
                ("Sample Input 1", "4"),
                ("Output for the Sample Input 1", "16"),
            ]
        )

        self.assertEqual(
            cases,
            [
                {"stdin": "4", "expected_stdout": "16"},
                {"stdin": "10", "expected_stdout": "100"},
            ],
        )


class ClassifierTests(unittest.TestCase):
    def test_reports_missing_dataset_explicitly(self) -> None:
        classifier = CodeClassifier(Path("missing-labeled-data.csv"))
        self.assertEqual(
            classifier.predict("int main() {}"),
            {"available": False, "reason": "No labeled dataset is available"},
        )

    def test_trains_on_a_small_labeled_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "labeled_examples.csv"
            dataset.write_text(
                "code,label\n"
                '"int main(){return 0;}",accepted\n'
                '"int main(){return 1;}",accepted\n'
                '"int main( {",compile_error\n'
                '"void main( {",compile_error\n',
                encoding="utf-8",
            )
            classifier = CodeClassifier(dataset)
            result = classifier.predict("int main(){return 0;}")
        self.assertTrue(result["available"])
        self.assertIn(result["label"], {"accepted", "compile_error"})
        self.assertIn("confidence", result)

    def test_loads_a_saved_classifier_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "labeled_examples.csv"
            dataset.write_text(
                "code,label\n"
                '"int main(){return 0;}",accepted\n'
                '"int main(){return 1;}",accepted\n'
                '"int main( {",compile_error\n'
                '"void main( {",compile_error\n',
                encoding="utf-8",
            )
            trained = CodeClassifier(dataset)
            model_path = Path(temp_dir) / "model.joblib"
            joblib.dump(trained.pipeline, model_path)

            loaded = CodeClassifier(
                Path(temp_dir) / "missing.csv",
                trained_model_path=model_path,
            )

        self.assertTrue(loaded.predict("int main(){return 0;}")["available"])


class KnowledgeTracingTests(unittest.TestCase):
    def test_predicts_case_probability_and_repeated_failures(self) -> None:
        history = [
            {
                "verdict": "WRONG_ANSWER",
                "tests": [{"case_id": 1, "status": "WRONG_ANSWER"}],
            },
            {
                "verdict": "WRONG_ANSWER",
                "tests": [{"case_id": 1, "status": "WRONG_ANSWER"}],
            },
            {
                "verdict": "ACCEPTED",
                "tests": [{"case_id": 1, "status": "PASSED"}],
            },
        ]

        result = TestCaseInformedKnowledgeTracer().predict(history)

        self.assertEqual(result["trend"], "improving")
        self.assertEqual(result["repeated_errors"], ["wrong_answer"])
        self.assertEqual(result["repeated_failed_test_cases"], [1])
        self.assertGreater(
            result["test_case_predictions"][0]["pass_probability"], 0
        )
        self.assertLess(
            result["test_case_predictions"][0]["pass_probability"], 1
        )

    def test_validates_history_request_shape(self) -> None:
        request = KnowledgeTraceRequest.model_validate(
            {
                "history": [
                    {
                        "verdict": "WRONG_ANSWER",
                        "tests": [{"case": 1, "status": "WRONG_ANSWER"}],
                    }
                ],
                "next_test_case_ids": [1],
            }
        )
        self.assertEqual(request.next_test_case_ids, [1])
        self.assertEqual(request.history[0].tests[0].case_id, 1)


class MisconceptionDetectionTests(unittest.TestCase):
    def test_groups_similar_attempts_without_claiming_ground_truth(self) -> None:
        attempts = [
            {
                "code": "int main() { int values[2]; return values[3]; }",
                "verdict": "RUNTIME_ERROR",
                "diagnostic": "array index out of bounds",
            },
            {
                "code": "int main() { int values[2]; return values[4]; }",
                "verdict": "RUNTIME_ERROR",
                "diagnostic": "array index out of bounds",
            },
        ]

        result = MisconceptionPatternDetector().analyze(attempts)

        self.assertEqual(len(result["clusters"]), 1)
        self.assertEqual(result["clusters"][0]["size"], 2)
        self.assertIn("not evidence", result["note"])


class CodeNetDatasetTests(unittest.TestCase):
    def test_exports_cpp_statuses_and_problem_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            metadata = root / "metadata"
            data = root / "data"
            output = root / "examples.csv"
            metadata.mkdir()
            cpp_dir = data / "p00001" / "C++"
            cpp_dir.mkdir(parents=True)
            (cpp_dir / "s000000001.cpp").write_text("int main() {}", encoding="utf-8")
            (cpp_dir / "s000000002.cpp").write_text("int main( {", encoding="utf-8")
            (metadata / "p00001.csv").write_text(
                "submission_id,problem_id,language,filename_ext,status\n"
                "s000000001,p00001,C++,cpp,Accepted\n"
                "s000000002,p00001,C++,cpp,Compile Error\n"
                "s000000003,p00001,Java,java,Accepted\n",
                encoding="utf-8",
            )

            counts = export_dataset(metadata, data, output, max_per_label=10, seed=42)

            self.assertEqual(counts, {"accepted": 1, "compile_error": 1})
            with output.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual({row["problem_id"] for row in rows}, {"p00001"})
            self.assertTrue(all(not row["compiler_message"] for row in rows))


class RunnerTests(unittest.TestCase):
    @patch("app.services.runner._docker_command", return_value=None)
    def test_never_executes_code_without_docker(self, _docker: object) -> None:
        with self.assertRaisesRegex(RunnerUnavailable, "was not executed"):
            analyze_cpp("int main() {}", [{"stdin": "", "expected_stdout": ""}])


class RequestValidationTests(unittest.TestCase):
    def test_requires_expected_output_for_each_test(self) -> None:
        with self.assertRaises(ValidationError):
            AnalyzeRequest.model_validate(
                {"code": "int main() {}", "test_cases": [{"stdin": "input"}]}
            )

    def test_accepts_empty_expected_output(self) -> None:
        request = AnalyzeRequest.model_validate(
            {
                "code": "int main() {}",
                "test_cases": [{"stdin": "", "expected_stdout": ""}],
            }
        )
        self.assertEqual(request.test_cases[0].expected_stdout, "")

    def test_analyze_accepts_optional_problem_scoped_retrieval(self) -> None:
        request = AnalyzeRequest.model_validate(
            {
                "code": "int main() {}",
                "test_cases": [{"stdin": "", "expected_stdout": ""}],
                "problem_id": "p00001",
            }
        )
        self.assertEqual(request.problem_id, "p00001")
        self.assertEqual(request.similarity_limit, 5)

    def test_rejects_malformed_problem_id_and_similarity_limit(self) -> None:
        base = {
            "code": "int main() {}",
            "test_cases": [{"stdin": "", "expected_stdout": ""}],
        }
        for extra in (
            {"problem_id": "../../outside"},
            {"similarity_limit": 11},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                AnalyzeRequest.model_validate({**base, **extra})

    def test_rejects_oversized_utf8_code(self) -> None:
        with self.assertRaises(ValidationError):
            AnalyzeRequest.model_validate(
                {
                    "code": "é" * 32769,
                    "test_cases": [{"stdin": "", "expected_stdout": ""}],
                }
            )

    def test_feedback_only_accepts_runner_verdicts(self) -> None:
        with self.assertRaises(ValidationError):
            FeedbackRequest.model_validate(
                {"code": "int main() {}", "verdict": "guess", "diagnostic": ""}
            )


if __name__ == "__main__":
    unittest.main()
