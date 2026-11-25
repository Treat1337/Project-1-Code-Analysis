"""
All-in-One Entry Point for Project_CodeNet C++ Analysis & Runner Platform.

Executing:
    python run.py

Automatically:
1. Verifies/prepares Python environment (.venv) and dependencies.
2. Checks if Ollama is running at 127.0.0.1:11434; if not, spawns 'ollama serve'
   in the background with OLLAMA_ORIGINS="*" and waits until ready.
3. Starts the FastAPI server (uvicorn server:app --host 0.0.0.0 --port 8000).
4. Automatically opens http://127.0.0.1:8000 in your default web browser.
5. Cleanly terminates all spawned background processes upon Ctrl+C.
"""

import atexit
import json
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


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    # Unix / fallback path
    VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)

OLLAMA_URL = "http://127.0.0.1:11434"
SERVER_PORT = 8000
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"

# Track background processes to terminate on exit
spawned_processes: list[subprocess.Popen] = []


def cleanup() -> None:
    """Terminates all spawned child processes cleanly."""
    if not spawned_processes:
        return
    print("\n[+] Shutting down background services...", flush=True)
    for proc in reversed(spawned_processes):
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    # Give processes a moment to terminate gracefully
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


# Register exit handlers
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
    """Tests if Ollama is responsive at 127.0.0.1:11434."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_ollama_running() -> bool:
    """Checks if Ollama is running; if not, spawns 'ollama serve' in background."""
    if is_ollama_running():
        print(f"[✓] Ollama service is already running at {OLLAMA_URL}")
        return True

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        # Common Windows path check
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
            cwd=ROOT,
        )
        spawned_processes.append(proc)
    except Exception as exc:
        print(f"[!] Failed to spawn Ollama: {exc}", file=sys.stderr, flush=True)
        return False

    # Wait for Ollama to become ready (up to 15 seconds)
    print("    Waiting for Ollama to be ready...", end="", flush=True)
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


def kill_stale_port_8000() -> None:
    """Frees port 8000 if occupied by a previously crashed process."""
    if not is_port_in_use(SERVER_PORT):
        return

    print(f"[*] Port {SERVER_PORT} is currently in use. Attempting to clear stale process...", flush=True)
    if sys.platform == "win32":
        try:
            cmd = f'powershell -NoProfile -Command "Get-Process -Id (Get-NetTCPConnection -LocalPort {SERVER_PORT} -ErrorAction SilentlyContinue).OwningProcess -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"'
            subprocess.run(cmd, shell=True, timeout=5, check=False)
            time.sleep(1)
        except Exception:
            pass


def start_fastapi_server() -> subprocess.Popen:
    """Starts FastAPI uvicorn bound to 0.0.0.0:8000."""
    kill_stale_port_8000()

    cmd = [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "server:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(SERVER_PORT),
    ]

    print(f"[*] Launching FastAPI server (0.0.0.0:{SERVER_PORT})...", flush=True)
    proc = subprocess.Popen(cmd, cwd=ROOT)
    spawned_processes.append(proc)

    # Wait for server to respond
    for _ in range(20):
        time.sleep(0.5)
        if proc.poll() is not None:
            raise RuntimeError(f"FastAPI server failed to start (exit code {proc.returncode}).")
        if is_port_in_use(SERVER_PORT):
            print(f"[✓] FastAPI server is listening at {SERVER_URL}")
            return proc

    return proc


def main() -> int:
    print("=" * 64)
    print("   Project_CodeNet C++ Platform — All-in-One Launcher")
    print("=" * 64)

    # 1. Ollama service
    ensure_ollama_running()

    # 2. FastAPI server
    try:
        server_proc = start_fastapi_server()
    except Exception as exc:
        print(f"[!] Error starting server: {exc}", file=sys.stderr, flush=True)
        cleanup()
        return 1

    # 3. Automatically open browser
    print(f"[*] Opening {SERVER_URL} in default browser...", flush=True)
    time.sleep(0.5)
    try:
        webbrowser.open(SERVER_URL)
    except Exception:
        pass

    # 4. Status banner
    print("\n" + "=" * 64)
    print("   ✓ Platform is LIVE!")
    print(f"   • Web UI:       {SERVER_URL}")
    print(f"   • Local file:   {ROOT / 'index.html'}")
    print(f"   • API Docs:     {SERVER_URL}/docs")
    print(f"   • AI Service:   {OLLAMA_URL}")
    print("   Press Ctrl+C to stop all services cleanly.")
    print("=" * 64 + "\n")

    # 5. Keep alive until Ctrl+C
    try:
        while True:
            time.sleep(0.5)
            # Check if server unexpectedly exited
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
