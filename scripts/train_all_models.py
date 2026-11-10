from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
MODELS = [
    ("TF-IDF + Logistic Regression", "train_classifier.py"),
    ("CodeBERT", "train_codebert.py"),
    ("ASTNN", "train_astnn.py"),
]
ML_DEPENDENCIES = {
    "torch": "torch",
    "transformers": "transformers",
    "tree-sitter": "tree_sitter",
    "tree-sitter-cpp": "tree_sitter_cpp",
}


def missing_ml_dependencies() -> list[str]:
    return [
        package
        for package, module in ML_DEPENDENCIES.items()
        if importlib.util.find_spec(module) is None
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train each trainable code model sequentially.")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "Dataset" / "codenet_verdicts.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "code-models",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--device", default=None, help="cuda hoặc cpu; mặc định tự chọn")
    args = parser.parse_args()
    args.dataset = args.dataset.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.dataset.is_file():
        parser.error(
            f"Không tìm thấy {args.dataset}; chạy trước "
            "'python scripts\\prepare_codenet_dataset.py'."
        )
    missing_dependencies = missing_ml_dependencies()
    if missing_dependencies:
        requirements = PROJECT_ROOT / "requirements-ml.txt"
        parser.error(
            f"Thiếu dependency ML: {', '.join(missing_dependencies)}. "
            f"Cài bằng đúng Python này: \"{sys.executable}\" -m pip install -r "
            f"\"{requirements}\"."
        )

    common_args = [
        "--dataset",
        str(args.dataset),
        "--output-dir",
        str(args.output_dir),
    ]
    neural_args = [
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
    ]
    codebert_args = [*neural_args, "--max-length", str(args.max_length)]
    if args.device:
        neural_args.extend(["--device", args.device])
        codebert_args.extend(["--device", args.device])

    for index, (model_name, script_name) in enumerate(MODELS, start=1):
        print(
            f"\n{'=' * 16} MODEL {index}/{len(MODELS)}: {model_name} {'=' * 16}",
            flush=True,
        )
        model_args = common_args.copy()
        if script_name == "train_classifier.py":
            model_args[model_args.index(str(args.output_dir))] = str(args.output_dir / "classifier")
        elif script_name == "train_codebert.py":
            model_args.extend(codebert_args)
        else:
            model_args.extend(neural_args)
        command = [sys.executable, str(PROJECT_ROOT / "scripts" / script_name), *model_args]
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if result.returncode:
            print(
                f"\nStopped at model {index}/{len(MODELS)} ({model_name}); "
                f"exit code={result.returncode}. Earlier models were saved.",
                file=sys.stderr,
                flush=True,
            )
            return result.returncode
        print(f"Completed model {index}/{len(MODELS)}: {model_name}", flush=True)

    model_reports = []
    for model_key in ("classifier", "codebert", "astnn"):
        metrics_path = args.output_dir / model_key / "metrics.json"
        model_reports.append(json.loads(metrics_path.read_text(encoding="utf-8")))
    report_path = args.output_dir / "comparison.json"
    report_path.write_text(
        json.dumps(
            {
                "dataset": str(args.dataset),
                "results": model_reports,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Combined report: {report_path}", flush=True)
    print("\nAll trainable models completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
