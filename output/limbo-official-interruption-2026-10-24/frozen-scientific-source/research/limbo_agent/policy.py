"""Matched LIMBO guard integration using public data and ConseqaX 2.1.1.

The decision algorithm is the *unchanged upstream* ``OutcomeGuard``. The
package condition runs it over a narrow compatibility view and round-trips
public verification through a typed package receipt. This is a representation
and integration comparison, not an independently invented recovery algorithm.
No model calls, tasks, fault plans, target predicates or grades are imported.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
import zipfile

from .boundary import (
    BoundaryJournalError,
    BoundaryLimits,
    BoundaryRefusal,
    PublicRuntimeBoundary,
    _copy,
    bind_public_runtime,
)


RECEIPT_SCHEMA = "conseqax-limbo-public-verification-v1"
FRAMEWORK_WHEEL_SHA256 = "c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98"
RECEIPT_SCOPE = (
    "Current native public-verifier report only; matching is inherited from "
    "the native service contract. Origin, durable settlement, absence of "
    "in-flight requests and exactly-once execution are not established."
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def audit_framework_wheel(wheel_path: str | Path) -> dict:
    """Bind all 54 installed package payload files to the exact selected wheel.

    This does not install packages or claim that all third-party dependency
    payloads are pinned. Bytecode caches are excluded; unexpected other package
    files and import-path shadowing are refused.
    """
    import consequa_x as cx

    wheel_path = Path(wheel_path).resolve(strict=True)
    wheel_sha = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    if wheel_sha != FRAMEWORK_WHEEL_SHA256:
        raise BoundaryRefusal("Scientific framework wheel identity differs")
    distribution = importlib.metadata.distribution("consequa-x")
    if distribution.version != "2.1.1" or cx.__version__ != "2.1.1":
        raise BoundaryRefusal("Scientific framework must be installed as version 2.1.1")
    package_root = Path(distribution.locate_file("consequa_x")).resolve(strict=True)
    if Path(cx.__file__).resolve(strict=True) != package_root / "__init__.py":
        raise BoundaryRefusal("Imported framework is shadowed outside the selected distribution")
    payload = {}
    with zipfile.ZipFile(wheel_path) as archive:
        for name in archive.namelist():
            if not name.startswith("consequa_x/") or name.endswith("/"):
                continue
            actual = Path(distribution.locate_file(name)).resolve(strict=True)
            if not actual.is_relative_to(package_root):
                raise BoundaryRefusal("Framework payload escaped its package root")
            content = actual.read_bytes()
            if content != archive.read(name):
                raise BoundaryRefusal("Installed framework payload differs: " + name)
            payload[name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    installed = {"consequa_x/" + path.relative_to(package_root).as_posix()
                 for path in package_root.rglob("*")
                 if path.is_file() and "__pycache__" not in path.relative_to(package_root).parts}
    if len(payload) != 54 or "consequa_x/py.typed" not in payload or installed != set(payload):
        raise BoundaryRefusal("Installed framework payload is incomplete or has unexpected files")
    return {"framework_version": distribution.version, "framework_wheel": str(wheel_path),
            "framework_wheel_sha256": wheel_sha, "framework_root": str(package_root),
            "framework_payload": payload, "framework_payload_count": len(payload),
            "coverage": "All wheel package payload bytes; excludes cache bytecode and dependency payloads"}


def _mapped_status(native_status: str) -> str:
    return {"found": "satisfied", "absent": "violated"}.get(native_status, "unknown")


def _milliseconds(seconds: float) -> int:
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or seconds < 0:
        raise BoundaryRefusal("Receipt virtual time must be finite and nonnegative")
    return int(round(seconds * 1000))


def make_public_receipt(episode_id: str, sequence: int, name: str, args: dict,
                        t_call: float, t_observed: float, native: dict) -> dict:
    """Check a real report using the pinned SDK; never verify privileged truth.

    ``absent`` violates only the current visible-match predicate. It is not
    proof that the write failed or that retry is safe. ``partial`` and all
    unavailable/future statuses stay distinct in the retained public report,
    while the package's three-valued predicate is unknown for them.
    """
    import consequa_x as cx

    if cx.__version__ != "2.1.1":
        raise RuntimeError("LIMBO receipts require the selected ConseqaX 2.1.1 wheel")
    native, args = _copy(native), _copy(args)
    if type(native) is not dict or type(native.get("status")) is not str or type(native.get("detail")) is not dict:
        raise BoundaryRefusal("Receipt requires a native string status and dictionary detail")
    registered_ms, observed_ms = _milliseconds(t_call), _milliseconds(t_observed)
    if t_observed < t_call or observed_ms < registered_ms:
        raise BoundaryRefusal("Receipt observation precedes the original dispatch")
    if type(episode_id) is not str or type(sequence) is not int or sequence < 1 or type(name) is not str:
        raise BoundaryRefusal("Receipt identity requires an episode, positive sequence and tool name")
    key = "limbo-public-" + hashlib.sha256(_canonical(
        [episode_id, sequence, name, args, t_call, t_observed, native])).hexdigest()
    action = cx.Action(action_id=key, actor="limbo_guard", name=name,
        arguments=args, registered_at_ms=registered_ms,
        contract=cx.OutcomeContract(contract_id=key + ":current-visible-match",
            predicate="limbo_current_public_verifier_match",
            expected={"tool": name, "arguments": args},
            deadline_ms=registered_ms, exact_count=None))
    observation = cx.Observation(observation_id=key + ":public-report",
        source="limbo_public_verifier", observed_at_ms=observed_ms, as_of_ms=observed_ms,
        scope={"evidence": "complete returned public report; not a complete world snapshot"},
        records=({"native": native},), available=True, complete=True)

    class PublicReportVerifier:
        def verify(self, action, observation):
            report = observation.to_dict()["records"][0]["native"]
            status = _mapped_status(report["status"])
            return cx.VerificationResult(contract_id=action.contract.contract_id,
                action_id=action.action_id, status=cx.VerificationStatus(status),
                observed_at_ms=observation.observed_at_ms, origin=cx.OriginStatus.UNKNOWN,
                evidence=(cx.Evidence(observation_id=observation.observation_id,
                    source=observation.source, as_of_ms=observation.as_of_ms,
                    details={"native_status": report["status"], "scope": RECEIPT_SCOPE}),),
                reason="Mapped current native report; no independent service or temporal inference")

    before = _canonical({"action": action.to_dict(), "observation": observation.to_dict()})
    result = cx.verify(action, observation, verifier=PublicReportVerifier())
    if before != _canonical({"action": action.to_dict(), "observation": observation.to_dict()}):
        raise RuntimeError("Package verification mutated the public report")
    receipt = {"schema": RECEIPT_SCHEMA, "framework_version": cx.__version__,
            "action": action.to_dict(), "observation": observation.to_dict(),
            "verification": result.to_dict(), "scope": RECEIPT_SCOPE,
            "time_base": "native_virtual_clock_ms",
            "deadline_scope": "Schema registration horizon only; no deadline or in-flight settlement predicate"}
    receipt["content_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    return receipt


def receipt_public_report(receipt: dict) -> dict:
    """Recover the exact report that the guard consumes, refusing inconsistent receipts."""
    receipt = _copy(receipt)
    try:
        content_sha = receipt.pop("content_sha256")
        if content_sha != hashlib.sha256(_canonical(receipt)).hexdigest():
            raise ValueError("content")
        if receipt["schema"] != RECEIPT_SCHEMA or receipt["framework_version"] != "2.1.1":
            raise ValueError("identity")
        action, observation, verification = (receipt[key] for key in ("action", "observation", "verification"))
        report = observation["records"][0]["native"]
        if (len(observation["records"]) != 1 or type(report["status"]) is not str
                or type(report["detail"]) is not dict
                or verification["status"] != _mapped_status(report["status"])
                or verification["action_id"] != action["action_id"]
                or verification["contract_id"] != action["contract"]["contract_id"]
                or verification["origin"] != "unknown"
                or verification["observed_at_ms"] != observation["observed_at_ms"]
                or verification["evidence"][0]["observation_id"] != observation["observation_id"]
                or verification["evidence"][0]["source"] != observation["source"]
                or verification["evidence"][0]["as_of_ms"] != observation["as_of_ms"]
                or action["contract"]["expected"] != {"tool": action["name"], "arguments": action["arguments"]}
                or verification["evidence"][0]["details"]["native_status"] != report["status"]):
            raise ValueError("binding")
    except (KeyError, IndexError, TypeError, ValueError):
        raise BoundaryRefusal("Inconsistent package public-verification receipt") from None
    return _copy(report)


class _ClockFacade:
    __slots__ = ("_public",)

    def __init__(self, public: PublicRuntimeBoundary):
        self._public = public

    @property
    def clock(self):
        return self._public.clock

    def advance(self, seconds):
        self._public.wait(seconds)


class _GuardFacade:
    """Only the exact public accesses made by non-oracle upstream OutcomeGuard."""
    __slots__ = ("_public", "_journal", "_episode_id", "_sequence", "_tainted", "tools", "world")

    def __init__(self, public: PublicRuntimeBoundary, episode_id: str, journal: Callable):
        self._public, self._journal, self._episode_id = public, journal, episode_id
        self._sequence = 0
        self._tainted = False
        self.world = _ClockFacade(public)
        self.tools = {}
        for name, meta in public.tool_metadata().items():
            fields = meta["contract"]
            # These callbacks evaluate declared public metadata through the
            # boundary; no native Contract, handler or verifier is forwarded.
            def evaluate(args, field, tool=name):
                return public.contract(tool, args)[field]
            contract = SimpleNamespace(**{key: fields[key] for key in (
                "write", "idempotent", "destructive", "irreversible", "batch_field", "compensator", "drift")},
                identity=(lambda args, fn=evaluate: fn(args, "identity")) if fields["has_identity"] else None,
                supports_key=lambda args, fn=evaluate: fn(args, "supports_key"),
                visibility_sla=lambda args, fn=evaluate: fn(args, "visibility_sla"))
            self.tools[name] = SimpleNamespace(contract=contract)

    @property
    def events(self):
        start = self._public.last_dispatch_start
        if start is None:
            raise BoundaryRefusal("No actual native dispatch timestamp exists")
        return (SimpleNamespace(t_start=start),)

    def execute(self, name, args, source="agent", note=""):
        if self._tainted:
            raise BoundaryJournalError("Package receipt audit sink previously failed")
        return self._public.execute(name, args, source=source, note=note)

    def verify(self, name, args, t_call, *, truth=False):
        if self._tainted:
            raise BoundaryJournalError("Package receipt audit sink previously failed")
        native = self._public.verify(name, args, t_call, truth=truth)
        self._sequence += 1
        receipt = make_public_receipt(self._episode_id, self._sequence, name, args,
                                      t_call, self._public.clock, native)
        # The *receipt-derived* values feed the unchanged guard. No raw report
        # bypass or additional read is used when making a retry decision.
        report = receipt_public_report(receipt)
        try:
            self._journal({"operation": "package_receipt", "phase": "return",
                           "receipt_sequence": self._sequence, "receipt": _copy(receipt)})
        except Exception:
            self._tainted = True
            raise BoundaryJournalError("Package receipt audit sink failed") from None
        return SimpleNamespace(status=report["status"], detail=report["detail"])


class ReceiptGuard:
    """Package-facing guard: receives only the capability-limited public view."""
    name = "conseqax_guard"
    prompt_variant = "vanilla"
    reflect = False

    def __init__(self, public: PublicRuntimeBoundary, episode_id: str, *, journal: Callable):
        from limbo.policies import make_policy as native_make_policy

        if type(public) is not PublicRuntimeBoundary or not callable(journal):
            raise BoundaryRefusal("An explicit public runtime and trusted audit sink are required")
        self._guard = native_make_policy("guard", episode_id)
        if self._guard.oracle is not None:
            raise BoundaryRefusal("Oracle policy cannot enter the measured package condition")
        self._facade = _GuardFacade(public, episode_id, journal)

    @property
    def interventions(self):
        return self._guard.interventions

    def execute(self, name: str, args: dict) -> dict:
        return self._guard.execute(self._facade, name, _copy(args))


class NativeReceiptPolicy:
    """Trusted native runner shim; native runtime never enters SDK receipt inputs."""
    name = "conseqax_guard"
    prompt_variant = "vanilla"
    reflect = False

    def __init__(self, episode_id: str, *, journal: Callable, limits: BoundaryLimits):
        if type(episode_id) is not str or not callable(journal) or type(limits) is not BoundaryLimits:
            raise BoundaryRefusal("Runner must supply explicit identity, audit sink and work limits")
        self.episode_id, self._journal, self._limits = episode_id, journal, limits
        self._guard = None
        self._runtime_id = None

    @property
    def interventions(self):
        return self._guard.interventions if self._guard is not None else []

    def execute(self, rt, name, args):
        if self._guard is None:
            public = bind_public_runtime(rt, limits=self._limits, journal=self._journal)
            self._guard = ReceiptGuard(public, self.episode_id, journal=self._journal)
            self._runtime_id = id(rt)
        elif self._runtime_id != id(rt):
            raise BoundaryRefusal("A policy instance cannot span native runtimes")
        return self._guard.execute(name, args)


def make_policy(name: str, episode_id: str, *, journal: Callable,
                limits: BoundaryLimits):
    """Scoped runner factory: original policies unchanged, one explicit new arm.

    The caller owns scoped replacement/restoration of ``limbo.agent.make_policy``.
    This factory never reads task definitions or modifies upstream source.
    """
    if name == "conseqax_guard":
        return NativeReceiptPolicy(episode_id, journal=journal, limits=limits)
    from limbo.policies import make_policy as native_make_policy
    if name not in {"vanilla", "guard", "sdk_retry3", "rules", "vbr"}:
        raise BoundaryRefusal("Only declared non-oracle study policies are allowed")
    return native_make_policy(name, episode_id)
