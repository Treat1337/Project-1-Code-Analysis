"""
app/services/classifier_service.py — Re-export of CodeClassifier.

Logic giữ nguyên trong classifier.py.
File này đặt tên theo target architecture.
"""
from app.services.classifier import CodeClassifier

__all__ = ["CodeClassifier"]
