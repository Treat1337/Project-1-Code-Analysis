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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def load_examples(dataset_path: Path) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    csv.field_size_limit(min(sys.maxsize, (1 << 31) - 1))
    with dataset_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"code", "label"}.issubset(reader.fieldnames or set()):
            raise ValueError("CSV cần có các cột code,label")
        for row in reader:
            code = (row.get("code") or "").strip()
            label = (row.get("label") or "").strip()
            if code and label:
                texts.append(f"{code}\n{(row.get('compiler_message') or '').strip()}")
                labels.append(label)
                if len(texts) % 500 == 0:
                    print(f"Classifier | loaded {len(texts)} samples...", flush=True)
    print(f"Classifier | valid samples: {len(texts)}", flush=True)
    return texts, labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Train TF-IDF + Logistic Regression classifier.")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "Dataset" / "codenet_verdicts.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "code-models" / "classifier",
    )
    args = parser.parse_args()
    if not args.dataset.is_file():
        parser.error(f"Không tìm thấy dataset: {args.dataset}")

    texts, labels = load_examples(args.dataset)
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values(), default=0) < 2:
        parser.error("Dataset cần ít nhất 2 nhãn và mỗi nhãn có ít nhất 2 mẫu.")

    test_count = max(len(counts), math.ceil(len(labels) * 0.2))
    if len(labels) - test_count < len(counts):
        parser.error("Không đủ mẫu để chia train/test; hãy thêm dữ liệu cho mỗi nhãn.")
    train_x, test_x, train_y, test_y = train_test_split(
        texts,
        labels,
        test_size=test_count,
        random_state=42,
        stratify=labels,
    )
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
