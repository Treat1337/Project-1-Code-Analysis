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
) -> dict[str, Any]:
    documents = knowledge_base.search(
        f"{verdict} {diagnostic}\n{static_analysis}\n{code}", limit=3
    )
    if not AI_API_KEY:
        return {
            "mode": "local",
            "explanation": _local_explanation(
                verdict, diagnostic, static_analysis, documents, learning_context
            ),
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
                    "nhân chưa được chứng minh. Không viết lại toàn bộ bài giải. Trả lời "
                    "bằng tiếng Việt, ngắn gọn, gồm nguyên nhân có căn cứ và một gợi ý học tập."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Verdict từ runner: {verdict}\n"
                    f"Chẩn đoán: {diagnostic[:4000]}\n"
                    f"Cảnh báo phân tích tĩnh từ compiler: {static_analysis[:4000] or 'Không có.'}\n"
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
        "sources": [doc["title"] for doc in documents],
    }


def _local_explanation(
    verdict: str,
    diagnostic: str,
    static_analysis: str,
    documents: list[dict[str, str]],
    learning_context: str = "",
) -> str:
    explanations = {
        "COMPILE_ERROR": "Trình biên dịch không tạo được chương trình. Hãy đọc dòng đầu tiên của thông báo lỗi và kiểm tra cú pháp, kiểu dữ liệu hoặc tên biến tại dòng được nêu.",
        "WRONG_ANSWER": "Chương trình đã chạy nhưng đầu ra chưa khớp đáp án chuẩn ở ít nhất một test. Hãy đối chiếu đầu vào, đầu ra mong đợi và kiểm tra các trường hợp biên.",
        "RUNTIME_ERROR": "Chương trình gặp lỗi trong lúc chạy. Kiểm tra truy cập ngoài phạm vi, phép chia cho 0, con trỏ và các giả định về dữ liệu đầu vào.",
        "TIME_LIMIT_EXCEEDED": "Chương trình vượt quá giới hạn thời gian ở ít nhất một test. Hãy xem lại vòng lặp và độ phức tạp thuật toán.",
        "ACCEPTED": "Chương trình biên dịch thành công và vượt qua tất cả test đã cung cấp. Điều này chỉ xác nhận các test hiện có, không đảm bảo mọi đầu vào.",
    }
    parts = [explanations.get(verdict, f"Runner trả về trạng thái {verdict}.")]
    if diagnostic.strip():
        parts.append(f"Chẩn đoán thực tế: {diagnostic.strip()[:1200]}")
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


def load_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase.from_json(KNOWLEDGE_PATH)
