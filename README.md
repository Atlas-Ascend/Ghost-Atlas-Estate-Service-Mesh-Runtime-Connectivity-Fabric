# Ghost Atlas Estate Service Mesh / Runtime Connectivity Fabric

Canonical east-west runtime connectivity layer for the Ghost Atlas estate.

This repository answers the question that the Estate Service Catalog cannot answer by itself:

> Once a healthy provider has been discovered, how does one Ghost Atlas service safely call another service and prove what happened?

## Technical role

This is the estate's **service mesh / east-west traffic control plane and application-level data-plane gateway**.

It does not replace:

- `Estate-Service-Catalog-Capability-Registry` — canonical service/capability discovery
- CrownGrid — estate capability/I/O routing
- JANUS / ODIN — authorization and bounded execution identity
- Estate Event Gateway — normalized event distribution
- Runtime Observatory — operator-facing telemetry
- Release Deployment Control Plane — release/promotion/deployment orchestration

Instead it sits between capability resolution and runtime invocation:

```text
ATLAS MIND / JANUS / PACKET OS
            |
            v
        CROWNGRID
            |
            v
ESTATE SERVICE CATALOG + CAPABILITY REGISTRY
            |
            | healthy provider candidates
            v
+---------------------------------------------------+
| GHOST ATLAS ESTATE SERVICE MESH                  |
|                                                   |
| service identity                                  |
| route policy                                      |
| retries / timeout                                 |
| deterministic failover                            |
| circuit breaker                                   |
| request correlation                               |
| invocation proxy                                  |
| telemetry / proof events                          |
+------------------------+--------------------------+
                         |
                         v
             RUNTIME SERVICES / WORKERS
                         |
                         v
                 ESTATE EVENT GATEWAY
                         |
                         v
                RUNTIME OBSERVATORY
```

## v0.1 implementation

The first implementation is intentionally deployable without requiring Kubernetes, Istio, Linkerd, Consul, or Envoy. It provides an application-level mesh gateway that can run on Render, EDEN, or another estate runtime and later sit behind or alongside a native proxy mesh.

### Runtime features

- registry-backed capability resolution
- deterministic provider selection and failover
- per-capability retry/timeout/circuit-breaker policies
- active circuit state with threshold and recovery window
- caller service identity headers
- optional HMAC request signing (`GA_MESH_SHARED_SECRET`)
- correlation IDs propagated across service calls
- HTTP invocation proxy for east-west traffic
- bounded response payload capture
- structured mesh events
- SSE telemetry stream for Runtime Observatory
- health/readiness endpoints

## API

- `GET /health`
- `GET /ready`
- `GET /v1/mesh/policies`
- `PUT /v1/mesh/policies/{capability_id}`
- `POST /v1/mesh/resolve`
- `POST /v1/mesh/invoke`
- `GET /v1/mesh/circuits`
- `POST /v1/mesh/circuits/{service_id}/reset`
- `GET /v1/mesh/events`
- `GET /v1/mesh/events/stream` (SSE)

## Environment

```text
PORT=8000
GA_SERVICE_REGISTRY_URL=http://estate-registry:8000
GA_EVENT_GATEWAY_URL=
GA_MESH_SHARED_SECRET=
GA_MESH_CALLER_SERVICE=estate.mesh
GA_MESH_MAX_CAPTURE_BYTES=65536
```

Secrets are never committed to this repository.

## Design law

1. **Registry owns service/capability truth.** The mesh consumes it; the mesh does not invent providers.
2. **JANUS/ODIN own authorization.** The mesh transports approved calls; it is not an executive authority.
3. **Fail closed.** No healthy provider, exhausted retries, open circuits, or invalid identity state returns an explicit failure.
4. **Correlation is mandatory.** Every invocation has a correlation ID and emits structured telemetry.
5. **Policies are bounded.** Retries, timeouts, circuit thresholds, and recovery windows have explicit limits.
6. **Native mesh adoption is evolutionary.** Envoy/Linkerd/Istio/mTLS can replace the HTTP data-plane adapter later without changing the estate-facing capability contract.

## Build truth

`MESH_ROUTE_RESOLUTION=PASS` when a capability resolves only through the canonical registry.

`FAILOVER=PASS` when an unhealthy/failing provider is skipped and the next eligible provider is attempted deterministically.

`CIRCUIT_BREAKER=PASS` when repeated failures open a provider circuit and recovery timeout permits a bounded half-open retry.

`SERVICE_IDENTITY=PASS` when caller identity and correlation metadata are propagated and optional HMAC signatures validate deterministically.

`TELEMETRY=PASS` when invocation lifecycle events are queryable and streamable over SSE.

`BUILD_TRUTH=PASS` only after CI passes tests, import checks, and production Docker build.
