# autoloop-issues (OSCAR) — how to run

Works the `mdopp/oscar` backlog. OSCAR is a bundle of ServiceBay artifacts (templates, Hermes skills, the `voice-gatekeeper` Python service, the `database` schema-init, the Hermes plugin) that runs **on ServiceBay** at `<SERVICEBAY_BOX>`. Real-box `/verify` and end-to-end checks deploy OSCAR through ServiceBay onto that box.

## One-shot (single invocation, up to 8 PRs)

```
/autoloop-issues
```

## Self-paced loop (recommended)

```
/loop /autoloop-issues
```

`/loop` re-fires the skill; `.claude/state/autoloop-state.json` keeps progress between firings.

## Stop / reset

- Stop: interrupt the session. State persists; the next run resumes from `in_progress`.
- Reset: `rm .claude/state/autoloop-state.json` (a fresh file is created next run).

## What's different from the ServiceBay copy

- **Repo/labels**: `mdopp/oscar` with labels `skill`, `template`, `infrastructure`, `phase-0/1`, `enhancement`, `bug`, `documentation`.
- **No release-please**: releases are cut by pushing a `v*` tag (the loop never tags/bumps).
- **CI is image-builds only** (`build-images.yml`) and only fires for `voice-gatekeeper/**` / `database/**` changes — **template-only / skill-only PRs have no CI**, so `/verify` is their gate.
- **Local gates**: pytest for `voice-gatekeeper` (`pip install -e '.[test]' && pytest`); YAML/frontmatter validation for templates/skills. No ESLint/tsc.
- **/verify deploys through ServiceBay** onto `<SERVICEBAY_BOX>` (same box, same access as ServiceBay's autoloop) and checks the OSCAR runtime (pods healthy, skills loaded, gatekeeper connected, schema migrated).
- **Cross-repo routing**: a defect found during `/verify` or end-to-end may be a **ServiceBay-platform** bug, not an OSCAR bug. The loop files those in `mdopp/servicebay` (it can't fix the platform from this repo), marks the OSCAR item `blocked` `"waiting on mdopp/servicebay#N"`, and waits.
- **End-to-end goal**: track (d) / the "does OSCAR work within the ServiceBay install?" section is the loop's ultimate check — a green E2E with an empty queue is the clean place to stop.

## When NOT to run

- Another session is editing files here.
- You're mid-incident on the box.
- You haven't reviewed the first few autonomous PRs yet — let humans review before going fully autonomous.
