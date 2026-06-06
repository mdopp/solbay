"""Tests for the privileged config sidecar (runs in the hermes pod)."""

from __future__ import annotations

import os

from solilos_chat.config_agent import build_app

TOKEN = "secret-key"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _app(tmp_path):
    return build_app(token=TOKEN, soul_path=str(tmp_path / "SOUL.md"))


async def test_health_needs_no_auth(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/health")
    assert resp.status == 200
    assert (await resp.json())["ok"] is True


async def test_put_soul_writes_with_auth(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.put("/soul", json={"content": "# Sol\nnew soul"}, headers=AUTH)
    assert resp.status == 200
    soul = tmp_path / "SOUL.md"
    assert soul.read_text(encoding="utf-8") == "# Sol\nnew soul"
    # World-readable so Hermes (a different uid in the shared pod) can read it.
    assert (os.stat(soul).st_mode & 0o777) == 0o644


async def test_put_soul_rejects_missing_auth(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.put("/soul", json={"content": "x"})
    assert resp.status == 401
    assert not (tmp_path / "SOUL.md").exists()


async def test_put_soul_rejects_wrong_token(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.put(
        "/soul", json={"content": "x"}, headers={"Authorization": "Bearer nope"}
    )
    assert resp.status == 401


async def test_put_soul_empty_rejected(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.put("/soul", json={"content": "   "}, headers=AUTH)
    assert resp.status == 400


async def test_get_soul_reads_with_auth(aiohttp_client, tmp_path):
    (tmp_path / "SOUL.md").write_text("# Sol\nhi", encoding="utf-8")
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/soul", headers=AUTH)
    body = await resp.json()
    assert body == {"ok": True, "content": "# Sol\nhi"}

    resp = await client.get("/soul")  # no auth
    assert resp.status == 401
