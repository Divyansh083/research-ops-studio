import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "tmp" / "launcher"
MANAGED_PORTS = (8000, 3000)
PID_FILES = {
    "backend": RUNTIME_DIR / "backend.pid",
    "frontend": RUNTIME_DIR / "frontend.pid",
}


def prefix_output(pipe, prefix):
    """Read from a pipe and print with a prefix."""
    try:
        for line in iter(pipe.readline, b""):
            print(f"{prefix} {line.decode(errors='replace').rstrip()}")
    except Exception as exc:
        print(f"{prefix} [Error reading output: {exc}]")


def check_port(port):
    """Check whether a TCP port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) == 0


def ensure_runtime_dir():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def write_pid_file(name, pid):
    ensure_runtime_dir()
    PID_FILES[name].write_text(str(pid), encoding="ascii")


def remove_pid_file(name):
    try:
        PID_FILES[name].unlink()
    except FileNotFoundError:
        pass


def remove_all_pid_files():
    for name in PID_FILES:
        remove_pid_file(name)


def pid_is_running(pid_text):
    try:
        pid = int(pid_text)
    except (TypeError, ValueError):
        return False

    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def remove_stale_pid_files():
    for name, pid_file in PID_FILES.items():
        if not pid_file.exists():
            continue

        pid_text = pid_file.read_text(encoding="ascii").strip()
        if not pid_is_running(pid_text):
            remove_pid_file(name)


def terminate_process_tree(process):
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/f", "/t", "/pid", str(process.pid)],
            capture_output=True,
            check=False,
        )
        return

    process.terminate()


def clean_next_cache():
    next_dir = PROJECT_ROOT / "frontend" / ".next"
    if not next_dir.exists():
        return

    import shutil

    try:
        shutil.rmtree(next_dir)
        print("Cache cleared.")
    except Exception as exc:
        print(f"Error clearing cache: {exc}")


def print_port_conflict_message(conflicts):
    ports = ", ".join(str(port) for port in conflicts)
    print("")
    print(f"Error: Port(s) {ports} are already in use.")
    print("For safety, this launcher only stops services that it started itself.")
    print("Close the original launcher terminal or run .\\scripts\\stop_all.cmd")
    print("to stop launcher-managed services. If another app owns the port,")
    print("stop that app manually before retrying.")
    print("")


def run():
    remove_stale_pid_files()

    if "--clean" in sys.argv:
        print("[*] Cleaning Next.js cache...")
        clean_next_cache()
        print("[v] Cache cleared.")

    print("--- Starting Multi-Agent Research Assistant ---")

    # Auto-kill any existing processes on ports 8000 or 3000
    for port in MANAGED_PORTS:
        if check_port(port):
            print(f"[!] Port {port} is occupied. Force-clearing it...")
            if os.name == "nt":
                # Robust PowerShell kill for port on Windows
                subprocess.run(
                    ["powershell", "-Command", f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"],
                    capture_output=True,
                    check=False
                )
            else:
                # Basic lsof/kill for Unix-like
                subprocess.run(f"lsof -ti:{port} | xargs kill -9", shell=True, capture_output=True, check=False)
            time.sleep(1) # Give OS time to release port

    conflicts = [port for port in MANAGED_PORTS if check_port(port)]
    if conflicts:
        print_port_conflict_message(conflicts)
        return 1

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
        "--reload-dir",
        "app",
    ]
    backend_proc = subprocess.Popen(
        backend_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )
    write_pid_file("backend", backend_proc.pid)

    frontend_cmd = ["npm.cmd" if os.name == "nt" else "npm", "run", "dev"]
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT / "frontend"),
        shell=(os.name == "nt"),
    )
    write_pid_file("frontend", frontend_proc.pid)

    threads = [
        threading.Thread(target=prefix_output, args=(backend_proc.stdout, "[Backend]"), daemon=True),
        threading.Thread(target=prefix_output, args=(backend_proc.stderr, "[Backend]"), daemon=True),
        threading.Thread(target=prefix_output, args=(frontend_proc.stdout, "[Frontend]"), daemon=True),
        threading.Thread(target=prefix_output, args=(frontend_proc.stderr, "[Frontend]"), daemon=True),
    ]

    for thread in threads:
        thread.start()

    print("")
    print("Services are running.")
    print("  - API:      http://localhost:8000")
    print("  - Frontend: http://localhost:3000")
    print("")
    print("Press Ctrl+C to stop both services.")
    print("")

    try:
        while True:
            if backend_proc.poll() is not None:
                print("")
                print("Backend stopped unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("")
                print("Frontend stopped unexpectedly.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("")
        print("Stopping services...")
    finally:
        terminate_process_tree(backend_proc)
        terminate_process_tree(frontend_proc)

        try:
            backend_proc.wait(timeout=5)
            frontend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                backend_proc.kill()
                frontend_proc.kill()

        remove_all_pid_files()
        print("Services stopped successfully.")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
