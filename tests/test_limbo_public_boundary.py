"""Invented offline public-API fakes; these are not LIMBO benchmark episodes."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from research.limbo_agent.boundary import (
    BoundaryJournalError,
    BoundaryLimits,
    BoundaryRefusal,
    PublicRuntimeBoundary,
    PublicRuntimeError,
    bind_public_runtime,
)


@dataclass
class FakeVerification:
    status: str
    detail: dict


class World:
    def __init__(self):
        self.clock = 10.0
        self.ledger = []
        self.pending = ["hidden delayed write"]
        self.waits = []

    def advance(self, seconds):
        self.waits.append(seconds)
        self.clock += seconds
        if seconds >= 3:
            self.ledger.extend(self.pending)
            self.pending.clear()


class ForbiddenAttribute:
    def __get__(self, instance, owner=None):
        raise AssertionError("hidden evaluator attribute was inspected")


class Runtime:
    targets = fault_plan = faults = events = fault_log = ForbiddenAttribute()

    def __init__(self):
        self.world = World()
        self.calls = []
        self.observation = {"ok": False, "error": {"type": "timeout"}}
        self.verification = FakeVerification("partial", {"missing_rows": [{"id": "b"}]})
        self.contract = SimpleNamespace(
            write=True, idempotent=False, destructive=False, irreversible=True,
            identity=lambda args: ("fake", args["id"], args.get("rows", [])),
            supports_key=lambda args: args.get("key_available", False),
            visibility_sla=lambda args: 2.0, batch_field="rows", compensator=None,
            drift=None,
        )
        # Accessing either callback is forbidden even during trusted binding.
        class Spec:
            handler = verifier = ForbiddenAttribute()
        spec = Spec()
        spec.name, spec.domain = "write_record", "invented"
        spec.description = "Invented test tool"
        spec.parameters = {"type": "object", "properties": {"id": {"type": "string"}}}
        spec.explicit_note, spec.consistency_note = "public keys", "public lag"
        spec.latency, spec.contract = 0.5, self.contract
        self.tools = {spec.name: spec}

    def execute(self, name, args, source="agent", note=""):
        self.calls.append(("execute", name, args, source, note))
        self.world.clock += 0.5
        return self.observation

    def verify(self, name, args, t_call, *, truth=False):
        self.calls.append(("verify", name, args, t_call, truth))
        self.world.clock += 0.25
        return self.verification


def bind(runtime=None, *, limits=None, journal=None):
    runtime = runtime or Runtime()
    entries = [] if journal is None else journal
    view = bind_public_runtime(
        runtime, limits=limits or BoundaryLimits(3, 3, 3, 10.0), journal=entries.append,
    )
    return view, runtime, entries


@pytest.mark.parametrize("name", [
    "world", "ledger", "tools", "targets", "faults", "fault_plan", "fault_log",
    "pending", "events", "runtime", "_runtime", "__dict__", "journal", "advance",
    "handler", "verifier", "flush", "trace", "finished", "_state",
])
def test_no_raw_native_attributes_or_forwarding(name):
    view, _, _ = bind()
    with pytest.raises(AttributeError):
        getattr(view, name)
    with pytest.raises(AttributeError):
        setattr(view, name, "injected")


def test_direct_construction_refused():
    with pytest.raises(TypeError, match="trusted runner"):
        PublicRuntimeBoundary()


def test_metadata_is_explicit_copied_data_without_callbacks():
    view, runtime, journal = bind()
    metadata = view.tool_metadata()
    assert set(metadata["write_record"]) == {
        "name", "domain", "description", "parameters", "explicit_note",
        "consistency_note", "latency", "contract",
    }
    assert "handler" not in metadata["write_record"]
    assert "verifier" not in metadata["write_record"]["contract"]
    metadata["write_record"]["parameters"]["properties"].clear()
    runtime.tools["write_record"].parameters["properties"]["private_later"] = {}
    journal[0]["metadata"]["write_record"]["description"] = "mutated audit copy"
    fresh = view.tool_metadata()["write_record"]
    assert fresh["description"] == "Invented test tool"
    assert fresh["parameters"]["properties"] == {"id": {"type": "string"}}


def test_contract_callback_inputs_and_outputs_have_no_aliases():
    view, runtime, _ = bind()
    args = {"id": "a", "rows": [{"id": "b"}], "key_available": True}
    result = view.contract("write_record", args)
    assert result["identity"] == ("fake", "a", [{"id": "b"}])
    assert result["supports_key"] is True
    assert result["visibility_sla"] == 2
    result["identity"][2][0]["id"] = "changed"
    assert args["rows"][0]["id"] == "b"
    assert view.contract("write_record", args)["identity"][2][0]["id"] == "b"
    assert view.accounting()["metadata_callback_calls"] == {
        "identity": 2, "supports_key": 2, "visibility_sla": 2,
    }


def test_metadata_callbacks_get_independent_argument_copies():
    runtime = Runtime()
    def identity(args):
        args["id"] = "mutated"
        return (args["id"],)
    runtime.contract.identity = identity
    runtime.contract.supports_key = lambda args: args["id"] == "original"
    view, _, _ = bind(runtime)
    assert view.contract("write_record", {"id": "original"})["supports_key"] is True


@pytest.mark.parametrize("truth", [True, 1, 0, None, "false", {}, []])
def test_privileged_or_nonboolean_verification_refused_before_native_call(truth):
    view, runtime, journal = bind()
    with pytest.raises(BoundaryRefusal, match="Privileged"):
        view.verify("write_record", {"id": "a"}, 10, truth=truth)
    assert runtime.calls == []
    assert journal[-1]["operation"] == "verify_refused"
    assert journal[-1]["delegated"] is False
    assert view.accounting()["delegated_calls"]["verify"] == 0


@pytest.mark.parametrize("status", ["unknown", "partial", "unverifiable", "absent", "found",
                                   "future_public_status"])
def test_public_verification_status_detail_preserved_without_success_coercion(status):
    runtime = Runtime()
    runtime.verification.status = status
    view, _, journal = bind(runtime)
    result = view.verify("write_record", {"id": "a"}, 10)
    assert result == {"status": status, "detail": {"missing_rows": [{"id": "b"}]}}
    result["detail"]["missing_rows"].clear()
    assert runtime.verification.detail["missing_rows"] == [{"id": "b"}]
    assert journal[-1]["result"]["detail"]["missing_rows"] == [{"id": "b"}]
    assert runtime.calls[-1][-1] is False


def test_real_execution_verification_wait_order_and_unknown_physical_costs():
    view, runtime, journal = bind()
    assert view.last_dispatch_start is None
    args = {"id": "a", "rows": [{"id": "b"}]}
    observed = view.execute("write_record", args, source="harness", note="attempt")
    assert observed == runtime.observation
    assert observed["ok"] is False
    assert view.last_dispatch_start == 10
    view.verify("write_record", args, view.last_dispatch_start)
    assert view.wait(3) == {"requested_seconds": 3, "clock_after": 13.75}
    assert runtime.world.waits == [3]
    assert runtime.world.ledger == ["hidden delayed write"]
    assert [call[0] for call in runtime.calls] == ["execute", "verify"]
    assert runtime.calls[0][3:] == ("harness", "attempt")
    assert view.clock == 13.75
    accounting = view.accounting()
    assert accounting["delegated_calls"] == {"execute": 1, "verify": 1, "wait": 1}
    assert accounting["requested_virtual_wait_seconds"] == 3
    assert accounting["native_physical_effect_count"] is None
    assert accounting["verification_cost"] is None
    work = [item for item in journal if item["phase"] == "return"
            and item["operation"] in ("execute", "verify", "wait")]
    assert [(item["virtual_start"], item["virtual_end"]) for item in work] == [
        (10, 10.5), (10.5, 10.75), (10.75, 13.75),
    ]


def test_execution_data_does_not_alias_caller_runtime_or_audit():
    view, runtime, journal = bind()
    args = {"id": "a", "rows": [{"id": "b"}]}
    result = view.execute("write_record", args)
    args["rows"].clear()
    result["error"]["type"] = "changed"
    runtime.calls[0][2]["rows"][0]["id"] = "mutated native args"
    assert runtime.observation["error"]["type"] == "timeout"
    start = next(item for item in journal if item["operation"] == "execute"
                 and item["phase"] == "start")
    assert start["inputs"]["args"]["rows"] == [{"id": "b"}]
    assert journal[-1]["result"]["error"]["type"] == "timeout"


@pytest.mark.parametrize("operation", ["execute", "verify", "wait"])
def test_declared_ceiling_blocks_before_dispatch(operation):
    view, runtime, journal = bind(limits=BoundaryLimits(0, 0, 0, 0))
    with pytest.raises(BoundaryRefusal, match="ceiling"):
        if operation == "execute":
            view.execute("write_record", {"id": "a"})
        elif operation == "verify":
            view.verify("write_record", {"id": "a"}, 10)
        else:
            view.wait(1)
    assert runtime.calls == []
    assert runtime.world.waits == []
    assert journal[-1]["delegated"] is False


def test_cumulative_wait_ceiling_and_no_local_clock_simulation():
    view, runtime, _ = bind(limits=BoundaryLimits(1, 1, 3, 3))
    view.wait(2)
    with pytest.raises(BoundaryRefusal, match="Total virtual wait"):
        view.wait(2)
    assert runtime.world.waits == [2]
    assert view.clock == 12
    assert view.accounting()["delegated_calls"]["wait"] == 1


def test_native_exception_counted_once_without_retry_or_exception_payload():
    runtime = Runtime()
    def broken(name, args, source, note):
        runtime.calls.append(("raised",))
        raise RuntimeError("hidden evaluator payload")
    runtime.execute = broken
    view, _, journal = bind(runtime)
    with pytest.raises(PublicRuntimeError, match="execute raised RuntimeError") as error:
        view.execute("write_record", {"id": "a"})
    assert "hidden" not in str(error.value)
    assert runtime.calls == [("raised",)]
    assert journal[-1]["delegated"] is True
    assert journal[-1]["error_type"] == "RuntimeError"
    assert view.accounting()["delegated_calls"]["execute"] == 1


def test_failing_audit_sink_closes_boundary_before_further_dispatch():
    runtime = Runtime()
    journal = []
    def sink(item):
        if item["operation"] == "execute" and item["phase"] == "return":
            raise OSError("disk unavailable")
        journal.append(item)
    view = bind_public_runtime(runtime, limits=BoundaryLimits(3, 3, 3, 3), journal=sink)
    with pytest.raises(BoundaryJournalError):
        view.execute("write_record", {"id": "a"})
    with pytest.raises(BoundaryJournalError, match="closed"):
        view.execute("write_record", {"id": "a"})
    assert len(runtime.calls) == 1
    assert [item["phase"] for item in journal if item["operation"] == "execute"] == ["start"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), object(), {1: "key"}])
def test_nonpublic_values_refused_without_native_call(bad):
    view, runtime, journal = bind()
    with pytest.raises(BoundaryRefusal):
        view.execute("write_record", {"id": bad})
    assert runtime.calls == []
    assert journal[-2]["operation"] == "execute_input_refused"
    assert journal[-2]["inputs"]["full_input_preserved"] is False
    assert journal[-1]["delegated"] is False


def test_cycle_and_object_hooks_not_executed():
    class Sneaky:
        def __deepcopy__(self, memo):
            pytest.fail("object hook was called")
        def __str__(self):
            pytest.fail("object was stringified")
    view, runtime, _ = bind()
    for value in (Sneaky(),):
        with pytest.raises(BoundaryRefusal):
            view.execute("write_record", {"id": value})
    cycle = []
    cycle.append(cycle)
    with pytest.raises(BoundaryRefusal, match="cyclic"):
        view.execute("write_record", {"id": cycle})
    assert runtime.calls == []


def test_native_nonpublic_result_refused_after_actual_dispatch():
    runtime = Runtime()
    runtime.observation = {"ok": True, "result": runtime.world}
    view, _, journal = bind(runtime)
    with pytest.raises(BoundaryRefusal, match="plain data"):
        view.execute("write_record", {"id": "a"})
    assert len(runtime.calls) == 1
    assert journal[-1]["delegated"] is True


@pytest.mark.parametrize("values", [(-1, 1, 1, 1), (True, 1, 1, 1), (1, 1, 1, -1),
                                    (1, 1, 1, float("inf"))])
def test_limits_must_be_explicit_nonnegative_finite(values):
    with pytest.raises(BoundaryRefusal):
        BoundaryLimits(*values)


@pytest.mark.parametrize("field,value", [("write", 1), ("batch_field", {}),
                                        ("compensator", []), ("drift", ("a", 2))])
def test_nonconforming_contract_metadata_refused_during_binding(field, value):
    runtime = Runtime()
    setattr(runtime.contract, field, value)
    with pytest.raises(BoundaryRefusal):
        bind(runtime)


def test_partial_metadata_work_is_counted_if_callback_raises():
    runtime = Runtime()
    def broken(args):
        raise KeyError("private callback state")
    runtime.contract.supports_key = broken
    view, _, journal = bind(runtime)
    with pytest.raises(PublicRuntimeError, match="contract raised KeyError"):
        view.contract("write_record", {"id": "a"})
    assert journal[-1]["error_type"] == "KeyError"
    assert view.accounting()["metadata_callback_calls"] == {
        "identity": 1, "supports_key": 1, "visibility_sla": 0,
    }
