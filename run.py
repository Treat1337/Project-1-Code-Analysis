import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
MINIMUM_PYTHON = (3, 12)


def run_setup_command(command: list[str], description: str) -> bool:
    print(f"\n==> {description}", flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, check=False)
    except OSError as exc:
        print(f"Không thể chạy lệnh {command[0]}: {exc}", file=sys.stderr, flush=True)
        return False
    if result.returncode:
        print(
            f"Lệnh thất bại với mã {result.returncode}: {' '.join(command)}",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def create_virtual_environment() -> bool:
    if VENV_PYTHON.exists():
        return True

    if sys.version_info[:2] >= MINIMUM_PYTHON:
        command = [sys.executable, "-m", "venv", ".venv"]
    else:
        launcher = shutil.which("py")
        if launcher is None:
            print(
                "Cần Python 3.12 trở lên hoặc Windows Python Launcher `py`.",
                file=sys.stderr,
            )
            return False
        command = [launcher, "-3.12", "-m", "venv", ".venv"]

    return run_setup_command(command, "Tạo môi trường ảo Python 3.12+")


def check_virtual_environment_version() -> bool:
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"Không thể kiểm tra Python trong .venv: {exc}", file=sys.stderr)
        return False
    if result.returncode:
        print(
            f"Không thể kiểm tra Python trong .venv: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return False

    try:
        version = tuple(int(part) for part in result.stdout.split()[-1].split(".")[:2])
    except (IndexError, ValueError):
        print(f"Không nhận diện được phiên bản Python: {result.stdout.strip()}", file=sys.stderr)
        return False
    if version < MINIMUM_PYTHON:
        print(
            f".venv đang dùng Python {'.'.join(map(str, version))}; "
            "cần Python 3.12 trở lên. Hãy xóa riêng thư mục .venv rồi chạy lại.",
            file=sys.stderr,
        )
        return False
    return True


def setup() -> bool:
    if not create_virtual_environment() or not check_virtual_environment_version():
        return False
    if not run_setup_command(
        [str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"],
        "Cài đặt dependencies",
    ):
        return False

    docker = shutil.which("docker")
    if docker is None:
        print(
            "\nCảnh báo: không tìm thấy Docker CLI. API và giao diện vẫn khởi chạy, "
            "nhưng không thể biên dịch/chạy code.",
            file=sys.stderr,
            flush=True,
        )
        return True
    if not run_setup_command(
        [
            docker,
            "build",
            "-t",
            "code-analysis-runner:latest",
            "-f",
            r"runner\Dockerfile",
            "runner",
        ],
        "Build Docker runner",
    ):
        print(
            "Cảnh báo: Docker runner chưa sẵn sàng. API và giao diện vẫn sẽ khởi chạy, "
            "nhưng không thể biên dịch/chạy code.",
            file=sys.stderr,
            flush=True,
        )
    return True


def stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def launch() -> int:
    commands = [
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--reload"],
        [str(VENV_PYTHON), "-m", "streamlit", "run", "ui.py"],
    ]
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for command in commands:
            process = subprocess.Popen(command, cwd=ROOT)
            processes.append(process)
            time.sleep(1)
            if process.poll() is not None:
                print(
                    f"Tiến trình khởi động thất bại: {' '.join(command)} "
                    f"(mã {process.returncode})",
                    file=sys.stderr,
                )
                return int(process.returncode or 1)

        print("\nỨng dụng đang chạy. Nhấn Ctrl+C để dừng API và giao diện.", flush=True)
        print("Giao diện: http://localhost:8501", flush=True)
        print("API docs:  http://127.0.0.1:8000/docs", flush=True)
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    print(
                        f"Một tiến trình đã dừng (mã {return_code}); "
                        "đang dừng các tiến trình còn lại.",
                        file=sys.stderr,
                    )
                    return int(return_code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nĐang dừng ứng dụng...", flush=True)
        return 0
    except OSError as exc:
        print(f"Không thể khởi chạy ứng dụng: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_processes(processes)


def main() -> int:
    if sys.platform != "win32":
        print("run.py được thiết kế để chạy trên Windows.", file=sys.stderr)
        return 1
    if not setup():
        return 1
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
