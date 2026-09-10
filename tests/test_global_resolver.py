from __future__ import annotations

from app.global_resolver import GlobalResolver


def test_registry_validation_passes() -> None:
    resolver = GlobalResolver()
    result = resolver.validate()
    assert result["status"] == "pass", result["errors"]
    assert result["resolution_id"] == "GA-HYPERNET-GLOBAL-RESOLUTION-002"
    assert result["counts"]["nodes.yaml"] >= 1
    assert result["counts"]["routes.yaml"] >= 1


def test_node_advertisement_and_heartbeat() -> None:
    resolver = GlobalResolver()
    advertised = resolver.advertise(
        "ga://node/eden",
        ["model.infer", "compute.execute"],
        {"capacity_score": 80, "cpu_free_pct": 72},
    )
    assert advertised["node"]["health"] == "online"
    assert "ga://capability/model.infer" in advertised["node"]["capabilities"]

    heartbeat = resolver.heartbeat(
        "ga://node/eden",
        resources={"capacity_score": 90, "cpu_free_pct": 81},
    )
    assert heartbeat["resources"]["capacity_score"] == 90


def test_model_inference_prefers_live_local_node() -> None:
    resolver = GlobalResolver()
    resolver.advertise(
        "ga://node/eden",
        ["model.infer"],
        {"capacity_score": 75},
    )
    resolver.advertise(
        "ga://node/render",
        ["model.infer"],
        {"capacity_score": 100},
    )
    result = resolver.resolve(
        "model.infer",
        source="ga://organ/atlas-mind",
        io_class="QUERY",
        prefer_local=True,
    )
    assert result["selected"] is not None
    assert result["selected"]["canonical_id"] == "ga://node/eden"
    assert result["route"]["canonical_id"] == "ga://route/model-inference"
    assert result["proof"] == "ga://organ/proofgrid"


def test_unknown_capability_is_rejected() -> None:
    resolver = GlobalResolver()
    try:
        resolver.resolve("does.not.exist")
    except Exception as exc:
        assert "unknown capability" in str(exc)
    else:
        raise AssertionError("unknown capability should fail")


def test_topology_contains_declared_nodes() -> None:
    resolver = GlobalResolver()
    topology = resolver.topology()
    ids = {item["canonical_id"] for item in topology["nodes"]}
    assert "ga://node/eden" in ids
    assert "ga://node/render" in ids
    assert "ga://node/vercel" in ids
