from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.codenet_dataset import (
    format_model_text,
    load_examples as load_dataset_examples,
)


def load_examples(
    dataset_path: Path,
    folder_fraction: float = 1.0,
    folder_batch_size: int = 50,
    io_workers: int = 8,
    max_per_label: int = 0,
) -> tuple[list[str], list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    groups: list[str] = []
    for row in load_dataset_examples(
        dataset_path,
        max_per_label=max_per_label,
        folder_fraction=folder_fraction,
        folder_batch_size=folder_batch_size,
        seed=42,
        io_workers=io_workers,
    ):
        code = (row.get("code") or "").strip()
        label = (row.get("label") or "").strip()
        if code and label:
            texts.append(
                format_model_text(
                    code,
                    row.get("compiler_message") or "",
                    row.get("problem_description") or "",
                    row.get("sample_input") or "",
                    row.get("sample_output") or "",
                )
            )
            labels.append(label)
            groups.append((row.get("problem_id") or "").strip())
    print(f"Classifier | valid samples: {len(texts)}", flush=True)
    return texts, labels, groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Train TF-IDF + Logistic Regression classifier.")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "Dataset" / "codenet_verdicts.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "code-models" / "classifier",
    )
    parser.add_argument("--folder-fraction", type=float, default=1.0)
    parser.add_argument("--folder-batch-size", type=int, default=50)
    parser.add_argument("--io-workers", type=int, default=8)
    parser.add_argument(
        "--max-per-label",
        type=int,
        default=0,
        help="Maximum samples per label for a CodeNet directory; 0 means no cap",
    )
    args = parser.parse_args()
    if not args.dataset.is_file() and not args.dataset.is_dir():
        parser.error(f"Không tìm thấy dataset CSV hoặc thư mục CodeNet: {args.dataset}")
    texts, labels, groups = load_examples(
        args.dataset,
        args.folder_fraction,
        args.folder_batch_size,
        args.io_workers,
        args.max_per_label,
    )
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values(), default=0) < 2:
        parser.error("Dataset cần ít nhất 2 nhãn và mỗi nhãn có ít nhất 2 mẫu.")

    test_count = max(len(counts), math.ceil(len(labels) * 0.2))
    if len(labels) - test_count < len(counts):
        parser.error("Không đủ mẫu để chia train/test; hãy thêm dữ liệu cho mỗi nhãn.")
    classes = set(labels)
    if all(groups) and len(set(groups)) > 1:
        for seed in range(42, 62):
            train_indices, test_indices = next(
                GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(
                    texts, labels, groups
                )
            )
            if (
                {labels[index] for index in train_indices} == classes
                and {labels[index] for index in test_indices} == classes
            ):
                break
        else:
            parser.error("Không thể chia train/test theo problem_id với đủ mọi nhãn.")
        split_name = "problem-disjoint"
        train_x = [texts[index] for index in train_indices]
        test_x = [texts[index] for index in test_indices]
        train_y = [labels[index] for index in train_indices]
        test_y = [labels[index] for index in test_indices]
    else:
        train_indices, test_indices = train_test_split(
            np.arange(len(texts)),
            test_size=test_count,
            random_state=42,
            stratify=labels,
        )
        split_name = "stratified"
        train_x = [texts[index] for index in train_indices]
        test_x = [texts[index] for index in test_indices]
        train_y = [labels[index] for index in train_indices]
        test_y = [labels[index] for index in test_indices]
    print(
        f"===== Model: TF-IDF + Logistic Regression =====\n"
        f"Train {len(train_x)} samples | test {len(test_x)} samples | "
        f"{len(counts)} labels | fitting model...",
        flush=True,
    )
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 5), max_features=50000)),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    model.fit(train_x, train_y)
    print(f"Classifier | fitted {len(train_x)}/{len(train_x)} training samples", flush=True)
    predictions = model.predict(test_x)
    label_order = sorted(counts)
    report: dict[str, Any] = {
        "model": "tfidf_logistic_regression",
        "dataset": str(args.dataset),
        "sample_count": len(labels),
        "train_count": len(train_x),
        "test_count": len(test_x),
        "split": split_name,
        "labels": label_order,
        "accuracy": round(accuracy_score(test_y, predictions), 4),
        "macro_f1": round(f1_score(test_y, predictions, average="macro", zero_division=0), 4),
        "confusion_matrix": confusion_matrix(test_y, predictions, labels=label_order).tolist(),
        "classification_report": classification_report(
            test_y, predictions, labels=label_order, output_dict=True, zero_division=0
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "model.joblib"
    report_path = args.output_dir / "metrics.json"
    joblib.dump(model, model_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved model: {model_path}", flush=True)
    print(f"Saved metrics: {report_path}", flush=True)
    print(
        f"Classifier | accuracy={report['accuracy']:.4f} | "
        f"macro-F1={report['macro_f1']:.4f}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, csv.Error, ValueError) as exc:
        print(f"Classifier training failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
