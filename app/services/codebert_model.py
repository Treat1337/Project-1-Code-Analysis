from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


CODEBERT_MODEL = "microsoft/codebert-base"


class TrainedCodeBERTModel:
    def __init__(self, model_dir: Path, metadata: dict[str, Any], device: torch.device) -> None:
        self.device = device
        self.labels: list[str] = metadata["labels"]
        self.max_length = int(metadata["max_length"])
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self.model.to(device)
        self.model.eval()

    def predict(self, code: str, compiler_message: str = "") -> dict[str, Any]:
        with torch.no_grad():
            text = f"{code}\n{compiler_message}".strip()
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_length,
            ).to(self.device)
            logits = self.model(**inputs).logits[0]
            probabilities = torch.softmax(logits, dim=-1)
            confidence, index = torch.max(probabilities, dim=-1)
        return {
            "available": True,
            "label": self.labels[int(index)],
            "confidence": round(float(confidence), 4),
            "note": "Experimental prediction only; never overrides the compiler or test runner verdict.",
        }
