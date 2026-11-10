from __future__ import annotations

from collections import Counter
from typing import Any

from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer


class MisconceptionPatternDetector:
    """Unsupervised grouping of similar attempts; clusters are not proven misconceptions."""

    def analyze(self, attempts: list[dict[str, str]]) -> dict[str, Any]:
        texts = [
            f"{attempt['verdict']} {attempt.get('diagnostic', '')}\n{attempt['code']}"
            for attempt in attempts
        ]
        vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            token_pattern=r"(?u)\b\w+\b",
            ngram_range=(1, 2),
            max_features=10000,
        )
        matrix = vectorizer.fit_transform(texts)
        labels = DBSCAN(eps=0.75, min_samples=2, metric="cosine").fit_predict(matrix)
        terms = vectorizer.get_feature_names_out()
        clusters: list[dict[str, Any]] = []
        cluster_labels = sorted(set(int(label) for label in labels if label >= 0))

        for cluster_id in cluster_labels:
            indices = [index for index, label in enumerate(labels) if label == cluster_id]
            mean_scores = matrix[indices].mean(axis=0).A1
            top_indices = mean_scores.argsort()[::-1][:5]
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "attempt_indices": indices,
                    "size": len(indices),
                    "common_terms": [str(terms[index]) for index in top_indices if mean_scores[index] > 0],
                    "verdicts": dict(
                        Counter(attempts[index]["verdict"] for index in indices)
                    ),
                }
            )

        return {
            "model": "TF-IDF + DBSCAN misconception-pattern baseline",
            "clusters": clusters,
            "unclustered_attempt_indices": [
                index for index, label in enumerate(labels) if label == -1
            ],
            "note": (
                "Clusters identify textually similar code/diagnostics only. They are candidate "
                "patterns for instructor review, not evidence of a student's actual reasoning "
                "or a validated implementation of the MISTAKE framework."
            ),
        }
