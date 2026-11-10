from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.config import MAX_CODE_BYTES, MAX_INPUT_BYTES, MAX_TEST_CASES


class TestCase(BaseModel):
    stdin: str = ""
    expected_stdout: str

    @field_validator("stdin")
    @classmethod
    def validate_stdin_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError(f"Test input must not exceed {MAX_INPUT_BYTES} bytes")
        return value


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1)
    test_cases: list[TestCase] = Field(min_length=1, max_length=MAX_TEST_CASES)
    problem_id: str | None = Field(default=None, pattern=r"^p\d{5}$")
    similarity_limit: int = Field(default=5, ge=1, le=10)

    @field_validator("code")
    @classmethod
    def validate_code_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CODE_BYTES:
            raise ValueError(f"Code must not exceed {MAX_CODE_BYTES} bytes")
        return value


class FeedbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_BYTES)
    verdict: Literal[
        "COMPILE_ERROR",
        "WRONG_ANSWER",
        "RUNTIME_ERROR",
        "TIME_LIMIT_EXCEEDED",
        "ACCEPTED",
    ]
    diagnostic: str = Field(default="", max_length=8192)
    static_analysis: str = Field(default="", max_length=8192)
    learning_context: str = Field(default="", max_length=4000)
    tests: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_TEST_CASES)

    @field_validator("code")
    @classmethod
    def validate_code_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CODE_BYTES:
            raise ValueError(f"Code must not exceed {MAX_CODE_BYTES} bytes")
        return value


class ClassifyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_BYTES)
    compiler_message: str = Field(default="", max_length=8192)

    @field_validator("code")
    @classmethod
    def validate_code_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CODE_BYTES:
            raise ValueError(f"Code must not exceed {MAX_CODE_BYTES} bytes")
        return value


class AttemptTestResult(BaseModel):
    case_id: int = Field(
        ge=1,
        le=MAX_TEST_CASES,
        validation_alias=AliasChoices("case_id", "case"),
    )
    status: Literal[
        "PASSED",
        "FAILED",
        "WRONG_ANSWER",
        "RUNTIME_ERROR",
        "TIME_LIMIT_EXCEEDED",
    ]


class SubmissionAttempt(BaseModel):
    verdict: Literal[
        "COMPILE_ERROR",
        "WRONG_ANSWER",
        "RUNTIME_ERROR",
        "TIME_LIMIT_EXCEEDED",
        "ACCEPTED",
    ]
    tests: list[AttemptTestResult] = Field(default_factory=list, max_length=MAX_TEST_CASES)


class KnowledgeTraceRequest(BaseModel):
    history: list[SubmissionAttempt] = Field(min_length=1, max_length=100)
    next_test_case_ids: list[int] = Field(default_factory=list, max_length=MAX_TEST_CASES)

    @field_validator("next_test_case_ids")
    @classmethod
    def validate_next_case_ids(cls, value: list[int]) -> list[int]:
        if any(case_id < 1 or case_id > MAX_TEST_CASES for case_id in value):
            raise ValueError(f"Test case IDs must be between 1 and {MAX_TEST_CASES}")
        if len(set(value)) != len(value):
            raise ValueError("Test case IDs must be unique")
        return value


class MisconceptionAttempt(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_BYTES)
    verdict: Literal[
        "COMPILE_ERROR",
        "WRONG_ANSWER",
        "RUNTIME_ERROR",
        "TIME_LIMIT_EXCEEDED",
        "ACCEPTED",
    ]
    diagnostic: str = Field(default="", max_length=8192)

    @field_validator("code")
    @classmethod
    def validate_code_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CODE_BYTES:
            raise ValueError(f"Code must not exceed {MAX_CODE_BYTES} bytes")
        return value


class MisconceptionRequest(BaseModel):
    attempts: list[MisconceptionAttempt] = Field(min_length=2, max_length=100)
