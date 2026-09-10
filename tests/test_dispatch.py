from app.dispatch import DispatchFabric
from app.global_resolver import GlobalResolver, ResolutionError


def _fabric():
    resolver = GlobalResolver()
    resolver.advertise("ga://node/eden", ["model.infer"], {"capacity_score": 10})
    fabric = DispatchFabric(resolver)
    return resolver, fabric


def test_dispatch_selects_registered_target():
    _, fabric = _fabric()
    result = fabric.dispatch(packet_id="PKT-001", capability="model.infer", payload={"prompt": "ping"})
    assert result["state"] == "DISPATCHED"
    assert result["target"] == "ga://node/eden"
    assert result["next_proof_stage"] == "ga://organ/seca"


def test_executor_and_proof_chain_close_loop():
    _, fabric = _fabric()
    fabric.register_executor("ga://node/eden", lambda record: {"ok": True, "packet_id": record.packet_id})
    result = fabric.dispatch(packet_id="PKT-002", capability="model.infer", execute=True)
    assert result["state"] == "EXECUTED"
    dispatch_id = result["dispatch_id"]
    for organ in fabric.proof_chain:
        result = fabric.complete_stage(dispatch_id, organ, {"verified": True})
    assert result["state"] == "COMPLETED"
    assert result["proof_chain"] == fabric.proof_chain
    assert result["next_proof_stage"] is None


def test_proof_chain_rejects_out_of_order_stage():
    _, fabric = _fabric()
    fabric.register_executor("ga://node/eden", lambda record: {"ok": True})
    result = fabric.dispatch(packet_id="PKT-003", capability="model.infer", execute=True)
    try:
        fabric.complete_stage(result["dispatch_id"], "ga://organ/proofgrid")
    except ResolutionError as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("expected proof-chain violation")


def test_missing_executor_is_explicit_state():
    _, fabric = _fabric()
    result = fabric.dispatch(packet_id="PKT-004", capability="model.infer")
    result = fabric.execute(result["dispatch_id"])
    assert result["state"] == "AWAITING_EXECUTOR"


def test_failure_can_enter_retryable_state():
    _, fabric = _fabric()
    result = fabric.dispatch(packet_id="PKT-005", capability="model.infer")
    result = fabric.fail(result["dispatch_id"], "temporary transport failure", retryable=True)
    assert result["state"] == "RETRYABLE"
    assert "transport" in result["error"]
