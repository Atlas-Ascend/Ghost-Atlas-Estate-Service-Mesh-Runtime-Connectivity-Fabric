from __future__ import annotations

import json

from app.dispatch import DispatchRecord
from app.executors import ExecutorRegistry, LocalCommandExecutor


def record() -> DispatchRecord:
    return DispatchRecord(
        dispatch_id="dispatch-test",
        packet_id="packet-test",
        capability="ga://capability/software.build",
        source="ga://organ/packet-os",
        target="ga://node/eden",
        route=None,
        state="DISPATCHED",
        created_at=0.0,
        updated_at=0.0,
        payload={"hello": "world"},
    )


def test_unconfigured_defaults_remain_unbound(monkeypatch):
    for key in [
        "GA_EDEN_EXECUTOR_ARGV", "GA_T5810_01_EXECUTOR_URL", "GA_T5810_02_EXECUTOR_URL",
        "GA_ODIN_EXECUTOR_URL", "GA_JANUS_EXECUTOR_URL", "GA_RENDER_EXECUTOR_URL",
        "GA_VERCEL_EXECUTOR_URL", "GA_NEON_EXECUTOR_URL",
    ]:
        monkeypatch.delenv(key, raising=False)
    registry = ExecutorRegistry().install_defaults()
    snap = registry.snapshot()
    assert snap["bound"] == []
    assert "ga://node/eden" in snap["unbound"]
    assert "ga://node/render" in snap["unbound"]


def test_local_executor_uses_json_stdin_without_shell():
    command = ["python", "-c", "import sys,json; p=json.load(sys.stdin); print(json.dumps({'packet_id':p['packet_id']}))"]
    result = LocalCommandExecutor("test", command)(record())
    assert result["exit_code"] == 0
    assert result["response"]["packet_id"] == "packet-test"


def test_local_binding_requires_json_argv(monkeypatch):
    monkeypatch.setenv("GA_EDEN_EXECUTOR_ARGV", json.dumps(["python", "worker.py"]))
    registry = ExecutorRegistry()
    registry.bind_local("ga://node/eden", command_env="GA_EDEN_EXECUTOR_ARGV")
    assert "ga://node/eden" in registry.snapshot()["bound"]
