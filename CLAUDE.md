# CLAUDE.md — briefing for agent sessions in this repo

You are operating Brian Fisher's AntCat pipeline toolkit on his Mac. Read
`WORKFLOW.md` before acting; for the Bolton NGC cycle read
`bolton/BOLTON_SYNC_RUNBOOK.md`. Those runbooks are the process — this file
is the rules of engagement.

## What you can reach

- **This Mac**: python3 (miniconda), git (push credentials in the keychain),
  the repo at `~/antcat/antcat-pipelines`, data in `~/antcat/taxonworks_sync/`
  and `~/antcat/snapshots/`.
- **The AntCat droplet**: `ssh antcat` (alias in Brian's ssh config). This is
  the PRODUCTION server for antcat.org. Real researchers depend on it.

## Hard rules

1. **Droplet is production.** Read-only by default. The only routine write is
   `export_references.rb` producing its CSV (Stage 1 of WORKFLOW.md). Anything
   beyond that requires Brian's explicit in-session go AND the staged gates:
   DigitalOcean snapshot → dry-run → single canary verified in the live UI →
   ~10-row batch verified → full run. No step skipped, ever.
2. **Show every droplet command before running it.** Never chain a droplet
   write behind an && where it executes without being seen.
3. **Verification gates are stop points.** Stage 2 must print `RESULT: PASS`
   and `join ... 100.00%`; Stage 3 must show 0 duplicate taxon_name_ids and
   near-100% agreement with the prior validated file, with every disagreement
   inspected row-by-row. A failed gate means stop and diagnose — never
   hand-patch outputs, never proceed on "close enough". Plausible counts are
   not validated counts.
4. **Data never enters git.** `.gitignore` enforces it; don't fight it. Data
   goes to `~/antcat/taxonworks_sync/`, snapshots to `~/antcat/snapshots/` as
   dated zips with `MANIFEST.sha256` (recipe in the snapshot CHANGELOGs).
5. **No secrets anywhere** — not in commits, not echoed to the transcript.
   Tokens come from env vars. This repo is public.
6. **Commit style**: small, verified, one concern per commit; message says
   what and why. Push after each verified unit of work. **Before any commit,
   `bash smoke.sh` from the repo root must print SMOKE PASS** — it catches
   truncated files and regressions of the hard-won fixes.
7. **Detached-script provenance**: whenever a script is copied to a server
   (docker cp, curl from raw, scp), record in the session log the commit it
   came from (`git rev-parse --short HEAD`) and the file's md5 — a script
   running off-repo must always be traceable to the exact version.
8. **When Brian gives an instruction that conflicts with a runbook, say so
   before acting** — the runbooks encode hard-won failures (DOI page leak,
   append-ordering bug, wrong-terminal executions). Don't silently override
   them, and don't silently obey either.

## Session pattern

Start: `git pull`, `pip install -r requirements.txt` if the smoke env check
warns, read WORKFLOW.md, state which stage you're executing. Before pairing
or attaching any data inputs: `bash data_currency.sh` — it lists what exists
with age and md5 and enforces the same-moment rule on the newest dump/CSV pair.
End: summarize what ran, what was verified, what changed on disk and in git,
and what the next session should pick up. If the session touched process
knowledge, update WORKFLOW.md or the relevant runbook in the same session and
commit it — future sessions only know what's written down.

## Sandbox quirks

Agent sandboxes run with `PYTHONSAFEPATH=1`, which strips the current
directory from `sys.path` — repo-root imports (`import protonym`) fail there
unless you run `PYTHONPATH=. python3 ...`. Also, the agent's `python3` is its
own sandbox environment, not Brian's miniconda: an import that works (or
fails) for the agent says the module is sound, not that Brian's interpreter is
configured the same way.

## Context

Deeper background (infrastructure details, open items, decision history)
lives in Brian's AntCat Claude project knowledge, deliberately NOT in this
public repo. If you need it, ask Brian rather than guessing.
