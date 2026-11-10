#!/usr/bin/env python3
"""Keep only C++ submissions in Project CodeNet data and problem CSV files."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CsvPlan:
    path: Path
    encoding: str
    kept_rows: int
    removed_rows: int


def plan_csv(path: Path) -> CsvPlan:
    with path.open("rb") as source:
        has_bom = source.read(3) == b"\xef\xbb\xbf"
    encoding = "utf-8-sig" if has_bom else "utf-8"
    kept_rows = 0
    removed_rows = 0

    with path.open("r", encoding=encoding, newline="") as source:
        reader = csv.reader(source)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"CSV file is empty: {path}") from error

        if "language" not in header:
            raise ValueError(f"CSV has no 'language' column: {path}")
        language_index = header.index("language")

        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    f"Malformed CSV row in {path} at line {line_number}: "
                    f"expected {len(header)} columns, got {len(row)}"
                )
            if row[language_index].strip() == "C++":
                kept_rows += 1
            else:
                removed_rows += 1

    return CsvPlan(path, encoding, kept_rows, removed_rows)


def plan_data_directories(data_root: Path) -> list[Path]:
    directories_to_remove: list[Path] = []
    for problem_dir in sorted(data_root.iterdir()):
        if problem_dir.is_symlink():
            raise ValueError(f"Refusing to inspect a symbolic link: {problem_dir}")
        if not problem_dir.is_dir():
            continue
        for language_dir in sorted(problem_dir.iterdir()):
            if language_dir.is_symlink() and language_dir.name != "C++":
                raise ValueError(f"Refusing to remove a symbolic link: {language_dir}")
            if language_dir.is_dir() and language_dir.name != "C++":
                directories_to_remove.append(language_dir)
    return directories_to_remove


def count_cpp_codes(data_root: Path) -> int:
    count = 0
    for problem_dir in data_root.iterdir():
        if not problem_dir.is_dir():
            continue
        cpp_dir = problem_dir / "C++"
        if cpp_dir.is_dir():
            count += sum(
                1
                for code_file in cpp_dir.iterdir()
                if code_file.is_file() and code_file.suffix.lower() == ".cpp"
            )
    return count


def rewrite_csv(plan: CsvPlan) -> None:
    temporary_path: Path | None = None
    try:
        with plan.path.open("r", encoding=plan.encoding, newline="") as source:
            reader = csv.reader(source)
            header = next(reader)
            language_index = header.index("language")

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding=plan.encoding,
                newline="",
                dir=plan.path.parent,
                prefix=f".{plan.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                writer = csv.writer(temporary)
                writer.writerow(header)
                for row in reader:
                    if row[language_index].strip() == "C++":
                        writer.writerow(row)

        os.replace(temporary_path, plan.path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove non-C++ language directories under data/ and remove "
            "non-C++ rows from metadata/pNNNNN.csv."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project_CodeNet directory (defaults to this script's directory)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Perform deletions and rewrite CSV files, reporting progress every "
            "minute; without this, only preview"
        ),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    metadata_root = root / "metadata"
    data_root = root / "data"
    if not metadata_root.is_dir() or not data_root.is_dir():
        parser.error(f"{root} must contain both 'metadata' and 'data' directories")

    csv_paths = sorted(metadata_root.glob("p[0-9][0-9][0-9][0-9][0-9].csv"))
    if not csv_paths:
        parser.error(f"No problem CSV files found in {metadata_root}")
    if any(path.is_symlink() for path in csv_paths):
        parser.error("Refusing to modify symbolic links in the metadata directory")

    csv_plans = [plan_csv(path) for path in csv_paths]
    data_directories = plan_data_directories(data_root)
    removed_rows = sum(plan.removed_rows for plan in csv_plans)
    cpp_code_count = count_cpp_codes(data_root)

    action = "Will remove" if args.apply else "Would remove"
    print(f"{action} {removed_rows:,} non-C++ CSV rows from {len(csv_plans):,} files.")
    print(f"{action} {len(data_directories):,} non-C++ language directories.")
    print(f"Found {cpp_code_count:,} remaining C++ code files.")
    if not args.apply:
        print("Preview only. Re-run with --apply to make these changes.")
        return

    progress = {
        "removed_rows": 0,
        "completed_csv_files": 0,
        "removed_directories": 0,
    }
    progress_lock = threading.Lock()
    stop_progress = threading.Event()

    def report_progress() -> None:
        while not stop_progress.wait(60):
            with progress_lock:
                removed_rows = progress["removed_rows"]
                completed_csv_files = progress["completed_csv_files"]
                removed_directories = progress["removed_directories"]
            print(
                f"Progress: deleted {removed_rows:,} CSV rows "
                f"({completed_csv_files:,}/{len(csv_plans):,} files committed) "
                f"and {removed_directories:,}/{len(data_directories):,} "
                "language directories.",
                flush=True,
            )

    progress_thread = threading.Thread(target=report_progress, daemon=True)
    progress_thread.start()
    try:
        for plan in csv_plans:
            rewrite_csv(plan)
            with progress_lock:
                progress["removed_rows"] += plan.removed_rows
                progress["completed_csv_files"] += 1
        for directory in data_directories:
            shutil.rmtree(directory)
            with progress_lock:
                progress["removed_directories"] += 1
    finally:
        stop_progress.set()
        progress_thread.join()

    print(
        f"C++-only cleanup completed: deleted "
        f"{progress['removed_rows']:,} CSV rows and "
        f"{progress['removed_directories']:,} language directories."
    )


if __name__ == "__main__":
    main()
