"""Client for Hermes' native session API.

Contract (the real Hermes API, port 8642, Bearer `API_SERVER_KEY`):
  - `POST /api/sessions`            -> create a session, returns `{"id": ...}`
  - `POST /api/sessions/{id}/chat`  -> body `{"input": ...}`, reply in
    `{"message": {"content": ...}}`

The gatekeeper owns one Hermes session per conversation (keyed by the uid or
the originating satellite) for real continuity across turns; an expired
session (404) is recreated once and the turn retried.
"""

from __future__ import annotations

from typing import Any

import httpx
from gatekeeper.logging import log


class HermesClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._sessions: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def converse(
        self,
        *,
        text: str,
        uid: str,
        endpoint: str,
        trace_id: str,
        location: str | None = None,
    ) -> str:
        conv_key = uid or endpoint
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            session_id = self._sessions.get(conv_key)
            if session_id is None:
                session_id = await self._create_session(client, uid, trace_id)
                if not session_id:
                    return ""
                self._sessions[conv_key] = session_id

            response = await self._chat(client, session_id, text)
            if response is not None and response.status_code == 404:
                # Session expired upstream — recreate once and retry the turn.
                session_id = await self._create_session(client, uid, trace_id)
                if not session_id:
                    self._sessions.pop(conv_key, None)
                    return ""
                self._sessions[conv_key] = session_id
                response = await self._chat(client, session_id, text)

            if response is None:
                return ""
            if response.status_code >= 400:
                log.error(
                    "gatekeeper.hermes.error",
                    trace_id=trace_id,
                    status=response.status_code,
                    body=response.text[:500],
                )
                return ""
            return _extract_reply(response.json())

    async def _create_session(
        self, client: httpx.AsyncClient, uid: str, trace_id: str
    ) -> str:
        url = f"{self._base_url}/api/sessions"
        response = await client.post(
            url, json={"user_id": uid}, headers=self._headers()
        )
        if response.status_code >= 400:
            log.error(
                "gatekeeper.hermes.error",
                trace_id=trace_id,
                status=response.status_code,
                body=response.text[:500],
            )
            return ""
        return _extract_session_id(response.json())

    async def _chat(
        self, client: httpx.AsyncClient, session_id: str, text: str
    ) -> httpx.Response:
        url = f"{self._base_url}/api/sessions/{session_id}/chat"
        return await client.post(url, json={"input": text}, headers=self._headers())


def _extract_session_id(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    session = body.get("session") if isinstance(body.get("session"), dict) else body
    return str(session.get("id") or session.get("session_id") or "")


def _extract_reply(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    msg = body.get("message")
    if isinstance(msg, dict):
        content = msg.get("content") or ""
        if content:
            return str(content)
    return str(
        body.get("output")
        or body.get("reply")
        or body.get("response")
        or body.get("text")
        or ""
    )
