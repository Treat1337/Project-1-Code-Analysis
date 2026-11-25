"""
app/models.py — Backward-compatible re-export.

Schemas đã được chuyển vào app/schemas/schemas.py.
File này giữ lại để không làm hỏng import cũ trong tests và scripts.
"""
from app.schemas.schemas import (
    AnalyzeRequest,
    ApiAiRequest,
    ApiRunRequest,
    AttemptTestResult,
    ClassifyRequest,
    FeedbackRequest,
    KnowledgeTraceRequest,
    MisconceptionAttempt,
    MisconceptionRequest,
    RunRequest,
    SubmissionAttempt,
    TestCase,
)

__all__ = [
    "AnalyzeRequest",
    "ApiAiRequest",
    "ApiRunRequest",
    "AttemptTestResult",
    "ClassifyRequest",
    "FeedbackRequest",
    "KnowledgeTraceRequest",
    "MisconceptionAttempt",
    "MisconceptionRequest",
    "RunRequest",
    "SubmissionAttempt",
    "TestCase",
]
