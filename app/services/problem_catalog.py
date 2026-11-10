from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re

from app.config import DATASET_DIR


_SAMPLE_INPUT = re.compile(r"sample\s+input\s*(\d+)", re.IGNORECASE)
_SAMPLE_OUTPUT = re.compile(
    r"output\s+for\s+(?:the\s+)?sample\s+input\s*(\d+)", re.IGNORECASE
)
_PROBLEM_ID = re.compile(r"p\d{5}")


@dataclass(frozen=True)
class Problem:
    problem_id: str
    title: str
    html: str
    sample_test_cases: list[dict[str, str]]


class _StatementParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.sections: list[tuple[str, str]] = []
        self._heading: str | None = None
        self._heading_parts: list[str] = []
        self._pre_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"h1", "h2", "h3"}:
            self._heading = tag.lower()
            self._heading_parts = []
        elif tag.lower() == "pre":
            self._pre_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"h1", "h2", "h3"} and self._heading == normalized:
            heading = " ".join("".join(self._heading_parts).split())
            if normalized == "h1":
                self.title_parts.append(heading)
            self._heading = None
        elif normalized == "pre" and self._pre_parts is not None:
            self.sections.append(
                (" ".join(self._heading_parts).strip(), "".join(self._pre_parts).strip())
            )
            self._pre_parts = None

    def handle_data(self, data: str) -> None:
        if self._heading:
            self._heading_parts.append(data)
        if self._pre_parts is not None:
            self._pre_parts.append(data)


def _descriptions_dir() -> Path:
    return DATASET_DIR / "Project_CodeNet" / "problem_descriptions"


def _input_output_dir(problem_id: str) -> Path:
    return (
        DATASET_DIR
        / "Project_CodeNet"
        / "derived"
        / "input_output"
        / "data"
        / problem_id
    )


def list_problem_ids() -> list[str]:
    descriptions = _descriptions_dir()
    if not descriptions.is_dir():
        raise FileNotFoundError(f"Problem descriptions directory does not exist: {descriptions}")
    return sorted(
        path.stem for path in descriptions.glob("p*.html") if _PROBLEM_ID.fullmatch(path.stem)
    )


def extract_sample_test_cases(sections: list[tuple[str, str]]) -> list[dict[str, str]]:
    samples: dict[int, dict[str, str]] = {}
    for heading, content in sections:
        output_match = _SAMPLE_OUTPUT.search(heading)
        if output_match:
            samples.setdefault(int(output_match.group(1)), {})["expected_stdout"] = content
            continue
        input_match = _SAMPLE_INPUT.search(heading)
        if input_match:
            samples.setdefault(int(input_match.group(1)), {})["stdin"] = content
    return [
        {"stdin": sample["stdin"], "expected_stdout": sample["expected_stdout"]}
        for _, sample in sorted(samples.items())
        if "stdin" in sample and "expected_stdout" in sample
    ]


def load_derived_test_cases(problem_id: str) -> list[dict[str, str]]:
    data_dir = _input_output_dir(problem_id)
    input_path = data_dir / "input.txt"
    output_path = data_dir / "output.txt"
    if not input_path.is_file() or not output_path.is_file():
        return []
    return [
        {
            "stdin": input_path.read_text(encoding="utf-8"),
            "expected_stdout": output_path.read_text(encoding="utf-8"),
        }
    ]


def load_problem(problem_id: str) -> Problem:
    if not _PROBLEM_ID.fullmatch(problem_id):
        raise ValueError(f"Invalid problem ID: {problem_id}")
    path = _descriptions_dir() / f"{problem_id}.html"
    source = path.read_text(encoding="utf-8")
    parser = _StatementParser()
    parser.feed(source)
    sample_test_cases = load_derived_test_cases(problem_id)
    if not sample_test_cases:
        sample_test_cases = extract_sample_test_cases(parser.sections)
    return Problem(
        problem_id=problem_id,
        title=parser.title_parts[0] if parser.title_parts else problem_id,
        html=source,
        sample_test_cases=sample_test_cases,
    )
