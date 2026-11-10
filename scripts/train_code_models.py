from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from torch import Tensor, nn
from torch.optim import AdamW
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.services.astnn_model import (
    ASTNNClassifier,
    ASTNN_UNKNOWN_TOKEN,
    build_ast_vocabulary,
    create_cpp_parser,
    encode_ast,
)
from app.services.codebert_model import CODEBERT_MODEL


def load_examples(dataset_path: Path) -> list[dict[str, str]]:
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
                examples.append(
                    {
                        "code": code,
                        "label": label,
                        "compiler_message": (row.get("compiler_message") or "").strip(),
                        "problem_id": (row.get("problem_id") or "").strip(),
                    }
                )
                if len(examples) % 500 == 0:
                    print(f"Đã đọc {len(examples)} mẫu hợp lệ...", flush=True)
    print(f"Valid samples: {len(examples)}", flush=True)
    labels = {sample["label"] for sample in examples}
    if len(labels) < 2:
        raise ValueError("Dataset needs at least two labels with non-empty code")
    if any(sum(sample["label"] == label for sample in examples) < 2 for label in labels):
        raise ValueError("Dataset needs at least two examples per label")
    return examples


def split_examples(examples: list[dict[str, str]]) -> tuple[list[int], list[int]]:
    labels = [sample["label"] for sample in examples]
    classes = set(labels)
    groups = [sample["problem_id"] for sample in examples]
    if all(groups) and len(set(groups)) > 1:
        for seed in range(42, 62):
            train_indices, test_indices = next(
                GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(
                    examples, labels, groups
                )
            )
            if (
                {labels[index] for index in train_indices} == classes
                and {labels[index] for index in test_indices} == classes
            ):
                return train_indices.tolist(), test_indices.tolist()
        raise ValueError(
            "Could not make a problem-disjoint split containing every label in both sets. "
            "Add more problems per label or remove the problem_id column."
        )

    test_count = max(len(classes), math.ceil(len(examples) * 0.2))
    if len(examples) - test_count < len(classes):
        raise ValueError(
            "Not enough samples for a stratified train/test split; add more examples per label."
        )
    train_indices, test_indices = train_test_split(
        np.arange(len(examples)),
        test_size=test_count,
        random_state=42,
        stratify=labels,
    )
    return train_indices.tolist(), test_indices.tolist()


def _batches(indices: list[int], batch_size: int, shuffle: bool) -> list[list[int]]:
    order = indices.copy()
    if shuffle:
        random.shuffle(order)
    return [order[start : start + batch_size] for start in range(0, len(order), batch_size)]


def _class_weights(labels: list[str], classes: list[str], device: torch.device) -> Tensor:
    counts = np.asarray([labels.count(label) for label in classes], dtype=np.float32)
    weights = len(labels) / (len(classes) * counts)
    return torch.tensor(weights, dtype=torch.float32, device=device)


def _report(
    model_name: str,
    true_labels: list[str],
    predicted_labels: list[str],
    classes: list[str],
) -> dict[str, Any]:
    return {
        "model": model_name,
        "accuracy": round(accuracy_score(true_labels, predicted_labels), 4),
        "macro_f1": round(
            f1_score(true_labels, predicted_labels, labels=classes, average="macro", zero_division=0),
            4,
        ),
        "classification_report": classification_report(
            true_labels,
            predicted_labels,
            labels=classes,
            output_dict=True,
            zero_division=0,
        ),
    }


def train_codebert(
    examples: list[dict[str, str]],
    train_indices: list[int],
    test_indices: list[int],
    classes: list[str],
    output_dir: Path,
    device: torch.device,
    epochs: int,
    batch_size: int,
    max_length: int,
    model_name: str,
) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(classes),
        id2label=dict(enumerate(classes)),
        label2id={label: index for index, label in enumerate(classes)},
    ).to(device)
    optimizer = AdamW(model.parameters(), lr=2e-5)
    label_ids = {label: index for index, label in enumerate(classes)}
    weights = _class_weights([examples[i]["label"] for i in train_indices], classes, device)

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        batch_count = 0
        processed = 0
        progress_interval = max(1, len(train_indices) // (batch_size * 20))
        for indices in _batches(train_indices, batch_size, shuffle=True):
            texts = [
                f'{examples[i]["code"]}\n{examples[i]["compiler_message"]}'.strip()
                for i in indices
            ]
            inputs = tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            ).to(device)
            targets = torch.tensor(
                [label_ids[examples[i]["label"]] for i in indices], device=device
            )
            optimizer.zero_grad()
            logits = model(**inputs).logits
            loss = nn.functional.cross_entropy(logits, targets, weight=weights)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += float(loss.detach())
            batch_count += 1
            processed += len(indices)
            if batch_count % progress_interval == 0 or processed == len(train_indices):
                print(
                    f"CodeBERT | epoch {epoch + 1}/{epochs} | "
                    f"train {processed}/{len(train_indices)} mẫu "
                    f"({processed / len(train_indices):.0%}) | "
                    f"loss={total_loss / batch_count:.4f}",
                    flush=True,
                )

    model.eval()
    predictions: list[str] = []
    with torch.no_grad():
        test_batches = _batches(test_indices, batch_size, shuffle=False)
        for batch_number, indices in enumerate(test_batches, start=1):
            texts = [
                f'{examples[i]["code"]}\n{examples[i]["compiler_message"]}'.strip()
                for i in indices
            ]
            inputs = tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            ).to(device)
            logits = model(**inputs).logits
            predictions.extend(classes[index] for index in logits.argmax(dim=-1).tolist())
            print(
                f"CodeBERT | test evaluation {min(batch_number * batch_size, len(test_indices))}"
                f"/{len(test_indices)} mẫu",
                flush=True,
            )

    model_dir = output_dir / "codebert"
    model_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(model_dir)
    tokenizer.save_pretrained(model_dir)
    (model_dir / "model.json").write_text(
        json.dumps(
            {"model_type": "codebert", "labels": classes, "max_length": max_length},
            indent=2,
        ),
        encoding="utf-8",
    )
    metrics = _report(
        "codebert",
        [examples[i]["label"] for i in test_indices],
        predictions,
        classes,
    )
    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def train_astnn(
    examples: list[dict[str, str]],
    train_indices: list[int],
    test_indices: list[int],
    classes: list[str],
    output_dir: Path,
    device: torch.device,
    epochs: int,
    batch_size: int,
) -> dict[str, Any]:
    print("ASTNN | đang tạo bộ từ vựng AST...", flush=True)
    parser = create_cpp_parser()
    vocabulary = build_ast_vocabulary(
        [examples[i]["code"] for i in train_indices],
        parser,
    )
    encoded: list[list[Any]] = []
    progress_interval = max(1, len(examples) // 20)
    for index, sample in enumerate(examples, start=1):
        encoded.append(encode_ast(sample["code"], vocabulary, parser))
        if index % progress_interval == 0 or index == len(examples):
            print(
                f"ASTNN | AST encoding {index}/{len(examples)} samples "
                f"({index / len(examples):.0%})",
                flush=True,
            )
    model = ASTNNClassifier(len(vocabulary), len(classes)).to(device)
    optimizer = AdamW(model.parameters(), lr=1e-3)
    label_ids = {label: index for index, label in enumerate(classes)}
    weights = _class_weights([examples[i]["label"] for i in train_indices], classes, device)

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        batch_count = 0
        processed = 0
        progress_interval = max(1, len(train_indices) // (batch_size * 20))
        for indices in _batches(train_indices, batch_size, shuffle=True):
            targets = torch.tensor(
                [label_ids[examples[i]["label"]] for i in indices], device=device
            )
            optimizer.zero_grad()
            logits = model([encoded[i] for i in indices])
            loss = nn.functional.cross_entropy(logits, targets, weight=weights)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += float(loss.detach())
            batch_count += 1
            processed += len(indices)
            if batch_count % progress_interval == 0 or processed == len(train_indices):
                print(
                    f"ASTNN | epoch {epoch + 1}/{epochs} | "
                    f"train {processed}/{len(train_indices)} mẫu "
                    f"({processed / len(train_indices):.0%}) | "
                    f"loss={total_loss / batch_count:.4f}",
                    flush=True,
                )

    model.eval()
    predictions: list[str] = []
    with torch.no_grad():
        test_batches = _batches(test_indices, batch_size, shuffle=False)
        for batch_number, indices in enumerate(test_batches, start=1):
            logits = model([encoded[i] for i in indices])
            predictions.extend(classes[index] for index in logits.argmax(dim=-1).tolist())
            print(
                f"ASTNN | test evaluation {min(batch_number * batch_size, len(test_indices))}"
                f"/{len(test_indices)} mẫu",
                flush=True,
            )

    model_dir = output_dir / "astnn"
    model_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_dir / "model.pt")
    (model_dir / "model.json").write_text(
        json.dumps(
            {
                "model_type": "astnn",
                "labels": classes,
                "vocabulary": vocabulary,
                "unknown_token": ASTNN_UNKNOWN_TOKEN,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metrics = _report(
        "astnn",
        [examples[i]["label"] for i in test_indices],
        predictions,
        classes,
    )
    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main(default_model: str | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Train {default_model} on a labeled code CSV."
            if default_model
            else "Train and compare CodeBERT and ASTNN on a labeled code CSV."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "Dataset" / "codenet_verdicts.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "code-models",
    )
    if default_model is None:
        parser.add_argument("--model", choices=["both", "codebert", "astnn"], default="both")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    if default_model != "astnn":
        parser.add_argument("--max-length", type=int, default=512)
        parser.add_argument("--codebert-model", default=CODEBERT_MODEL)
    parser.add_argument("--device", default=None, help="Defaults to CUDA when available, otherwise CPU")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        parser.error("epochs and batch-size must be positive")
    if default_model != "astnn" and not 1 <= args.max_length <= 512:
        parser.error("max-length must be between 1 and 512")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if device.type == "cuda" and not torch.cuda.is_available():
        parser.error(
            "CUDA được yêu cầu nhưng PyTorch hiện tại không có CUDA. "
            "Cài bản PyTorch CUDA hoặc bỏ --device cuda để chạy bằng CPU."
        )
    print(f"Thiết bị train: {device}", flush=True)
    examples = load_examples(args.dataset)
    train_indices, test_indices = split_examples(examples)
    classes = sorted({sample["label"] for sample in examples})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "dataset": str(args.dataset),
        "sample_count": len(examples),
        "train_count": len(train_indices),
        "test_count": len(test_indices),
        "split": "problem-disjoint" if all(sample["problem_id"] for sample in examples) else "stratified",
        "labels": classes,
        "device": str(device),
        "results": [],
    }
    print(
        f"Dataset: total {len(examples)} | train {len(train_indices)} | "
        f"test {len(test_indices)} | labels {len(classes)}",
        flush=True,
    )

    trainers = {
        "codebert": lambda: train_codebert(
            examples, train_indices, test_indices, classes, args.output_dir,
            device, args.epochs, args.batch_size, args.max_length, args.codebert_model,
        ),
        "astnn": lambda: train_astnn(
            examples, train_indices, test_indices, classes, args.output_dir,
            device, args.epochs, args.batch_size,
        ),
    }
    model_selection = default_model or args.model
    selected_models = ["codebert", "astnn"] if model_selection == "both" else [model_selection]
    for model_index, model_name in enumerate(selected_models, start=1):
        print(
            f"\n===== Model {model_index}/{len(selected_models)}: "
            f"{model_name.upper()} =====",
            flush=True,
        )
        report["results"].append(trainers[model_name]())

    report_path = args.output_dir / "comparison.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Comparison report: {report_path}")
    for result in report["results"]:
        print(f'{result["model"]}: accuracy={result["accuracy"]:.4f} '
              f'macro_f1={result["macro_f1"]:.4f}')


if __name__ == "__main__":
    main()
