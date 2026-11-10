from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch


class TrainedCodeClassifier:
    def __init__(self, model_dir: Path, device: str | None = None) -> None:
        self.model_dir = model_dir
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        with (model_dir / "model.json").open(encoding="utf-8") as source:
            metadata: dict[str, Any] = json.load(source)

        model_type = metadata.get("model_type")
        if model_type == "codebert":
            from app.services.codebert_model import TrainedCodeBERTModel

            self.model = TrainedCodeBERTModel(model_dir, metadata, self.device)
        elif model_type == "astnn":
            from app.services.astnn_model import TrainedASTNNModel

            self.model = TrainedASTNNModel(model_dir, metadata, self.device)
        else:
            raise ValueError(f"Unsupported neural model type: {model_type}")

    def predict(self, code: str, compiler_message: str = "") -> dict[str, Any]:
        return self.model.predict(code, compiler_message)
