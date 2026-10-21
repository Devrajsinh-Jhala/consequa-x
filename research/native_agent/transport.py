"""Process-local safeguards for the unmodified Tau text-generation path.

Install LocalOnlyGuard before importing Tau/LiteLLM. This is defense in depth
for a trusted Python harness, not an OS firewall or sandbox for hostile code.
No function in this module loads a model or dispatches a generation request.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import sys
import threading
from urllib.parse import urlsplit


LOCAL_API_BASE = "http://127.0.0.1:11434/v1"
LOCAL_MODEL = "conseqax-native-probe-20261020:ctx16k"
LITELLM_MODEL = "openai/" + LOCAL_MODEL
CONTEXT_TOKENS = 16384
MODEL_BLOB_SHA256 = "85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9"
MODEL_MANIFEST_SHA256 = "7f091551b95c30f4ff31a067faa273f56a3563b556cfd3d9f80d47c9b5d20ffc"


class TransportRefusal(BaseException):
    """Fail closed without a provider's retry handler swallowing the refusal."""


class ContextRefusal(TransportRefusal):
    pass


def configure_local_environment(data_dir: Path | str) -> dict:
    """Remove credentials/proxies and disable optional telemetry/dotenv loading.

    Only names of removed variables are recorded; values are never retained.
    Must run in the research child, never to reconfigure the user's shell.
    """
    removed = []
    for name in tuple(os.environ):
        upper = name.upper()
        if (upper.endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN"))
                or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                             "OPENAI_BASE_URL", "OPENAI_API_BASE", "LITELLM_PROXY_API_BASE",
                             "GOOGLE_APPLICATION_CREDENTIALS", "AWS_SHARED_CREDENTIALS_FILE"}):
            os.environ.pop(name, None)
            removed.append(name)
    os.environ.update({
        "PYTHON_DOTENV_DISABLED": "1", "TAU2_DATA_DIR": str(data_dir),
        "LITELLM_LOCAL_MODEL_COST_MAP": "True", "LITELLM_TELEMETRY": "False",
        "DO_NOT_TRACK": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    })
    sys.dont_write_bytecode = True
    return {"removed_variable_names": sorted(removed), "credential_values_recorded": False}


class LocalOnlyGuard:
    """Permit numeric loopback Ollama TCP and Python's internal socketpair only.

    An audit hook covers imports before httpx exists. HTTP request inspection is
    attached after importing httpx under that guard. The socketpair allowance
    is thread-local and active only inside the standard library implementation;
    arbitrary extra loopback services are not generally allowed.
    """

    def __init__(self, *, protected_roots=(), allow_generation=False, allow_render_only=False,
                 api_base=LOCAL_API_BASE):
        if api_base not in {LOCAL_API_BASE, "http://127.0.0.1:11436/v1"}:
            raise ValueError("Only the normal or explicitly isolated research listener is supported")
        self.api_base = api_base
        self.server_base = api_base.removesuffix("/v1")
        self.server_port = urlsplit(api_base).port
        self.protected_roots = tuple(Path(p).resolve() for p in protected_roots)
        self.allow_generation = allow_generation
        self.allow_render_only = allow_render_only
        self.tokenizer_runner = None
        self.before_generation = None
        self.require_native_invocation = False
        self.events: list[dict] = []
        self.active = False
        self._thread = threading.local()
        self._restore = []

    def refuse(self, kind: str, detail: str):
        self.events.append({"kind": kind, "allowed": False, "detail": detail})
        raise TransportRefusal(f"{kind}: {detail}")

    @contextmanager
    def native_invocation(self, native_request: dict):
        """Bind one native completion to at most one unchanged generation send.

        The scope captures inputs before LiteLLM can mutate them. Process-local
        transport development may omit a scope; native episodes require one.
        Render/tokenizer requests do not consume the generation allowance.
        """
        if getattr(self._thread, "native_invocation", None) is not None:
            self.refuse("native_invocation", "Nested native completion scope refused")
        expected = deepcopy({key: value for key, value in native_request.items()
                             if key.lower() not in {"api_key", "authorization"}})
        if expected.get("model") != LITELLM_MODEL or not isinstance(expected.get("messages"), list):
            self.refuse("native_invocation", "Native completion model/messages are not the frozen input shape")
        self._thread.native_invocation = {"request": expected, "dispatched": False}
        try:
            yield
        finally:
            self._thread.native_invocation = None

    def _check_native_generation(self, payload):
        scope = getattr(self._thread, "native_invocation", None)
        if scope is None:
            if self.require_native_invocation:
                self.refuse("native_invocation", "Generation outside a recorded native completion refused")
            return None
        if scope["dispatched"]:
            self.refuse("native_invocation", "A second generation attempt within one native completion refused")
        expected = scope["request"]
        fields = {"max_tokens", "temperature", "seed", "tools", "tool_choice"}
        if set(payload) - (fields | {"model", "messages"}):
            self.refuse("native_invocation", "Generation added unbound request fields")
        if (payload.get("model") != expected["model"].removeprefix("openai/")
                or not isinstance(payload.get("messages"), list)):
            self.refuse("native_invocation", "Generation changed native model/messages")
        try:
            same_messages = native_wire_equivalent(payload["messages"], expected["messages"])
        except (TypeError, AttributeError):
            same_messages = False
        if not same_messages:
            self.refuse("native_invocation", "Generation changed native message history or tool-call association")
        for field in fields:
            actual, native = payload.get(field), expected.get(field)
            if (type(actual) is not type(native)
                    or json.dumps(actual, sort_keys=True, allow_nan=False)
                    != json.dumps(native, sort_keys=True, allow_nan=False)):
                self.refuse("native_invocation", "Generation changed native request field: " + field)
        return scope

    def address(self, address, kind="network"):
        if not isinstance(address, tuple) or len(address) < 2:
            self.refuse(kind, "Non-IPv4 TCP address refused")
        host, port = address[:2]
        internal = bool(getattr(self._thread, "socketpair", 0))
        runner_port = self.tokenizer_runner and self.tokenizer_runner["port"]
        allowed_ports = {self.server_port} | ({runner_port} if runner_port is not None else set())
        if host == "127.0.0.1" and (port in allowed_ports or internal):
            self.events.append({"kind": kind, "allowed": True,
                                "host": host, "port": port, "internal_socketpair": internal})
            return
        self.refuse(kind, f"Destination {host!r}:{port!r} is outside the allowlist")

    def _audit(self, event, args):
        if not self.active:
            return
        if event == "socket.connect":
            self.address(args[1], event)
        elif event in {"socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}:
            self.refuse(event, "DNS/name resolution refused")
        elif event == "socket.getaddrinfo":
            self.address((args[0], args[1]), event)
        elif event == "socket.sendto":
            self.refuse(event, "Datagram networking refused")
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            self.refuse(event, "Imported subprocesses refused")
        elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path, mode, flags = args
            resolved = Path(os.fsdecode(path)).resolve()
            writing = ((mode and any(c in mode for c in "wax+"))
                       or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and any(resolved.is_relative_to(p) for p in self.protected_roots):
                self.refuse(event, "Write to protected source/model path refused")
            if not writing and (resolved.name.lower().startswith(".env")
                                or resolved.name.lower() in {"credentials", ".pypirc", "pypi token.txt"}):
                self.refuse(event, "Credential/dotenv read refused")

    def _patch(self, target, name, replacement):
        self._restore.append((target, name, getattr(target, name)))
        setattr(target, name, replacement)

    def __enter__(self):
        if self.active:
            raise RuntimeError("Guard already active")
        self.active = True
        sys.addaudithook(self._audit)
        original_connect_ex = socket.socket.connect_ex
        original_pair = socket.socketpair

        def connect_ex(sock, address):
            self.address(address, "socket.connect_ex")
            return original_connect_ex(sock, address)

        def pair(*args, **kwargs):
            self._thread.socketpair = getattr(self._thread, "socketpair", 0) + 1
            try:
                return original_pair(*args, **kwargs)
            finally:
                self._thread.socketpair -= 1

        self._patch(socket.socket, "connect_ex", connect_ex)
        self._patch(socket, "socketpair", pair)
        return self

    def check_http(self, method: str, url: str, body: bytes):
        parsed = urlsplit(url)
        runner_port = self.tokenizer_runner and self.tokenizer_runner["port"]
        allowed_ports = {self.server_port} | ({runner_port} if runner_port is not None else set())
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.port not in allowed_ports or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            self.refuse("http", "HTTP URL outside exact local endpoint")
        method = method.upper()
        if parsed.port == runner_port:
            if (method, parsed.path) != ("POST", "/tokenize"):
                self.refuse("http", "Private runner permits POST /tokenize only")
            self.events.append({"kind": "http", "allowed": True, "method": method,
                                "path": parsed.path, "port": parsed.port,
                                "body_sha256": hashlib.sha256(body).hexdigest()})
            return
        allowed = {("GET", "/api/version"), ("GET", "/api/tags"),
                   ("GET", "/api/ps"), ("POST", "/api/show")}
        if self.allow_generation or self.allow_render_only:
            allowed.add(("POST", "/v1/chat/completions"))
        if (method, parsed.path) not in allowed:
            self.refuse("http", f"Unapproved HTTP operation {method} {parsed.path}")
        payload = json.loads(body) if body else {}
        if parsed.path in {"/api/show", "/v1/chat/completions"}:
            if payload.get("model") != LOCAL_MODEL:
                self.refuse("http", "A different or hosted model was requested")
        if parsed.path == "/v1/chat/completions":
            if not self.allow_generation and payload.get("_debug_render_only") is not True:
                self.refuse("http", "Only server rendering is authorized")
            if payload.get("stream", False):
                self.refuse("http", "Streaming is outside the frozen transport")
            if payload.get("n", 1) != 1:
                self.refuse("http", "Multiple provider completions refused")
            if payload.get("_debug_render_only") is not True:
                scope = self._check_native_generation(payload)
                if self.before_generation is not None:
                    self.before_generation(payload)
                if scope is not None:
                    scope["dispatched"] = True
        self.events.append({"kind": "http", "allowed": True, "method": method,
                            "path": parsed.path, "body_sha256": hashlib.sha256(body).hexdigest(),
                            "parsed_body_sha256": hashlib.sha256(
                                json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                            "generation_request": (parsed.path == "/v1/chat/completions"
                                                   and payload.get("_debug_render_only") is not True)})

    def register_tokenizer_runner(self, *, port: int, pid: int, executable: str,
                                  executable_sha256: str, model_blob: str, model_blob_sha256: str):
        """Bind a separately authorized loaded research runner's private tokenizer.

        The caller must discover its live PID/command line and prove the exact
        loaded model binding. Only POST /tokenize becomes available at this port.
        No private completion/health/admin route is allowed by this exception.
        """
        if (type(port) is not int or not 1024 <= port <= 65535 or port == 11434
                or type(pid) is not int or pid <= 0
                or Path(executable).name != "llama-server.exe"
                or len(executable_sha256) != 64
                or model_blob_sha256 != MODEL_BLOB_SHA256
                or Path(model_blob).name != "sha256-" + MODEL_BLOB_SHA256):
            raise ValueError("Unverified private tokenizer runner binding")
        self.tokenizer_runner = {"port": port, "pid": pid, "executable": executable,
                                 "executable_sha256": executable_sha256,
                                 "model_blob": model_blob, "model_blob_sha256": model_blob_sha256,
                                 "allowed_http": "POST /tokenize"}

    def attach_httpx(self):
        """Import under the network guard, then inspect actual outgoing bytes."""
        import httpx

        original_send = httpx.Client.send
        original_async_send = httpx.AsyncClient.send

        def send(client, request, *args, **kwargs):
            self.check_http(request.method, str(request.url), request.read())
            return original_send(client, request, *args, **kwargs)

        async def async_send(client, request, *args, **kwargs):
            self.check_http(request.method, str(request.url), await request.aread())
            return await original_async_send(client, request, *args, **kwargs)

        self._patch(httpx.Client, "send", send)
        self._patch(httpx.AsyncClient, "send", async_send)
        return httpx

    def __exit__(self, *exc):
        self.active = False
        for target, name, original in reversed(self._restore):
            setattr(target, name, original)
        self._restore.clear()


def local_model_kwargs(*, max_tokens=512, seed=1701, timeout=180, api_base=LOCAL_API_BASE) -> dict:
    if type(max_tokens) is not int or not 1 <= max_tokens <= 512:
        raise ValueError("Frozen generation output cap is 1..512 tokens")
    if api_base not in {LOCAL_API_BASE, "http://127.0.0.1:11436/v1"}:
        raise ValueError("Unapproved research listener")
    return {"api_base": api_base, "api_key": "local-dummy-unused",
            "temperature": 0, "max_tokens": max_tokens, "seed": seed,
            "num_retries": 0, "timeout": timeout}


def native_wire_equivalent(observed: list[dict], native: list[dict]) -> bool:
    """OpenAI's client may omit content:null on prior assistant tool-call turns.

    Permit only that documented absent/null equivalence. All roles, contents,
    tool arguments/IDs, association and message order must otherwise match.
    """
    def normalize(messages):
        return [{key: value for key, value in message.items()
                 if not (key == "content" and value is None and message.get("tool_calls"))}
                for message in messages]

    return normalize(observed) == normalize(native)


def read_gguf_metadata(path: Path | str) -> dict:
    """Read GGUF v2/v3 metadata, never tensor/weight payloads or a model runtime."""
    with Path(path).open("rb") as stream:
        def number(fmt):
            size = struct.calcsize("<" + fmt)
            raw = stream.read(size)
            if len(raw) != size:
                raise ValueError("Truncated GGUF metadata")
            return struct.unpack("<" + fmt, raw)[0]

        def string():
            length = number("Q")
            if length > 100_000_000:
                raise ValueError("GGUF string is outside the metadata limit")
            raw = stream.read(length)
            if len(raw) != length:
                raise ValueError("Truncated GGUF string")
            return raw.decode("utf-8")

        def value(kind):
            formats = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
                       6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
            if kind in formats:
                return number(formats[kind])
            if kind == 8:
                return string()
            if kind == 9:
                subtype, count = number("I"), number("Q")
                if count > 2_000_000 or subtype == 9:
                    raise ValueError("Unsupported GGUF metadata array")
                return [value(subtype) for _ in range(count)]
            raise ValueError(f"Unknown GGUF type {kind}")

        if stream.read(4) != b"GGUF" or number("I") not in {2, 3}:
            raise ValueError("Expected little-endian GGUF v2/v3")
        number("Q")  # tensor count; no tensor payload is read
        count = number("Q")
        if count > 10000:
            raise ValueError("GGUF metadata count outside bounds")
        metadata = {}
        for _ in range(count):
            key = string()
            if key in metadata:
                raise ValueError("Duplicate GGUF key")
            metadata[key] = value(number("I"))
        metadata["_metadata_end_bytes"] = stream.tell()
        return metadata


def tokenizer_from_gguf(metadata: dict):
    """Rebuild the installed Qwen2 BPE vocabulary with exact GGUF token IDs.

    This counts a supplied rendered prompt exactly under that vocabulary; the
    caller must separately validate that rendering matches the server runtime.
    It is not a byte/token estimate and it does not assert server render parity.
    """
    from tokenizers import AddedToken, Regex, Tokenizer, models, pre_tokenizers

    if (metadata.get("tokenizer.ggml.model") != "gpt2"
            or metadata.get("tokenizer.ggml.pre") != "qwen2"):
        raise ValueError("Only the verified installed qwen2 BPE is supported")
    tokens = metadata["tokenizer.ggml.tokens"]
    kinds = metadata["tokenizer.ggml.token_type"]
    if len(tokens) != len(kinds) or len(set(tokens)) != len(tokens):
        raise ValueError("Malformed GGUF vocabulary")
    merges = [tuple(merge.split(" ")) for merge in metadata["tokenizer.ggml.merges"]]
    if any(len(pair) != 2 for pair in merges):
        raise ValueError("Malformed BPE merge")
    tokenizer = Tokenizer(models.BPE(vocab={t: i for i, t in enumerate(tokens)}, merges=merges,
                                     fuse_unk=False, byte_fallback=False))
    pattern = (r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}|"
               r" ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+")
    tokenizer.pre_tokenizer = pre_tokenizers.Sequence([
        pre_tokenizers.Split(Regex(pattern), behavior="isolated"),
        pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False),
    ])
    tokenizer.add_special_tokens([AddedToken(token, normalized=False, special=True)
                                  for token, kind in zip(tokens, kinds) if kind in {2, 3, 4}])
    if any(tokenizer.token_to_id(t) != i for i, t in enumerate(tokens)):
        raise ValueError("Reconstructed token IDs do not match the GGUF")
    return tokenizer


def ollama_tools_for_render(tools: list[dict]) -> list[dict]:
    """Mirror the pinned Ollama 0.40.6 typed tool representation, offline only.

    Native HTTP schemas stay untouched. Ollama's api/types.go serializes typed
    tool/property fields in declaration order and arbitrary Go maps in key
    order. It drops ``title`` at typed schema nodes. Refuse any other unknown
    typed-node keyword: silently mirroring its loss could hide a constraint.
    ``$defs`` and ``items`` are arbitrary JSON and retain all their keywords.
    Every live request must still pass independent server byte/token parity.
    """
    def arbitrary(value):
        if isinstance(value, dict):
            return {key: arbitrary(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [arbitrary(item) for item in value]
        return value

    def checked(value, allowed, where):
        if not isinstance(value, dict) or set(value) - set(allowed) - {"title"}:
            raise ContextRefusal(f"Unsupported provider-normalized schema node: {where}")

    def properties(value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ContextRefusal("Expected ordered native tool properties")
        return {key: property_schema(item) for key, item in value.items()}

    def property_schema(value):
        order = ("anyOf", "type", "items", "description", "enum", "properties", "required")
        checked(value, order, "property")
        rendered = {}
        for key in order:
            if key in {"anyOf", "enum", "type"} and key in value and value[key] == []:
                raise ContextRefusal("Provider would discard an empty schema constraint")
            if key not in value or value[key] is None or value[key] == "" or value[key] == []:
                continue
            item = value[key]
            if key == "anyOf":
                item = [property_schema(branch) for branch in item]
            elif key == "properties":
                item = properties(item)
            elif key == "type" and isinstance(item, list) and len(item) == 1:
                item = item[0]
            else:
                item = arbitrary(item)
            rendered[key] = item
        return rendered

    result = []
    for tool in tools:
        checked(tool, ("type", "items", "function"), "tool")
        function = tool.get("function")
        checked(function, ("name", "description", "parameters"), "function")
        parameters = function.get("parameters")
        checked(parameters, ("type", "$defs", "items", "required", "properties"), "parameters")
        if not isinstance(parameters.get("type", ""), str):
            raise ContextRefusal("Unsupported provider parameter type")
        rendered_parameters = {"type": parameters.get("type", "")}
        for key in ("$defs", "items", "required"):
            if key in parameters and parameters[key] is not None and parameters[key] != []:
                rendered_parameters[key] = arbitrary(parameters[key])
        rendered_parameters["properties"] = properties(parameters.get("properties"))
        rendered_function = {"name": function.get("name", "")}
        if function.get("description"):
            rendered_function["description"] = function["description"]
        rendered_function["parameters"] = rendered_parameters
        rendered_tool = {"type": tool.get("type", "")}
        if tool.get("items") is not None:
            rendered_tool["items"] = arbitrary(tool["items"])
        rendered_tool["function"] = rendered_function
        result.append(rendered_tool)
    return result


def ollama_messages_for_render(messages: list[dict]) -> list[dict]:
    """Predict pinned provider parsing of prior assistant tool-call arguments.

    The native wire keeps argument JSON strings. Ollama's OpenAI conversion
    parses their outer object into an ordered map; nested objects are regular
    Go maps. Preserve all values, retain outer key order, sort nested keys, and
    let the template serialize the parsed object rather than its original JSON
    spelling. Refuse integers which would lose precision in provider float64.
    Exact live byte parity is still required, including number formatting.
    """
    from copy import deepcopy

    def nested(value):
        if isinstance(value, dict):
            return {key: nested(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [nested(item) for item in value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int) and abs(value) > 2 ** 53 - 1:
            raise ContextRefusal("Provider float64 would lose argument integer precision")
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ContextRefusal("Non-finite tool argument number")
            if value.is_integer():
                return int(value)
        return value

    result = deepcopy(messages)
    for message in result:
        for call in message.get("tool_calls") or []:
            function = call.get("function", call)
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(arguments, dict):
                raise ContextRefusal("Expected object-valued prior tool arguments")
            function["arguments"] = {key: nested(value) for key, value in arguments.items()}
    return result


def render_gguf_template(metadata: dict, messages: list[dict], tools: list[dict] | None = None) -> str:
    """Render complete history plus pinned provider-normalized tool schemas.

    This is a prediction of the actual provider prompt, not a modification of
    native HTTP messages/tools. The provider drops schema titles; all other
    schema constraints must survive or this renderer refuses the request.
    Server byte parity and exact runtime token IDs remain mandatory.
    """
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    environment = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
    environment.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)
    return environment.from_string(metadata["tokenizer.chat_template"]).render(
        messages=ollama_messages_for_render(messages), tools=ollama_tools_for_render(tools or []),
        add_generation_prompt=True,
    )


def context_gate(prompt: str, tokenizer, *, output_tokens=512, context_tokens=CONTEXT_TOKENS,
                 reserve_tokens=64, add_bos=False, add_eos=False) -> dict:
    """Refuse a complete rendered prompt rather than trimming any messages."""
    count = len(tokenizer.encode(prompt, add_special_tokens=False).ids)
    total = count + int(add_bos) + int(add_eos) + output_tokens + reserve_tokens
    receipt = {"rendered_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "prompt_tokens": count, "add_bos": add_bos, "add_eos": add_eos,
               "output_tokens": output_tokens, "reserve_tokens": reserve_tokens,
               "context_tokens": context_tokens, "required_tokens": total,
               "fits": total <= context_tokens, "truncation_requested": False}
    if not receipt["fits"]:
        raise ContextRefusal(json.dumps(receipt, sort_keys=True))
    return receipt


class ServerContextGate:
    """Exact full-history preview/tokenization before each actual completion.

    Assign an instance to guard.before_generation after a successful frozen
    preflight and private-runner binding. It performs only render/tokenize/ps
    requests, stores their receipts, and never sends an actual generation. The
    existing original httpx send proceeds only after this callback returns.
    """

    def __init__(self, guard: LocalOnlyGuard, metadata: dict, tokenizer, *, on_receipt=None):
        if not guard.tokenizer_runner or not guard.allow_render_only:
            raise ValueError("Verified research tokenizer runner and render permission required")
        self.guard, self.metadata, self.tokenizer = guard, metadata, tokenizer
        self.on_receipt = on_receipt
        self.receipts: list[dict] = []

    def __call__(self, payload: dict):
        from copy import deepcopy

        receipt = {"request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                   "request": deepcopy(payload), "generation_dispatched_by_gate": False,
                   "runtime_tokenizer_runner": dict(self.guard.tokenizer_runner)}
        try:
            self._check(payload, receipt)
            receipt["passed"] = True
            return receipt
        except BaseException as error:
            receipt["passed"] = False
            receipt["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            self.receipts.append(receipt)
            if self.on_receipt:
                self.on_receipt(receipt)

    def _check(self, payload: dict, receipt: dict):
        from copy import deepcopy
        import httpx
        import psutil

        binding = self.guard.tokenizer_runner
        process = psutil.Process(binding["pid"])
        args = process.cmdline()
        if (process.exe() != binding["executable"] or binding["model_blob"] not in args
                or "--port" not in args or args[args.index("--port") + 1] != str(binding["port"])):
            raise ContextRefusal("Recorded private tokenizer runner identity changed")
        receipt["verified_live_runner"] = True
        cap = payload.get("max_tokens")
        if type(cap) is not int or not 1 <= cap <= 512:
            raise ContextRefusal("Actual request has no valid frozen output cap")
        offline_prompt = render_gguf_template(self.metadata, payload["messages"], payload.get("tools"))
        receipt["offline_rendered_prompt"] = offline_prompt
        offline_receipt = context_gate(offline_prompt, self.tokenizer, output_tokens=cap)
        receipt["offline_context"] = offline_receipt
        preview_payload = deepcopy(payload)
        preview_payload["_debug_render_only"] = True
        with httpx.Client(trust_env=False, timeout=60) as client:
            resident_response = client.get(self.guard.server_base + "/api/ps")
            resident_response.raise_for_status()
            resident = resident_response.json()
            receipt["resident_response"] = resident
            profiles = [model for model in resident.get("models", [])
                        if model.get("name") == LOCAL_MODEL or model.get("model") == LOCAL_MODEL]
            if (len(profiles) != 1 or profiles[0].get("context_length") != CONTEXT_TOKENS
                    or profiles[0].get("digest") != MODEL_MANIFEST_SHA256):
                raise ContextRefusal("Expected pinned 16384-token model is no longer resident")
            receipt["resident_profile"] = profiles[0]
            preview_response = client.post(self.guard.api_base + "/chat/completions", json=preview_payload)
            preview_response.raise_for_status()
            preview = preview_response.json()
            receipt["server_preview"] = preview
            prompt = preview.get("_debug_info", {}).get("rendered_template")
            receipt["same_rendered_bytes"] = prompt == offline_prompt
            if prompt != offline_prompt:
                raise ContextRefusal("Server full prompt differs from untruncated offline rendering")
            tokenize_payload = {"content": prompt, "add_special": True,
                                "parse_special": True, "with_pieces": False}
            token_response = client.post(f"http://127.0.0.1:{binding['port']}/tokenize", json=tokenize_payload)
            token_response.raise_for_status()
            actual = token_response.json()
            receipt["runtime_tokenizer"] = actual
            observed = actual.get("tokens")
            expected = self.tokenizer.encode(prompt, add_special_tokens=False).ids
            receipt["same_token_ids"] = observed == expected
            if observed != expected:
                raise ContextRefusal("Live runtime tokenizer differs from frozen offline token IDs")


@contextmanager
def capture_native_requests(guard: LocalOnlyGuard):
    """Capture actual native HTTP construction and refuse every dispatch."""
    httpx = guard.attach_httpx()
    captured = []
    original = httpx.Client.send

    def capture(client, request, *args, **kwargs):
        body = request.read()
        guard.check_http(request.method, str(request.url), body)
        captured.append({"method": request.method, "url": str(request.url),
                         "body": json.loads(body), "sent": False})
        raise TransportRefusal("Captured request; dispatch deliberately refused")

    httpx.Client.send = capture
    try:
        yield captured
    finally:
        httpx.Client.send = original
