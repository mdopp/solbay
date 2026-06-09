"""Tests for the multi-profile Hermes provisioning (#293a).

provision_profiles creates + configures a `household` and an `admin` Hermes
profile. Each profile gets its own config.yaml (ollama model+providers, the
box-confirmed recipe that avoids the openrouter 401), a `.no-bundled-skills`
marker (drops the 105-skill bundled catalog), its SOUL.md, and its own
mcp_servers block (household: servicebay-mcp + gatekeeper-mcp only; admin:
servicebay_admin + servicebay-mcp).

The hyphenated post-deploy.py is loaded via importlib (same pattern as the
sibling token tests); no live ServiceBay / hermes container is touched —
profile_create and the MCP-token mints are monkeypatched so the render runs
offline against a temp data dir.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

TEMPLATES = pathlib.Path(__file__).resolve().parents[1]

GOOD = "sb_0a1b2c3d_ABCDEF234567"
ADMIN = "sb_cccccccc_DDDD234567"

HOUSEHOLD_SERVERS = [
    ("servicebay-mcp", "http://127.0.0.1:5888/mcp", GOOD),
    ("gatekeeper-mcp", "http://127.0.0.1:10760/mcp", ""),
]
ADMIN_SERVERS = [
    ("servicebay_admin", "http://127.0.0.1:5888/mcp", ADMIN),
    ("servicebay-mcp", "http://127.0.0.1:5888/mcp", GOOD),
]

PROVIDER_URL = "http://127.0.0.1:11434/v1"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pd():
    return _load("solilos_post_deploy", TEMPLATES / "solilos" / "post-deploy.py")


# ── render_ollama_model_block: the load-bearing recipe ──────────────────────


def test_model_block_declares_ollama_provider(pd):
    block = pd.render_ollama_model_block(PROVIDER_URL, "gemma4:e2b")
    assert "model:\n" in block
    assert "  provider: ollama\n" in block
    assert "  model: gemma4:e2b\n" in block
    # The box-confirmed anti-401 recipe: an explicit providers.ollama with the
    # api URL + a (dummy) api_key. Without it the profile 401s on openrouter.
    assert "providers:\n" in block
    assert "  ollama:\n" in block
    assert f"    api: {PROVIDER_URL}\n" in block
    assert '    api_key: "ollama"\n' in block
    # No custom/openrouter provider leaks in.
    assert "provider: custom" not in block
    assert "openrouter" not in block


def test_profile_config_has_household_mcp_and_no_admin(pd):
    content = pd.render_profile_config_yaml(
        PROVIDER_URL, "gemma4:e2b", HOUSEHOLD_SERVERS
    )
    assert "  provider: ollama\n" in content
    assert "  model: gemma4:e2b\n" in content
    assert "servicebay-mcp:" in content
    assert "gatekeeper-mcp:" in content
    assert "servicebay_admin" not in content
    # cronjob load-bearing; kanban trimmed.
    assert "    - kanban\n" in content
    assert "    - cronjob\n" not in content


def test_profile_config_admin_carries_admin_mcp(pd):
    content = pd.render_profile_config_yaml(PROVIDER_URL, "gemma4:12b", ADMIN_SERVERS)
    assert "  model: gemma4:12b\n" in content
    assert "servicebay_admin:" in content
    assert f"Bearer {ADMIN}" in content
    assert "servicebay-mcp:" in content


# ── .no-bundled-skills marker ───────────────────────────────────────────────


def test_writes_no_bundled_skills_marker(pd, tmp_path):
    profile_dir = tmp_path / "household"
    assert pd.write_no_bundled_skills_marker(str(profile_dir)) is True
    assert (profile_dir / ".no-bundled-skills").exists()
    # Idempotent on a second run.
    assert pd.write_no_bundled_skills_marker(str(profile_dir)) is False


# ── per-profile SOUL.md (sidecar-hash guard, #283) ──────────────────────────


def test_profile_soul_installed_then_preserved_when_edited(pd, tmp_path):
    profile_dir = tmp_path / "household"
    profile_dir.mkdir()
    source = TEMPLATES / "solilos" / "SOUL.md"
    shipped = source.read_text(encoding="utf-8")
    assert pd.write_profile_soul(str(profile_dir), str(source)) is True
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == shipped
    # An operator edit afterwards is preserved across a redeploy.
    edited = "# Our House\n\nhand-tuned\n"
    (profile_dir / "SOUL.md").write_text(edited, encoding="utf-8")
    assert pd.write_profile_soul(str(profile_dir), str(source)) is False
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == edited


# ── provision_profiles: the full per-profile build ──────────────────────────


def test_provision_profiles_builds_both(pd, tmp_path, monkeypatch):
    created: list[str] = []
    monkeypatch.setattr(
        pd, "hermes_profile_create", lambda p: created.append(p) or True
    )
    monkeypatch.setattr(pd, "household_mcp_servers", lambda: HOUSEHOLD_SERVERS)
    monkeypatch.setattr(pd, "admin_mcp_servers", lambda: ADMIN_SERVERS)

    pd.provision_profiles(str(tmp_path), PROVIDER_URL)

    assert created == ["household", "admin"]
    profiles = tmp_path / "hermes" / "profiles"

    hh = profiles / "household"
    hh_cfg = (hh / "config.yaml").read_text(encoding="utf-8")
    assert "  provider: ollama\n" in hh_cfg
    assert "  model: gemma4:e2b\n" in hh_cfg
    assert f"    api: {PROVIDER_URL}\n" in hh_cfg
    assert "servicebay-mcp:" in hh_cfg
    assert "gatekeeper-mcp:" in hh_cfg
    assert "servicebay_admin" not in hh_cfg
    assert (hh / ".no-bundled-skills").exists()
    assert (hh / "SOUL.md").read_text(encoding="utf-8").startswith("# Solilos")

    adm = profiles / "admin"
    adm_cfg = (adm / "config.yaml").read_text(encoding="utf-8")
    assert "  model: gemma4:12b\n" in adm_cfg
    assert "servicebay_admin:" in adm_cfg
    assert "servicebay-mcp:" in adm_cfg
    assert (adm / ".no-bundled-skills").exists()
    # The admin profile gets the operator soul, not the household one.
    assert "operator" in (adm / "SOUL.md").read_text(encoding="utf-8").lower()


def test_provision_profiles_env_overrides_models(pd, tmp_path, monkeypatch):
    monkeypatch.setattr(pd, "hermes_profile_create", lambda p: True)
    monkeypatch.setattr(pd, "household_mcp_servers", lambda: [])
    monkeypatch.setattr(pd, "admin_mcp_servers", lambda: [])
    monkeypatch.setenv("HOUSEHOLD_PROFILE_MODEL", "gemma4:custom-hh")
    monkeypatch.setenv("ADMIN_PROFILE_MODEL", "gemma4:custom-adm")

    pd.provision_profiles(str(tmp_path), PROVIDER_URL)

    profiles = tmp_path / "hermes" / "profiles"
    assert "  model: gemma4:custom-hh\n" in (
        profiles / "household" / "config.yaml"
    ).read_text(encoding="utf-8")
    assert "  model: gemma4:custom-adm\n" in (
        profiles / "admin" / "config.yaml"
    ).read_text(encoding="utf-8")


def test_household_mcp_excludes_admin(pd, monkeypatch):
    """household_mcp_servers reuses collect_mcp_servers, which never emits the
    operator servicebay_admin entry."""
    monkeypatch.setattr(pd, "collect_mcp_servers", lambda: HOUSEHOLD_SERVERS)
    servers = pd.household_mcp_servers()
    names = [name for name, _, _ in servers]
    assert "servicebay_admin" not in names
    assert "servicebay-mcp" in names
    assert "gatekeeper-mcp" in names
