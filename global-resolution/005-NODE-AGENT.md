# GA-HYPERNET-GLOBAL-RESOLUTION-005 // NODE AGENT + AUTO-REGISTRATION

A reboot-resilient Hypernet node joins the estate by running two bounded processes:

1. `agent.executor_server` — capability-gated execution endpoint.
2. `agent.node_agent` — hardware inventory, advertisement, heartbeat, retry/rejoin loop.

## Boot lifecycle

`BOOT -> identity -> inventory -> executor online -> advertise -> heartbeat -> governed packet acceptance -> bounded execution -> receipt -> heartbeat`

## Required environment

- `GA_NODE_ID` canonical `ga://node/*` identity.
- `GA_CONTROL_PLANE_URL` service-mesh control plane.
- `GA_NODE_TOKEN` optional bearer secret.
- `GA_NODE_COMMAND_MAP` JSON object mapping capability IDs to fixed argv arrays.

Optional:

- `GA_NODE_CAPABILITIES`
- `GA_NODE_LISTEN_HOST`
- `GA_NODE_LISTEN_PORT`
- `GA_NODE_ADVERTISE_HOST`
- `GA_NODE_HEARTBEAT_SECONDS`
- `GA_NODE_EXEC_TIMEOUT`

## Safety invariant

Auto-registration does not imply arbitrary execution authority. Executor commands are fixed argv arrays sourced from the node's explicit capability map and are invoked with `shell=False`. A capability without a binding returns HTTP 403.

## Persistence

- Linux/server nodes: `agent/install/linux-systemd.sh`
- JANUS/ODIN Termux nodes: `agent/install/termux-boot.sh`

## Proof criteria

A node is ACTIVE only when the control plane observes a non-expired heartbeat, the node has advertised a canonical identity and declared capabilities, and the executor endpoint is explicitly configured. Packet execution remains incomplete until the 003 proof chain completes: `SECA -> DevOS -> ProofGrid -> Thoth -> JANUS PRIME`.
