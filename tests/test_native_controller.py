"""Hand-written public-record fixtures; no official task or gold data."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from research.native_agent import controller as c


def reservation(**updates):
    return {"reservation_id": "SYNTHETIC", "status": "confirmed", "cabin": "economy",
            "total_baggages": 1, "nonfree_baggages": 0,
            "passengers": [{"first_name": "Example", "last_name": "Fixture"}],
            "flights": [{"flight_number": "SYN1", "date": "2030-01-01", "price": 10}], **updates}


def public(value):
    return {"available": True, "value": value}


@pytest.mark.parametrize("name,args,after", [
    ("cancel_reservation", {"reservation_id": "SYNTHETIC"}, reservation(status="cancelled")),
    ("update_reservation_baggages", {"reservation_id": "SYNTHETIC", "total_baggages": 2,
        "nonfree_baggages": 1, "payment_id": "synthetic"},
        reservation(total_baggages=2, nonfree_baggages=1)),
    ("update_reservation_passengers", {"reservation_id": "SYNTHETIC",
        "passengers": [{"first_name": "New", "last_name": "Fixture"}]},
        reservation(passengers=[{"first_name": "New", "last_name": "Fixture"}])),
    ("update_reservation_flights", {"reservation_id": "SYNTHETIC", "cabin": "business",
        "flights": [{"flight_number": "SYN2", "date": "2030-02-02"}], "payment_id": "synthetic"},
        reservation(cabin="business", flights=[{"flight_number": "SYN2", "date": "2030-02-02", "price": 20}])),
])
def test_requested_reservation_fields_are_not_acknowledgement_truth(name, args, after):
    before = public(reservation())
    contract = c.compile_contract(name, args, before)
    frozen = deepcopy((contract, before, after))
    assert c.field_status(contract, public(after), [])[0] == "satisfied"
    assert c.field_status(contract, before, [])[0] == "violated"
    assert (contract, before, after) == frozen


def test_unknown_on_missing_fields_error_or_mismatched_identity():
    contract = c.compile_contract("cancel_reservation", {"reservation_id": "SYNTHETIC"}, public(reservation()))
    for after in ({"available": False, "value": None}, public({"reservation_id": "other"}),
                  public({"reservation_id": "SYNTHETIC"})):
        assert c.field_status(contract, after, [])[0] == "unknown"
    assert c.parsed_read({"error": True, "content": json.dumps(reservation(status="cancelled"))})["available"] is False
    assert c.parsed_read({"content": "not-json"})["available"] is False
    assert c.parsed_read({"content": "[]"})["available"] is False


def test_missing_preflight_never_becomes_known():
    contract = c.compile_contract("cancel_reservation", {"reservation_id": "SYNTHETIC"},
                                  {"available": False, "value": None})
    assert c.field_status(contract, public(reservation(status="cancelled")), [])[0] == "unknown"
    assert c.read_plan("cancel_reservation", {}) == []


def test_certificate_requires_exactly_one_new_matching_mapping_entry():
    before = public({"user_id": "fixture", "payment_methods": {"old": {"source": "certificate", "amount": 25}}})
    contract = c.compile_contract("send_certificate", {"user_id": "fixture", "amount": 25}, before)
    after = deepcopy(before)
    assert c.field_status(contract, after, [])[0] == "violated"
    after["value"]["payment_methods"]["new"] = {"source": "certificate", "amount": 25}
    assert c.field_status(contract, after, [])[0] == "satisfied"
    after["value"]["payment_methods"]["new2"] = {"source": "certificate", "amount": 25}
    assert c.field_status(contract, after, [])[0] == "violated"


def booking():
    return {"user_id": "fixture", "origin": "AAA", "destination": "BBB", "flight_type": "one_way",
            "cabin": "economy", "passengers": [{"first_name": "Example", "last_name": "Fixture"}],
            "total_baggages": 1, "nonfree_baggages": 0, "insurance": "no",
            "flights": [{"flight_number": "SYN1", "date": "2030-01-01"}],
            "payment_methods": [{"payment_id": "synthetic", "amount": 10}]}


def test_booking_requires_new_identity_and_complete_actual_detail_reads():
    args = booking()
    contract = c.compile_contract("book_reservation", args, public({"user_id": "fixture", "reservations": ["OLD"]}))
    after = public({"user_id": "fixture", "reservations": ["OLD", "NEW"]})
    row = {**args, "reservation_id": "NEW"}
    assert c.field_status(contract, after, [])[0] == "unknown"
    assert c.field_status(contract, after, [public(row)])[0] == "satisfied"
    row["reservation_id"] = "OLD"
    assert c.field_status(contract, after, [public(row)])[0] == "unknown"


def test_guard_does_not_reset_from_tool_call_id_user_turn_or_changed_payload():
    args = {"reservation_id": "SYNTHETIC"}
    key = c.operation_key("episode", "cancel_reservation", args)
    assert key == c.operation_key("episode", "cancel_reservation", dict(reversed(list(args.items()))))
    guard = c.DuplicateGuard()
    resource = c.resource_key("cancel_reservation", args)
    guard.dispatched(key, resource)
    assert guard.reason(key, resource)
    assert guard.reason("different-payload", resource)
    guard.resolved(key, "violated")
    assert guard.reason(key, resource)
    assert guard.reason("different-payload", resource) is None
    guard.resolved(key, "satisfied")
    assert guard.reason(key, resource)
    assert c.operation_key("other-episode", "cancel_reservation", args) != key


def test_factory_rejects_invalid_arms_before_importing_native_runner():
    with pytest.raises(ValueError):
        c.make_agent_factory("unknown", "episode")


def test_network_blocked_native_wrapper_roundtrip_with_installed_211():
    """Actual native message/factory classes, synthetic provider proposals only."""
    source = Path(os.environ.get("CONSEQAX_NATIVE_SOURCE", "C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit"))
    python = Path(os.environ.get("CONSEQAX_211_PYTHON", "D:/ConsequaX-Research/recovery-2.1.1-venv/Scripts/python.exe"))
    dependencies = Path(os.environ.get("CONSEQAX_NATIVE_SITE", "D:/ConsequaX-Research/native-agent-pilot-venv/Lib/site-packages"))
    if not (source / "src/tau2/agent/llm_agent.py").is_file() or not python.is_file() or not dependencies.is_dir():
        pytest.skip("Pinned native source, native dependencies and installed 2.1.1 interpreter required")
    code = r'''
import builtins, json, os, socket, sys
from pathlib import Path
root, source, dependencies = sys.argv[1:]
sys.path[:0] = [root, str(Path(source) / "src")]
sys.path.append(dependencies)
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["TAU2_DATA_DIR"] = str(Path(source) / "data")
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
def refuse(*a, **k):
    raise AssertionError("Unexpected network attempt in synthetic integration")
socket.socket.connect = refuse
socket.getaddrinfo = refuse
original_open = builtins.open
def safe_open(path, *args, **kwargs):
    if str(path).replace("\\", "/").endswith("/tasks.json"):
        raise AssertionError("Official tasks are outside this synthetic test")
    return original_open(path, *args, **kwargs)
builtins.open = safe_open
from research.native_agent.controller import make_agent_factory
from tau2.data_model.message import AssistantMessage, ToolCall, ToolMessage, UserMessage
import tau2.utils.llm_utils as llm
for arm in ("B", "C", "R", "G"):
    proposals = [AssistantMessage(role="assistant", tool_calls=[ToolCall(id="write-1", name="cancel_reservation", arguments={"reservation_id":"SYNTHETIC"})]),
                 AssistantMessage(role="assistant", tool_calls=[ToolCall(id="write-2", name="cancel_reservation", arguments={"reservation_id":"SYNTHETIC"})])]
    llm.generate = lambda **kwargs: proposals.pop(0)
    agent = make_agent_factory(arm, "synthetic-"+arm)([], "FULL NATIVE POLICY FIXTURE", llm="synthetic-no-provider", task=object())
    state = agent.get_init_state()
    pre, state = agent.generate_next_message(UserMessage.text("Cancel the synthetic reservation."), state)
    assert pre.tool_calls[0].name == "get_reservation_details"
    write, state = agent.generate_next_message(ToolMessage(role="tool", id=pre.tool_calls[0].id, content=json.dumps({"reservation_id":"SYNTHETIC","status":"confirmed"})), state)
    assert write.tool_calls[0].name == "cancel_reservation"
    post, state = agent.generate_next_message(ToolMessage(role="tool", id="write-1", content=json.dumps({"reservation_id":"SYNTHETIC","status":"cancelled"})), state)
    assert post.tool_calls[0].name == "get_reservation_details"
    second, state = agent.generate_next_message(ToolMessage(role="tool", id=post.tool_calls[0].id, content=json.dumps({"reservation_id":"SYNTHETIC","status":"cancelled"})), state)
    assert bool(second.tool_calls) == (arm in ("B", "R"))
    receipts = [e for e in agent.events if e["event"] == "receipt"]
    if arm == "B":
        assert not receipts and [e for e in agent.events if e["event"] == "raw_public_capture"]
    else:
        assert receipts[0]["receipt"]["verification"]["status"] == "satisfied"
        assert receipts[0]["receipt"]["verification"]["origin"] == "unknown"
        assert receipts[0]["model_visible"]
    assert state.system_messages[0].content.endswith("</policy>")
    assert "FULL NATIVE POLICY FIXTURE" in state.system_messages[0].content
    assert [e["index"] for e in agent.events] == list(range(len(agent.events)))
    if arm in ("B", "C"):
        assert "consequa_x" not in sys.modules
print(json.dumps({"arms": ["B","C","R","G"], "actual_network_calls":0,"official_tasks":0,"synthetic_roundtrip":"passed"}))
'''
    result = subprocess.run([str(python), "-I", "-B", "-c", code,
        str(Path(__file__).resolve().parents[1]), str(source), str(dependencies)],
        text=True, capture_output=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout.splitlines()[-1])["synthetic_roundtrip"] == "passed"
