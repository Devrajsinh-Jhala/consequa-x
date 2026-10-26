"""Versioned multi-family transport; historical Qwen transport stays unchanged.

The native LIMBO renderer/parser still owns messages and tool calls. This
extension uses the bound provider's complete render-only preview and its exact
GGUF runner tokenizer for the context gate. It does NOT claim independent
offline template/tokenizer parity for additional model families. No history is
trimmed. Every actual HTTP dispatch and failed invocation is retained.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
import time

from research.limbo_agent.transport import (
    AuditedLIMBOClient, canonical, read_gguf_metadata, sha256,
    write_bytes, write_json,
)

SCHEMA = "conseqax-expanded-limbo-transport-v1"


def checked_context(prompt, tokens, *, output_tokens, context_tokens, reserve_tokens=64):
    """Check an exact bound runner token sequence, including its special tokens."""
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("Full provider-rendered prompt is required")
    if (not isinstance(tokens, list) or not tokens
            or any(type(token) is not int or token < 0 for token in tokens)):
        raise ValueError("Exact runtime token IDs are required")
    for number in (output_tokens, context_tokens, reserve_tokens):
        if type(number) is not int or number < 1:
            raise ValueError("Positive explicit context/output/reserve budget required")
    required = len(tokens) + output_tokens + reserve_tokens
    result = {"rendered_prompt_sha256": sha256(prompt.encode()),
              "prompt_tokens": len(tokens), "output_tokens": output_tokens,
              "reserve_tokens": reserve_tokens, "required_tokens": required,
              "context_tokens": context_tokens, "fits": required <= context_tokens,
              "truncation_requested": False,
              "tokenizer_scope": "Bound native runner; not independent offline reconstruction"}
    if not result["fits"]:
        raise ValueError("Full native history exceeds the prospective context budget: "
                         + json.dumps(result, sort_keys=True))
    return result


class ExpandedLIMBOClient(AuditedLIMBOClient):
    """One dispatch, local-only, explicit temperature and provider-native preview."""

    def __init__(self, *args, temperature=0.2, **kwargs):
        if (type(temperature) not in (int, float) or not math.isfinite(temperature)
                or not 0 <= temperature <= 2):
            raise ValueError("Finite temperature in [0,2] required")
        super().__init__(*args, **kwargs)
        self.temperature = temperature
        write_json(self.journal_dir / "expanded-client-config.json", {
            "schema": SCHEMA, "runtime": asdict(self.binding),
            "temperature": temperature, "seed": self.seed,
            "max_output_tokens": self.max_output_tokens,
            "max_requests": self.max_requests, "automatic_http_retries": 0,
            "configuration_scope": "This extension's temperature supersedes the base constructor's initial zero; actual native request bytes bind the value",
            "context_gate": "Complete provider-native preview plus bound native runner token IDs",
            "independent_offline_template_tokenizer_parity": False,
        })

    def __enter__(self):
        if self._entered:
            raise RuntimeError("One-shot client reuse is refused")
        self._entered = True
        self.guard.__enter__()
        self._active = True
        try:
            self._verify_identity(initial=True)
            self.metadata = read_gguf_metadata(self.binding.model_blob)
            if not self.metadata.get("tokenizer.chat_template"):
                raise RuntimeError("Bound GGUF lacks a declared chat template")
            self._event("expanded_client_ready", model_generations=0,
                        architecture=self.metadata.get("general.architecture"),
                        offline_tokenizer_parity=False, temperature=self.temperature)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _context_check(self, payload):
        binding = self.binding
        receipt = {"schema": SCHEMA, "request_sha256": sha256(canonical(payload)),
                   "request": payload, "generation_dispatched_by_gate": False,
                   "runtime_binding": asdict(binding),
                   "independent_offline_template_tokenizer_parity": False}
        try:
            self._verify_identity()
            residency = self._json_call("GET", binding.api_base.removesuffix("/v1") + "/api/ps")
            profiles = [item for item in residency.get("models", [])
                        if item.get("name") == binding.model or item.get("model") == binding.model]
            if (len(profiles) != 1 or profiles[0].get("context_length") != binding.context_tokens
                    or profiles[0].get("digest") != binding.model_digest):
                raise RuntimeError("Bound model residency/context/digest changed")
            receipt["resident_response"] = residency
            preview = self._json_call("POST", binding.api_base + "/chat/completions",
                                      {**payload, "_debug_render_only": True})
            receipt["server_preview"] = preview
            prompt = preview.get("_debug_info", {}).get("rendered_template")
            if not isinstance(prompt, str) or not prompt:
                raise RuntimeError("Provider did not return its complete rendered prompt")
            receipt["provider_rendered_prompt"] = prompt
            tokenized = self._json_call("POST", f"http://127.0.0.1:{binding.runner_port}/tokenize",
                {"content": prompt, "add_special": True, "parse_special": True, "with_pieces": False})
            receipt["runtime_tokenizer"] = tokenized
            receipt["context"] = checked_context(prompt, tokenized.get("tokens"),
                output_tokens=self.max_output_tokens, context_tokens=binding.context_tokens)
            receipt["passed"] = True
            return receipt
        except BaseException as error:
            receipt["passed"] = False
            receipt["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            prefix = self._current["prefix"]
            write_json(prefix.with_name(prefix.name + "-context.json"), receipt)

    def _post(self, path, body):
        if path != "/chat/completions" or self._current is None or self._current["dispatched"]:
            raise RuntimeError("Exactly one native chat dispatch per invocation is allowed")
        expected_fields = {"model", "messages", "tools", "max_tokens", "temperature"}
        if (set(body) != expected_fields or body["model"] != self.model
                or body["temperature"] != self.temperature):
            raise RuntimeError("Native renderer changed model/temperature/request shape")
        payload = dict(body)
        if self.seed is not None:
            payload["seed"] = self.seed
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        prefix = self._current["prefix"]
        write_bytes(prefix.with_name(prefix.name + "-request.bin"), data)
        self._context_check(payload)
        timeout = self._remaining(self.timeout_s)
        self._current["dispatched"] = 1
        self._dispatches += 1
        self._event("before_dispatch", invocation=self._current["number"],
                    request_sha256=sha256(data), timeout_s=timeout, dispatches=1)
        started = time.monotonic()
        status, headers, raw = self._wire("POST", self.binding.api_base + path, data, timeout)
        write_bytes(prefix.with_name(prefix.name + "-response.bin"), raw)
        write_json(prefix.with_name(prefix.name + "-response-meta.json"), {
            "status": status, "headers": headers, "body_sha256": sha256(raw),
            "latency_s": time.monotonic() - started})
        if status != 200:
            raise RuntimeError("Single model dispatch returned HTTP " + str(status))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Model response is not an object")
        self._current["response"] = payload
        # The inherited complete() retains native parse errors and usage.
        return payload, time.monotonic() - started
