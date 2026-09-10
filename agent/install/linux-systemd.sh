#!/usr/bin/env bash
set -euo pipefail
: "${GA_NODE_ID:?set GA_NODE_ID}"
: "${GA_CONTROL_PLANE_URL:?set GA_CONTROL_PLANE_URL}"
ROOT="${GA_NODE_ROOT:-/opt/ghost-atlas-hypernet}"
PY="${GA_NODE_PYTHON:-python3}"
mkdir -p "$ROOT"
cp -r agent "$ROOT/agent"
cat >/etc/ghost-atlas-node.env <<EOF
GA_NODE_ID=${GA_NODE_ID}
GA_CONTROL_PLANE_URL=${GA_CONTROL_PLANE_URL}
GA_NODE_LISTEN_PORT=${GA_NODE_LISTEN_PORT:-8765}
GA_NODE_HEARTBEAT_SECONDS=${GA_NODE_HEARTBEAT_SECONDS:-30}
EOF
if [[ -n "${GA_NODE_TOKEN:-}" ]]; then echo "GA_NODE_TOKEN=${GA_NODE_TOKEN}" >>/etc/ghost-atlas-node.env; fi
if [[ -n "${GA_NODE_COMMAND_MAP:-}" ]]; then echo "GA_NODE_COMMAND_MAP=${GA_NODE_COMMAND_MAP}" >>/etc/ghost-atlas-node.env; fi
cat >/etc/systemd/system/ghost-atlas-node-executor.service <<EOF
[Unit]
Description=Ghost Atlas Hypernet Node Executor
After=network-online.target
Wants=network-online.target
[Service]
EnvironmentFile=/etc/ghost-atlas-node.env
WorkingDirectory=$ROOT
ExecStart=$PY -m uvicorn agent.executor_server:app --host 0.0.0.0 --port \${GA_NODE_LISTEN_PORT}
Restart=always
RestartSec=3
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/ghost-atlas-node-agent.service <<EOF
[Unit]
Description=Ghost Atlas Hypernet Node Agent
After=network-online.target ghost-atlas-node-executor.service
Wants=network-online.target
Requires=ghost-atlas-node-executor.service
[Service]
EnvironmentFile=/etc/ghost-atlas-node.env
WorkingDirectory=$ROOT
ExecStart=$PY -m agent.node_agent
Restart=always
RestartSec=3
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ghost-atlas-node-executor.service ghost-atlas-node-agent.service
systemctl --no-pager --full status ghost-atlas-node-agent.service || true
