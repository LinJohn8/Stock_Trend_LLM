from __future__ import annotations

from services.runtime_ports import find_available_port
from tasks import start_app


def test_find_available_port_skips_used_preferred() -> None:
    port = find_available_port(9690, used={9690})
    assert 9690 < port <= 9699


def test_project_service_pids_only_match_stock_check_processes(monkeypatch) -> None:
    ps_output = """
      111 /usr/bin/python -m uvicorn main:app --host 127.0.0.1 --port 9690
      222 /usr/bin/python -m streamlit run dashboard/streamlit_app.py --server.port 9696
      333 /usr/bin/python -m streamlit run another/app.py --server.port 9696
      444 /usr/bin/python worker.py
    """

    monkeypatch.setattr(start_app.os, "getpid", lambda: 999)
    monkeypatch.setattr(start_app.subprocess, "check_output", lambda *args, **kwargs: ps_output)

    assert start_app._project_service_pids() == [111, 222]
