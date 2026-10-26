"""Linux GPU identity checks around the existing full-history native transport."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import psutil

from research.expanded_limbo.transport import ExpandedLIMBOClient
from research.limbo_agent.transport import file_sha256, write_json


class KaggleGPUClient(ExpandedLIMBOClient):
    def __init__(self, *args, condition, gpu_devices, gpu_load_proof, **kwargs):
        self.condition, self.gpu_devices, self.gpu_load_proof = condition, gpu_devices, gpu_load_proof
        super().__init__(*args, **kwargs)
        write_json(self.journal_dir / "kaggle-gpu-config.json", {
            "schema": "conseqax-kaggle-gpu-condition-v1", "condition": condition,
            "runtime": asdict(self.binding), "gpu_devices": gpu_devices,
            "gpu_load_proof": gpu_load_proof,
            "cpu_fallback_allowed": False})

    def _verify_identity(self, *, initial=False):
        binding = self.binding
        for pid, executable, born in (
            (binding.server_pid, binding.server_executable, binding.server_create_time),
            (binding.runner_pid, binding.runner_executable, binding.runner_create_time),
        ):
            process = psutil.Process(pid)
            if (Path(process.exe()).resolve() != Path(executable).resolve()
                    or abs(process.create_time() - born) > .001):
                raise RuntimeError("Bound Kaggle research process changed")
        args = psutil.Process(binding.runner_pid).cmdline()
        for flag, value in {"--model": binding.model_blob, "--port": str(binding.runner_port),
                            "--host": "127.0.0.1", "-np": "1",
                            "-c": str(binding.context_tokens), "-ngl": "999"}.items():
            if (flag not in args or args.index(flag) + 1 >= len(args)
                    or args[args.index(flag) + 1] != value):
                raise RuntimeError("GPU model runner binding differs: " + flag)
        if "--offline" not in args:
            raise RuntimeError("Model runner is not offline")
        from .audit import verify_gpu_load_proof
        try:
            verify_gpu_load_proof(self.gpu_load_proof, {
                "runner_pid": binding.runner_pid, "runner_create_time": binding.runner_create_time,
                "model_blob_sha256": binding.model_blob_sha256})
        except ValueError as exc:
            raise RuntimeError("GPU load proof is invalid before generation") from exc
        proof = self.gpu_load_proof
        if (proof.get("runner_pid") != binding.runner_pid
                or proof.get("runner_create_time") != binding.runner_create_time
                or proof.get("model_blob_sha256") != binding.model_blob_sha256
                or proof.get("requested_gpu_layers") != 999
                or type(proof.get("total_layers")) is not int or proof["total_layers"] <= 0
                or proof.get("offloaded_layers") != proof["total_layers"]):
            raise RuntimeError("Bound GPU runner lacks a complete layer-offload proof")
        for path, expected in ((binding.model_blob, binding.model_blob_sha256),
                              (binding.server_executable, binding.server_executable_sha256),
                              (binding.runner_executable, binding.runner_executable_sha256)):
            stat = Path(path).stat()
            stamp = (stat.st_size, stat.st_mtime_ns)
            if initial:
                if file_sha256(path) != expected:
                    raise RuntimeError("Pinned GPU runtime/model file changed")
                self._identity_files[path] = stamp
            elif self._identity_files.get(path) != stamp:
                raise RuntimeError("Bound GPU runtime/model changed after preflight")
        version = self._json_call("GET", binding.api_base.removesuffix("/v1") + "/api/version")
        if version.get("version") != self.condition["runtime_version"]:
            raise RuntimeError("GPU runtime version changed")
        resident = self._json_call("GET", binding.api_base.removesuffix("/v1") + "/api/ps")
        models = [m for m in resident.get("models", [])
                  if m.get("name") == binding.model or m.get("model") == binding.model]
        if len(models) != 1:
            raise RuntimeError("Expected exactly one bound GPU-resident model")
        size, vram = models[0].get("size"), models[0].get("size_vram")
        if (models[0].get("digest") != binding.model_digest
                or models[0].get("context_length") != binding.context_tokens
                or type(size) is not int or type(vram) is not int
                or size <= 0 or vram <= 0):
            raise RuntimeError("Expected full GPU residency; CPU fallback is refused")
