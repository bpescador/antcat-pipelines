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
| `status_block_survey.rb` | server | no | Sizes the free-text status block (Status as species, Junior/Senior synonym of, Subspecies of): formats, tags, date order, merge risk. |
| `status_block_survey2.rb` | server | no | Subspecies of `{tax}` tags vs terminal taxa; year inversions vs same-year order. |
| `status_block_survey3.rb` | server | no | Same-year citation pairs and reference dates (superseded: compares dates as numbers, which misorders mixed precision). |
| `reference_dates_survey.rb` | server | no | Reference publication dates: precision, gaps, nested references, undated references cited in history. |
| `convert_status_block.rb` | server | MODE=write | Converts the status block to StatusAsSpecies, JuniorSynonymOf, SeniorSynonymOf, SubspeciesOf (one item per citation). Predicts the page and keeps a protonym only if the converted page equals the prediction. Needs AntCat #1591 and #1593. KINDS, ONLY, LIMIT. One activity per protonym. |
| `convert_forms_and_types.rb` | server | MODE=write | Same method for form descriptions (FormDescriptions) and single-citation lectotype/neotype designations (TypeSpecimenDesignation). |
| `small_kinds_survey.rb` | server | no | Sizes junior primary/secondary homonym, replacement name (both directions) and unavailable name lines; tags; the cross-page effect of Replacement name for trailers. |
| `convert_small_kinds.rb` | server | MODE=write | Converts those kinds, one item per line, in two passes: KINDS=homonyms,replaced_by,unavailable first, then KINDS=replacement_for (its trailer is generated from the replaced name's structured homonym items and must show the same names, or the same names plus their citation). {prottac P} becomes {taxac T}, T the terminal taxon. |
| `nested_in_citations.rb` | server | MODE=write | Rewrites "Author, in {ref P}: pages" as "{ref N}: pages" where exactly one nested reference under P has that author and the pages; lists the rest for an editor. |

The Python scripts use fixed paths under `/tmp/ho/`; copy the export there first (`cp history_lines_<date>.tsv /tmp/ho/lines.tsv`).

## How to run

Server scripts go in `/var/www/antcat-2/tmp/` and run as `antcat` inside the app container:

```
docker exec -u antcat -w /app -e RAILS_ENV=production [-e MODE=...] antcat-app bundle exec rails runner tmp/<script>.rb
```

Writes: dump the database first (the droplet snapshot does not cover the database volume), check mode, staging write plus REVERSE test, production canary, then the full run.

## First run (2026-11-07)

Species-group: 96.7% of pairwise observations agree with the order. 74 pages broke a strong rule: 47 reordered by script (request_uuid a7a77289-7905-4e5b-b4c0-10b172c8c5c9, canary c81fabc5-70e3-4525-8649-b189d2afcacb), 27 sent for manual review. Data stays out of git.

## Same-year order and the status block (2026-11-07 and 08)

Citations within one reference year keep the editors' order (Brian; AntCat #1593). Reference dates are often missing (1,868 of 13,043) or imprecise (YYYY, YYYYMM), so they cannot decide. Status block on production 2026-11-08: check 61cdd26e (18,165 identical, 837 full stop, 207 year order fixed, 240 held, 0 errors), canary 5697ad09, full run started 09:00. Runner notes: set `ActiveRecord::Base.logger = nil`; long runs with `setsid nohup ... &`; Ctrl-C does not stop `docker exec` without `-t` (kill the PID on the host).

## Small kinds (2026-11-08)

Production: dump `antcat-manual-pre-small-kinds-20261108-1240`; pass 1 check a2d14d21, canary 5f499882 (154759, 154924), write 146e5347: 416 converted, 779 lines. Pass 2 check 70ecaaa6, write a77cf2e1: 319 converted (267 identical, 52 trailer citation added, Brian: "allow group A"); after comparing trailers as displayed, write 45760b8e: 30 more. Items now: JuniorPrimaryHomonymOf 244, JuniorSecondaryHomonymOf 125, HomonymReplacedBy 396, ReplacementNameFor 351, UnavailableName 18. 27 pages held for Bradley (`antcat__replacement_name_mismatches_for_bradley_20261108.xlsx`).
