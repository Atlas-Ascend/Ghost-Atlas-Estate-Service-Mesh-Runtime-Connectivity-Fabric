from agent.node_agent import declared_capabilities, inventory


def test_declared_capabilities_for_eden(monkeypatch):
    monkeypatch.delenv("GA_NODE_CAPABILITIES", raising=False)
    caps = declared_capabilities("ga://node/eden")
    assert "compute.execute" in caps
    assert "model.infer" in caps


def test_extra_capabilities(monkeypatch):
    monkeypatch.setenv("GA_NODE_CAPABILITIES", "alpha.run,beta.run")
    caps = declared_capabilities("ga://node/gaia")
    assert "alpha.run" in caps
    assert "beta.run" in caps


def test_inventory_has_capacity_score():
    data = inventory()
    assert data["cpu_count"] >= 0
    assert data["capacity_score"] >= 1
    assert "disk" in data
