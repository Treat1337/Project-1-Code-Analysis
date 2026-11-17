from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

STATUS_LABELS = {
    "Accepted": "accepted",
    "Compile Error": "compile_error",
    "Wrong Answer": "wrong_answer",
    "Time Limit Exceeded": "time_limit_exceeded",
    "Memory Limit Exceeded": "memory_limit_exceeded",
    "WA: Presentation Error": "presentation_error",
    "Runtime Error": "runtime_error",
    "Output Limit Exceeded": "output_limit_exceeded",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def load_examples(dataset_path: Path, max_per_label: int = 500) -> list[dict[str, str]]:
    if dataset_path.is_file():
        with dataset_path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        return [row for row in rows if (row.get("code") or "").strip() and row.get("label")]
    if not dataset_path.is_dir():
        raise FileNotFoundError(f"Dataset does not exist: {dataset_path}")
    metadata_dir, data_dir = dataset_path / "metadata", dataset_path / "data"
    if not metadata_dir.is_dir() or not data_dir.is_dir():
        raise ValueError(f"Expected CodeNet folders metadata and data under {dataset_path}")
    rng = random.Random(42)
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: dict[str, int] = defaultdict(int)
    for metadata_path in sorted(metadata_dir.glob("p[0-9][0-9][0-9][0-9][0-9].csv")):
        with metadata_path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                label = STATUS_LABELS.get((row.get("status") or "").strip())
                if (row.get("language") or "").strip() != "C++" or label is None:
                    continue
                problem_id = (row.get("problem_id") or "").strip()
                submission_id = (row.get("submission_id") or "").strip()
                extension = (row.get("filename_ext") or "cpp").strip() or "cpp"
                code = _read(data_dir / problem_id / "C++" / f"{submission_id}.{extension}").strip()
                if not code:
                    continue
                seen[label] += 1
                io_dir = dataset_path / "derived" / "input_output" / "data" / problem_id
                sample = {
                    "code": code, "label": label, "compiler_message": "",
                    "problem_id": problem_id, "submission_id": submission_id,
                    "problem_description": _read(dataset_path / "problem_descriptions" / f"{problem_id}.html"),
                    "sample_input": _read(io_dir / "input.txt"),
                    "sample_output": _read(io_dir / "output.txt"),
                }
                bucket = buckets[label]
                if max_per_label == 0 or len(bucket) < max_per_label:
                    bucket.append(sample)
                elif rng.randrange(seen[label]) < max_per_label:
                    bucket[rng.randrange(max_per_label)] = sample
    examples = [item for label in sorted(buckets) for item in buckets[label]]
    print(f"CodeNet | loaded {len(examples)} balanced samples from {dataset_path}", flush=True)
    return examples
