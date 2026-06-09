"""HermesClient.create_session title-collision retry (#301).

Hermes enforces globally-unique session titles, so two household chats whose
first message is the same text (e.g. "Welche Lichter sind an?") would 400 "title
already in use" — a real resident-facing "(no reply)". create_session retries
with a unique suffix appended after the human title (the marker prefix stays
anchored).
"""

from __future__ import annotations

import json
from unittest.mock import patch

from solilos_chat import marker
from solilos_chat.hermes import HermesClient, HermesError


class _Resp:
    def __init__(self, status: int, text: str):
        self._status = status
        self._text = text

    @property
    def status(self) -> int:
        return self._status

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Sess:
    """Stand-in for aiohttp.ClientSession that hands out queued responses and
    records each posted payload."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posted: list[dict] = []

    def post(self, url, json=None, headers=None):
        self.posted.append(json)
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _collision(title: str) -> _Resp:
    return _Resp(
        400,
        json.dumps(
            {
                "error": {
                    "message": f"Title '{title}' is already in use by session api_1",
                    "code": "invalid_title",
                }
            }
        ),
    )


async def test_create_session_retries_on_title_collision():
    sess = _Sess(
        [_collision("[uid] Welche Lichter sind an?"), _Resp(200, '{"id": "s2"}')]
    )
    with patch("solilos_chat.hermes.aiohttp.ClientSession", return_value=sess):
        client = HermesClient("http://hermes", "key")
        sid = await client.create_session("mdopp", title="Welche Lichter sind an?")
    assert sid == "s2"
    # First attempt = plain embedded title; the retry disambiguates it but keeps
    # the human text and the uid marker prefix.
    t0, t1 = sess.posted[0]["title"], sess.posted[1]["title"]
    assert t0 != t1
    assert "Welche Lichter sind an?" in t1
    assert t1.startswith(marker.marker_for("mdopp"))


async def test_create_session_no_retry_when_unique():
    sess = _Sess([_Resp(200, '{"id": "s1"}')])
    with patch("solilos_chat.hermes.aiohttp.ClientSession", return_value=sess):
        client = HermesClient("http://hermes", "key")
        sid = await client.create_session("mdopp", title="Hallo")
    assert sid == "s1"
    assert len(sess.posted) == 1  # no retry on the happy path
    assert sess.posted[0]["title"] == marker.embed("mdopp", "Hallo")


async def test_create_session_raises_after_unresolved_collisions():
    sess = _Sess([_collision("t"), _collision("t"), _collision("t")])
    with patch("solilos_chat.hermes.aiohttp.ClientSession", return_value=sess):
        client = HermesClient("http://hermes", "key")
        try:
            await client.create_session("mdopp", title="x")
            raise AssertionError("expected HermesError")
        except HermesError:
            pass
    assert len(sess.posted) == 3  # bounded retries
