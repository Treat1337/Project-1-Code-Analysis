"""
app/services/codebert_service.py — Re-export of CodeBERT model.

Logic giữ nguyên trong codebert_model.py.
File này đặt tên theo target architecture.
"""
from app.services.codebert_model import (
    CODEBERT_MODEL,
    TrainedCodeBERTModel,
)

__all__ = [
    "CODEBERT_MODEL",
    "TrainedCodeBERTModel",
]
