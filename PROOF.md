# Build Truth — Ghost Atlas Estate Service Mesh v0.1

## Purpose

Prove the Ghost Atlas estate has an executable east-west runtime connectivity fabric that consumes canonical service discovery and applies bounded routing, identity, retry, failover, circuit-breaking, and telemetry semantics before runtime invocation.

## Acceptance gates

### MESH_ROUTE_RESOLUTION

PASS when:

- capability resolution is delegated to the Estate Service Catalog runtime API;
- the mesh does not invent provider identities;
- provider ordering received from the registry is preserved unless a provider is blocked by mesh circuit state;
- no eligible provider fails closed.

### TRAFFIC_POLICY

PASS when:

- timeout is bounded to 100–30000 ms;
- retries are bounded to 0–5;
- circuit failure threshold is bounded to 1–20;
- recovery window is bounded to 1–300 seconds;
- degraded-provider routing is explicit rather than implicit.

### SERVICE_IDENTITY

PASS when:

- caller service identity is propagated on every invocation;
- correlation ID is propagated on every invocation;
- mesh timestamp is propagated on every invocation;
- when `GA_MESH_SHARED_SECRET` is configured, requests carry a deterministic HMAC-SHA256 signature.

This v0.1 identity contract is application-level signing. It is not represented as mTLS. Native workload identity and mTLS are production-hardening follow-ons.

### RETRY_AND_FAILOVER

PASS when:

- network failure, timeout, or upstream 5xx is considered transport/provider failure;
- bounded retry policy is applied;
- a failing provider may be skipped in favor of the next registry-qualified candidate;
- application 4xx responses are returned to the caller and are not silently retried against another provider.

### CIRCUIT_BREAKER

PASS when:

- provider failures are counted;
- the circuit opens at the configured threshold;
- open circuits are skipped during resolution/invocation;
- recovery window permits a bounded half-open attempt;
- success closes/reset the circuit;
- operator reset endpoint exists.

### TELEMETRY

PASS when:

- invocation start/completion/failure events carry correlation IDs;
- route resolution emits a structured event;
- events are queryable over HTTP;
- events are streamable over SSE;
- optional Estate Event Gateway publication does not block the invocation path when telemetry publication fails.

### DEPLOYMENT

PASS when:

- Docker image builds;
- Render blueprint declares the web service;
- `/health` is the production health check;
- runtime serves `app.main:app`.

### BUILD_TRUTH

PASS only when GitHub Actions successfully executes tests, imports the runtime, and builds the production container on the promoted commit.

## Canonical proof statement

```text
ESTATE_SERVICE_MESH=IMPLEMENTED
REGISTRY_BACKED_ROUTING=IMPLEMENTED
BOUNDED_TRAFFIC_POLICY=IMPLEMENTED
SERVICE_IDENTITY_HEADERS=IMPLEMENTED
OPTIONAL_HMAC_IDENTITY=IMPLEMENTED
RETRY=IMPLEMENTED
FAILOVER=IMPLEMENTED
CIRCUIT_BREAKER=IMPLEMENTED
CORRELATION_PROPAGATION=IMPLEMENTED
HTTP_DATA_PLANE_PROXY=IMPLEMENTED
SSE_TELEMETRY=IMPLEMENTED
EVENT_GATEWAY_PUBLISHER=IMPLEMENTED
MACHINE_SCHEMAS=IMPLEMENTED
RENDER_BLUEPRINT=DECLARED
CI_BUILD_TRUTH=DECLARED
NATIVE_MTLS=FUTURE_HARDENING
```

A green CI run upgrades the corresponding implemented/declared gates to repository-proven PASS.
