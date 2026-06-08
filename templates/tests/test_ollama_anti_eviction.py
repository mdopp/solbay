"""Tests for the ollama anti-eviction config (#268): OLLAMA_MAX_LOADED_MODELS=1
and OLLAMA_KEEP_ALIVE=24h, wired on both the variables.json defaults and the
GPU `.container` Quadlet render path.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

TEMPLATES = pathlib.Path(__file__).resolve().parents[1]
OLLAMA = TEMPLATES / "ollama"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def variables():
    return json.loads((OLLAMA / "variables.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ollama_pd():
    return _load("ollama_post_deploy", OLLAMA / "post-deploy.py")


# ── variables.json defaults ───────────────────────────────────────────────


def test_max_loaded_models_default_is_one(variables):
    assert variables["OLLAMA_MAX_LOADED_MODELS"]["default"] == "1"


def test_keep_alive_default_is_24h(variables):
    assert variables["OLLAMA_KEEP_ALIVE"]["default"] == "24h"


# ── template.yml env wiring ───────────────────────────────────────────────


def test_template_yml_wires_max_loaded_models():
    tmpl = (OLLAMA / "template.yml").read_text(encoding="utf-8")
    assert "name: OLLAMA_MAX_LOADED_MODELS" in tmpl
    assert "{{OLLAMA_MAX_LOADED_MODELS}}" in tmpl
    assert "name: OLLAMA_KEEP_ALIVE" in tmpl


# ── GPU .container render path parity ─────────────────────────────────────


def test_gpu_unit_carries_max_loaded_models_and_24h(ollama_pd, monkeypatch):
    # No env set → the render path falls back to the new defaults.
    monkeypatch.delenv("OLLAMA_MAX_LOADED_MODELS", raising=False)
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    unit = ollama_pd.render_gpu_container_unit("11434", "/mnt/data/stacks")
    assert "Environment=OLLAMA_MAX_LOADED_MODELS=1" in unit
    assert "Environment=OLLAMA_KEEP_ALIVE=24h" in unit


def test_gpu_unit_honors_env_overrides(ollama_pd, monkeypatch):
    monkeypatch.setenv("OLLAMA_MAX_LOADED_MODELS", "2")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "60m")
    unit = ollama_pd.render_gpu_container_unit("11434", "/mnt/data/stacks")
    assert "Environment=OLLAMA_MAX_LOADED_MODELS=2" in unit
    assert "Environment=OLLAMA_KEEP_ALIVE=60m" in unit
