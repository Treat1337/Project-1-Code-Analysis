#!/usr/bin/env python3
"""
start_all.py — Khởi động toàn bộ hệ thống Code Analysis Platform

Dịch vụ sẽ được khởi động:
  1. FastAPI server.py    → http://127.0.0.1:8000  (Compiler, Problems, Web UI)
  2. FastAPI app/main.py  → http://127.0.0.1:8001  (AI Models: ASTNN, CodeBERT, CodeClassifier)
  3. Go Backend           → http://127.0.0.1:8080  (Auth, Session, Submission)

Yêu cầu:
  - Python 3.10+  (uvicorn, fastapi, torch, transformers đã cài trong .venv)
  - Go 1.23+      (cần có trong PATH hoặc cấu hình GO_BIN bên dưới)
  - g++            (MinGW-w64 trên Windows, hoặc gcc trên Linux)
  - File backend/.env đã được tạo từ backend/.env.example

Dừng: Nhấn Ctrl+C
"""

import subprocess
import sys
import os
import signal
import time
import shutil

# ---------------------------------------------------------------------------
# Cấu hình đường dẫn
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(VENV_PYTHON):
    # Linux / macOS
    VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "bin", "python")

# Tìm Go binary
_GO_CANDIDATES = [
    shutil.which("go"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Go\bin\go.exe"),
    r"C:\Program Files\Go\bin\go.exe",
    "/usr/local/go/bin/go",
    "/usr/bin/go",
]
GO_BIN = next((p for p in _GO_CANDIDATES if p and os.path.isfile(p)), None)

# ---------------------------------------------------------------------------
# Màu sắc terminal (ANSI)
# ---------------------------------------------------------------------------
_HAS_COLOR = sys.platform != "win32" or os.environ.get("TERM") == "xterm"
def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _HAS_COLOR else text
GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
RED    = lambda t: _c("31", t)
CYAN   = lambda t: _c("36", t)
BOLD   = lambda t: _c("1",  t)

# ---------------------------------------------------------------------------
# Kiểm tra yêu cầu trước khi khởi động
# ---------------------------------------------------------------------------
def preflight():
    ok = True
    print(BOLD("\n=== Kiểm tra yêu cầu ==="))

    # Python venv
    if os.path.exists(VENV_PYTHON):
        print(GREEN(f"  [OK] Python venv: {VENV_PYTHON}"))
    else:
        print(RED(f"  [FAIL] Không tìm thấy Python venv tại {VENV_PYTHON}"))
        print(       "         Tạo venv: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt")
        ok = False

    # Go binary
    if GO_BIN:
        print(GREEN(f"  [OK] Go: {GO_BIN}"))
    else:
        print(RED("  [FAIL] Không tìm thấy Go. Cài từ https://go.dev/dl/"))
        ok = False

    # g++ (không bắt buộc dừng, chỉ cảnh báo)
    gpp = shutil.which("g++")
    if gpp:
        print(GREEN(f"  [OK] g++: {gpp}"))
    else:
        print(YELLOW("  [WARN] g++ không tìm thấy trong PATH. Compile sẽ thất bại."))

    # backend/.env
    env_file = os.path.join(BACKEND_DIR, ".env")
    env_example = os.path.join(BACKEND_DIR, ".env.example")
    if os.path.exists(env_file):
        print(GREEN(f"  [OK] backend/.env"))
    elif os.path.exists(env_example):
        import shutil as sh
        sh.copy(env_example, env_file)
        print(YELLOW(f"  [AUTO] Đã tạo backend/.env từ .env.example (mặc định)"))
    else:
        print(RED("  [FAIL] Thiếu backend/.env và backend/.env.example"))
        ok = False

    # server.py và app/main.py
    for rel in ("server.py", "app/main.py"):
        full = os.path.join(BASE_DIR, rel)
        if os.path.exists(full):
            print(GREEN(f"  [OK] {rel}"))
        else:
            print(RED(f"  [FAIL] Không tìm thấy {full}"))
            ok = False

    print()
    return ok

# ---------------------------------------------------------------------------
# Khởi động các dịch vụ
# ---------------------------------------------------------------------------
processes: list[subprocess.Popen] = []

def start_service(name: str, cmd: list[str], cwd: str, port: int):
    """Khởi động một dịch vụ, trả về process."""
    print(CYAN(f"  Đang khởi động {name} → http://127.0.0.1:{port}"))
    print(f"    cmd: {' '.join(cmd)}")
    try:
        p = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append(p)
        return p
    except FileNotFoundError as e:
        print(RED(f"  [ERROR] Không thể khởi động {name}: {e}"))
        return None

def stream_output(proc, label: str):
    """In log từ subprocess với nhãn dịch vụ. Chạy trong thread riêng."""
    import threading
    colors = {"server.py": "32", "app/main.py": "35", "go-backend": "36"}
    code = colors.get(label, "37")
    def _run():
        try:
            for line in proc.stdout:
                print(f"\033[{code}m[{label}]\033[0m {line}", end="")
        except Exception:
            pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

def shutdown(sig=None, frame=None):
    print(BOLD("\n\n=== Đang dừng toàn bộ dịch vụ... ==="))
    for p in reversed(processes):
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    print(GREEN("Đã dừng tất cả. Tạm biệt!"))
    sys.exit(0)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(BOLD("\n╔══════════════════════════════════════════════╗"))
    print(BOLD("║   Code Analysis Platform — Khởi động hệ thống ║"))
    print(BOLD("╚══════════════════════════════════════════════╝"))

    if not preflight():
        print(RED("Vui lòng sửa các lỗi trên trước khi chạy lại."))
        sys.exit(1)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(BOLD("=== Khởi động các dịch vụ ==="))

    # 1. FastAPI server.py (port 8000)
    p1 = start_service(
        "FastAPI server.py (Compiler + UI)",
        [VENV_PYTHON, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=BASE_DIR,
        port=8000,
    )
    if p1:
        stream_output(p1, "server.py")

    time.sleep(1)

    # 2. FastAPI app/main.py (port 8001)
    p2 = start_service(
        "FastAPI app/main.py (AI Models)",
        [VENV_PYTHON, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=BASE_DIR,
        port=8001,
    )
    if p2:
        stream_output(p2, "app/main.py")

    time.sleep(1)

    # 3. Go Backend (port 8080)
    if GO_BIN:
        p3 = start_service(
            "Go Backend (Auth + Submit)",
            [GO_BIN, "run", "./cmd/server"],
            cwd=BACKEND_DIR,
            port=8080,
        )
        if p3:
            stream_output(p3, "go-backend")
    else:
        print(RED("  [SKIP] Bỏ qua Go Backend do không tìm thấy go binary."))
        p3 = None

    print()
    print(BOLD("=== Hệ thống đang chạy ==="))
    print(GREEN("  Web UI        → http://127.0.0.1:8000"))
    print(GREEN("  AI Service    → http://127.0.0.1:8001"))
    print(GREEN("  Auth Backend  → http://127.0.0.1:8080"))
    print(YELLOW("\nNhấn Ctrl+C để dừng toàn bộ."))
    print()

    # Giữ cho script không thoát; thoát nếu dịch vụ nào crash
    try:
        while True:
            for name, proc in [("server.py", p1), ("app/main.py", p2), ("go-backend", p3)]:
                if proc and proc.poll() is not None:
                    print(RED(f"\n[WARN] {name} đã thoát với code {proc.returncode}. Hệ thống có thể không hoạt động đúng."))
            time.sleep(5)
    except KeyboardInterrupt:
        shutdown()

if __name__ == "__main__":
    main()
