from __future__ import annotations

import csv
import math
import random
import sys
from concurrent.futures import ThreadPoolExecutor
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


def format_model_text(
    code: str,
    compiler_message: str = "",
    problem_description: str = "",
    sample_input: str = "",
    sample_output: str = "",
) -> str:
    """Build the same model input for training and serving."""
    parts = [
        "<CODE>",
        code.strip(),
        "</CODE>",
    ]
    context = {
        "COMPILER_MESSAGE": compiler_message,
        "PROBLEM": problem_description,
        "SAMPLE_INPUT": sample_input,
        "SAMPLE_OUTPUT": sample_output,
    }
    for name, value in context.items():
        if value.strip():
            parts.extend((f"<{name}>", value.strip(), f"</{name}>"))
    return "\n".join(parts)


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


def _load_metadata_folder(
    metadata_path: Path,
    data_dir: Path,
) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
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
            if code:
                samples.append(
                    {
                        "code": code,
                        "label": label,
                        "compiler_message": "",
                        "problem_id": problem_id,
                        "submission_id": submission_id,
                    }
                )
    return samples


def load_examples(
    dataset_path: Path,
    max_per_label: int = 500,
    folder_fraction: float = 1.0,
    folder_batch_size: int = 50,
    seed: int = 42,
    io_workers: int = 8,
) -> list[dict[str, str]]:
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
    if not 0 < folder_fraction <= 1:
        raise ValueError("folder_fraction must be greater than 0 and at most 1")
    if folder_batch_size < 1:
        raise ValueError("folder_batch_size must be positive")
    if io_workers < 1:
        raise ValueError("io_workers must be positive")

    rng = random.Random(seed)
    samples: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: dict[str, int] = defaultdict(int)
    contexts: dict[str, tuple[str, str, str]] = {}
    metadata_files = sorted(metadata_dir.glob("p[0-9][0-9][0-9][0-9][0-9].csv"))
    if not metadata_files:
        raise FileNotFoundError(f"No CodeNet metadata CSV files found in {metadata_dir}")

    target_folder_count = max(1, round(len(metadata_files) * folder_fraction))
    selected_indices = sorted(rng.sample(range(len(metadata_files)), target_folder_count))
    selected_metadata_files = [metadata_files[index] for index in selected_indices]

    print(
        f"Folders | selected {target_folder_count}/{len(metadata_files)} "
        f"({folder_fraction:.0%}) | batch size {folder_batch_size}",
        flush=True,
    )

    for batch_start in range(0, len(selected_metadata_files), folder_batch_size):
        metadata_batch = selected_metadata_files[batch_start:batch_start + folder_batch_size]
        batch_folder_count = len(metadata_batch)
        processed_folder_count = min(batch_start + batch_folder_count, target_folder_count)

        with ThreadPoolExecutor(max_workers=io_workers) as executor:
            folder_results = executor.map(
                lambda path: _load_metadata_folder(path, data_dir),
                metadata_batch,
            )
            for folder_samples in folder_results:
                for sample in folder_samples:
                    label = sample["label"]
                    problem_id = sample["problem_id"]
                    seen[label] += 1
                    if problem_id not in contexts:
                        contexts[problem_id] = _load_problem_context(dataset_path, problem_id)
                    description, sample_input, sample_output = contexts[problem_id]
                    sample.update(
                        {
                            "problem_description": description,
                            "sample_input": sample_input,
                            "sample_output": sample_output,
                        }
                    )
                    bucket = samples[label]
                    if max_per_label == 0 or len(bucket) < max_per_label:
                        bucket.append(sample)
                    else:
                        replacement = rng.randrange(seen[label])
                        if replacement < max_per_label:
                            bucket[replacement] = sample

        print(
            f"Data pushed | {processed_folder_count}/{target_folder_count} folders "
            f"| batch {batch_start // folder_batch_size + 1}/"
            f"{math.ceil(target_folder_count / folder_batch_size)}",
            flush=True,
        )
    examples = [sample for label in sorted(samples) for sample in samples[label]]
    print(f"CodeNet | loaded {len(examples)} balanced samples from {dataset_path}", flush=True)
    return examples


def _load_csv(dataset_path: Path) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    csv.field_size_limit(min(sys.maxsize, (1 << 31) - 1))
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
