"""Frontend-contract checks for the chat-header persona × speed dropdown (#278).

The separate Thinking (Aus/An) and Persona selectors are combined into ONE
dropdown whose entries pair each persona with a speed (schnell/Thinking),
mapping back to the unchanged payload.personality + payload.reasoning wiring.
It carries the #274 hide paths: hidden in the pinned "Zuhause" chat and in the
ServiceBay-admin embed. The Thema picker still omits the two system contexts.
The real check is the box-verify across the contexts; these lock the
markup/JS contract.
"""

from __future__ import annotations

import re

from solilos_chat.server import STATIC_DIR

_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def test_separate_reasoning_control_is_gone():
    # The standalone Thinking toggle and its select are removed; only the single
    # combined persona dropdown remains in the header.
    assert 'id="reasoning-control"' not in _HTML
    assert 'id="reasoning-mode"' not in _HTML
    assert 'id="persona-control"' in _HTML
    assert 'id="personality"' in _HTML


def test_dropdown_crosses_persona_with_speed():
    # Each persona is crossed with the two speeds; the option value packs
    # `<persona-id>|<reasoning>` and the label appends the German speed suffix.
    assert '{ suffix: "schnell", reasoning: "none" }' in _HTML
    assert '{ suffix: "Thinking", reasoning: "high" }' in _HTML
    assert 'opt.value = p.id + "|" + sp.reasoning;' in _HTML
    assert 'opt.textContent = p.label + " (" + sp.suffix + ")";' in _HTML


def test_selection_maps_back_to_persona_and_reasoning():
    # currentPersonality()/currentReasoning() unpack the combined value so the
    # backend personality + reasoning routing is unchanged.
    assert "function parsePersonaSpeed(v)" in _HTML
    assert (
        "function currentPersonality() { return parsePersonaSpeed(personalitySel.value).id; }"
        in _HTML
    )
    assert (
        "function currentReasoning() { return parsePersonaSpeed(personalitySel.value).reasoning; }"
        in _HTML
    )
    # The turn payload still sends both fields.
    assert "personality: currentPersonality(), reasoning: currentReasoning()" in _HTML


def test_household_hides_the_combined_control():
    # syncPinnedActive hides the single combined persona control (+ Thema) when
    # the household context is active — the #274 hide path on the new control.
    sync = re.search(
        r"function syncPinnedActive\(activeS\) \{(.*?)\n      \}", _HTML, re.S
    )
    assert sync, "syncPinnedActive not found"
    body = sync.group(1)
    assert "reasoningCtrl" not in body
    assert "personaCtrl.hidden = active" in body
    assert "topicCtrl.hidden = true" in body
    # Highlight stays selection-driven (no #262 always-highlight regression).
    assert 'householdBtn.classList.toggle("active", active)' in body


def test_thema_picker_omits_system_contexts():
    assert 'FIXED_CONTEXT_TOPICS = { household: 1, "servicebay-admin": 1 }' in _HTML
    # The option-building loop skips the fixed-context slugs.
    assert "if (FIXED_CONTEXT_TOPICS[t.slug]) return;" in _HTML


def test_embed_hides_persona_and_topic():
    rule = re.search(
        r"\.embed #persona-control,\s*\.embed #topic-control \{([^}]*)\}", _HTML
    )
    assert rule, "embed persona/topic hide rule missing"
    assert "display: none" in rule.group(1)


def test_chat_search_is_left_aligned():
    # The flex grow spacer now sits AFTER the search wrap, so the in-chat search
    # sits left (next to the title) instead of being pushed right (#280).
    search = _HTML.index('class="chat-search-wrap"')
    grow = _HTML.index('class="chat-head-grow"')
    assert search < grow


def test_household_chat_title_reads_zuhause():
    # In the household context the header title is "Zuhause", not the generic
    # "Neuer Chat" placeholder (#281), without breaking non-household derivation.
    sync = re.search(
        r"function syncPinnedActive\(activeS\) \{(.*?)\n      \}", _HTML, re.S
    )
    assert sync, "syncPinnedActive not found"
    body = sync.group(1)
    assert '"Zuhause"' in body
    assert (
        "topicsBySlug[HOUSEHOLD_TOPIC] && topicsBySlug[HOUSEHOLD_TOPIC].display_name"
        in body
    )
    # The plain renderSessions default for non-household chats is preserved.
    assert (
        'ct.textContent = (activeS && (activeS.title || activeS.preview)) || "Neuer Chat";'
        in _HTML
    )
