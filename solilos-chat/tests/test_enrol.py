"""Tests for the voice-enrolment tool (gatekeeper POST /enrol accessor, #364).

The gatekeeper HTTP call is mocked with a local aiohttp app served by
`aiohttp_client`, so we assert the exact request the tool builds, that it
passes the gatekeeper's ok/reason verdict through on both success and
failure, and that the raw audio samples never reach a log line.
"""

from __future__ import annotations

import base64
import json
import logging

import pytest
from aiohttp import web

from solilos_chat.engine.tools.enrol import build_enrol_tools

_SAMPLE = base64.b64encode(b"\x00\x01" * 16).decode()


@pytest.fixture
async def gatekeeper(aiohttp_client):
    """A stub gatekeeper that records the last /enrol request and replies
    with whatever the test queued."""
    seen: dict = {}
    reply: dict = {
        "status": 200,
        "body": {"ok": True, "uid": "lena", "samples_used": 3},
    }

    async def enrol(request: web.Request) -> web.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = await request.json()
        return web.json_response(reply["body"], status=reply["status"])

    app = web.Application()
    app.router.add_post("/enrol", enrol)
    client = await aiohttp_client(app)
    base = str(client.make_url("")).rstrip("/")
    return base, seen, reply


async def test_builds_the_right_request(gatekeeper):
    base, seen, _ = gatekeeper
    (tool,) = build_enrol_tools(base, gatekeeper_token="s3cret")
    out = json.loads(
        await tool.handler({"uid": "lena", "samples": [_SAMPLE, _SAMPLE, _SAMPLE]})
    )
    assert out == {"ok": True, "uid": "lena", "samples_used": 3}
    assert seen["body"] == {"uid": "lena", "samples": [_SAMPLE, _SAMPLE, _SAMPLE]}
    assert seen["auth"] == "Bearer s3cret"


async def test_passes_failure_through(gatekeeper):
    base, _, reply = gatekeeper
    reply["status"] = 422
    reply["body"] = {"ok": False, "reason": "not_enough_usable_samples"}
    (tool,) = build_enrol_tools(base)
    out = json.loads(await tool.handler({"uid": "lena", "samples": [_SAMPLE]}))
    assert out == {"ok": False, "reason": "not_enough_usable_samples"}


async def test_rejects_bad_uid_without_calling_gatekeeper(gatekeeper):
    base, seen, _ = gatekeeper
    (tool,) = build_enrol_tools(base)
    out = json.loads(await tool.handler({"uid": "../etc", "samples": [_SAMPLE]}))
    assert out == {"ok": False, "reason": "invalid_uid"}
    assert seen == {}  # never reached the gatekeeper


async def test_rejects_missing_samples(gatekeeper):
    base, seen, _ = gatekeeper
    (tool,) = build_enrol_tools(base)
    out = json.loads(await tool.handler({"uid": "lena", "samples": []}))
    assert out == {"ok": False, "reason": "missing_samples"}
    assert seen == {}


async def test_does_not_log_audio(gatekeeper, caplog):
    base, _, _ = gatekeeper
    (tool,) = build_enrol_tools(base, gatekeeper_token="s3cret")
    with caplog.at_level(logging.DEBUG):
        await tool.handler({"uid": "lena", "samples": [_SAMPLE, _SAMPLE, _SAMPLE]})
    assert _SAMPLE not in caplog.text
