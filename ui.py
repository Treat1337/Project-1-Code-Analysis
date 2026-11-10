import os
from typing import Any

import requests
import streamlit as st
from streamlit_ace import st_ace

from app.services.problem_catalog import Problem, list_problem_ids, load_problem


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
VERDICT_STYLES = {
    "ACCEPTED": ("Accepted (AC)", "#28a745"),
    "WRONG_ANSWER": ("Wrong Answer (WA)", "#dc3545"),
    "TIME_LIMIT_EXCEEDED": ("Time Limit Exceeded (TLE)", "#ffc107"),
    "COMPILE_ERROR": ("Compilation Error (CE)", "#dc3545"),
    "RUNTIME_ERROR": ("Runtime Error (RE)", "#dc3545"),
}
STATUS_LABELS = {
    "solved": "Đã giải",
    "in_progress": "Đang làm",
    "not_started": "Chưa làm",
}


@st.cache_data(show_spinner=False)
def cached_problem_ids() -> list[str]:
    return list_problem_ids()


@st.cache_data(show_spinner=False)
def cached_problem(problem_id: str) -> Problem:
    return load_problem(problem_id)


@st.cache_data(ttl=5, show_spinner=False)
def get_api_health() -> dict[str, Any]:
    response = requests.get(f"{API_URL}/health", timeout=8)
    response.raise_for_status()
    return response.json()


def parse_test_cases(text: str) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    input_part: list[str] = []
    output_part: list[str] = []
    mode: str | None = None

    def content(lines: list[str]) -> str:
        return "\n".join(lines) + ("\n" if lines else "")

    for line in text.splitlines():
        marker = line.strip().lower()
        if marker in {"input:", "input"}:
            if mode is not None:
                cases.append(
                    {"stdin": content(input_part), "expected_stdout": content(output_part)}
                )
            input_part, output_part, mode = [], [], "input"
        elif marker in {"output:", "output", "expected:"}:
            mode = "output"
        elif mode == "input":
            input_part.append(line)
        elif mode == "output":
            output_part.append(line)
    if mode is not None:
        cases.append(
            {"stdin": content(input_part), "expected_stdout": content(output_part)}
        )
    return cases


def clear_editor(problem_id: str) -> None:
    code_key = f"cpp_code_{problem_id}"
    revision_key = f"cpp_editor_revision_{problem_id}"
    st.session_state[code_key] = ""
    st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1


st.set_page_config(page_title="Trợ giảng C++ AI", page_icon="🧑‍💻", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #101318; }
    [data-testid="stMetric"] {
        background: #1b2028; border: 1px solid #303744;
        padding: 14px; border-radius: 10px;
    }
    .verdict-card {
        padding: 14px 18px; border-radius: 10px; color: #fff;
        font-size: 1.25rem; font-weight: 700; margin: 4px 0 16px;
    }
    div[data-testid="stTabs"] button { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Trợ giảng phân tích code C++")
st.caption("Làm bài, chạy code trong Docker sandbox và xem phản hồi học tập trong một màn hình.")

try:
    health = get_api_health()
    runner = health["runner"]
except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f"Không thể kiểm tra API tại {API_URL}: {exc}")
    st.stop()

if runner.get("available"):
    st.success("Docker sandbox sẵn sàng.")
else:
    st.warning(f"Sandbox chưa sẵn sàng: {runner.get('reason', 'Không rõ nguyên nhân')}.")

try:
    problem_ids = cached_problem_ids()
except (OSError, ValueError) as exc:
    st.error(f"Không thể tải danh sách đề bài Project CodeNet: {exc}")
    st.stop()

if not problem_ids:
    st.error("Không tìm thấy đề bài Project CodeNet.")
    st.stop()

problem_status = st.session_state.setdefault("problem_status", {})

left, right = st.columns([1.05, 1], gap="large")

with left:
    st.subheader("Workspace")
    selected_id = st.selectbox(
        "Bài tập Project CodeNet",
        options=problem_ids,
        format_func=lambda problem_id: (
            f"{problem_id} — "
            f"{STATUS_LABELS[problem_status.get(problem_id, 'not_started')]}"
        ),
    )
    try:
        problem = cached_problem(selected_id)
    except (OSError, ValueError) as exc:
        st.error(f"Không thể tải đề {selected_id}: {exc}")
        st.stop()
    st.caption(f"{selected_id} · {problem.title}")
    with st.expander(f"Đề bài · {problem.title}", expanded=True):
        st.html(problem.html)

    st.markdown("#### Mã nguồn C++17")
    code_key = f"cpp_code_{selected_id}"
    revision_key = f"cpp_editor_revision_{selected_id}"
    editor_key = f"cpp_editor_{selected_id}_{st.session_state.get(revision_key, 0)}"
    if code_key not in st.session_state:
        st.session_state[code_key] = (
            "#include <iostream>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    // TODO: viết lời giải\n"
            "    return 0;\n"
            "}\n"
        )
    code = st_ace(
        value=st.session_state[code_key],
        language="c_cpp",
        theme="monokai",
        key=editor_key,
        height=360,
        font_size=14,
        tab_size=4,
        show_gutter=True,
        show_print_margin=False,
        wrap=True,
        auto_update=True,
    )
    if code is not None:
        st.session_state[code_key] = code
    else:
        code = st.session_state[code_key]

    st.markdown("#### Test cases")
    if problem.sample_test_cases:
        st.caption(
            "Đã nạp input/output mẫu từ dữ liệu bài toán; có thể sửa hoặc thêm test "
            "theo định dạng Input:/Output:."
        )
        initial_tests = "\n\n".join(
            f"Input:\n{case['stdin']}\nOutput:\n{case['expected_stdout']}"
            for case in problem.sample_test_cases
        )
    else:
        st.info("Đề bài không có ví dụ mẫu. Hãy nhập ít nhất một cặp Input:/Output: để chạy thử.")
        initial_tests = ""

    tests_text = st.text_area(
        "Input/Output mong đợi (mỗi test gồm Input: và Output:)",
        height=180,
        value=initial_tests,
        key=f"tests_{selected_id}",
        help="Có thể nhập nhiều test liên tiếp; đầu ra được so sánh theo token.",
    )
    submit_col, clear_col = st.columns(2)
    with submit_col:
        submitted = st.button(
            "Nộp bài & Phân tích",
            type="primary",
            use_container_width=True,
            disabled=not runner.get("available", False),
        )
    with clear_col:
        st.button(
            "Xóa code",
            use_container_width=True,
            on_click=clear_editor,
            args=(selected_id,),
        )

with right:
    st.subheader("Analysis & Feedback Hub")
    execution_tab, feedback_tab, knowledge_tab = st.tabs(
        ["Kết quả chạy Docker", "Phân tích AI", "Tài liệu học tập"]
    )

    results_by_problem = st.session_state.setdefault("analysis_results", {})
    errors_by_problem = st.session_state.setdefault("analysis_errors", {})
    result = results_by_problem.get(selected_id)
    analysis_error = errors_by_problem.get(selected_id)
    if submitted:
        results_by_problem.pop(selected_id, None)
        errors_by_problem.pop(selected_id, None)
        result = None
        analysis_error = None
        test_cases = parse_test_cases(tests_text)
        if not code or not code.strip():
            errors_by_problem[selected_id] = "Hãy nhập mã nguồn C++."
            st.rerun()
        if not test_cases:
            errors_by_problem[selected_id] = (
                "Hãy thêm ít nhất một test case theo định dạng Input:/Output:."
            )
            st.rerun()

        problem_status.setdefault(selected_id, "in_progress")
        try:
            with st.spinner("Đang biên dịch, chạy Docker và tạo phân tích..."):
                response = requests.post(
                    f"{API_URL}/analyze",
                    json={
                        "code": code,
                        "test_cases": test_cases,
                        "problem_id": selected_id,
                    },
                    timeout=100,
                )
            if response.ok:
                result = response.json()
                results_by_problem[selected_id] = result
                if result.get("verdict") == "ACCEPTED":
                    problem_status[selected_id] = "solved"
            else:
                try:
                    detail = response.json().get("detail", response.text)
                except ValueError:
                    detail = response.text
                errors_by_problem[selected_id] = (
                    f"API trả lỗi {response.status_code}: {detail}"
                )
                analysis_error = errors_by_problem[selected_id]
        except requests.RequestException as exc:
            errors_by_problem[selected_id] = f"Không thể gọi API: {exc}"
            analysis_error = errors_by_problem[selected_id]

    if analysis_error:
        st.error(analysis_error)

    if result:
        verdict = result.get("verdict", "UNKNOWN")
        label, color = VERDICT_STYLES.get(verdict, (verdict, "#6c757d"))
        with execution_tab:
            st.markdown(
                f'<div class="verdict-card" style="background:{color}">{label}</div>',
                unsafe_allow_html=True,
            )
            duration = result.get("duration_ms")
            metric_col, memory_col = st.columns(2)
            metric_col.metric(
                "Thời gian thực thi tổng",
                f"{duration} ms" if duration is not None else "Không có dữ liệu",
            )
            memory_col.metric("Bộ nhớ", "Runner chưa đo")

            tests = result.get("tests", [])
            if tests:
                rows = [
                    {
                        "Test": f"Test {test.get('case', index)}",
                        "Trạng thái": test.get("status", "UNKNOWN"),
                        "Chi tiết": test.get("stderr") or (
                            "Đầu ra không khớp" if test.get("status") == "WRONG_ANSWER" else "—"
                        ),
                    }
                    for index, test in enumerate(tests, start=1)
                ]
                st.dataframe(rows, hide_index=True, use_container_width=True)
                for index, test in enumerate(tests, start=1):
                    with st.expander(f"Chi tiết Test {test.get('case', index)}"):
                        if test.get("stdout") is not None:
                            st.caption("Output")
                            st.code(test["stdout"] or "(rỗng)", language="text")
                        if test.get("expected_stdout") is not None:
                            st.caption("Expected")
                            st.code(test["expected_stdout"] or "(rỗng)", language="text")
                        if test.get("stderr"):
                            st.caption("stderr")
                            st.code(test["stderr"], language="text")
                st.caption(
                    "Runner hiện chỉ cung cấp thời gian tổng; chưa thu thập thời gian riêng "
                    "hoặc mức dùng bộ nhớ cho từng test."
                )
            elif verdict == "COMPILE_ERROR":
                st.info("Không có test nào chạy được vì chương trình chưa biên dịch thành công.")

            if result.get("diagnostic"):
                st.error("Chẩn đoán từ runner")
                st.code(result["diagnostic"], language="text")
            if result.get("static_analysis"):
                with st.expander("Cảnh báo phân tích tĩnh từ compiler"):
                    st.code(result["static_analysis"], language="text")
            localization = result.get("error_localization", {})
            compiler_locations = localization.get("compiler_diagnostics", [])
            failing_cases = localization.get("failing_test_cases", [])
            if compiler_locations or failing_cases:
                st.markdown("**Vị trí và bằng chứng đáng chú ý**")
                for location in compiler_locations:
                    position = f"Dòng {location['line']}"
                    if location.get("column") is not None:
                        position += f", cột {location['column']}"
                    st.write(
                        f"- {position} ({location['severity']}): {location['message']}"
                    )
                if failing_cases:
                    cases = ", ".join(
                        f"Test {case['case']} ({case['status']})" for case in failing_cases
                    )
                    st.write(f"- Test làm lộ vấn đề: {cases}")
                st.caption(localization.get("note", ""))
            ml = result.get("ml_prediction", {})
            if ml.get("available"):
                st.caption(
                    f"Dự đoán ML thử nghiệm: {ml['label']} "
                    f"({ml['confidence']:.0%}) — không thay verdict."
                )
        with feedback_tab:
            feedback = result.get("feedback", {})
            st.caption(
                f"Chế độ: {feedback.get('mode', 'không rõ')} · "
                f"Nguồn: {', '.join(feedback.get('sources', [])) or 'không có'}"
            )
            st.markdown("**Giải thích và gợi ý**")
            st.write(feedback.get("explanation", "Chưa có phản hồi từ dịch vụ phân tích."))
            hints = {
                "COMPILE_ERROR": [
                    "Đọc thông báo lỗi đầu tiên và xác định tên tệp, dòng được nêu.",
                    "Kiểm tra cú pháp, kiểu dữ liệu và khai báo ngay quanh vị trí đó.",
                ],
                "WRONG_ANSWER": [
                    "So sánh output và expected của test thất bại để tìm khác biệt đầu tiên.",
                    "Thử thêm trường hợp biên phù hợp với ràng buộc của đề bài.",
                ],
                "RUNTIME_ERROR": [
                    "Thu nhỏ input gây lỗi để tái hiện hành vi.",
                    "Kiểm tra chỉ số mảng, phép chia và giả định về dữ liệu đầu vào.",
                ],
                "TIME_LIMIT_EXCEEDED": [
                    "Xem test nào vượt giới hạn và kích thước input tương ứng.",
                    "Ước lượng độ phức tạp của các vòng lặp và thao tác lặp lại.",
                ],
            }.get(verdict, [])
            if hints:
                st.markdown("**Gợi ý từng bước**")
                for index, hint in enumerate(hints, start=1):
                    st.markdown(f"{index}. {hint}")
            if result.get("static_analysis"):
                st.warning("Compiler có cảnh báo; xem nội dung trong tab Kết quả chạy Docker.")
            retrieval = result.get("code_retrieval", {})
            st.markdown("**Code tham chiếu cùng bài toán**")
            if retrieval.get("available"):
                st.caption(
                    f"Đã lập chỉ mục {retrieval.get('indexed_count', 0)} submission C++; "
                    f"bỏ qua {retrieval.get('missing_source_count', 0)} file thiếu và "
                    f"{retrieval.get('oversized_source_count', 0)} file vượt giới hạn."
                )
                verdict_comparison = retrieval.get("nearest_by_verdict", [])
                if verdict_comparison:
                    st.caption(
                        "Gần nhất theo verdict: "
                        + " · ".join(
                            f"{item['verdict']} {item['similarity']:.3f}"
                            for item in verdict_comparison
                        )
                    )
                references = retrieval.get("results", [])
                if references:
                    for reference in references:
                        with st.expander(
                            f"{reference['submission_id']} · {reference['verdict']} · "
                            f"similarity {reference['similarity']:.3f}"
                        ):
                            st.code(reference["code_excerpt"], language="cpp")
                            if reference.get("truncated"):
                                st.caption("Đoạn code được rút gọn.")
                else:
                    st.info("Không tìm thấy submission có độ tương đồng TF-IDF đáng kể.")
                st.caption(retrieval.get("note", ""))
            else:
                st.info(retrieval.get("reason", "Không có dữ liệu code tham chiếu."))
    else:
        with execution_tab:
            st.info("Nộp bài để xem verdict và kết quả từng test.")
        with feedback_tab:
            st.info("Phân tích AI và gợi ý sẽ xuất hiện sau khi chạy bài.")

    with knowledge_tab:
        if result:
            query = " ".join(
                part
                for part in (
                    result.get("verdict", ""),
                    result.get("diagnostic", ""),
                    result.get("static_analysis", ""),
                    code[:1000],
                )
                if part
            )
            try:
                knowledge_response = requests.get(
                    f"{API_URL}/knowledge/search",
                    params={"q": query, "limit": 5},
                    timeout=10,
                )
                knowledge_response.raise_for_status()
                documents = knowledge_response.json().get("results", [])
            except (requests.RequestException, ValueError) as exc:
                st.error(f"Không thể tải tài liệu liên quan: {exc}")
            else:
                if documents:
                    for document in documents:
                        with st.container(border=True):
                            st.markdown(f"**{document['title']}**")
                            st.write(document["content"])
                else:
                    st.info("Chưa tìm thấy tài liệu khớp với kết quả này.")
        else:
            st.info("Tài liệu liên quan sẽ được truy xuất sau khi chạy bài.")
