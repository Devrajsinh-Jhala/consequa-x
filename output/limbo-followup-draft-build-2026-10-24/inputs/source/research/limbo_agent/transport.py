"""One-shot loopback transport for the unchanged pinned LIMBO chat renderer.

This client replaces HTTP dispatch only. Native ``LLMClient._complete_chat``
constructs all model-visible messages/tools and parses every response. A
declared optional seed is the sole added provider field. No method here loads,
downloads or starts a model. Use one client in one episode subprocess.

The network guard is defense in depth for trusted code, not an OS sandbox.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from research.native_agent.transport import (
    LocalOnlyGuard, context_gate, read_gguf_metadata, render_gguf_template,
    tokenizer_from_gguf,
)


UPSTREAM_LLM_SHA256 = "a394cb8bc6777ea94c1e5071f690c6b3e49e1e74626cb389d494ab0e458dd464"
SCHEMA = "conseqax-limbo-local-transport-v1"


def render_limbo_template(metadata, messages, tools):
    """Predict provider elision of literal default-true schema declarations.

    Native HTTP schemas are never changed. The pinned provider's typed tool
    representation omits additionalProperties. Omission has the same JSON
    Schema meaning as literal true; false, numeric values and schema-valued
    restrictions are refused. Opaque items/$defs remain untouched. Every live
    request must still match the server's complete prompt bytes and token IDs.
    """
    normalized = deepcopy(tools or [])

    def typed(node):
        if not isinstance(node, dict):
            return
        if "additionalProperties" in node:
            if node["additionalProperties"] is not True:
                raise ValueError("Provider cannot preserve a non-default additionalProperties constraint")
            del node["additionalProperties"]
        properties = node.get("properties")
        if isinstance(properties, dict):
            for value in properties.values():
                typed(value)
        for branch in node.get("anyOf") or []:
            typed(branch)

    for tool in normalized:
        typed(tool.get("function", {}).get("parameters"))
    return render_gguf_template(metadata, messages, normalized)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False).encode("utf-8")


def file_sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_bytes(path, value):
    with Path(path).open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, value):
    write_bytes(path, canonical(value) + b"\n")


@dataclass(frozen=True)
class RuntimeBinding:
    api_base: str
    model: str
    model_digest: str
    model_blob: str
    model_blob_sha256: str
    server_pid: int
    server_executable: str
    server_executable_sha256: str
    server_create_time: float
    runner_pid: int
    runner_executable: str
    runner_executable_sha256: str
    runner_create_time: float
    runner_port: int
    context_tokens: int
    parallel_slots: int

    @classmethod
    def from_dict(cls, value):
        return cls(**value)

    def __post_init__(self):
        parsed = urlsplit(self.api_base)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.port != 11436 or parsed.path != "/v1" or parsed.query
                or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("Only the explicitly isolated numeric loopback research listener is allowed")
        if not self.model or any(c.isspace() for c in self.model):
            raise ValueError("An exact local model alias is required")
        for value in (self.model_digest, self.model_blob_sha256,
                      self.server_executable_sha256, self.runner_executable_sha256):
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("Exact lowercase SHA-256 runtime identities are required")
        for value in (self.server_pid, self.runner_pid, self.context_tokens, self.parallel_slots):
            if type(value) is not int or value <= 0:
                raise ValueError("Invalid process/context/slot binding")
        if (type(self.runner_port) is not int or not 1024 <= self.runner_port <= 65535
                or self.runner_port in {11434, 11436}):
            raise ValueError("Invalid private runtime tokenizer listener")
        for value in (self.server_create_time, self.runner_create_time):
            if type(value) not in {float, int} or not math.isfinite(value) or value <= 0:
                raise ValueError("Process creation times are required")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Returning None declines the follow-up; urllib's default HTTP error
        # handler then exposes the original status/body to _wire for retention.
        return None


class LoopbackGuard(LocalOnlyGuard):
    """Reuse the frozen socket audit hook, with separately bound LIMBO identity."""

    def __init__(self, binding, *, protected_roots=()):
        super().__init__(api_base=binding.api_base, protected_roots=protected_roots)
        self.binding = binding
        self.tokenizer_runner = {"pid": binding.runner_pid, "port": binding.runner_port,
                                 "executable": binding.runner_executable,
                                 "model_blob": binding.model_blob}

    def check_http(self, method, url, body):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.port not in {self.server_port, self.binding.runner_port}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            self.refuse("http", "Request outside exact research runtime endpoints")
        pair = (method.upper(), parsed.path)
        allowed = ({("POST", "/tokenize")} if parsed.port == self.binding.runner_port else
                   {("GET", "/api/ps"), ("GET", "/api/version"),
                    ("POST", "/v1/chat/completions")})
        if pair not in allowed:
            self.refuse("http", "Unapproved research runtime HTTP operation")
        payload = json.loads(body) if body else {}
        if parsed.path == "/v1/chat/completions" and payload.get("model") != self.binding.model:
            self.refuse("http", "Model identity changed")
        self.events.append({"kind": "http", "allowed": True, "method": pair[0],
                            "path": pair[1], "body_sha256": sha256(body)})


def native_llm_module():
    native = importlib.import_module("limbo.llm")
    source = Path(native.__file__).read_bytes().replace(b"\r\n", b"\n")
    if sha256(source) != UPSTREAM_LLM_SHA256:
        raise RuntimeError("LIMBO client bytes differ from the declared upstream pin")
    return native


def usage_availability(payload):
    """Missing native usage is unknown, even though its aggregate uses zeros."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    cached = usage.get("prompt_tokens_details")
    reasoning = usage.get("completion_tokens_details")
    candidates = {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "cached_tokens": cached.get("cached_tokens") if isinstance(cached, dict) else None,
        "reasoning_tokens": usage.get("reasoning_tokens", reasoning.get("reasoning_tokens")
                                      if isinstance(reasoning, dict) else None),
    }
    return {name: {"available": type(value) is int and value >= 0,
                   "value": value if type(value) is int and value >= 0 else None}
            for name, value in candidates.items()}


class AuditedLIMBOClient:
    protocol = "chat"

    def __init__(self, binding: RuntimeBinding, journal_dir, *, max_requests,
                 max_output_tokens, request_timeout_s, seed=None,
                 absolute_deadline_monotonic=None, protected_roots=()):
        if type(max_requests) is not int or max_requests < 1:
            raise ValueError("Positive fixed invocation limit required")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 512:
            raise ValueError("Output cap must be 1..512 tokens")
        if type(request_timeout_s) not in {int, float} or not math.isfinite(request_timeout_s) or request_timeout_s <= 0:
            raise ValueError("Positive finite request deadline required")
        if seed is not None and type(seed) is not int:
            raise ValueError("Seed must be an explicit integer or None")
        if (absolute_deadline_monotonic is not None
                and (type(absolute_deadline_monotonic) not in {float, int}
                     or not math.isfinite(absolute_deadline_monotonic))):
            raise ValueError("Invalid hard monotonic deadline")
        self.binding, self.model = binding, binding.model
        self.max_output_tokens, self.temperature = max_output_tokens, 0
        self.max_requests, self.timeout_s, self.seed = max_requests, request_timeout_s, seed
        self.deadline = absolute_deadline_monotonic
        self.max_attempts = self.concurrency = 1
        self.journal_dir = Path(journal_dir).resolve()
        self.journal_dir.mkdir(parents=True, exist_ok=False)
        self.guard = LoopbackGuard(binding, protected_roots=protected_roots)
        self.native = native_llm_module()
        self._lock = threading.Lock()
        self._active = False
        self._entered = False
        self._invocations = 0
        self._dispatches = 0
        self._current = None
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._identity_files = {}
        self.metadata = self.tokenizer = None
        write_json(self.journal_dir / "client-config.json", {
            "schema": SCHEMA, "runtime": asdict(binding), "max_requests": max_requests,
            "max_output_tokens": max_output_tokens, "request_timeout_s": request_timeout_s,
            "max_requests_semantics": "Maximum permitted model invocations; a subsequent native call is retained as a local budget refusal with no HTTP dispatch",
            "seed_extension": seed, "temperature": 0, "max_attempts": 1, "concurrency": 1,
            "absolute_deadline_monotonic": absolute_deadline_monotonic,
            "native_llm_sha256": UPSTREAM_LLM_SHA256,
            "missing_native_usage_aggregate_warning": "Native Usage uses zero for missing; use per-call availability journals",
        })

    def _event(self, kind, **fields):
        value = {"schema": SCHEMA, "event": kind, "utc": utc(),
                 "monotonic": time.monotonic(), **fields}
        with (self.journal_dir / "model-calls.jsonl").open("ab") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def __enter__(self):
        if self._entered:
            raise RuntimeError("One-shot client reuse is refused; create a new episode journal")
        self._entered = True
        self.guard.__enter__()
        self._active = True
        try:
            self._verify_identity(initial=True)
            self.metadata = read_gguf_metadata(self.binding.model_blob)
            self.tokenizer = tokenizer_from_gguf(self.metadata)
            self._event("client_ready", model_generations=0)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        if self._active:
            self._active = False
            self.guard.__exit__(*exc)
            write_json(self.journal_dir / "network-events.json", self.guard.events)
            write_json(self.journal_dir / "client-summary.json", {
                "schema": SCHEMA, "invocations": self._invocations,
                "native_invocations_including_budget_refusals": self._invocations,
                "permitted_model_invocations": min(self._invocations, self.max_requests),
                "budget_refusals": max(0, self._invocations - self.max_requests),
                "generation_dispatch_attempts": self._dispatches,
                "missing_usage_must_not_be_treated_as_zero": True,
                "automatic_http_retries": 0, "finished_utc": utc(),
            })
        return False

    def _verify_identity(self, *, initial=False):
        import psutil

        b = self.binding
        for pid, executable, born in ((b.server_pid, b.server_executable, b.server_create_time),
                                      (b.runner_pid, b.runner_executable, b.runner_create_time)):
            process = psutil.Process(pid)
            if (Path(process.exe()).resolve() != Path(executable).resolve()
                    or abs(process.create_time() - born) > 0.001):
                raise RuntimeError("Bound research process identity changed")
        args = psutil.Process(b.runner_pid).cmdline()
        expected = {"--model": b.model_blob, "--port": str(b.runner_port), "--host": "127.0.0.1",
                    "-c": str(b.context_tokens * b.parallel_slots), "-np": str(b.parallel_slots),
                    "--cache-type-k": "q8_0", "--cache-type-v": "q8_0", "--flash-attn": "on"}
        for flag, value in expected.items():
            if flag not in args or args.index(flag) + 1 >= len(args) or args[args.index(flag) + 1] != value:
                raise RuntimeError("Loaded runner argument mismatch: " + flag)
        if "--offline" not in args:
            raise RuntimeError("Research runner is not offline")
        for path, digest in ((b.model_blob, b.model_blob_sha256),
                             (b.server_executable, b.server_executable_sha256),
                             (b.runner_executable, b.runner_executable_sha256)):
            stat = Path(path).stat()
            stamp = (stat.st_size, stat.st_mtime_ns)
            if initial:
                if file_sha256(path) != digest:
                    raise RuntimeError("Bound runtime file SHA-256 changed")
                self._identity_files[path] = stamp
            elif self._identity_files.get(path) != stamp:
                raise RuntimeError("Bound runtime file changed after identity preflight")

    def _remaining(self, maximum):
        if self.deadline is None:
            return maximum
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Hard episode deadline reached before dispatch")
        return min(maximum, remaining)

    def _wire(self, method, url, data, timeout):
        self.guard.check_http(method, url, data)
        req = Request(url, data=data if method == "POST" else None, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(req, timeout=timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as error:
            return error.code, dict(error.headers.items()), error.read()

    def _json_call(self, method, url, payload=None):
        # Preserve native insertion order here too: the provider's typed tool
        # properties keep request order, so a sorted preview could prove parity
        # for a different prompt than the subsequent actual request.
        data = b"" if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        status, headers, data = self._wire(method, url, data, self._remaining(60))
        if status != 200:
            raise RuntimeError("Render/tokenizer/residency endpoint returned HTTP " + str(status))
        value = json.loads(data)
        if not isinstance(value, dict):
            raise RuntimeError("Runtime metadata response is not an object")
        return value

    def _context_check(self, payload):
        b = self.binding
        receipt = {"schema": SCHEMA, "request_sha256": sha256(canonical(payload)),
                   "request": payload, "generation_dispatched_by_gate": False,
                   "runtime_binding": asdict(b)}
        try:
            self._verify_identity()
            prompt = render_limbo_template(self.metadata, payload["messages"], payload.get("tools"))
            receipt["offline_rendered_prompt"] = prompt
            receipt["offline_context"] = context_gate(prompt, self.tokenizer,
                output_tokens=self.max_output_tokens, context_tokens=b.context_tokens, reserve_tokens=64)
            ps = self._json_call("GET", b.api_base.removesuffix("/v1") + "/api/ps")
            receipt["resident_response"] = ps
            profiles = [item for item in ps.get("models", [])
                        if item.get("name") == b.model or item.get("model") == b.model]
            if (len(profiles) != 1 or profiles[0].get("context_length") != b.context_tokens
                    or profiles[0].get("digest") != b.model_digest):
                raise RuntimeError("Pinned model is not resident with the declared context/digest")
            preview = self._json_call("POST", b.api_base + "/chat/completions",
                                      {**payload, "_debug_render_only": True})
            receipt["server_preview"] = preview
            observed_prompt = preview.get("_debug_info", {}).get("rendered_template")
            receipt["same_rendered_bytes"] = observed_prompt == prompt
            if observed_prompt != prompt:
                raise RuntimeError("Server prompt differs from complete offline history/schema rendering")
            tokens = self._json_call("POST", f"http://127.0.0.1:{b.runner_port}/tokenize",
                                     {"content": prompt, "add_special": True,
                                      "parse_special": True, "with_pieces": False})
            receipt["runtime_tokenizer"] = tokens
            expected = self.tokenizer.encode(prompt, add_special_tokens=False).ids
            receipt["same_token_ids"] = tokens.get("tokens") == expected
            if not receipt["same_token_ids"]:
                raise RuntimeError("Runtime token IDs differ from the exact GGUF vocabulary")
            receipt["passed"] = True
            return receipt
        except BaseException as error:
            receipt["passed"] = False
            receipt["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            write_json(self._current["prefix"].with_name(self._current["prefix"].name + "-context.json"), receipt)

    def complete(self, system, conversation, tools):
        if not self._active:
            raise RuntimeError("Use AuditedLIMBOClient as an active context manager")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Concurrent/nested model invocations are refused")
        self._invocations += 1
        number = self._invocations
        prefix = self.journal_dir / f"{number:04d}"
        self._current = {"number": number, "prefix": prefix, "dispatched": 0, "response": None}
        start = time.monotonic()
        terminal = {"schema": SCHEMA, "invocation": number, "started_utc": utc(),
                    "dispatches": 0, "returned": False, "usage": None,
                    "permitted_model_invocation": number <= self.max_requests,
                    "budget_refusal": number > self.max_requests}
        try:
            write_json(prefix.with_name(prefix.name + "-native-input.json"),
                       {"system": system, "conversation": conversation, "tools": tools})
            self._event("request_start", invocation=number,
                        permitted_model_invocation=terminal["permitted_model_invocation"],
                        budget_refusal=terminal["budget_refusal"])
            if number > self.max_requests:
                raise RuntimeError("Declared combined model-invocation cap exhausted")
            self._remaining(self.timeout_s)
            # Pinned native code alone constructs messages/tools and parses the
            # returned payload; our _post changes only actual HTTP dispatch.
            turn = self.native.LLMClient._complete_chat(self, system, conversation, tools)
            terminal["returned"] = True
            terminal["usage"] = usage_availability(self._current["response"])
            terminal["native_usage_aggregate"] = turn.usage.as_dict()
            self._event("request_return", invocation=number, usage=terminal["usage"])
            return turn
        except BaseException as error:
            terminal["error"] = {"type": type(error).__name__, "message": str(error)}
            self._event("request_error", invocation=number, **terminal["error"])
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise self.native.LLMError(f"Audited local transport refused/failed: {type(error).__name__}: {error}",
                                       retryable=False) from error
        finally:
            terminal["finished_utc"] = utc()
            terminal["wall_s"] = time.monotonic() - start
            terminal["dispatches"] = self._current["dispatched"]
            if isinstance(self._current["response"], dict):
                # Parsing a malformed assistant turn can fail after a real
                # response with metered usage. Preserve that observed cost.
                terminal["usage"] = usage_availability(self._current["response"])
            terminal["dispatch_attempt_count_is_not_proof_of_server_acceptance"] = True
            try:
                write_json(prefix.with_name(prefix.name + "-terminal.json"), terminal)
            finally:
                self._current = None
                self._lock.release()

    def _post(self, path, body):
        if path != "/chat/completions" or self._current is None or self._current["dispatched"]:
            raise RuntimeError("Only one chat completion dispatch per recorded invocation is permitted")
        expected_fields = {"model", "messages", "tools", "max_tokens", "temperature"}
        if set(body) != expected_fields or body["model"] != self.model or body["temperature"] != 0:
            raise RuntimeError("Native request shape/model/temperature changed")
        payload = {**body}
        if self.seed is not None:
            payload["seed"] = self.seed
        # Native serializer is reproduced byte-for-byte; only the declared
        # seed extension can add a request field. Exact bytes are retained.
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        prefix = self._current["prefix"]
        write_bytes(prefix.with_name(prefix.name + "-request.bin"), data)
        self._context_check(payload)
        timeout = self._remaining(self.timeout_s)
        self._current["dispatched"] = 1
        self._dispatches += 1
        self._event("before_dispatch", invocation=self._current["number"], request_sha256=sha256(data),
                    timeout_s=timeout, dispatches=1)
        started = time.monotonic()
        status, headers, raw = self._wire("POST", self.binding.api_base + path, data, timeout)
        write_bytes(prefix.with_name(prefix.name + "-response.bin"), raw)
        write_json(prefix.with_name(prefix.name + "-response-meta.json"),
                   {"status": status, "headers": headers, "body_sha256": sha256(raw),
                    "latency_s": time.monotonic() - started})
        if status != 200:
            raise RuntimeError("Single model dispatch returned HTTP " + str(status))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Model response is not an object")
        self._current["response"] = payload
        return payload, time.monotonic() - started
