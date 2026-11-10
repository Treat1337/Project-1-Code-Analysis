import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


class CodeClassifier:
    """Optional experimental classifier; execution verdicts remain authoritative."""

    def __init__(
        self,
        dataset_path: Path,
        neural_model_dir: Path | None = None,
        trained_model_path: Path | None = None,
    ) -> None:
        self.dataset_path = dataset_path
        self.pipeline: Pipeline | None = None
        self.neural_model: Any | None = None
        self.reason = "No labeled dataset is available"
        if neural_model_dir is not None:
            from app.services.neural_classifier import TrainedCodeClassifier

            self.neural_model = TrainedCodeClassifier(neural_model_dir)
            self.reason = ""
            return
        if trained_model_path is not None and trained_model_path.is_file():
            self.pipeline = joblib.load(trained_model_path)
            if not isinstance(self.pipeline, Pipeline):
                raise ValueError(f"Trained classifier at {trained_model_path} is not a sklearn Pipeline")
            self.reason = ""
            return
        self._train()

    @property
    def available(self) -> bool:
        return self.pipeline is not None or self.neural_model is not None

    def _train(self) -> None:
        if not self.dataset_path.is_file():
            return
        texts: list[str] = []
        labels: list[str] = []
        try:
            csv.field_size_limit(min(sys.maxsize, (1 << 31) - 1))
            with self.dataset_path.open(encoding="utf-8-sig", newline="") as source:
                for row in csv.DictReader(source):
                    code = (row.get("code") or "").strip()
                    label = (row.get("label") or "").strip()
                    if code and label:
                        message = (row.get("compiler_message") or "").strip()
                        texts.append(f"{code}\n{message}")
                        labels.append(label)
        except (OSError, csv.Error) as exc:
            self.reason = f"Could not read labeled dataset: {exc}"
            return
        counts = Counter(labels)
        if len(counts) < 2 or min(counts.values()) < 2:
            self.reason = "Dataset needs at least two labels and two examples per label"
            return
        self.pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 5), max_features=50000)),
                ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
            ]
        )
        self.pipeline.fit(texts, labels)
        self.reason = ""

    def predict(self, code: str, compiler_message: str = "") -> dict[str, Any]:
        if self.neural_model is not None:
            return self.neural_model.predict(code, compiler_message)
        if self.pipeline is None:
            return {"available": False, "reason": self.reason}
        features = code + "\n" + compiler_message
        prediction = str(self.pipeline.predict([features])[0])
        probabilities = self.pipeline.predict_proba([features])[0]
        confidence = float(max(probabilities))
        return {
            "available": True,
            "label": prediction,
            "confidence": round(confidence, 4),
            "note": "Experimental prediction only; never overrides the compiler or test runner verdict.",
        }
