import json
import urllib.error
import urllib.request
from typing import Any

from app.config import AI_API_KEY, AI_BASE_URL, AI_MODEL, KNOWLEDGE_PATH
from app.services.retrieval import KnowledgeBase


class LLMProviderError(RuntimeError):
    pass


def explain(
    code: str,
    verdict: str,
    diagnostic: str,
    knowledge_base: KnowledgeBase,
    static_analysis: str = "",
    learning_context: str = "",
    tests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tests = tests or []
    documents = knowledge_base.search(
        f"{verdict} {diagnostic}\n{static_analysis}\n"
        f"{_test_evidence(tests)}\n{code}",
        limit=3,
    )
    evidence = _build_evidence(verdict, diagnostic, static_analysis, tests)
    if not AI_API_KEY:
        return {
            "mode": "local",
            "explanation": _local_explanation(
                verdict, diagnostic, static_analysis, documents, learning_context, tests
            ),
            "evidence": evidence,
            "sources": [doc["title"] for doc in documents],
        }

    context = "\n\n".join(f"[{doc['title']}]\n{doc['content']}" for doc in documents)
    payload = {
        "model": AI_MODEL,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Bạn là trợ giảng C++ cho sinh viên mới học. Chỉ giải thích dựa trên "
                    "verdict, chẩn đoán và tài liệu được cung cấp; không khẳng định nguyên "
                    "nhân chưa được chứng minh. Không viết lại toàn bộ bài giải. Với "
                    "WRONG_ANSWER, phải nêu input, output thực tế, output mong đợi và "
                    "khác biệt đầu tiên nếu có. Nếu chưa đủ bằng chứng để chỉ ra dòng code, "
                    "hãy nói rõ chưa thể kết luận, không được bịa dòng. Trả lời bằng tiếng "
                    "Việt, có các mục: Kết luận, Bằng chứng, Vùng code cần kiểm tra, "
                    "Bước sửa/kiểm thử tiếp theo."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Verdict từ runner: {verdict}\n"
                    f"Chẩn đoán: {diagnostic[:4000]}\n"
                    f"Cảnh báo phân tích tĩnh từ compiler: {static_analysis[:4000] or 'Không có.'}\n"
                    f"Bằng chứng từng test:\n{_test_evidence(tests) or 'Không có.'}\n"
                    f"Phân tích tiến trình/quan niệm sai lầm (chỉ là gợi ý thực nghiệm): "
                    f"{learning_context[:4000] or 'Không có.'}\n"
                    f"Code:\n{code[:16000]}\n\n"
                    f"Tài liệu tham khảo:\n{context or 'Không tìm thấy tài liệu phù hợp.'}"
                ),
            },
        ],
    }
    request = urllib.request.Request(
        f"{AI_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read(1_000_000))
        explanation = data["choices"][0]["message"]["content"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(f"LLM provider request failed: {exc}") from exc
    if not isinstance(explanation, str) or not explanation.strip():
        raise LLMProviderError("LLM provider returned an empty explanation")
    return {
        "mode": "llm",
        "explanation": explanation.strip(),
        "evidence": evidence,
        "sources": [doc["title"] for doc in documents],
    }


def _local_explanation(
    verdict: str,
    diagnostic: str,
    static_analysis: str,
    documents: list[dict[str, str]],
    learning_context: str = "",
    tests: list[dict[str, Any]] | None = None,
) -> str:
    tests = tests or []
    explanations = {
        "COMPILE_ERROR": "Trình biên dịch không tạo được chương trình. Hãy đọc dòng đầu tiên của thông báo lỗi và kiểm tra cú pháp, kiểu dữ liệu hoặc tên biến tại dòng được nêu.",
        "WRONG_ANSWER": "Chương trình đã chạy nhưng có test cho kết quả sai. Bằng chứng dưới đây cho biết chính xác input và vị trí khác biệt đầu tiên; đây là nơi nên bắt đầu kiểm tra logic.",
        "RUNTIME_ERROR": "Chương trình gặp lỗi trong lúc chạy. Kiểm tra truy cập ngoài phạm vi, phép chia cho 0, con trỏ và các giả định về dữ liệu đầu vào.",
        "TIME_LIMIT_EXCEEDED": "Chương trình vượt quá giới hạn thời gian ở ít nhất một test. Hãy xem lại vòng lặp và độ phức tạp thuật toán.",
        "ACCEPTED": "Chương trình biên dịch thành công và vượt qua tất cả test đã cung cấp. Điều này chỉ xác nhận các test hiện có, không đảm bảo mọi đầu vào.",
    }
    parts = [explanations.get(verdict, f"Runner trả về trạng thái {verdict}.")]
    if diagnostic.strip():
        parts.append(f"Chẩn đoán thực tế: {diagnostic.strip()[:1200]}")
    parts.extend(_test_findings(verdict, tests))
    if static_analysis.strip():
        parts.append(f"Cảnh báo compiler: {static_analysis.strip()[:1200]}")
    if documents:
        parts.append(f"Kiến thức liên quan: {documents[0]['content']}")
    if learning_context.strip():
        parts.append(
            "Gợi ý từ phân tích lịch sử (chưa được kiểm chứng): "
            f"{learning_context.strip()[:1200]}"
        )
    return "\n\n".join(parts)


def _build_evidence(
    verdict: str,
    diagnostic: str,
    static_analysis: str,
    tests: list[dict[str, Any]],
) -> dict[str, Any]:
    failing = [test for test in tests if test.get("status") != "PASSED"]
    return {
        "verdict": verdict,
        "diagnostic": diagnostic,
        "static_analysis": static_analysis,
        "failing_tests": failing,
        "certainty": (
            "high" if diagnostic or failing else "limited"
        ),
        "note": (
            "Test failure identifies an input and output mismatch, not necessarily the exact "
            "source line responsible."
        ),
    }


def _test_evidence(tests: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for test in tests:
        case = test.get("case", "?")
        status = test.get("status", "UNKNOWN")
        lines.append(f"Test {case}: {status}")
        if test.get("stdin") is not None:
            lines.append(f"  Input: {str(test['stdin'])[:2000]}")
        if test.get("stdout") is not None:
            lines.append(f"  Actual output: {str(test['stdout'])[:2000]}")
        if test.get("expected_stdout") is not None:
            lines.append(f"  Expected output: {str(test['expected_stdout'])[:2000]}")
        diff = test.get("output_diff")
        if diff and diff.get("first_difference"):
            first = diff["first_difference"]
            lines.append(
                f"  First token difference #{first['token_index']}: "
                f"actual={first['actual']!r}, expected={first['expected']!r}"
            )
        if test.get("stderr"):
            lines.append(f"  stderr: {str(test['stderr'])[:2000]}")
    return "\n".join(lines)


def _test_findings(verdict: str, tests: list[dict[str, Any]]) -> list[str]:
    if verdict != "WRONG_ANSWER":
        return []
    findings: list[str] = []
    for test in tests:
        if test.get("status") != "WRONG_ANSWER":
            continue
        case = test.get("case", "?")
        findings.append(f"Bằng chứng Test {case}:\n{_test_evidence([test])}")
        diff = test.get("output_diff")
        if diff and diff.get("first_difference"):
            first = diff["first_difference"]
            findings.append(
                f"Khác biệt đầu tiên ở token {first['token_index']}: "
                f"chương trình in {first['actual']!r}, nhưng cần {first['expected']!r}."
            )
    if not findings:
        findings.append(
            "Chưa có output thực tế/expected trong dữ liệu runner nên chưa thể xác định "
            "khác biệt cụ thể."
        )
    return findings


def load_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase.from_json(KNOWLEDGE_PATH)
