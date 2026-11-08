# history_order/

Canonical order of history lines on AntCat protonym pages, derived from production and accepted by Brian on 2026-11-07. Brian's project notes: `claude/HISTORY_ORDER.md`.

## Files

| File | Where it runs | Writes? | Purpose |
|---|---|---|---|
| `history_census.rb` | server | no | Counts history items by kind, and how many are convertible to structured items. |
| `history_order_check.rb` | server | no | Prints pages that already have structured items, in the order the catalog renders them. |
| `history_lines_export.rb` | server | no | Exports every history item (protonym, position, type, text start) to `tmp/history_lines.tsv`. |
| `history_order_classify.py` | Mac | no | Classifies each line into a kind. Reads `/tmp/ho/lines.tsv`, writes `/tmp/ho/rows.json`. |
| `history_order_derive.py` | Mac | no | Derives the order of kinds and its strength. Argument: `species-group`, `genus-group` or `family-group`. |
| `history_order_fixes.py` | Mac | no | Splits order violations into script-fixable pages and pages for review. |
| `reorder_history_by_kind.rb` | server | MODE=write | Reorders pages from `tmp/history_reorder_approved.tsv` with AntCat's own reorder operation. MODE=check by default; ONLY=protonym ids; REVERSE=1 rolls back with the same file. |

The Python scripts use fixed paths under `/tmp/ho/`; copy the export there first (`cp history_lines_<date>.tsv /tmp/ho/lines.tsv`).

## How to run

Server scripts go in `/var/www/antcat-2/tmp/` and run as `antcat` inside the app container:

```
docker exec -u antcat -w /app -e RAILS_ENV=production [-e MODE=...] antcat-app bundle exec rails runner tmp/<script>.rb
```

Writes: dump the database first (the droplet snapshot does not cover the database volume), check mode, staging write plus REVERSE test, production canary, then the full run.

## First run (2026-11-07)

Species-group: 96.7% of pairwise observations agree with the order. 74 pages broke a strong rule: 47 reordered by script (request_uuid a7a77289-7905-4e5b-b4c0-10b172c8c5c9, canary c81fabc5-70e3-4525-8649-b189d2afcacb), 27 sent for manual review. Data stays out of git.
