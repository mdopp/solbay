"""Tests for the instance-per-profile Hermes topology (#293b): the solilos Pod
runs one gateway container per profile — `hermes-household` (`-p household`) on
HERMES_API_PORT and `hermes-admin` (`-p admin`) on HERMES_ADMIN_API_PORT —
sharing the same volumes. Validates the template.yml as parseable YAML and the
new HERMES_ADMIN_API_PORT variable.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
import yaml

TEMPLATES = pathlib.Path(__file__).resolve().parents[1]
SOLILOS = TEMPLATES / "solilos"


@pytest.fixture(scope="module")
def raw_template() -> str:
    return (SOLILOS / "template.yml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pod(raw_template: str) -> dict:
    # ServiceBay substitutes {{VAR}} at deploy time; a bare `{{X}}` after a
    # colon is invalid YAML, so swap each placeholder for a scalar to parse.
    sub = re.sub(r"\{\{[A-Z0-9_]+\}\}", "PLACEHOLDER", raw_template)
    docs = list(yaml.safe_load_all(sub))
    return docs[0]


@pytest.fixture(scope="module")
def variables() -> dict:
    return json.loads((SOLILOS / "variables.json").read_text(encoding="utf-8"))


def _container(pod: dict, name: str) -> dict:
    for c in pod["spec"]["containers"]:
        if c["name"] == name:
            return c
    raise AssertionError(f"container {name!r} not found")


# ── the two gateway containers exist (and the placeholder is gone) ──────────


def test_both_gateway_containers_present(pod):
    names = {c["name"] for c in pod["spec"]["containers"]}
    assert "hermes-household" in names
    assert "hermes-admin" in names


def test_admin_soul_placeholder_retired(pod):
    names = {c["name"] for c in pod["spec"]["containers"]}
    assert "admin-soul" not in names


def test_single_hermes_container_replaced(pod):
    # The old single `hermes` container is gone — split into the two profiles.
    names = {c["name"] for c in pod["spec"]["containers"]}
    assert "hermes" not in names


# ── each gateway runs its own profile ───────────────────────────────────────


def test_household_runs_household_profile_gateway(pod):
    hh = _container(pod, "hermes-household")
    assert hh["args"] == ["-p", "household", "gateway", "run"]
    assert hh["image"] == "docker.io/nousresearch/hermes-agent:latest"


def test_admin_runs_admin_profile_gateway(pod):
    adm = _container(pod, "hermes-admin")
    assert adm["args"] == ["-p", "admin", "gateway", "run"]
    assert adm["image"] == "docker.io/nousresearch/hermes-agent:latest"


# ── distinct API ports; only household runs the dashboard ───────────────────


def test_gateways_bind_distinct_api_ports(raw_template):
    hh_block = raw_template.split("- name: hermes-household")[1].split(
        "- name: config-agent"
    )[0]
    adm_block = raw_template.split("- name: hermes-admin")[1]
    assert "{{HERMES_API_PORT}}" in hh_block
    assert "{{HERMES_ADMIN_API_PORT}}" in adm_block
    # The household port must not leak into the admin gateway env, nor vice
    # versa, or both gateways would race the same host port.
    assert "{{HERMES_ADMIN_API_PORT}}" not in hh_block
    assert "{{HERMES_API_PORT}}" not in adm_block


def test_only_household_runs_dashboard(raw_template):
    hh_block = raw_template.split("- name: hermes-household")[1].split(
        "- name: config-agent"
    )[0]
    adm_block = raw_template.split("- name: hermes-admin")[1]
    assert "name: HERMES_DASHBOARD" in hh_block
    assert "name: HERMES_DASHBOARD" not in adm_block


# ── both gateways share the same household data volumes ─────────────────────


def test_both_gateways_share_core_volumes(pod):
    shared = {"hermes-data", "syncthing-notes", "solilos-data"}
    for name in ("hermes-household", "hermes-admin"):
        mounts = {m["name"] for m in _container(pod, name)["volumeMounts"]}
        assert shared <= mounts, (name, sorted(mounts))


def test_admin_gateway_carries_ha_and_ollama_env(raw_template):
    adm_block = raw_template.split("- name: hermes-admin")[1]
    assert "HASS_URL" in adm_block
    assert "HASS_TOKEN" in adm_block
    assert "OPENAI_BASE_URL" in adm_block


# ── every mount resolves to a declared volume; no orphan volumes ────────────


def test_all_mounts_resolve_to_declared_volumes(pod):
    declared = {v["name"] for v in pod["spec"]["volumes"]}
    for c in pod["spec"].get("initContainers", []) + pod["spec"]["containers"]:
        for m in c.get("volumeMounts", []):
            assert m["name"] in declared, (c["name"], m["name"])


# ── the new admin-API-port variable + the ports annotation ──────────────────


def test_admin_api_port_variable_defined(variables):
    assert "HERMES_ADMIN_API_PORT" in variables
    assert variables["HERMES_ADMIN_API_PORT"]["default"] == "8643"


def test_admin_api_port_distinct_from_household(variables):
    assert (
        variables["HERMES_ADMIN_API_PORT"]["default"]
        != variables["HERMES_API_PORT"]["default"]
    )


def test_ports_annotation_raw_lists_admin_port(raw_template):
    ann = raw_template.split("servicebay.ports:")[1].splitlines()[0]
    assert "{{HERMES_ADMIN_API_PORT}}" in ann
    assert "{{HERMES_API_PORT}}" in ann


def test_admin_soul_image_variable_removed(variables):
    # The busybox placeholder image is no longer referenced — its wizard var is
    # gone so the operator isn't prompted for a now-unused image.
    assert "ADMIN_SOUL_IMAGE" not in variables
