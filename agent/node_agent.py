from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class AgentConfig:
    canonical_id: str
    control_plane_url: str
    listen_host: str = "0.0.0.0"
    listen_port: int = 8765
    heartbeat_seconds: int = 30
    token: str | None = None

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            canonical_id=os.environ["GA_NODE_ID"],
            control_plane_url=os.getenv("GA_CONTROL_PLANE_URL", "http://127.0.0.1:8000").rstrip("/"),
            listen_host=os.getenv("GA_NODE_LISTEN_HOST", "0.0.0.0"),
            listen_port=int(os.getenv("GA_NODE_LISTEN_PORT", "8765")),
            heartbeat_seconds=int(os.getenv("GA_NODE_HEARTBEAT_SECONDS", "30")),
            token=os.getenv("GA_NODE_TOKEN") or None,
        )


def _run(argv: list[str], timeout: int = 2) -> str | None:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, shell=False)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        return None
    return None


def inventory() -> dict[str, Any]:
    total, used, free = shutil.disk_usage(Path.home())
    cpu_count = os.cpu_count() or 0
    memory_bytes = None
    if Path("/proc/meminfo").exists():
        try:
            line = next(x for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemTotal:"))
            memory_bytes = int(line.split()[1]) * 1024
        except Exception:
            memory_bytes = None
    gpu = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    tailscale_ip = _run(["tailscale", "ip", "-4"])
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": cpu_count,
        "memory_bytes": memory_bytes,
        "disk": {"total": total, "used": used, "free": free},
        "gpu": gpu,
        "tailscale_ip": tailscale_ip,
        "capacity_score": max(1, cpu_count) + int((memory_bytes or 0) / (1024**3)),
    }


def declared_capabilities(node_id: str) -> list[str]:
    defaults = {
        "ga://node/eden": ["compute.execute", "model.infer", "packet.dispatch", "service.host"],
        "ga://node/t5810-01": ["compute.execute", "build.execute", "model.infer", "service.host"],
        "ga://node/t5810-02": ["compute.execute", "build.execute", "model.infer", "service.host"],
        "ga://node/gaia": ["compute.execute", "build.execute", "service.host"],
        "ga://node/odin": ["field.execute", "packet.dispatch", "diagnostics.run", "estate.observe"],
        "ga://node/janus": ["intent.capture", "command.authorize", "packet.dispatch", "estate.observe"],
    }
    extra = [x.strip() for x in os.getenv("GA_NODE_CAPABILITIES", "").split(",") if x.strip()]
    return sorted(set(defaults.get(node_id, []) + extra))


class NodeAgent:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.resources = inventory()
        self.capabilities = declared_capabilities(config.canonical_id)

    @property
    def headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.config.token}"} if self.config.token else {}

    @property
    def executor_endpoint(self) -> str:
        host = os.getenv("GA_NODE_ADVERTISE_HOST") or self.resources.get("tailscale_ip") or self.resources.get("hostname")
        return f"http://{host}:{self.config.listen_port}"

    def advertise(self) -> dict[str, Any]:
        payload = {
            "canonical_id": self.config.canonical_id,
            "capabilities": self.capabilities,
            "resources": self.resources,
            "health": "online",
            "metadata": {"agent": "GA-HYPERNET-005", "executor_endpoint": self.executor_endpoint},
        }
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{self.config.control_plane_url}/v1/global/advertise", json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def heartbeat(self) -> dict[str, Any]:
        self.resources = inventory()
        payload = {"canonical_id": self.config.canonical_id, "health": "online", "resources": self.resources}
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{self.config.control_plane_url}/v1/global/heartbeat", json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def loop(self) -> None:
        backoff = 2
        while True:
            try:
                self.advertise()
                backoff = 2
                while True:
                    time.sleep(self.config.heartbeat_seconds)
                    self.heartbeat()
            except KeyboardInterrupt:
                return
            except Exception as exc:
                print(json.dumps({"event": "node-agent-error", "node": self.config.canonical_id, "error": str(exc), "retry_in": backoff}))
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    NodeAgent(AgentConfig.from_env()).loop()
