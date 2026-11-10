import csv
import math
import sys
from collections import Counter
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "Dataset" / "labeled_examples.csv"


def main() -> int:
    if not DATASET_PATH.is_file():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        return 1

    texts: list[str] = []
    labels: list[str] = []
    try:
        csv.field_size_limit(min(sys.maxsize, (1 << 31) - 1))
        with DATASET_PATH.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                code = (row.get("code") or "").strip()
                label = (row.get("label") or "").strip()
                if code and label:
                    message = (row.get("compiler_message") or "").strip()
                    texts.append(f"{code}\n{message}")
                    labels.append(label)
    except (OSError, csv.Error) as exc:
        print(f"Could not read dataset: {exc}", file=sys.stderr)
        return 1

    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values(), default=0) < 2:
        print("Need at least two labels and two examples per label.", file=sys.stderr)
        return 1

    test_count = max(len(counts), math.ceil(len(labels) * 0.25))
    if len(labels) - test_count < len(counts):
        print("Not enough examples for a stratified train/test split.", file=sys.stderr)
        return 1

    train_x, test_x, train_y, test_y = train_test_split(
        texts,
        labels,
        test_size=test_count,
        random_state=42,
        stratify=labels,
    )
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 5), max_features=50000)),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    label_order = sorted(counts)
    print(f"Samples: {len(labels)} | train: {len(train_x)} | test: {len(test_x)}")
    print(f"Labels: {', '.join(label_order)}")
    print(f"Accuracy: {accuracy_score(test_y, predictions):.4f}")
    print(f"Macro-F1: {f1_score(test_y, predictions, average='macro', zero_division=0):.4f}")
    print("Confusion matrix (rows=true, columns=predicted):")
    print(f"Labels: {label_order}")
    print(confusion_matrix(test_y, predictions, labels=label_order))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
