#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
: "${GA_NODE_ID:?set GA_NODE_ID}"
: "${GA_CONTROL_PLANE_URL:?set GA_CONTROL_PLANE_URL}"
ROOT="${GA_NODE_ROOT:-$HOME/ghost-atlas-hypernet}"
mkdir -p "$ROOT" "$HOME/.termux/boot"
cp -r agent "$ROOT/agent"
cat >"$ROOT/node.env" <<EOF
export GA_NODE_ID='${GA_NODE_ID}'
export GA_CONTROL_PLANE_URL='${GA_CONTROL_PLANE_URL}'
export GA_NODE_LISTEN_PORT='${GA_NODE_LISTEN_PORT:-8765}'
export GA_NODE_HEARTBEAT_SECONDS='${GA_NODE_HEARTBEAT_SECONDS:-30}'
EOF
[[ -n "${GA_NODE_TOKEN:-}" ]] && printf "export GA_NODE_TOKEN='%s'\n" "$GA_NODE_TOKEN" >>"$ROOT/node.env"
[[ -n "${GA_NODE_COMMAND_MAP:-}" ]] && printf "export GA_NODE_COMMAND_MAP='%s'\n" "$GA_NODE_COMMAND_MAP" >>"$ROOT/node.env"
cat >"$HOME/.termux/boot/ghost-atlas-hypernet.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
source "$ROOT/node.env"
cd "$ROOT"
pkill -f 'uvicorn agent.executor_server:app' 2>/dev/null || true
pkill -f 'python.*agent.node_agent' 2>/dev/null || true
nohup python -m uvicorn agent.executor_server:app --host 0.0.0.0 --port \"\$GA_NODE_LISTEN_PORT\" >"$ROOT/executor.log" 2>&1 &
sleep 2
nohup python -m agent.node_agent >"$ROOT/agent.log" 2>&1 &
EOF
chmod +x "$HOME/.termux/boot/ghost-atlas-hypernet.sh"
"$HOME/.termux/boot/ghost-atlas-hypernet.sh"
echo "HYPERNET_NODE_BOOT=INSTALLED"
