"""Tests for the topics store + the topic endpoints (#241)."""

from __future__ import annotations

import sqlite3

import pytest

from solilos_chat import topics_store
from solilos_chat.server import build_app

# The schema the 0004/0005 migrations create, replayed locally so the store and
# endpoint tests run against a real sqlite db without alembic.
_SCHEMA = """
CREATE TABLE topics (
  slug TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  parent TEXT,
  scope TEXT NOT NULL DEFAULT 'resident',
  owner_uid TEXT,
  default_model TEXT,
  default_persona TEXT,
  color TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE session_topics (
  session_id TEXT NOT NULL,
  topic_slug TEXT NOT NULL REFERENCES topics(slug),
  role TEXT NOT NULL DEFAULT 'secondary',
  owner_uid TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (session_id, topic_slug)
);
CREATE UNIQUE INDEX session_topics_one_primary_idx
  ON session_topics (session_id) WHERE role = 'primary';
CREATE INDEX session_topics_session_idx ON session_topics (session_id);
"""


def _db(tmp_path) -> str:
    path = str(tmp_path / "solilos.db")
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.executemany(
        "INSERT INTO topics (slug, display_name, scope, owner_uid, color) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("household", "Household", "shared", None, "#0052CC"),
            ("projekt/wintergarten", "Wintergarten", "resident", "mdopp", "#22aa55"),
            ("lenas-topic", "Lena", "resident", "lena", None),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_list_topics_scopes_to_resident(tmp_path):
    db = _db(tmp_path)
    slugs = {t["slug"] for t in topics_store.list_topics(db, "mdopp")}
    # mdopp sees shared (household) + own (wintergarten), not lena's resident one.
    assert slugs == {"household", "projekt/wintergarten"}


def test_list_topics_missing_db_is_empty(tmp_path):
    assert topics_store.list_topics(str(tmp_path / "nope.db"), "mdopp") == []


def test_set_primary_replaces_existing(tmp_path):
    db = _db(tmp_path)
    topics_store.set_primary(db, "sess-1", "household", "mdopp")
    topics_store.set_primary(db, "sess-1", "projekt/wintergarten", "mdopp")
    got = topics_store.get_session_topics(db, "sess-1", "mdopp")
    assert got == {"primary": "projekt/wintergarten", "secondary": []}


def test_only_one_primary_row_per_session(tmp_path):
    db = _db(tmp_path)
    topics_store.set_primary(db, "sess-1", "household", "mdopp")
    topics_store.set_primary(db, "sess-1", "projekt/wintergarten", "mdopp")
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM session_topics WHERE session_id='sess-1' AND role='primary'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_secondary_promote_to_primary_no_collision(tmp_path):
    db = _db(tmp_path)
    topics_store.add_secondary(db, "sess-1", "household", "mdopp")
    # Promoting a slug that is already a secondary tag must not hit the PK.
    topics_store.set_primary(db, "sess-1", "household", "mdopp")
    got = topics_store.get_session_topics(db, "sess-1", "mdopp")
    assert got == {"primary": "household", "secondary": []}


def test_add_and_remove_secondary(tmp_path):
    db = _db(tmp_path)
    topics_store.add_secondary(db, "sess-1", "household", "mdopp")
    topics_store.add_secondary(db, "sess-1", "household", "mdopp")  # idempotent
    topics_store.add_secondary(db, "sess-1", "projekt/wintergarten", "mdopp")
    got = topics_store.get_session_topics(db, "sess-1", "mdopp")
    assert got["primary"] is None
    assert got["secondary"] == ["household", "projekt/wintergarten"]
    topics_store.remove_topic(db, "sess-1", "household", "mdopp")
    assert topics_store.get_session_topics(db, "sess-1", "mdopp")["secondary"] == [
        "projekt/wintergarten"
    ]


def test_assignments_scoped_per_resident(tmp_path):
    db = _db(tmp_path)
    topics_store.set_primary(db, "sess-1", "household", "mdopp")
    # lena never sees mdopp's assignment on the same session id (D3).
    assert topics_store.get_session_topics(db, "sess-1", "lena") == {
        "primary": None,
        "secondary": [],
    }


def test_primary_topics_for_list(tmp_path):
    db = _db(tmp_path)
    topics_store.set_primary(db, "sess-1", "household", "mdopp")
    topics_store.add_secondary(db, "sess-2", "household", "mdopp")
    got = topics_store.primary_topics_for(db, ["sess-1", "sess-2", "sess-3"], "mdopp")
    assert got == {"sess-1": "household"}


# ---- Endpoint tests ----

from tests.test_server import _FakeHermes  # noqa: E402


async def test_topics_endpoint_lists_registry(aiohttp_client, tmp_path):
    db = _db(tmp_path)
    app = build_app(
        hermes=_FakeHermes(),
        remote_user_header="Remote-User",
        default_uid="household",
        solilos_db_path=db,
    )
    client = await aiohttp_client(app)
    resp = await client.get("/api/topics", headers={"Remote-User": "mdopp"})
    body = await resp.json()
    assert resp.status == 200
    slugs = {t["slug"] for t in body["topics"]}
    assert slugs == {"household", "projekt/wintergarten"}


async def test_session_topics_set_and_read(aiohttp_client, tmp_path):
    db = _db(tmp_path)
    app = build_app(
        hermes=_FakeHermes(),
        remote_user_header="Remote-User",
        default_uid="household",
        solilos_db_path=db,
    )
    client = await aiohttp_client(app)
    hdr = {"Remote-User": "mdopp"}
    resp = await client.post(
        "/api/sessions/sess-1/topics",
        json={"action": "primary", "slug": "household"},
        headers=hdr,
    )
    body = await resp.json()
    assert resp.status == 200
    assert body["primary"] == "household"
    resp = await client.post(
        "/api/sessions/sess-1/topics",
        json={"action": "add_secondary", "slug": "projekt/wintergarten"},
        headers=hdr,
    )
    body = await resp.json()
    assert body["secondary"] == ["projekt/wintergarten"]
    resp = await client.get("/api/sessions/sess-1/topics", headers=hdr)
    body = await resp.json()
    assert body["primary"] == "household"
    assert body["secondary"] == ["projekt/wintergarten"]


async def test_session_topics_invalid_action_rejected(aiohttp_client, tmp_path):
    db = _db(tmp_path)
    app = build_app(
        hermes=_FakeHermes(),
        remote_user_header="Remote-User",
        default_uid="household",
        solilos_db_path=db,
    )
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/sessions/sess-1/topics",
        json={"action": "bogus", "slug": "household"},
        headers={"Remote-User": "mdopp"},
    )
    assert resp.status == 400


@pytest.mark.parametrize("payload", [{"slug": ""}, {"action": "primary"}])
async def test_session_topics_empty_slug_rejected(aiohttp_client, tmp_path, payload):
    db = _db(tmp_path)
    app = build_app(
        hermes=_FakeHermes(),
        remote_user_header="Remote-User",
        default_uid="household",
        solilos_db_path=db,
    )
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/sessions/sess-1/topics",
        json=payload,
        headers={"Remote-User": "mdopp"},
    )
    assert resp.status == 400


async def test_session_list_annotates_primary_topic(aiohttp_client, tmp_path):
    from solilos_chat import marker

    db = _db(tmp_path)
    store = [
        {"id": "sess-1", "title": marker.marker_for("mdopp") + "A chat"},
        {"id": "sess-2", "title": marker.marker_for("mdopp") + "Another"},
    ]
    topics_store.set_primary(db, "sess-1", "household", "mdopp")
    app = build_app(
        hermes=_FakeHermes(store=store),
        remote_user_header="Remote-User",
        default_uid="household",
        solilos_db_path=db,
    )
    client = await aiohttp_client(app)
    resp = await client.get("/api/sessions", headers={"Remote-User": "mdopp"})
    body = await resp.json()
    by_id = {s["id"]: s for s in body["sessions"]}
    assert by_id["sess-1"]["primary_topic"] == "household"
    assert by_id["sess-2"]["primary_topic"] is None
