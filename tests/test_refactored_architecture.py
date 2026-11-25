"""
tests/test_refactored_architecture.py — Automated verification for refactored architecture.

Tests:
1. Configuration & Path integrity (PROJECT_ROOT, pathlib usage).
2. Service integrity (dataset loader, cpp runner, ollama client).
3. Schema & Model validation (Pydantic models, backward-compatible re-exports).
4. Direct endpoint handler verification:
   - serve_index() -> FileResponse
   - health() -> dict
   - api_problem_list() -> dict
   - api_problem_detail() -> dict
   - api_run() -> dict (boilerplate check, execution)
   - predict_models() -> dict
5. ML models loading and inference.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from fastapi.responses import FileResponse

from app.config import (
    CODEBERT_MODEL_DIR,
    ASTNN_MODEL_DIR,
    CLASSIFIER_MODEL_PATH,
    DATASET_DIR,
    PROJECT_ROOT,
    STATIC_DIR,
    TEMP_DIR,
)
from app.main import (
    app,
    serve_index,
    health,
    classifier,
    codebert_model,
    astnn_model,
)
from app.api.problems import api_problem_list, api_problem_detail
from app.api.judge import api_run
from app.api.ai import predict_models
from app.schemas.schemas import ApiRunRequest, ClassifyRequest
from app.services.dataset_loader import valid_problem_id, extract_title, sanitize_problem_html


class ConfigArchitectureTests(unittest.TestCase):
    def test_project_root_is_valid_directory(self) -> None:
        self.assertTrue(PROJECT_ROOT.is_dir())
        self.assertTrue((PROJECT_ROOT / "app").is_dir())
        self.assertTrue((PROJECT_ROOT / "run.py").is_file())

    def test_paths_are_pathlib_instances(self) -> None:
        self.assertIsInstance(PROJECT_ROOT, Path)
        self.assertIsInstance(DATASET_DIR, Path)
        self.assertIsInstance(STATIC_DIR, Path)
        self.assertIsInstance(TEMP_DIR, Path)

    def test_checkpoints_exist_in_models_or_artifacts(self) -> None:
        self.assertTrue(CLASSIFIER_MODEL_PATH.is_file())
        self.assertTrue((ASTNN_MODEL_DIR / "model.json").is_file())
        self.assertTrue((CODEBERT_MODEL_DIR / "model.json").is_file())

    def test_static_directory_contains_separated_assets(self) -> None:
        self.assertTrue((STATIC_DIR / "index.html").is_file())
        self.assertTrue((STATIC_DIR / "css" / "style.css").is_file())
        self.assertTrue((STATIC_DIR / "js" / "editor.js").is_file())
        self.assertTrue((STATIC_DIR / "js" / "app.js").is_file())


class DatasetLoaderTests(unittest.TestCase):
    def test_problem_id_validation(self) -> None:
        self.assertTrue(valid_problem_id("p00001"))
        self.assertTrue(valid_problem_id("p99999"))
        self.assertFalse(valid_problem_id("p1"))
        self.assertFalse(valid_problem_id("problem1"))
        self.assertFalse(valid_problem_id("../../etc/passwd"))

    def test_html_sanitization(self) -> None:
        raw = '<script>alert("xss")</script><h1 onclick="boom()">Title</h1><p>Content</p>'
        sanitized = sanitize_problem_html(raw)
        self.assertNotIn("<script", sanitized)
        self.assertNotIn("onclick", sanitized)
        self.assertIn("Title", sanitized)

    def test_extract_title(self) -> None:
        html = "<html><body><h1>Problem Title</h1></body></html>"
        self.assertEqual(extract_title(html, "fallback"), "Problem Title")


class ApiEndpointsTests(unittest.TestCase):
    def test_serve_index_returns_fileresponse(self) -> None:
        response = serve_index()
        self.assertIsInstance(response, FileResponse)
        self.assertTrue(Path(response.path).is_file())

    def test_health_endpoint(self) -> None:
        data = health()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("classifier", data)
        self.assertIn("models", data)
        self.assertIn("runner", data)

    def test_get_problems_list(self) -> None:
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            prob_dir = temp_path / "problem_descriptions"
            io_dir = temp_path / "data"
            prob_dir.mkdir()
            io_dir.mkdir()

            (prob_dir / "p00001.html").write_text("<h1>Problem 1</h1>", encoding="utf-8")
            (io_dir / "p00001").mkdir()

            with patch("app.api.problems.PROBLEM_DESCRIPTIONS", prob_dir):
                with patch("app.api.problems.TEST_IO_DATA", io_dir):
                    api_problem_list.cache_clear()
                    data = api_problem_list()
                    self.assertIn("problems", data)
                    self.assertEqual(len(data["problems"]), 1)
                    self.assertEqual(data["problems"][0]["problem_id"], "p00001")
                    self.assertEqual(data["problems"][0]["title"], "Problem 1")

    def test_get_problem_detail_valid(self) -> None:
        try:
            data = api_problem_detail("p00001")
            self.assertEqual(data.get("problem_id"), "p00001")
            self.assertIn("title", data)
            self.assertIn("html", data)
            self.assertIn("test_cases", data)
        except Exception as e:
            # If dataset is not downloaded in this test environment
            self.assertIn("not found", str(e).lower())

    def test_api_run_rejects_empty_boilerplate(self) -> None:
        req = ApiRunRequest(
            problem_id="p00001",
            language="cpp",
            code="",
            custom_input="1 2",
        )
        res = api_run(req)
        self.assertEqual(res.get("verdict"), "Empty Output")

    def test_api_run_detects_unmodified_starter_template(self) -> None:
        req = ApiRunRequest(
            problem_id="p00001",
            language="cpp",
            code="#include <bits/stdc++.h>\nusing namespace std;\nint main() {\n    return 0;\n}\n",
            custom_input="1 2",
        )
        res = api_run(req)
        self.assertEqual(res.get("verdict"), "Wrong Answer")

    def test_models_predict_endpoint(self) -> None:
        req = ClassifyRequest(
            code="#include <iostream>\nint main() { int x; std::cin >> x; std::cout << x * 2; return 0; }",
            compiler_message="",
            problem_description="Multiply by two",
            sample_input="3",
            sample_output="6",
        )
        data = predict_models(req)
        self.assertIn("codeclassifier", data)
        self.assertIn("astnn", data)
        self.assertIn("codebert", data)
        self.assertIn("analysis_time_ms", data)


class MLModelsInferenceTests(unittest.TestCase):
    def test_classifier_is_available_and_predicts(self) -> None:
        self.assertTrue(classifier.available)
        result = classifier.predict("int main() { return 0; }")
        self.assertTrue(result.get("available"))
        self.assertIn("label", result)
        self.assertIn("confidence", result)

    def test_neural_models_status(self) -> None:
        # Check ASTNN and CodeBERT availability
        self.assertIsNotNone(codebert_model)
        self.assertIsNotNone(astnn_model)
        codebert_res = codebert_model.predict("int main() { return 0; }")
        self.assertTrue(codebert_res.get("available"))
        astnn_res = astnn_model.predict("int main() { return 0; }")
        self.assertTrue(astnn_res.get("available"))


class BackwardCompatibilityImportsTests(unittest.TestCase):
    def test_app_models_reexport(self) -> None:
        import app.models as legacy_models
        self.assertTrue(hasattr(legacy_models, "AnalyzeRequest"))
        self.assertTrue(hasattr(legacy_models, "ApiRunRequest"))
        self.assertTrue(hasattr(legacy_models, "RunRequest"))

    def test_app_services_runner_reexport(self) -> None:
        import app.services.runner as legacy_runner
        self.assertTrue(hasattr(legacy_runner, "run_cpp"))
        self.assertTrue(hasattr(legacy_runner, "analyze_cpp"))
        self.assertTrue(hasattr(legacy_runner, "RunnerUnavailable"))

    def test_server_py_backward_compat(self) -> None:
        import server
        self.assertTrue(hasattr(server, "app"))


if __name__ == "__main__":
    unittest.main()
