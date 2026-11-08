"""One prospective CPU-only tool round trip; no benchmark tasks or downloads.

Use only the existing private runtime and cached weights. Preserve every result,
make at most two model calls, and never retry an unsuccessful qualification.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import zipfile

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.kaggle_limbo.bundle import binding  # noqa: E402
from research.kaggle_limbo.granite_format import repair_template  # noqa: E402
from research.limbo_agent.harness import manifest, plain  # noqa: E402
from research.limbo_agent.transport import RuntimeBinding  # noqa: E402
from research.expanded_limbo.transport import ExpandedLIMBOClient  # noqa: E402
from scripts.start_durable_limbo_runtime import verify_private  # noqa: E402

ARCHIVE_SHA = "fe021dc3109fe0f2c2881f19a37a51fc08654c5470dee857cb461d10db924f95"
BASE = "http://127.0.0.1:11436"


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def api(path, payload=None, timeout=300):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def qualify(output, archive, runtime_dir, models_dir, family="granite"):
    output, runtime_dir, models_dir = [Path(p).resolve() for p in (output, runtime_dir, models_dir)]
    require(not output.exists(), "Refuse replacing a prior qualification")
    require(binding(archive)["sha256"] == ARCHIVE_SHA, "Expected the exact uploaded failure evidence")
    require(psutil.virtual_memory().available > 4 * 1024**3, "Need four GiB free for this CPU check")
    private = verify_private(runtime_dir)
    require(private["declared_version"] == "0.40.10", "Use the same pinned runtime version")
    study = ROOT / "output/kaggle-benchmark-2026-11-08/conseqax-kaggle-study"
    protocol = json.loads((study / "study-design.json").read_text())
    model = next(m for m in protocol["models"] if m["family"] == family)
    weights_sha = model["weights"]["sha256"]
    alias = f"conseqax-expanded-{family}-formatcheck-20261108-v1:ctx8k"
    blob = models_dir / "blobs" / ("sha256-" + weights_sha)
    require(binding(blob) == model["weights"], "Cached model weights changed")
    metadata = study / "assets/models" / family
    image = json.loads((metadata / "registry-manifest.json").read_text())
    template_layer = next(p for p in image["layers"] if p["mediaType"] == "application/vnd.ollama.image.template")
    original = (metadata / template_layer["digest"].replace(":", "-")).read_bytes()
    patch = repair_template(original) if family == "granite" else {
        "schema": "conseqax-original-template-unchanged-v1", "template": original.decode("utf-8"),
        "original": model["chat_template"], "patched": model["chat_template"]}
    catalog = json.loads((study / "assets/model-catalog.json").read_text())
    original_tag = catalog[model["id"]]["original_tag"]
    with zipfile.ZipFile(archive) as saved:
        candidates = [n for n in saved.namelist() if n.endswith(f"/{family}/client/0001-request.bin")]
        require(len(candidates) == 1, "Expected one original model qualification request")
        request = json.loads(saved.read(candidates[0]))
    require(request["max_tokens"] == 128 and request["temperature"] == .2 and request["seed"] == 2501,
            "Do not change the declared qualification sampling")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 11436))
    output.mkdir(parents=True)
    save(output / "template-repair.json", patch)
    save(output / "prospective-plan.json", {
        "scope": "CPU engineering qualification; not Kaggle validation or a native benchmark episode",
        "original_failure_archive": binding(archive), "program": binding(__file__),
        "template_repair_source": binding(ROOT / "research/kaggle_limbo/granite_format.py"),
        "original_template": patch["original"], "candidate_template": patch["patched"],
        "weights": binding(blob), "alias": alias, "family": family, "maximum_model_calls": 2,
        "automatic_retries": 0, "sampling": {"max_tokens": 128, "temperature": .2, "seed": 2501},
        "first_call_requirement": "Exactly one lookup_echo tool call with name test-item",
        "followup_requirement": "After the observed tool result, return test-item and no further tool call",
        "normal_service_modified": False, "model_downloads": 0, "native_tasks": 0})
    environment = dict(os.environ)
    environment.update(OLLAMA_HOST="127.0.0.1:11436", OLLAMA_MODELS=str(models_dir),
        OLLAMA_NO_CLOUD="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1",
        OLLAMA_KV_CACHE_TYPE="q8_0", OLLAMA_FLASH_ATTENTION="1", OLLAMA_CONTEXT_LENGTH="8192",
        OLLAMA_KEEP_ALIVE="-1", OLLAMA_NOPRUNE="1", OLLAMA_DEBUG="1", CUDA_VISIBLE_DEVICES="-1")
    executable = runtime_dir / "ollama.exe"
    success, count, process = False, 0, None
    try:
        with (output / "server.stdout.log").open("xb") as out, (output / "server.stderr.log").open("xb") as err:
            child = subprocess.Popen([str(executable), "serve"], env=environment,
                stdout=out, stderr=err, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        process = psutil.Process(child.pid)
        save(output / "owned-server.json", {"pid": process.pid, "create_time": process.create_time(),
            "executable": process.exe(), "executable_binding": binding(process.exe())})
        for _ in range(60):
            try:
                require(api("/api/version", timeout=2)["version"] == "0.40.10", "Unexpected listener")
                break
            except OSError:
                require(child.poll() is None, "Private qualification server stopped")
                time.sleep(.5)
        else:
            raise RuntimeError("Private CPU server did not start")
        require(not any(m["name"] == alias for m in api("/api/tags")["models"]), "Qualification alias exists")
        created = api("/api/create", {"model": alias, "from": original_tag, "template": patch["template"],
            "parameters": {"num_ctx": 8192, "num_predict": 128, "temperature": .2, "num_gpu": 0}, "stream": False})
        save(output / "alias-created.json", created)
        require(created.get("status") == "success", "Candidate alias creation failed")
        show = api("/api/show", {"model": alias})
        require(show["template"] == patch["template"], "Provider did not install the candidate bytes")
        save(output / "candidate-show.json", show)
        loaded = api("/api/generate", {"model": alias, "prompt": "", "stream": False,
            "keep_alive": -1, "options": {"num_ctx": 8192, "num_predict": 0, "num_gpu": 0}})
        save(output / "load-only.json", loaded)
        require(loaded.get("done_reason") == "load" and not loaded.get("response"), "Load generated text")
        resident = [m for m in api("/api/ps")["models"] if m["name"] == alias]
        require(len(resident) == 1 and resident[0]["size_vram"] == 0, "This check must use CPU only")
        runners = [p for p in process.children(recursive=True) if p.name().lower() == "llama-server.exe"]
        require(len(runners) == 1, "Expected one owned CPU runner")
        runner, args = runners[0], runners[0].cmdline()
        require(str(blob) == args[args.index("--model") + 1], "Runner loaded different weights")
        lease = RuntimeBinding(api_base=BASE + "/v1", model=alias, model_digest=resident[0]["digest"],
            model_blob=str(blob), model_blob_sha256=weights_sha,
            server_pid=process.pid, server_executable=process.exe(), server_create_time=process.create_time(),
            server_executable_sha256=binding(process.exe())["sha256"], runner_pid=runner.pid,
            runner_executable=runner.exe(), runner_create_time=runner.create_time(),
            runner_executable_sha256=binding(runner.exe())["sha256"],
            runner_port=int(args[args.index("--port") + 1]), context_tokens=8192, parallel_slots=1)
        save(output / "runtime-binding.json", asdict(lease))
        native = ROOT / "output/kaggle-benchmark-2026-11-08/conseqax-kaggle-study/native"
        sys.path.insert(0, str(native))
        conversation = [request["messages"][1]]
        tools = [t["function"] for t in request["tools"]]
        with ExpandedLIMBOClient(lease, output / "client", max_requests=2, max_output_tokens=128,
                request_timeout_s=300, temperature=.2, seed=2501,
                absolute_deadline_monotonic=time.monotonic() + 600,
                protected_roots=(str(native), str(models_dir))) as client:
            count += 1
            turn = client.complete(request["messages"][0]["content"], conversation, tools)
            save(output / "first-parsed-turn.json", plain(turn))
            require(len(turn.tool_calls) == 1 and turn.tool_calls[0].name == "lookup_echo"
                    and turn.tool_calls[0].parsed_arguments() == ({"name": "test-item"}, None),
                    "Candidate failed first tool call; stop without retry")
            call = turn.tool_calls[0]
            conversation.extend([{"role": "assistant", "content": turn.text, "tool_calls": [asdict(call)]},
                {"role": "tool", "tool_call_id": call.id, "content": '{"name":"test-item","ok":true}'},
                {"role": "user", "content": "The tool completed. Reply with the completed name only. Do not call any tool again."}])
            count += 1
            followup = client.complete(request["messages"][0]["content"], conversation, tools)
            save(output / "followup-parsed-turn.json", plain(followup))
            require(not followup.tool_calls and followup.text.strip() == "test-item",
                    "Candidate failed tool-result followup; stop without retry")
        success = True
    except BaseException as exc:
        save(output / "error.json", {"type": type(exc).__name__, "message": str(exc),
                                    "traceback": traceback.format_exc(limit=12)})
        raise
    finally:
        if process is not None and process.is_running():
            try:
                api("/api/generate", {"model": alias, "prompt": "", "stream": False, "keep_alive": 0,
                                      "options": {"num_predict": 0}}, timeout=30)
            except Exception:
                pass
            children = process.children(recursive=True)
            for owned in reversed(children):
                if owned.is_running():
                    owned.terminate()
            if process.is_running():
                process.terminate()
            _, alive = psutil.wait_procs([*children, process], timeout=10)
            for owned in alive:
                if owned.is_running():
                    owned.kill()
        save(output / "qualification-result.json", {"passed": success, "model_invocations": count,
            "maximum_model_calls": 2, "automatic_retries": 0, "native_tasks": 0,
            "CPU_engineering_check_only": True, "GPU_qualification_completed": False,
            "normal_service_modified": False})
        save(output / "manifest.json", manifest(output))
    return {"passed": success, "model_invocations": count, "GPU_qualification_completed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=Path("C:/Users/DELL/Downloads/results.zip"))
    parser.add_argument("--private-runtime", type=Path, default=Path("C:/Code/ConsequaX-Research/ollama-runtime-0.40.10"))
    parser.add_argument("--models", type=Path, default=Path("C:/Code/ConsequaX-Research/models"))
    parser.add_argument("--family", choices=("granite", "qwen", "llama"), default="granite")
    args = parser.parse_args()
    print(json.dumps(qualify(args.output, args.archive, args.private_runtime, args.models, args.family)))


if __name__ == "__main__":
    main()
