"""Tests for the per-turn reasoning-effort selection (#222)."""

from __future__ import annotations

import pytest

from gatekeeper import reasoning


@pytest.mark.parametrize(
    "text",
    [
        "welche Lichter sind an",
        "mach das Licht im Wohnzimmer aus",
        "wie spät ist es",
        "stell einen Timer auf zehn Minuten",
        "",
        "denke an die Einkaufsliste",  # "denk(e) an" is not a think-cue
    ],
)
def test_default_is_fast(text):
    assert reasoning.choose_effort(text) == reasoning.FAST
    assert reasoning.wants_reasoning(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "denk mal scharf nach",
        "Denke gründlich nach bitte",
        "erkläre mir das genau",
        "begründe das",
        "think it through",
        "think this carefully",
        "reason it through",
        "explain this in detail",
    ],
)
def test_explicit_cue_is_thorough(text):
    assert reasoning.choose_effort(text) == reasoning.THOROUGH
    assert reasoning.wants_reasoning(text) is True
