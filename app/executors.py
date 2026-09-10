from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import request, error

from .dispatch import DispatchRecord


class ExecutorError(RuntimeError):
    pass


class ExecutorAdapter(Protocol):
    adapter_id: str
    def __call__(self, record: DispatchRecord) -> dict[str, Any]: ...


@dataclass
class HttpExecutor:
    adapter_id: str
    base_url: str
    token_env: str | None = None
    timeout_seconds: int = 30

    def __call__(self, record: DispatchRecord) -> dict[str, Any]:
        if not self.base_url:
            raise ExecutorError(f"{self.adapter_id}: endpoint not configured")
        body = json.dumps({
            "dispatch_id": record.dispatch_id,
            "packet_id": record.packet_id,
            "capability": record.capability,
            "payload": record.payload,
            "source": record.source,
        }).encode("utf-8")
        headers = {"content-type": "application/json", "x-ga-dispatch-id": record.dispatch_id}
        if self.token_env:
            token = os.getenv(self.token_env, "")
            if not token:
                raise ExecutorError(f"{self.adapter_id}: missing credential {self.token_env}")
            headers["authorization"] = f"Bearer {token}"
        req = request.Request(self.base_url.rstrip("/") + "/v1/execute", data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return {"adapter": self.adapter_id, "status": response.status, "response": payload}
        except error.HTTPError as exc:
            raise ExecutorError(f"{self.adapter_id}: HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise ExecutorError(f"{self.adapter_id}: transport failure: {exc.reason}") from exc


@dataclass
class LocalCommandExecutor:
    adapter_id: str
    command: list[str]
    timeout_seconds: int = 60

    def __call__(self, record: DispatchRecord) -> dict[str, Any]:
        if not self.command:
            raise ExecutorError(f"{self.adapter_id}: command not configured")
        # Bounded executor: no shell=True; packet is delivered only through stdin JSON.
        proc = subprocess.run(
            self.command,
            input=json.dumps({
                "dispatch_id": record.dispatch_id,
                "packet_id": record.packet_id,
                "capability": record.capability,
                "payload": record.payload,
                "source": record.source,
            }),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            shell=False,
            check=False,
        )
        if proc.returncode != 0:
            raise ExecutorError(f"{self.adapter_id}: exit={proc.returncode}; stderr={proc.stderr[-2000:]}")
        stdout = proc.stdout.strip()
        try:
            result: Any = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            result = {"stdout": stdout[-4000:]}
        return {"adapter": self.adapter_id, "exit_code": proc.returncode, "response": result}


class ExecutorRegistry:
    """Maps canonical Hypernet nodes to bounded executor adapters.

    Bindings are explicit. Missing configuration leaves nodes unbound rather than
    silently executing through another transport.
    """

    def __init__(self) -> None:
        self.adapters: dict[str, ExecutorAdapter] = {}
        self.reasons: dict[str, str] = {}

    def bind_http(self, node_id: str, *, env: str, token_env: str | None = None) -> None:
        endpoint = os.getenv(env, "").strip()
        if not endpoint:
            self.reasons[node_id] = f"missing endpoint env {env}"
            return
        self.adapters[node_id] = HttpExecutor(f"http:{node_id}", endpoint, token_env)

    def bind_local(self, node_id: str, *, command_env: str) -> None:
        raw = os.getenv(command_env, "").strip()
        if not raw:
            self.reasons[node_id] = f"missing command env {command_env}"
            return
        command = json.loads(raw)
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ExecutorError(f"{node_id}: {command_env} must be a JSON argv array")
        self.adapters[node_id] = LocalCommandExecutor(f"local:{node_id}", command)

    def install_defaults(self) -> "ExecutorRegistry":
        self.bind_local("ga://node/eden", command_env="GA_EDEN_EXECUTOR_ARGV")
        self.bind_http("ga://node/t5810-01", env="GA_T5810_01_EXECUTOR_URL", token_env="GA_HYPERNET_NODE_TOKEN")
        self.bind_http("ga://node/t5810-02", env="GA_T5810_02_EXECUTOR_URL", token_env="GA_HYPERNET_NODE_TOKEN")
        self.bind_http("ga://node/odin", env="GA_ODIN_EXECUTOR_URL", token_env="GA_HYPERNET_NODE_TOKEN")
        self.bind_http("ga://node/janus", env="GA_JANUS_EXECUTOR_URL", token_env="GA_HYPERNET_NODE_TOKEN")
        self.bind_http("ga://node/render", env="GA_RENDER_EXECUTOR_URL", token_env="GA_RENDER_EXECUTOR_TOKEN")
        self.bind_http("ga://node/vercel", env="GA_VERCEL_EXECUTOR_URL", token_env="GA_VERCEL_EXECUTOR_TOKEN")
        self.bind_http("ga://node/neon", env="GA_NEON_EXECUTOR_URL", token_env="GA_NEON_EXECUTOR_TOKEN")
        return self

    def attach(self, fabric: Any) -> None:
        for node_id, adapter in self.adapters.items():
            fabric.register_executor(node_id, adapter)

    def snapshot(self) -> dict[str, Any]:
        return {
            "bound": sorted(self.adapters),
            "unbound": {k: self.reasons[k] for k in sorted(self.reasons)},
        }
