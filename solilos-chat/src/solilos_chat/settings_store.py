"""Tiny persisted app-settings store (JSON sidecar next to solilos.db).

The only setting today is the **non-household model preference** (#332-followup):
which of the two gateway-backed models everyday (non-household) chats route to —
`"fast"` (e2b, the household gateway) or `"thorough"` (12b, the sol-deep
gateway). It is a routing toggle, not a Hermes config rewrite, so it lives here
rather than in `config.yaml`: the chat server owns it and reads it per turn.

It rides a JSON file beside `solilos.db` (the same persistent writable volume
`topics_store` uses) so no schema migration is needed. The chat server caches
the value in memory and treats this file as the restart-survival source.
"""

from __future__ import annotations

import json
from pathlib import Path

_VALID = ("fast", "thorough")
DEFAULT_PREF = "thorough"
_KEY = "other_model_pref"


def _path(db_path: str) -> Path:
    return Path(db_path).parent / "app_settings.json"


def get_other_model_pref(db_path: str) -> str:
    """The everyday-chat model preference; `DEFAULT_PREF` when unset/invalid."""
    try:
        data = json.loads(_path(db_path).read_text("utf-8"))
    except (OSError, ValueError):
        return DEFAULT_PREF
    value = data.get(_KEY) if isinstance(data, dict) else None
    return value if value in _VALID else DEFAULT_PREF


def set_other_model_pref(db_path: str, value: str) -> None:
    """Persist the everyday-chat model preference. Raises ValueError on a bad
    value (callers validate first, so this is a guard, not a code path)."""
    if value not in _VALID:
        raise ValueError(f"other_model_pref must be one of {_VALID}, got {value!r}")
    p = _path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({_KEY: value}), "utf-8")
