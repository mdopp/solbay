"""Voice-enrolment tool — wraps the gatekeeper's `POST /enrol`.

The onboarding dialog (#354) collects N spoken samples from a new resident
and calls this to register their voice profile: it POSTs the uid + base64
PCM samples to the gatekeeper's enrolment endpoint, which averages the ECAPA
embeddings and upserts `voice_embeddings`. This module is only the accessor;
sample capture and the dialog live elsewhere.

Biometric care: the samples are raw voice (a biometric identifier), so they
never appear in the returned result or any log line — only the uid, sample
count and the gatekeeper's ok/reason are surfaced. Enrolment failures are
returned verbatim (never swallowed into a false success) so the dialog can
react. This is an onboarding/admin accessor, not a guest- or household-
callable tool — see profiles.py for which toolset it joins.
"""

from __future__ import annotations

import json
import re
from typing import Any

import aiohttp

from solilos_chat.engine.tools import Tool

# Same uid shape the gatekeeper's /enrol enforces — validate before the call so
# a malformed uid is a clear local error, not an opaque 400.
_UID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_TIMEOUT = aiohttp.ClientTimeout(total=30)


def build_enrol_tools(gatekeeper_url: str, gatekeeper_token: str = "") -> list[Tool]:
    base = gatekeeper_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if gatekeeper_token:
        headers["Authorization"] = f"Bearer {gatekeeper_token}"

    async def enrol(args: dict[str, Any]) -> str:
        uid = str(args.get("uid") or "").strip()
        if not _UID_RE.match(uid):
            return json.dumps({"ok": False, "reason": "invalid_uid"})
        samples = args.get("samples")
        if not isinstance(samples, list) or not samples:
            return json.dumps({"ok": False, "reason": "missing_samples"})

        async with aiohttp.ClientSession(timeout=_TIMEOUT) as client:
            async with client.post(
                f"{base}/enrol",
                json={"uid": uid, "samples": samples},
                headers=headers,
            ) as resp:
                # The gatekeeper returns {"ok": bool, "reason": ...}; pass its
                # verdict through unchanged on both success and failure so the
                # dialog never reads a false success.
                try:
                    body = await resp.json()
                except aiohttp.ContentTypeError:
                    return json.dumps(
                        {"ok": False, "reason": f"gatekeeper_http_{resp.status}"}
                    )
        return json.dumps(body, ensure_ascii=False)

    return [
        Tool(
            name="voice_enrol",
            description=(
                "Registriert ein Sprachprofil für eine Bewohner-uid beim"
                " Gatekeeper (Onboarding). samples = base64-PCM-Aufnahmen."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "uid": {"type": "string"},
                    "samples": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "base64 16kHz mono int16 PCM samples",
                    },
                },
                "required": ["uid", "samples"],
            },
            handler=enrol,
        ),
    ]
