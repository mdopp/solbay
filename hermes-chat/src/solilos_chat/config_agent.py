"""Privileged config sidecar — runs *inside* the hermes pod.

The public chat pod cannot write Hermes' identity/config: SOUL.md and
config.yaml live in Hermes' own data dir (`/opt/data`, mode 0700, owned by
a foreign subuid), unreachable from the rootless chat pod's mount. This tiny
service runs as a second container in the hermes pod, mounts that data dir
read-write, and exposes a narrow loopback API the chat pod calls to apply an
admin's soul edit (model switching joins it later).

It is **not** internet-facing — it binds loopback only, behind no proxy, and
authenticates with the *same* Hermes API key the chat pod already holds
(`API_SERVER_KEY`), so no new secret crosses the wire. The admin gate stays
in the chat pod (Authelia `Remote-Groups`); this agent only trusts that a
caller proving the Hermes key is an internal Solilos service.

SOUL.md is loaded fresh by Hermes on every message, so a soul write takes
effect live — no restart.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from aiohttp import web

from solilos_chat.logging import log


def _atomic_write(path: str, content: str) -> None:
    """Write `content` to `path` atomically (temp in the same dir + replace),
    0644 so Hermes (a different uid in this shared pod) can read it."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_app(*, token: str, soul_path: str) -> web.Application:
    def authorized(request: web.Request) -> bool:
        # Constant work regardless of presence; the key is a shared secret,
        # not a per-user credential, so a plain compare is fine here.
        auth = request.headers.get("Authorization", "")
        return bool(token) and auth == f"Bearer {token}"

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def get_soul(request: web.Request) -> web.Response:
        if not authorized(request):
            return web.json_response(
                {"ok": False, "reason": "unauthorized"}, status=401
            )
        try:
            content = Path(soul_path).read_text(encoding="utf-8")
        except OSError:
            content = ""
        return web.json_response({"ok": True, "content": content})

    async def put_soul(request: web.Request) -> web.Response:
        if not authorized(request):
            return web.json_response(
                {"ok": False, "reason": "unauthorized"}, status=401
            )
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — any malformed JSON
            return web.json_response(
                {"ok": False, "reason": "invalid_json"}, status=400
            )
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            return web.json_response(
                {"ok": False, "reason": "empty_content"}, status=400
            )
        try:
            _atomic_write(soul_path, content)
        except OSError as e:
            log.error("agent.soul.write_failed", path=soul_path, error=str(e))
            return web.json_response(
                {"ok": False, "reason": "write_failed"}, status=500
            )
        log.info("agent.soul.written", path=soul_path)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/soul", get_soul)
    app.router.add_put("/soul", put_soul)
    return app


async def serve(host: str, port: int, *, token: str, soul_path: str) -> None:
    app = build_app(token=token, soul_path=soul_path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("agent.listening", host=host, port=port, soul_path=soul_path)
    await asyncio.Event().wait()


def main() -> None:
    host = os.environ.get("AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("AGENT_PORT", "8650"))
    # Reuse the Hermes API key as the shared internal secret (no new secret).
    token = os.environ.get("API_SERVER_KEY", "")
    soul_path = os.environ.get("SOUL_PATH", "/opt/data/SOUL.md")
    log.info("agent.boot", host=host, port=port)
    asyncio.run(serve(host, port, token=token, soul_path=soul_path))


if __name__ == "__main__":
    main()
