"""The everyday-chat model preference store (JSON sidecar next to solilos.db)."""

from __future__ import annotations

import pytest

from solilos_chat import settings_store


def _db(tmp_path) -> str:
    return str(tmp_path / "solilos.db")


def test_default_is_thorough_when_unset(tmp_path):
    assert settings_store.get_other_model_pref(_db(tmp_path)) == "thorough"


def test_roundtrip_fast(tmp_path):
    db = _db(tmp_path)
    settings_store.set_other_model_pref(db, "fast")
    assert settings_store.get_other_model_pref(db) == "fast"


def test_roundtrip_thorough(tmp_path):
    db = _db(tmp_path)
    settings_store.set_other_model_pref(db, "thorough")
    assert settings_store.get_other_model_pref(db) == "thorough"


def test_invalid_persisted_value_falls_back_to_default(tmp_path):
    db = _db(tmp_path)
    (tmp_path / "app_settings.json").write_text('{"other_model_pref": "12b"}', "utf-8")
    assert settings_store.get_other_model_pref(db) == "thorough"


def test_set_rejects_invalid_value(tmp_path):
    with pytest.raises(ValueError):
        settings_store.set_other_model_pref(_db(tmp_path), "12b")
