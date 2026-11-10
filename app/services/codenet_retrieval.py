import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_PROBLEM_ID = re.compile(r"p\d{5}")
_SUBMISSION_ID = re.compile(r"s\d+")
_FILE_EXTENSION = re.compile(r"[A-Za-z0-9]+")
_VERDICTS = {
    "Accepted": "ACCEPTED",
    "Compile Error": "COMPILE_ERROR",
    "Wrong Answer": "WRONG_ANSWER",
    "Runtime Error": "RUNTIME_ERROR",
    "Time Limit Exceeded": "TIME_LIMIT_EXCEEDED",
    "Memory Limit Exceeded": "MEMORY_LIMIT_EXCEEDED",
    "WA: Presentation Error": "PRESENTATION_ERROR",
    "Output Limit Exceeded": "OUTPUT_LIMIT_EXCEEDED",
}
_MAX_REFERENCES_PER_VERDICT = 100
_MAX_SOURCE_BYTES = 64 * 1024
_MAX_EXCERPT_CHARACTERS = 4000


@dataclass(frozen=True)
class _ProblemIndex:
    records: tuple[dict[str, str], ...]
    vectorizer: TfidfVectorizer
    matrix: Any
    missing_sources: int
    oversized_sources: int


class CodeNetSimilarityIndex:
    def __init__(self, dataset_dir: Path) -> None:
        self.metadata_dir = dataset_dir / "Project_CodeNet" / "metadata"
        self.data_dir = dataset_dir / "Project_CodeNet" / "data"

    def search(self, problem_id: str, code: str, limit: int = 5) -> dict[str, Any]:
        if not _PROBLEM_ID.fullmatch(problem_id):
            raise ValueError(f"Invalid problem ID: {problem_id}")
        if not code.strip():
            return {"available": False, "reason": "Submitted code is empty"}
        if not 1 <= limit <= 10:
            raise ValueError("Similarity limit must be between 1 and 10")

        index = self._load_problem_index(problem_id)
        if not index.records:
            return {
                "available": False,
                "problem_id": problem_id,
                "indexed_count": 0,
                "reason": "No usable C++ reference submissions are available for this problem",
                "missing_source_count": index.missing_sources,
                "oversized_source_count": index.oversized_sources,
            }

        query = index.vectorizer.transform([code])
        scores = cosine_similarity(query, index.matrix).ravel()
        ranked = scores.argsort()[::-1]

        def reference(position: int) -> dict[str, Any]:
            record = index.records[position]
            excerpt = record["source_code"][:_MAX_EXCERPT_CHARACTERS]
            return {
                "submission_id": record["submission_id"],
                "problem_id": problem_id,
                "verdict": record["verdict"],
                "similarity": round(float(scores[position]), 4),
                "code_excerpt": excerpt,
                "truncated": len(record["source_code"]) > len(excerpt),
            }

        results = []
        nearest_by_verdict: dict[str, dict[str, Any]] = {}
        for position in ranked:
            score = float(scores[position])
            if score <= 0:
                break
            position = int(position)
            match = reference(position)
            nearest_by_verdict.setdefault(match["verdict"], match)
            if len(results) < limit:
                results.append(match)

        return {
            "available": True,
            "problem_id": problem_id,
            "indexed_count": len(index.records),
            "missing_source_count": index.missing_sources,
            "oversized_source_count": index.oversized_sources,
            "results": results,
            "nearest_by_verdict": list(nearest_by_verdict.values()),
            "note": (
                "Similarity is lexical TF-IDF evidence, not proof of correctness. "
                "CodeNet metadata does not include per-test-case outcomes."
            ),
        }

    @lru_cache(maxsize=4)
    def _load_problem_index(self, problem_id: str) -> _ProblemIndex:
        metadata_path = self.metadata_dir / f"{problem_id}.csv"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"CodeNet metadata does not exist: {metadata_path}")

        sampled: dict[str, list[tuple[str, Path]]] = {}
        seen: dict[str, int] = {}
        missing_sources = 0
        oversized_sources = 0
        rng = Random(problem_id)
        required_columns = {"submission_id", "problem_id", "language", "filename_ext", "status"}
        try:
            with metadata_path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
                    raise RuntimeError(
                        f"CodeNet metadata must contain columns: {', '.join(sorted(required_columns))}"
                    )
                for row in reader:
                    if (
                        row.get("problem_id", "").strip() != problem_id
                        or row.get("language", "").strip() != "C++"
                    ):
                        continue
                    verdict = _VERDICTS.get(row.get("status", "").strip())
                    if verdict is None:
                        continue
                    submission_id = row.get("submission_id", "").strip()
                    extension = row.get("filename_ext", "cpp").strip() or "cpp"
                    if not _SUBMISSION_ID.fullmatch(submission_id) or not _FILE_EXTENSION.fullmatch(
                        extension
                    ):
                        continue
                    code_path = (
                        self.data_dir
                        / problem_id
                        / "C++"
                        / f"{submission_id}.{extension}"
                    )
                    try:
                        size = code_path.stat().st_size
                    except FileNotFoundError:
                        missing_sources += 1
                        continue
                    except OSError as exc:
                        raise RuntimeError(
                            f"Could not inspect CodeNet source at {code_path}: {exc}"
                        ) from exc
                    if size > _MAX_SOURCE_BYTES:
                        oversized_sources += 1
                        continue

                    count = seen.get(verdict, 0) + 1
                    seen[verdict] = count
                    bucket = sampled.setdefault(verdict, [])
                    candidate = (submission_id, code_path)
                    if len(bucket) < _MAX_REFERENCES_PER_VERDICT:
                        bucket.append(candidate)
                    else:
                        replacement = rng.randrange(count)
                        if replacement < _MAX_REFERENCES_PER_VERDICT:
                            bucket[replacement] = candidate
        except (OSError, UnicodeError, csv.Error) as exc:
            raise RuntimeError(f"Could not read CodeNet metadata at {metadata_path}: {exc}") from exc

        records: list[dict[str, str]] = []
        for verdict, references in sorted(sampled.items()):
            for submission_id, code_path in references:
                try:
                    source_code = code_path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    raise RuntimeError(f"Could not read CodeNet source at {code_path}: {exc}") from exc
                if len(source_code.strip()) < 3:
                    continue
                records.append(
                    {
                        "submission_id": submission_id,
                        "verdict": verdict,
                        "source_code": source_code,
                    }
                )

        if not records:
            return _ProblemIndex(
                records=(),
                vectorizer=TfidfVectorizer(analyzer="char", ngram_range=(3, 5)),
                matrix=None,
                missing_sources=missing_sources,
                oversized_sources=oversized_sources,
            )

        vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            max_features=100_000,
        )
        matrix = vectorizer.fit_transform([record["source_code"] for record in records])
        return _ProblemIndex(
            records=tuple(records),
            vectorizer=vectorizer,
            matrix=matrix,
            missing_sources=missing_sources,
            oversized_sources=oversized_sources,
        )
