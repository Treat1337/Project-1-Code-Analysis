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


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_problem_context(root: Path, problem_id: str) -> tuple[str, str, str]:
    description = _read_text(root / "problem_descriptions" / f"{problem_id}.html")
    input_dir = root / "derived" / "input_output" / "data" / problem_id
    sample_input = _read_text(input_dir / "input.txt")
    sample_output = _read_text(input_dir / "output.txt")
    return description, sample_input, sample_output


def load_examples(dataset_path: Path, max_per_label: int = 500) -> list[dict[str, str]]:
    """Load CSV examples or sample balanced C++ submissions directly from CodeNet."""
    if dataset_path.is_file():
        return _load_csv(dataset_path)
    if not dataset_path.is_dir():
        raise FileNotFoundError(f"Dataset does not exist: {dataset_path}")

    metadata_dir = dataset_path / "metadata"
    data_dir = dataset_path / "data"
    if not metadata_dir.is_dir() or not data_dir.is_dir():
        raise ValueError(
            f"Expected CodeNet folders metadata and data under {dataset_path}"
        )
    if max_per_label < 0:
        raise ValueError("max_per_label must be non-negative")

    rng = random.Random(42)
    samples: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: dict[str, int] = defaultdict(int)
    contexts: dict[str, tuple[str, str, str]] = {}
    metadata_files = sorted(metadata_dir.glob("p[0-9][0-9][0-9][0-9][0-9].csv"))
    if not metadata_files:
        raise FileNotFoundError(f"No CodeNet metadata CSV files found in {metadata_dir}")

    for metadata_path in metadata_files:
        with metadata_path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if row.get("language", "").strip() != "C++":
                    continue
                label = STATUS_LABELS.get(row.get("status", "").strip())
                if label is None:
                    continue
                problem_id = row.get("problem_id", "").strip()
                submission_id = row.get("submission_id", "").strip()
                extension = row.get("filename_ext", "cpp").strip() or "cpp"
                code_path = data_dir / problem_id / "C++" / f"{submission_id}.{extension}"
                code = _read_text(code_path).strip()
                if not code:
                    continue
                seen[label] += 1
                if problem_id not in contexts:
                    contexts[problem_id] = _load_problem_context(dataset_path, problem_id)
                description, sample_input, sample_output = contexts[problem_id]
                sample = {
                    "code": code,
                    "label": label,
                    "compiler_message": "",
                    "problem_id": problem_id,
                    "problem_description": description,
                    "sample_input": sample_input,
                    "sample_output": sample_output,
                    "submission_id": submission_id,
                }
                bucket = samples[label]
                if max_per_label == 0 or len(bucket) < max_per_label:
                    bucket.append(sample)
                else:
                    replacement = rng.randrange(seen[label])
                    if replacement < max_per_label:
                        bucket[replacement] = sample
    examples = [sample for label in sorted(samples) for sample in samples[label]]
    print(f"CodeNet | loaded {len(examples)} balanced samples from {dataset_path}", flush=True)
    return examples


def _load_csv(dataset_path: Path) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    with dataset_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"code", "label"}.issubset(reader.fieldnames or set()):
            raise ValueError("Dataset CSV must include 'code' and 'label' columns")
        for row in reader:
            code = (row.get("code") or "").strip()
            label = (row.get("label") or "").strip()
            if code and label:
                examples.append(dict(row))
    return examples
