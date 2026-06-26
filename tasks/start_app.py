from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser

from database.db import init_db
from services.runtime_ports import choose_runtime_ports
from utils.logger import ensure_log_files


def _project_service_pids() -> list[int]:
    """Find orphaned services started by this project, without requiring psutil."""
    current_pid = os.getpid()
    try:
        output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    except Exception:
        return []

    pids: list[int] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        is_api = "-m uvicorn main:app" in command
        is_dashboard = "-m streamlit run dashboard/streamlit_app.py" in command
        if is_api or is_dashboard:
            pids.append(pid)
    return pids


def _cleanup_existing_services() -> None:
    pids = _project_service_pids()
    if not pids:
        return

    print(f"Cleaning old Stock-check services: {', '.join(map(str, pids))}", flush=True)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  Unable to stop process {pid}; please close it manually if ports stay busy.", flush=True)

    deadline = time.time() + 4
    while time.time() < deadline:
        alive = [pid for pid in pids if _pid_exists(pid)]
        if not alive:
            return
        time.sleep(0.2)

    for pid in pids:
        if not _pid_exists(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  Unable to force-stop process {pid}; please close it manually.", flush=True)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            process.terminate()

    deadline = time.time() + 8
    while time.time() < deadline:
        if all(process.poll() is not None for process in processes):
            return
        time.sleep(0.2)

    for process in processes:
        if process.poll() is not None:
            continue
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Stock Trend LLM API and dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard/API bind host.")
    parser.add_argument("--lan", action="store_true", help="Bind dashboard and API to 0.0.0.0 for LAN access.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()

    ensure_log_files()
    init_db()
    _cleanup_existing_services()
    ports = choose_runtime_ports()
    host = "0.0.0.0" if args.lan else args.host
    public_host = "127.0.0.1"

    env = os.environ.copy()
    env["ENABLE_DASHBOARD_SCHEDULER"] = "false"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"

    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        host,
        "--port",
        str(ports.api_port),
    ]
    dashboard_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "dashboard/streamlit_app.py",
        "--server.address",
        host,
        "--server.port",
        str(ports.dashboard_port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]

    print("Stock Trend LLM started with unified runtime ports:", flush=True)
    print(f"  Backend API: http://{public_host}:{ports.api_port}", flush=True)
    print(f"  Dashboard:   http://{public_host}:{ports.dashboard_port}", flush=True)
    if args.lan:
        print(
            "  LAN mode: dashboard/API bind to 0.0.0.0; use this machine's LAN IP with the same ports.",
            flush=True,
        )

    processes: list[subprocess.Popen] = [
        subprocess.Popen(api_cmd, env=env, start_new_session=True),
        subprocess.Popen(dashboard_cmd, env=env, start_new_session=True),
    ]

    shutting_down = False

    def _handle_shutdown(signum, frame) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print("\nStopping services...", flush=True)
        _stop_processes(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_shutdown)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _handle_shutdown)

    try:
        time.sleep(2)
        if not args.no_browser:
            webbrowser.open(f"http://{public_host}:{ports.dashboard_port}")
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...", flush=True)
    finally:
        _stop_processes(processes)


if __name__ == "__main__":
    main()
