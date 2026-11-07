# combinations/

Scripts that add missing obsolete combinations to AntCat. First used 2026-11-07, when 1,673 were created on production (Brian's project notes: `claude/MISSING_COMBINATIONS_PLAN.md`).

A combination is missing when a species-group protonym has a "Combination in G" history item, free text or relational, but no species-rank taxon in genus G. AntWeb only recognises names that exist as taxa, so a specimen identified under a missing combination is not moved to the current name.

## Scripts

| Script | Writes? | Purpose |
|---|---|---|
| `missing_combinations_dryrun.rb` | no | Finds missing combinations; proposes the spelling with gender agreement; writes `tmp/missing_combinations_dryrun.tsv`. |
| `subgenus_tag_check.rb` | no | Counts "Combination in" tags pointing to subgenera whose name also exists as a genus. |
| `create_missing_combinations.rb` | MODE=write only | Creates taxa from a reviewed `tmp/missing_combinations_approved.tsv`. MODE=check by default. LIMIT=n, ONLY=protonym ids for canaries. Re-checks every row live. AntCatBot, `automated_edit: true`, one request_uuid per run. |
| `verify_created_combinations.rb` | no | UUID=... Checks every taxon of a run against the intended record shape. |
| `rollback_missing_combinations.rb` | MODE=write only | UUID=... Removes one run's taxa, except any changed or linked since. |

## How to run

Scripts go in `/var/www/antcat-2/tmp/` on the server (the container sees `/app/tmp/`). Run them as `antcat` inside the app container:

```
docker exec -u antcat -w /app -e RAILS_ENV=production [-e MODE=...] antcat-app bundle exec rails runner tmp/<script>.rb
```

Order: dry run, review the TSV, build the approved list, check mode, staging write and verify (and rollback test), manual mysqldump on production, canary, verify, full batch, verify.

The droplet snapshot does not include the database volume; the mysqldump is the safety copy.

## Spelling rule

See the header of `missing_combinations_dryrun.rb`. Same-gender genera and indeclinable or genitive epithets keep the current spelling; declinable adjectives are declined with a port of TaxonWorks `predict_three_forms`; -is/-e into or out of a neuter genus, and anything unclear, is left for a person. Data files (TSVs) stay out of git.
