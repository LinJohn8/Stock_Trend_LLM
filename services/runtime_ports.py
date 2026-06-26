from __future__ import annotations

import socket
from dataclasses import dataclass

from config.settings import get_settings


@dataclass(frozen=True)
class RuntimePorts:
    api_port: int
    dashboard_port: int

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def dashboard_url(self) -> str:
        return f"http://127.0.0.1:{self.dashboard_port}"


def find_available_port(preferred: int, used: set[int] | None = None) -> int:
    settings = get_settings()
    used = used or set()
    candidates = [preferred] + [
        port
        for port in range(settings.port_range_start, settings.port_range_end + 1)
        if port != preferred
    ]
    for port in candidates:
        if port in used:
            continue
        if _is_port_free(port):
            return port
    raise RuntimeError(f"端口范围 {settings.port_range_start}-{settings.port_range_end} 内没有可用端口")


def choose_runtime_ports() -> RuntimePorts:
    settings = get_settings()
    api_port = find_available_port(settings.api_preferred_port)
    dashboard_port = find_available_port(settings.dashboard_preferred_port, used={api_port})
    return RuntimePorts(api_port=api_port, dashboard_port=dashboard_port)


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
