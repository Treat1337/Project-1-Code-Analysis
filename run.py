"""
run.py — Application Entry Point for Code Analysis Platform.

Responsibilities:
1. Load configuration from app.config.
2. Verify Python environment, dependencies, and system compiler (g++).
3. Ensure Ollama is running if configured, without spawning duplicate processes.
4. Launch Uvicorn with app.main:app.
5. Open browser if configured.
6. Handle graceful shutdown of background processes upon SIGINT/SIGTERM.
"""
from __future__ import annotations

import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from app.config import (
    HOST,
    PORT,
    PROJECT_ROOT,
    QWEN_BASE_URL,
    QWEN_ENABLED,
)

VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)

SERVER_URL = f"http://127.0.0.1:{PORT}" if HOST in {"0.0.0.0", "127.0.0.1"} else f"http://{HOST}:{PORT}"

spawned_processes: list[subprocess.Popen] = []


def cleanup() -> None:
    """Terminates all spawned background child processes cleanly."""
    if not spawned_processes:
        return
    print("\n[+] Shutting down background services...", flush=True)
    for proc in reversed(spawned_processes):
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    deadline = time.monotonic() + 3.0
    for proc in reversed(spawned_processes):
        remaining = max(0.1, deadline - time.monotonic())
        if proc.poll() is None:
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
    spawned_processes.clear()
    print("[✓] All services stopped cleanly.", flush=True)


atexit.register(cleanup)


def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, signal_handler)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether a TCP port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_ollama_running() -> bool:
    """Tests if Ollama is responsive at configured QWEN_BASE_URL."""
    try:
        req = urllib.request.Request(f"{QWEN_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_ollama_running() -> bool:
    """Checks if Ollama is running; if not and configured, spawns 'ollama serve' in background."""
    if not QWEN_ENABLED:
        print("[*] Ollama integration is disabled by configuration (QWEN_ENABLED=0).")
        return False

    if is_ollama_running():
        print(f"[✓] Ollama service is already running at {QWEN_BASE_URL}")
        return True

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        common_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if common_path.is_file():
            ollama_bin = str(common_path)

    if not ollama_bin:
        print(
            "[!] Warning: 'ollama' executable not found in PATH or standard directories.\n"
            "    AI feedback will be unavailable until Ollama is started manually.",
            file=sys.stderr,
            flush=True,
        )
        return False

    print(f"[*] Starting Ollama server ({ollama_bin} serve)...", flush=True)
    env = os.environ.copy()
    env["OLLAMA_ORIGINS"] = "*"

    try:
        proc = subprocess.Popen(
            [ollama_bin, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=PROJECT_ROOT,
        )
        spawned_processes.append(proc)
    except Exception as exc:
        print(f"[!] Failed to spawn Ollama: {exc}", file=sys.stderr, flush=True)
        return False

    print("    Waiting for Ollama to become ready...", end="", flush=True)
    for _ in range(30):
        time.sleep(0.5)
        print(".", end="", flush=True)
        if is_ollama_running():
            print(" [✓] Ready!")
            return True
        if proc.poll() is not None:
            print(f" [!] Exited with code {proc.returncode}")
            return False

    print(" [!] Timeout waiting for Ollama.")
    return False


def kill_stale_port(port: int) -> None:
    """Frees port if occupied by a previously crashed process."""
    if not is_port_in_use(port):
        return

    print(f"[*] Port {port} is in use. Attempting to clear stale process...", flush=True)
    if sys.platform == "win32":
        try:
            cmd = f'powershell -NoProfile -Command "Get-Process -Id (Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"'
            subprocess.run(cmd, shell=True, timeout=5, check=False)
            time.sleep(1)
        except Exception:
            pass


def start_uvicorn_server() -> subprocess.Popen:
    """Starts FastAPI uvicorn bound to configured HOST and PORT using app.main:app."""
    kill_stale_port(PORT)

    cmd = [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]

    print(f"[*] Launching Uvicorn server (app.main:app on {HOST}:{PORT})...", flush=True)
    proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
    spawned_processes.append(proc)

    # Wait for server to respond
    for _ in range(25):
        time.sleep(0.5)
        if proc.poll() is not None:
            raise RuntimeError(f"FastAPI server failed to start (exit code {proc.returncode}).")
        if is_port_in_use(PORT):
            print(f"[✓] FastAPI server is listening at {SERVER_URL}")
            return proc

    return proc


def check_dependencies() -> None:
    """Verify compiler and core Python dependencies."""
    gpp = shutil.which("g++")
    if gpp:
        print(f"[✓] Compiler available: {gpp}")
    else:
        print("[!] Warning: g++ compiler not found in PATH. C++ execution will fail without it.")


def main() -> int:
    print("=" * 64)
    print("   Code Analysis & Programming Education Platform")
    print("=" * 64)

    check_dependencies()
    ensure_ollama_running()

    try:
        server_proc = start_uvicorn_server()
    except Exception as exc:
        print(f"[!] Error starting server: {exc}", file=sys.stderr, flush=True)
        cleanup()
        return 1

    # Automatically open browser
    open_browser = os.getenv("OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no"}
    if open_browser:
        print(f"[*] Opening {SERVER_URL} in default browser...", flush=True)
        time.sleep(0.5)
        try:
            webbrowser.open(SERVER_URL)
        except Exception:
            pass

    print("\n" + "=" * 64)
    print("   ✓ Platform is LIVE!")
    print(f"   • Web UI:       {SERVER_URL}")
    print(f"   • API Docs:     {SERVER_URL}/docs")
    print(f"   • AI Service:   {QWEN_BASE_URL}")
    print("   Press Ctrl+C to stop all services cleanly.")
    print("=" * 64 + "\n")

    try:
        while True:
            time.sleep(0.5)
            code = server_proc.poll()
            if code is not None:
                print(f"[!] Server process exited with code {code}.", file=sys.stderr)
                break
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(main())
