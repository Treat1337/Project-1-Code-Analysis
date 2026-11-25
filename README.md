# Nền tảng Hỗ trợ Học Lập trình C++ với Project_CodeNet & AI Feedback

Nền tảng luyện tập lập trình chuẩn LeetCode Dark Theme dành riêng cho **C++**, tích hợp trực tiếp kho dữ liệu **Project_CodeNet** (hơn 3.800 bài toán có mô tả HTML, bộ testcase chuẩn và code mẫu Accepted thực tế) kết hợp tính năng **AI Feedback** chẩn đoán lỗi tự động chạy bằng mô hình cục bộ qua Ollama.

---

## 🌟 Tính năng Nổi bật

1. **Chuyên biệt C++ (C++ Only)**:
   - Trình soạn thảo mã nguồn tối ưu cho C++ với starter template chuẩn:
     ```cpp
     #include <bits/stdc++.h>
     using namespace std;

     int main() {
         
         return 0;
     }
     ```
   - Biên dịch và thực thi trực tiếp bằng `g++ -O2` với giới hạn thời gian (Timeout 3s) và chuẩn hóa so khớp kết quả output.

2. **Dữ liệu thực tế từ Project_CodeNet**:
   - **Mô tả bài toán:** Nạp trực tiếp từ các file HTML gốc trong thư mục `problem_descriptions/`, hiển thị chuẩn Dark mode, hỗ trợ đầy đủ công thức toán học (`var`, `sub`, `sup`, `table`, `pre`).
   - **Testcase chuẩn:** Tự động nạp các cặp `input.txt` / `output.txt` từ `derived/input_output/data/` vào panel Testcase.
   - **Solutions Tab:** Hiển thị bài giải `Accepted` thực tế bằng C++ từ tập dữ liệu cùng mã `submission_id` và nút Copy Code tiện lợi.

3. **AI Feedback Tự động & Kín đáo (Silent Backend Proxy)**:
   - Toàn bộ giao diện hiển thị nhãn thanh lịch: **AI Feedback** (không hiển thị nhãn hiệu, phiên bản hay logo bên ngoài).
   - Khi chạy code gặp lỗi (`Wrong Answer`, `Compilation Error`, `Runtime Error`, `Time Limit Exceeded`), hệ thống tự động kích hoạt chẩn đoán qua Ollama proxy backend.
   - Phản hồi phân tích cấu trúc 3 phần rõ ràng: **Nguyên nhân gốc rễ (Root Cause)**, **Sai sót cụ thể (Specific Flaw)**, và **Hướng khắc phục (Actionable Fix)** bằng Markdown.

4. **Giao diện 3 Panel Tiêu chuẩn LeetCode**:
   - **Left Pane:** Gồm 2 tab duy nhất: `Description` và `Solutions`.
   - **Right-Top Pane:** Code Editor với thanh đánh số dòng chuẩn xác 1:1, hỗ trợ phím `Tab` (4 spaces), nút `Reset`, `Format`.
   - **Right-Bottom Pane:** Console gồm 3 tab `Testcase`, `Test Result`, và `AI Feedback` (kèm badge cảnh báo nhấp nháy khi có lỗi).
   - Thanh điều hướng trên cùng (Topbar) tích hợp duy nhất **1 cặp nút Run & Submit** bên cạnh đồng hồ đếm giờ.
   - Hỗ trợ thanh kéo co giãn (Splitters) và nút **Phóng to (⛶) / Thu nhỏ (—)** trên từng panel.
   - Slide-out Problem Drawer tìm kiếm hơn 3.800 bài toán và nút **Random** chọn bài ngẫu nhiên.

5. **Thống nhất Một Source of Truth duy nhất (`index.html`)**:
   - `index.html` hoạt động hoàn hảo khi mở qua Web Server (`http://127.0.0.1:8000`) lẫn khi mở trực tiếp file cục bộ (`file:///.../index.html`).
   - Frontend tự động chuyển hướng API client về `http://127.0.0.1:8000/api/` khi phát hiện giao thức `file:`.

---

## 🛠 Yêu cầu Hệ thống

- **Hệ điều hành:** Windows 10/11 (hoặc Linux/macOS)
- **Python:** 3.10 trở lên (đã cài đặt FastAPI, Uvicorn, Requests, httpx)
- **Trình biên dịch C++:** `g++` (MinGW-w64 / MSYS2) đã thêm vào biến môi trường `PATH`
- **Ollama:** Đã cài đặt trên máy và đã tải model phục vụ phân tích:
  ```bash
  ollama pull qwen2.5-coder:3b-instruct-q8_0
  ```

---

## 🚀 Khởi chạy Nhanh — Chỉ 1 Lệnh Duy Nhất

Khởi động toàn bộ nền tảng bằng script all-in-one:

```powershell
python run.py
```

### Script `run.py` sẽ tự động thực hiện:
1. Kiểm tra dịch vụ Ollama tại `127.0.0.1:11434`. Nếu chưa chạy, script sẽ tự khởi chạy `ollama serve` ở chế độ ngầm với `OLLAMA_ORIGINS="*"`.
2. Khởi chạy FastAPI backend (`uvicorn server:app --host 0.0.0.0 --port 8000`).
3. Tự động mở trình duyệt web tới địa chỉ `http://127.0.0.1:8000`.
4. Dọn dẹp an toàn và tắt sạch các tiến trình ngầm khi bạn bấm `Ctrl+C`.

---

## 📁 Cấu trúc Thư mục Chính

```text
Code_Analysis/
├── run.py                 # Điểm khởi chạy all-in-one (Ollama + FastAPI + Browser)
├── server.py              # FastAPI Backend (CORS, load Project_CodeNet, g++ runner, Ollama proxy)
├── index.html             # Single source of truth UI (LeetCode Dark theme, C++ Editor, AI Feedback)
├── README.md              # Tài liệu hướng dẫn dự án
├── requirements.txt       # Danh sách thư viện Python
└── Dataset/
    └── Project_CodeNet/
        ├── problem_descriptions/     # File HTML mô tả bài toán (p00000.html - p04052.html)
        ├── derived/input_output/data/# Thư mục testcase input/output (p00000 - p04052)
        ├── metadata/                 # CSV metadata thông tin submission
        └── data/                     # Mã nguồn bài nộp thực tế (Accepted C++ solutions)
```

---

## 📡 Danh sách API Endpoints (`server.py`)

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | Trả về giao diện chính `index.html` |
| `GET` | `/api/problems` | Danh sách 3.867 bài toán Project_CodeNet kèm tiêu đề |
| `GET` | `/api/problem/{id}` | Chi tiết bài toán (HTML đã lọc, testcase, bài giải C++ Accepted) |
| `POST` | `/api/run` | Biên dịch và thực thi code C++ với `g++ -O2`, trả về verdict chi tiết |
| `POST` | `/api/ai-feedback` | Proxy gửi prompt chẩn đoán lỗi tới Ollama cục bộ |
