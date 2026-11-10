from __future__ import annotations

import argparse
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
    "Runtime Error": "runtime_error",
    "WA: Presentation Error": "presentation_error",
    "Output Limit Exceeded": "output_limit_exceeded",
}


def export_dataset(
    metadata_dir: Path,
    data_dir: Path,
    destination: Path,
    max_per_label: int,
    seed: int,
) -> dict[str, int]:
    if max_per_label < 1:
        raise ValueError("max_per_label must be at least 1")
    rng = random.Random(seed)
    samples: dict[str, list[tuple[str, str, Path]]] = defaultdict(list)
    seen: dict[str, int] = defaultdict(int)

    metadata_files = sorted(metadata_dir.glob("p[0-9][0-9][0-9][0-9][0-9].csv"))
    if not metadata_files:
        raise FileNotFoundError(f"No Project CodeNet metadata CSV files found in {metadata_dir}")

    for file_index, metadata_path in enumerate(metadata_files, start=1):
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

                seen[label] += 1
                sample = (problem_id, label, code_path)
                bucket = samples[label]
                if len(bucket) < max_per_label:
                    bucket.append(sample)
                else:
                    replacement = rng.randrange(seen[label])
                    if replacement < max_per_label:
                        bucket[replacement] = sample
        if file_index % 100 == 0 or file_index == len(metadata_files):
            eligible = sum(seen.values())
            print(
                f"Metadata: {file_index}/{len(metadata_files)} files | "
                f"{eligible} labeled C++ submissions",
                flush=True,
            )

    samples = {
        label: [sample for sample in bucket if sample[2].is_file()]
        for label, bucket in samples.items()
    }
    counts: dict[str, int] = {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["code", "label", "compiler_message", "problem_id"],
        )
        writer.writeheader()
        for label in sorted(samples):
            for problem_id, sample_label, code_path in samples[label]:
                writer.writerow(
                    {
                        "code": code_path.read_text(encoding="utf-8", errors="replace"),
                        "label": sample_label,
                        "compiler_message": "",
                        "problem_id": problem_id,
                    }
                )
            counts[label] = len(samples[label])
    return counts


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Export a reproducible, balanced C++ verdict dataset from Project CodeNet."
    )
    parser.add_argument(
        "--project-codenet",
        type=Path,
        default=project_root / "Dataset" / "Project_CodeNet",
    )
    parser.add_argument("--output", type=Path, default=project_root / "Dataset" / "codenet_verdicts.csv")
    parser.add_argument("--max-per-label", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    counts = export_dataset(
        args.project_codenet / "metadata",
        args.project_codenet / "data",
        args.output,
        args.max_per_label,
        args.seed,
    )
    print(f"Wrote {sum(counts.values())} examples to {args.output}")
    for label, count in sorted(counts.items()):
        print(f"{label}: {count}")


if __name__ == "__main__":
    main()
