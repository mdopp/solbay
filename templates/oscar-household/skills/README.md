# OSCAR skills

Household-specific skills consumed by [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Hermes provides the agent loop, skill registry, cron, messaging gateways, and the self-improvement loop natively. OSCAR contributes only the **household-specific** procedures tied to *our* SQLite schema (`oscar.db`) or *our* policy choices (cloud audit).

The `oscar-household` ServiceBay template bind-mounts this directory into the Hermes container at `/opt/data/skills/oscar`, alongside the path to `oscar.db`. Hermes loads everything here on startup.

## Currently registered skills

| Directory | `name:` | Phase | One-liner |
|---|---|---|---|
| `status/` | `oscar-status` | 0 | Pings every OSCAR dependency (`oscar.db`, Hermes, Ollama, Home Assistant, ServiceBay-MCP; voice probes once Phase 1 voice is deployed) and returns per-component status. Read-only. |
| `audit-query/` | `oscar-audit-query` | 0 | Read-only query over `cloud_audit` (and future Phase-3a household-domain tables) in `oscar.db`. |
| `debug-set/` | `oscar-debug-set` | 0 | Admin: toggle `system_settings.debug_mode` row in `oscar.db` (verbose logging on demand, TTL-bounded). |

All three operate directly against `oscar.db` (inline SQLite) and ServiceBay-MCP (`get_health_checks`/`diagnose`) — no external `oscar_*` libraries or separate companion scripts.

## What's *not* a skill in OSCAR

| Capability | Lives in |
|---|---|
| Lights / heating / scenes | Hermes Skills Hub — `smart-home/home-assistant` skill (PR'd from OSCAR's removed `light/`) |
| Help (`/skills`, `/help`) | Hermes native |
| Timers / alarms / reminders / recurring tasks | Hermes cron |
| Skill management, authorship, review, revert | Hermes' built-in skill management + self-improvement loop |
| Messaging-gateway pairing, identity-link | Hermes' messaging-gateway pairing |

Context: [`../oscar-architecture.md`](../oscar-architecture.md).
