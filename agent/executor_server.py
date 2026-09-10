from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Ghost Atlas Hypernet Node Executor", version="0.5.0")


class ExecuteRequest(BaseModel):
    packet_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


def _auth(authorization: str | None) -> None:
    expected = os.getenv("GA_NODE_TOKEN")
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid node token")


def _allowed_commands() -> dict[str, list[str]]:
    raw = os.getenv("GA_NODE_COMMAND_MAP", "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GA_NODE_COMMAND_MAP must be JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("GA_NODE_COMMAND_MAP must be an object")
    return {str(k): [str(x) for x in v] for k, v in value.items() if isinstance(v, list) and v}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "node": os.getenv("GA_NODE_ID", "unconfigured"), "capabilities": sorted(_allowed_commands())}


@app.post("/execute")
def execute(request: ExecuteRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    command_map = _allowed_commands()
    argv = command_map.get(request.capability) or command_map.get(request.capability.removeprefix("ga://capability/"))
    if not argv:
        raise HTTPException(status_code=403, detail=f"capability not bound: {request.capability}")
    timeout = int(os.getenv("GA_NODE_EXEC_TIMEOUT", "300"))
    proc = subprocess.run(
        argv,
        input=json.dumps({"packet_id": request.packet_id, "capability": request.capability, "payload": request.payload}),
        text=True,
        capture_output=True,
        timeout=timeout,
        shell=False,
        check=False,
    )
    result = {
        "packet_id": request.packet_id,
        "capability": request.capability,
        "node": os.getenv("GA_NODE_ID"),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-65536:],
        "stderr": proc.stderr[-65536:],
    }
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=result)
    return result
