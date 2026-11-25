# Nền tảng Hỗ trợ Học Lập trình C++ với AI — Code Analysis Platform

Nền tảng luyện tập lập trình Dark Theme dành riêng cho **C++**, tích hợp kho dữ liệu **Project_CodeNet** (hơn 3.800 bài toán), **AI Feedback** cục bộ (ASTNN + CodeBERT + CodeClassifier), hệ thống tài khoản đầy đủ (**đăng ký / đăng nhập / lịch sử Submit**) và **Go Backend** bảo mật cho xác thực và lưu trữ.

---

## Mục lục

1. [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
2. [Yêu cầu](#yêu-cầu)
3. [Cài đặt](#cài-đặt)
4. [Cấu hình môi trường](#cấu-hình-môi-trường)
5. [Khởi động](#khởi-động)
6. [Hướng dẫn sử dụng](#hướng-dẫn-sử-dụng)
7. [API Endpoint](#api-endpoint)
8. [Cơ sở dữ liệu SQLite](#cơ-sở-dữ-liệu-sqlite)
9. [Bảo mật](#bảo-mật)
10. [Giới hạn đã biết](#giới-hạn-đã-biết)

---

## Kiến trúc hệ thống

```
┌─────────────────────────────────────────────┐
│              Trình duyệt (Vanilla JS)         │
│         http://127.0.0.1:8000/index.html      │
└───────┬───────────────┬───────────────┬───────┘
        │               │               │
        ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌──────────────┐
 │FastAPI 8000 │ │FastAPI 8001 │ │  Go Backend  │
 │  server.py  │ │ app/main.py │ │  port 8080   │
 │             │ │             │ │              │
 │ - Problems  │ │ - ASTNN     │ │ - Register   │
 │ - Compiler  │ │ - CodeBERT  │ │ - Login      │
 │ - AI Proxy  │ │ - CodeClass │ │ - Logout     │
 │ - index.html│ │ - /predict  │ │ - Run/Submit │
 └──────┬──────┘ └─────────────┘ │ - History    │
        │                        └──────┬───────┘
        ▼                               ▼
   g++ subprocess                  SQLite WAL
   (Docker nếu có)             backend/data/*.db
```

| Dịch vụ | Cổng | Mô tả |
|---------|------|-------|
| FastAPI `server.py` | **8000** | Phục vụ giao diện web, danh sách bài toán, biên dịch & chạy C++, AI feedback proxy |
| FastAPI `app/main.py` | **8001** | Dịch vụ AI cục bộ: ASTNN, CodeBERT, CodeClassifier |
| Go Backend | **8080** | Xác thực, session, Run proxy, Submit + lưu SQLite |

---

## Yêu cầu

| Phần mềm | Phiên bản | Ghi chú |
|---------|-----------|---------|
| Python | 3.10 + | uvicorn, fastapi, torch, transformers, … |
| Go | 1.23 + | Cho Go Backend |
| g++ | MinGW-w64 / GCC | Biên dịch code C++ người dùng |
| Docker | Tùy chọn | Sandbox cô lập khi chạy code (khuyến nghị production) |
| Ollama | Tùy chọn | AI Feedback bổ sung qua LLM cục bộ |

---

## Cài đặt

### 1. Clone / mở thư mục dự án

```bash
cd "Code_Analysis"
```

### 2. Cài Python dependencies

```bash
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
# Linux / macOS
.venv/bin/pip install -r requirements.txt
```

### 3. Cài Go (nếu chưa có)

Tải từ https://go.dev/dl/ và cài đặt.  
Kiểm tra: `go version`

### 4. Cài Go dependencies cho Backend

```bash
cd backend
go mod tidy
cd ..
```

### 5. Tạo file cấu hình Backend

```bash
# Windows
copy backend\.env.example backend\.env
# Linux / macOS
cp backend/.env.example backend/.env
```

Chỉnh sửa `backend/.env` nếu cần (xem mục [Cấu hình môi trường](#cấu-hình-môi-trường)).

---

## Cấu hình môi trường

File: `backend/.env`

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `SERVER_PORT` | `8080` | Cổng Go Backend |
| `SQLITE_PATH` | `./data/code_analysis.db` | Đường dẫn SQLite |
| `COOKIE_SECURE` | `false` | `true` cho production HTTPS |
| `SESSION_TTL_HOURS` | `24` | Thời gian sống của session (giờ) |
| `COMPILER_SERVICE_URL` | `http://127.0.0.1:8000` | URL FastAPI server.py |
| `COMPILER_RUN_PATH` | `/api/run` | Đường dẫn endpoint chạy code |
| `COMPILER_TIMEOUT_SECONDS` | `15` | Timeout biên dịch/chạy (giây) |
| `AI_SERVICE_URL` | `http://127.0.0.1:8001` | URL FastAPI app/main.py |
| `AI_PREDICT_PATH` | `/api/models/predict` | Đường dẫn endpoint AI |
| `AI_TIMEOUT_SECONDS` | `20` | Timeout gọi AI (giây) |
| `MAX_CODE_BYTES` | `65536` | Giới hạn kích thước code (bytes) |
| `PIPELINE_VERSION` | `v1` | Phiên bản pipeline AI |

> **Lưu ý:** Không commit file `.env` lên git. File này đã có trong `.gitignore`.

---

## Khởi động

### Cách 1 — Script tự động (khuyến nghị)

```bash
python start_all.py
```

Script sẽ tự động:
- Kiểm tra Python venv, Go, g++, file `.env`
- Tạo `.env` từ `.env.example` nếu chưa có
- Khởi động cả 3 dịch vụ và in log theo màu
- Nhấn **Ctrl+C** để dừng tất cả

### Cách 2 — Khởi động thủ công (3 terminal)

**Terminal 1 — FastAPI server.py (port 8000)**
```bash
.venv\Scripts\python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — FastAPI AI Service (port 8001)**
```bash
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

**Terminal 3 — Go Backend (port 8080)**
```bash
cd backend
go run ./cmd/server
```

### Truy cập

Mở trình duyệt tại: **http://127.0.0.1:8000**

> SQLite database được tạo tự động tại `backend/data/code_analysis.db` khi Go Backend khởi động lần đầu.  
> Backup được lưu tại `backend/backups/` (định kỳ 6 giờ).

---

## Hướng dẫn sử dụng

### Đăng ký tài khoản

1. Nhấn nút **Login** ở góc phải Toolbar.
2. Chuyển tab **Register**.
3. Nhập **Username** (3–50 ký tự), **Email** (tùy chọn), **Password** (8+ ký tự, có chữ hoa, số và ký tự đặc biệt).
4. Nhấn **Create Account**.

### Đăng nhập

1. Nhấn nút **Login**.
2. Nhập **Username hoặc Email** và **Password**.
3. Nhấn **Sign In**.
4. Toolbar hiển thị **username** sau khi đăng nhập thành công.

### Run (Chạy code)

- Yêu cầu đăng nhập.
- Nhấn nút **Run** → code được gửi tới FastAPI server.py để biên dịch và chạy.
- **Kết quả Run KHÔNG được lưu vào lịch sử.**
- Hiển thị: stdout, stderr, exit code, thời gian thực thi.

### Submit (Nộp bài)

- Yêu cầu đăng nhập.
- Nhấn nút **Submit** → code được gửi tới Go Backend.
- Go Backend gọi Compiler và AI Service song song.
- **Kết quả được lưu vào SQLite** theo tài khoản.
- Hiển thị: kết quả biên dịch, phân tích ASTNN + CodeBERT + CodeClassifier, tóm tắt lỗi.

### My Account & Lịch sử Submit

1. Nhấn vào **username** trên Toolbar → chọn **My Account**.
2. Xem thống kê: tổng submit, số Accepted/Rejected, tỷ lệ thành công.
3. Bảng lịch sử hỗ trợ: tìm kiếm, lọc theo trạng thái, sắp xếp, phân trang.
4. Nhấn vào một submission → xem chi tiết: source code (highlight C++), kết quả compiler, 3 mô hình AI.

### Đổi mật khẩu

Vào **My Account** → nhấn **Change Password** → nhập mật khẩu cũ và mới.

### Đăng xuất

Nhấn **username** → **Logout**.

---

## API Endpoint

### Go Backend (port 8080)

| Method | Endpoint | Auth | Mô tả |
|--------|----------|------|-------|
| `GET` | `/api/health` | Không | Kiểm tra trạng thái |
| `GET` | `/api/auth/csrf` | Không | Lấy CSRF token |
| `POST` | `/api/auth/register` | Không | Đăng ký tài khoản |
| `POST` | `/api/auth/login` | Không | Đăng nhập |
| `POST` | `/api/auth/logout` | Cookie + CSRF | Đăng xuất |
| `GET` | `/api/auth/me` | Cookie | Thông tin tài khoản hiện tại |
| `POST` | `/api/auth/change-password` | Cookie + CSRF | Đổi mật khẩu |
| `POST` | `/api/code/run` | Cookie + CSRF | Chạy code (không lưu) |
| `POST` | `/api/code/submit` | Cookie + CSRF | Submit + phân tích AI + lưu |
| `GET` | `/api/submissions` | Cookie | Danh sách submissions |
| `GET` | `/api/submissions/stats` | Cookie | Thống kê submissions |
| `GET` | `/api/submissions/{id}` | Cookie | Chi tiết một submission |
| `DELETE` | `/api/submissions/{id}` | Cookie + CSRF | Xóa submission |

### FastAPI server.py (port 8000)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/api/problems` | Danh sách bài toán |
| `GET` | `/api/problem/{id}` | Chi tiết bài toán |
| `POST` | `/api/run` | Biên dịch và chạy C++ |
| `POST` | `/api/ai-feedback` | AI Feedback (Ollama proxy) |

### FastAPI AI Service (port 8001)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/api/models/predict` | Phân tích code: ASTNN + CodeBERT + CodeClassifier |
| `POST` | `/analyze` | ASTNN phân tích cấu trúc AST |
| `POST` | `/run` | Chạy code (AI service) |
| `POST` | `/classify` | CodeClassifier phân loại |

---

## Cơ sở dữ liệu SQLite

**Vị trí:** `backend/data/code_analysis.db`  
**Chế độ:** WAL (Write-Ahead Logging) — hiệu năng cao cho đọc/ghi đồng thời  
**Backup:** `backend/backups/backup_<timestamp>.db` (tự động mỗi 6 giờ)

### Schema

```sql
-- Bảng người dùng
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT,
    password_hash TEXT NOT NULL,          -- Argon2id
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Bảng phiên đăng nhập
CREATE TABLE sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,      -- SHA-256/HMAC của session token
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Bảng lịch sử nộp bài
CREATE TABLE submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_code     TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'cpp',
    problem_id      TEXT,
    status          TEXT NOT NULL DEFAULT 'processing',  -- processing/accepted/rejected/error
    compile_status  TEXT,                                -- ok/error
    analysis_result TEXT,                               -- JSON: kết quả 3 mô hình AI
    error_summary   TEXT,
    model_version   TEXT,
    request_id      TEXT UNIQUE,                        -- Idempotency key
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Bảo mật

| Biện pháp | Chi tiết |
|-----------|---------|
| **Mật khẩu** | Argon2id (m=64 MiB, t=3, p=2) — không lưu plaintext |
| **Session Token** | 32 bytes `crypto/rand`, hashed SHA-256/HMAC trong DB |
| **Cookie** | `HttpOnly`, `SameSite=Strict`, `Secure=true` trong production |
| **CSRF** | Double-submit cookie pattern — header `X-CSRF-Token` bắt buộc cho POST/PUT/DELETE |
| **Rate Limiting** | 5 login/phút, 10 register/phút mỗi IP (in-memory) |
| **Giới hạn code** | Tối đa 65 536 bytes, body 1 MiB |
| **SQL** | Parameterized queries, không concatenate string; transactions cho multi-step |
| **Source code** | Không ghi log source code trong Go Backend |
| **CORS** | Chỉ chấp nhận `http://127.0.0.1:8000` và `http://localhost:8000` |
| **Docker** | Sandbox: `--network=none`, `--read-only`, `--cap-drop=ALL`, `--memory=512m` (khi daemon chạy) |

---

## Giới hạn đã biết

| Giới hạn | Mô tả |
|---------|-------|
| **Docker** | Nếu Docker daemon không chạy, `server.py` gọi `g++` trực tiếp qua subprocess — không có sandbox cô lập |
| **HTTPS** | Development dùng HTTP; đặt `COOKIE_SECURE=true` và cấu hình reverse proxy (nginx/caddy) cho production |
| **Rate limiter** | In-memory, reset khi khởi động lại; không hỗ trợ distributed rate limiting |
| **Email** | Đăng ký không xác minh email |
| **Session** | Đổi mật khẩu không tự động thu hồi các session khác |
| **AI predictions** | Kết quả ASTNN/CodeBERT/CodeClassifier được đánh dấu *experimental* — không dùng để xác định Accepted/Rejected chính thức |
| **CORS server.py** | `/api/run` và `/api/ai-feedback` của `server.py` gốc dùng `allow_origins=["*"]` (không thay đổi để giữ tương thích) |
| **E2E browser test** | Chưa có kiểm thử tự động end-to-end trong trình duyệt; toàn bộ tính năng đã kiểm thử qua unit test + integration test của Go Backend |

---

## Cấu trúc thư mục

```
Code_Analysis/
├── index.html                  # Giao diện Web IDE (Vanilla JS)
├── server.py                   # FastAPI: Problems, Compiler, AI proxy (port 8000)
├── app/
│   └── main.py                 # FastAPI: AI Models (port 8001)
├── backend/                    # Go Backend (port 8080)
│   ├── cmd/server/main.go      # Entry point
│   ├── internal/
│   │   ├── config/
│   │   ├── database/
│   │   ├── handlers/
│   │   ├── middleware/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── routes/
│   │   └── services/
│   ├── migrations/             # SQL migrations (001–003)
│   ├── tests/                  # Integration tests
│   ├── data/                   # SQLite database (tự tạo)
│   ├── backups/                # Backup tự động
│   ├── .env                    # Cấu hình (không commit)
│   └── .env.example            # Template cấu hình
├── artifacts/code-models/      # Model weights AI
├── start_all.py                # Script khởi động tất cả dịch vụ
├── requirements.txt
└── README.md
```

---

*Phiên bản tài liệu: 2.0 — Cập nhật sau tích hợp Go Backend + SQLite + Account System*
