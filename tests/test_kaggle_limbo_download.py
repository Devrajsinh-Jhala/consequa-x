"""Offline fault injection for setup downloads; no GPU or inference requests."""
from __future__ import annotations

import hashlib
from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
import sys
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.kaggle_limbo import runtime  # noqa: E402

URL = "https://example.invalid/pinned-asset"
SIGNED_URL = "https://cdn.invalid/asset?token=must-not-appear"
PAYLOAD = b"exact pinned artifact bytes"


def expected(payload=PAYLOAD):
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


class Response(BytesIO):
    def __init__(self, payload=PAYLOAD, *, status=200, headers=None, fault=None):
        super().__init__(payload)
        self.status = status
        self.headers = {"Content-Length": str(len(payload)), **(headers or {})}
        self.fault = fault

    def getcode(self):
        return self.status

    def read(self, size=-1):
        data = super().read(size)
        if not data and self.fault is not None:
            fault, self.fault = self.fault, None
            raise fault
        return data


def network(monkeypatch, sequence):
    """Record actual requests without opening any network connection."""
    sequence = iter(sequence)
    calls, delays = [], []

    def fake_urlopen(request, **kwargs):
        calls.append((request, kwargs))
        value = next(sequence)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(runtime.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(runtime.time, "sleep", delays.append)
    monkeypatch.delenv("CONSEQAX_SESSION_START_MONOTONIC", raising=False)
    return calls, delays


def headers(request):
    return {key.lower(): value for key, value in request.header_items()}


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
def test_transient_http_error_retries_original_url(monkeypatch, tmp_path, code, capsys):
    error = urllib.error.HTTPError(SIGNED_URL, code, "transient", {}, None)
    calls, delays = network(monkeypatch, [error, Response()])
    destination = tmp_path / "asset"
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert [request.full_url for request, _ in calls] == [URL, URL]
    assert delays == [2]
    assert all(headers(request)["accept-encoding"] == "identity" for request, _ in calls)
    captured = capsys.readouterr()
    assert "must-not-appear" not in captured.out + captured.err


@pytest.mark.parametrize("fault", [
    urllib.error.URLError("temporary DNS failure"),
    TimeoutError("temporary timeout"),
    ConnectionError("temporary reset"),
    IncompleteRead(b"", 1),
])
def test_transient_connection_fault_retries(monkeypatch, tmp_path, fault):
    calls, delays = network(monkeypatch, [fault, Response()])
    destination = tmp_path / "asset"
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert len(calls) == 2 and delays == [2]


def test_midstream_disconnect_resumes_only_the_missing_suffix(monkeypatch, tmp_path):
    prefix = PAYLOAD[:7]
    suffix = PAYLOAD[len(prefix):]
    calls, delays = network(monkeypatch, [
        Response(prefix, headers={"Content-Length": str(len(PAYLOAD))},
            fault=ConnectionResetError("stream reset")),
        Response(suffix, status=206, headers={
            "Content-Range": f"bytes {len(prefix)}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}"}),
    ])
    destination = tmp_path / "asset"
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert headers(calls[1][0])["range"] == f"bytes={len(prefix)}-"
    assert delays == [2]
    assert not destination.with_name("asset.download").exists()


def test_existing_partial_is_resumed(monkeypatch, tmp_path):
    destination = tmp_path / "asset"
    destination.with_name("asset.download").write_bytes(PAYLOAD[:7])
    calls, delays = network(monkeypatch, [Response(PAYLOAD[7:], status=206, headers={
        "Content-Range": f"bytes 7-{len(PAYLOAD) - 1}/{len(PAYLOAD)}"})])
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert headers(calls[0][0])["range"] == "bytes=7-"
    assert not delays


def test_server_ignoring_range_restarts_instead_of_appending(monkeypatch, tmp_path):
    destination = tmp_path / "asset"
    destination.with_name("asset.download").write_bytes(PAYLOAD[:7])
    calls, delays = network(monkeypatch, [Response()])
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert headers(calls[0][0])["range"] == "bytes=7-"
    assert not delays


@pytest.mark.parametrize("content_range", [
    "bytes 6-26/27",  # Starts before the saved prefix.
    "bytes 8-26/27",  # Omits a byte after the saved prefix.
    "bytes 7-26/99",  # Different total size.
    "bytes 7-26/*",   # Unbound total size.
    "nonsense",
    None,
])
def test_malformed_partial_response_never_installs(monkeypatch, tmp_path, content_range):
    destination = tmp_path / "asset"
    destination.with_name("asset.download").write_bytes(PAYLOAD[:7])
    range_headers = {} if content_range is None else {"Content-Range": content_range}
    calls, _ = network(monkeypatch, [Response(PAYLOAD[7:], status=206,
        headers=range_headers) for _ in range(5)])
    with pytest.raises((ValueError, RuntimeError)):
        runtime.download(URL, destination, expected())
    assert not destination.exists()
    assert 1 <= len(calls) <= 5


def test_full_valid_partial_is_verified_and_promoted_without_network(monkeypatch, tmp_path):
    destination = tmp_path / "asset"
    partial = destination.with_name("asset.download")
    partial.write_bytes(PAYLOAD)
    calls, delays = network(monkeypatch, [])
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert not partial.exists()
    assert not calls and not delays


@pytest.mark.parametrize("payload", [PAYLOAD[:-1], b"x" * len(PAYLOAD), PAYLOAD + b"extra"])
def test_wrong_length_or_digest_is_never_installed(monkeypatch, tmp_path, payload):
    destination = tmp_path / "asset"
    network(monkeypatch, [Response(payload) for _ in range(5)])
    with pytest.raises((ValueError, RuntimeError)):
        runtime.download(URL, destination, expected())
    assert not destination.exists()


def test_corrupt_full_partial_is_never_promoted(monkeypatch, tmp_path):
    destination = tmp_path / "asset"
    destination.with_name("asset.download").write_bytes(b"x" * len(PAYLOAD))
    network(monkeypatch, [urllib.error.URLError("offline") for _ in range(5)])
    with pytest.raises((ValueError, RuntimeError)):
        runtime.download(URL, destination, expected())
    assert not destination.exists()


def test_exhausted_retries_preserve_partial_and_hide_signed_urls(monkeypatch, tmp_path, capsys):
    destination = tmp_path / "asset"
    partial = destination.with_name("asset.download")
    partial.write_bytes(PAYLOAD[:7])
    calls, delays = network(monkeypatch, [
        urllib.error.HTTPError(SIGNED_URL, 504, "Gateway Time-out", {}, None)
        for _ in range(5)])
    with pytest.raises(RuntimeError) as caught:
        runtime.download(URL, destination, expected())
    assert len(calls) == 5
    assert delays == [2, 4, 8, 16]
    assert partial.read_bytes() == PAYLOAD[:7]
    assert not destination.exists()
    captured = capsys.readouterr()
    assert "must-not-appear" not in str(caught.value) + captured.out + captured.err


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_terminal_http_error_fails_without_retry_or_signed_url(monkeypatch, tmp_path, code):
    calls, delays = network(monkeypatch, [
        urllib.error.HTTPError(SIGNED_URL, code, "terminal", {}, None)])
    with pytest.raises(RuntimeError) as caught:
        runtime.download(URL, tmp_path / "asset", expected())
    assert len(calls) == 1 and not delays
    assert "must-not-appear" not in str(caught.value)


def test_verified_cached_destination_does_not_download(monkeypatch, tmp_path):
    destination = tmp_path / "asset"
    destination.write_bytes(PAYLOAD)
    calls, delays = network(monkeypatch, [])
    runtime.download(URL, destination, expected())
    assert not calls and not delays


def test_modified_cached_destination_fails_without_replacing_it(monkeypatch, tmp_path):
    destination = tmp_path / "asset"
    destination.write_bytes(b"modified")
    calls, delays = network(monkeypatch, [])
    with pytest.raises((ValueError, RuntimeError)):
        runtime.download(URL, destination, expected())
    assert destination.read_bytes() == b"modified"
    assert not calls and not delays


def test_setup_fallback_stays_with_explicit_urls(monkeypatch, tmp_path):
    fallback = "https://example.invalid/official-pinned-asset"
    calls, _ = network(monkeypatch, [
        urllib.error.HTTPError(SIGNED_URL, 504, "Gateway Time-out", {}, None), Response()])
    destination = tmp_path / "asset"
    runtime.download(URL, destination, expected(), fallback_urls=(fallback,))
    assert destination.read_bytes() == PAYLOAD
    assert calls[0][0].full_url == URL
    assert calls[1][0].full_url in (URL, fallback)
    assert all(request.full_url in (URL, fallback) for request, _ in calls)


def test_measured_runtime_api_does_not_acquire_setup_retries(monkeypatch):
    calls, delays = [], []

    class Opener:
        def open(self, request, **kwargs):
            calls.append(request)
            raise urllib.error.HTTPError(SIGNED_URL, 504, "Gateway Time-out", {}, None)

    monkeypatch.setattr(runtime.urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(runtime.time, "sleep", delays.append)
    with pytest.raises(urllib.error.HTTPError):
        runtime.api("/api/generate", {"prompt": "invented fixture"})
    assert len(calls) == 1 and not delays


def test_expired_setup_budget_prevents_any_network_request(monkeypatch, tmp_path):
    calls, delays = network(monkeypatch, [])
    monkeypatch.setenv("CONSEQAX_SESSION_START_MONOTONIC", "10")
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 10 + 7 * 3600)
    with pytest.raises(RuntimeError, match="deadline"):
        runtime.download(URL, tmp_path / "asset", expected())
    assert not calls and not delays
    assert not (tmp_path / "asset").exists()


def test_retry_cannot_extend_the_setup_budget(monkeypatch, tmp_path):
    calls, delays = network(monkeypatch, [
        urllib.error.HTTPError(SIGNED_URL, 504, "Gateway Time-out", {}, None)])
    monkeypatch.setenv("CONSEQAX_SESSION_START_MONOTONIC", "10")
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 10 + 7 * 3600 - 1)
    with pytest.raises(RuntimeError, match="setup time"):
        runtime.download(URL, tmp_path / "asset", expected())
    assert len(calls) == 1 and not delays
    assert calls[0][1]["timeout"] <= 1


@pytest.mark.parametrize("encoding", ["gzip", "br"])
def test_encoded_response_is_rejected_before_writing(monkeypatch, tmp_path, encoding):
    calls, delays = network(monkeypatch, [Response(headers={"Content-Encoding": encoding})])
    destination = tmp_path / "asset"
    with pytest.raises(ValueError, match="Encoded"):
        runtime.download(URL, destination, expected())
    assert len(calls) == 1 and not delays
    assert not destination.exists()
    assert not destination.with_name("asset.download").exists()


def test_overlong_stream_without_content_length_is_not_installed(monkeypatch, tmp_path):
    calls, delays = network(monkeypatch, [Response(PAYLOAD + b"extra", headers={
        "Content-Length": None})])
    destination = tmp_path / "asset"
    with pytest.raises(ValueError, match="exceeds"):
        runtime.download(URL, destination, expected())
    assert len(calls) == 1 and not delays
    assert not destination.exists()
    assert destination.with_name("asset.download").stat().st_size <= len(PAYLOAD)


def test_incomplete_read_exception_retains_its_bytes_before_resuming(monkeypatch, tmp_path):
    class PartialReadResponse(Response):
        def read(self, size=-1):
            raise IncompleteRead(PAYLOAD[:7], len(PAYLOAD) - 7)

    calls, delays = network(monkeypatch, [
        PartialReadResponse(),
        Response(PAYLOAD[7:], status=206, headers={
            "Content-Range": f"bytes 7-{len(PAYLOAD) - 1}/{len(PAYLOAD)}"}),
    ])
    destination = tmp_path / "asset"
    runtime.download(URL, destination, expected())
    assert destination.read_bytes() == PAYLOAD
    assert headers(calls[1][0])["range"] == "bytes=7-"
    assert delays == [2]
