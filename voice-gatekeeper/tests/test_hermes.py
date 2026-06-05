"""Tests for the session-based Hermes client (#142).

The client talks to Hermes' native API: create a session via
`POST /api/sessions`, then send turns to `POST /api/sessions/{id}/chat`
with `{"input": ...}`, reading the reply from `{"message": {"content": ...}}`.
HTTP is mocked with httpx.MockTransport so the contract is exercised without
a live Hermes.
"""

from __future__ import annotations

import httpx
import pytest

from gatekeeper.hermes import HermesClient, _extract_reply


def _install_transport(monkeypatch, handler):
    """Route the client's httpx.AsyncClient through a mock transport."""
    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


async def test_create_session_then_chat_round_trip(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "sess-1"})
        if request.url.path == "/api/sessions/sess-1/chat":
            return httpx.Response(200, json={"message": {"content": "pongII"}})
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)
    client = HermesClient("http://hermes:8642", "secret")
    reply = await client.converse(
        text="ping", uid="michael", endpoint="voice-pe:sat", trace_id="t1"
    )

    assert reply == "pongII"
    assert calls[0][:2] == ("POST", "/api/sessions")
    assert calls[0][2] == {"user_id": "michael"}
    assert calls[1][:2] == ("POST", "/api/sessions/sess-1/chat")
    assert calls[1][2] == {"input": "ping"}


async def test_bearer_token_sent(monkeypatch):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "s"})
        return httpx.Response(200, json={"message": {"content": "ok"}})

    _install_transport(monkeypatch, handler)
    client = HermesClient("http://hermes:8642", "secret")
    await client.converse(text="hi", uid="u", endpoint="e", trace_id="t")

    assert seen == ["Bearer secret", "Bearer secret"]


async def test_session_reused_across_turns(monkeypatch):
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "sess-A"})
        return httpx.Response(200, json={"message": {"content": "reply"}})

    _install_transport(monkeypatch, handler)
    client = HermesClient("http://hermes:8642", "")

    await client.converse(text="first", uid="michael", endpoint="e", trace_id="t1")
    await client.converse(text="second", uid="michael", endpoint="e", trace_id="t2")

    # Exactly one session created; the second turn reuses the cached id.
    assert paths.count("/api/sessions") == 1
    assert paths.count("/api/sessions/sess-A/chat") == 2


async def test_expired_session_recreated_once(monkeypatch):
    state = {"session_calls": 0}
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/sessions":
            state["session_calls"] += 1
            sid = "old" if state["session_calls"] == 1 else "new"
            return httpx.Response(200, json={"id": sid})
        if request.url.path == "/api/sessions/old/chat":
            return httpx.Response(404, text="session expired")
        if request.url.path == "/api/sessions/new/chat":
            return httpx.Response(200, json={"message": {"content": "recovered"}})
        return httpx.Response(500)

    _install_transport(monkeypatch, handler)
    client = HermesClient("http://hermes:8642", "")
    # Seed a stale session id so the first chat hits the 404 path.
    client._sessions["michael"] = "old"

    reply = await client.converse(text="hi", uid="michael", endpoint="e", trace_id="t")

    assert reply == "recovered"
    assert state["session_calls"] == 1  # recreated exactly once
    assert client._sessions["michael"] == "new"


async def test_chat_error_returns_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "s"})
        return httpx.Response(500, text="boom")

    _install_transport(monkeypatch, handler)
    client = HermesClient("http://hermes:8642", "")
    reply = await client.converse(text="hi", uid="u", endpoint="e", trace_id="t")
    assert reply == ""


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"message": {"content": "pongII"}}, "pongII"),
        ({"output": "out"}, "out"),
        ({"reply": "rep"}, "rep"),
        ({"response": "resp"}, "resp"),
        ({"text": "txt"}, "txt"),
        ({"message": {}}, ""),
        ({}, ""),
        ("not-a-dict", ""),
    ],
)
def test_extract_reply_shapes(body, expected):
    assert _extract_reply(body) == expected
