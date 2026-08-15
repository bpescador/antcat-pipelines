# Changelog entry — paste into antcat_open_items.md

## [DONE] July 2026 — Bolton 2026 Status-as-species citation sync

Wrote 565 missing "Status as species" citations from Barry Bolton's 2026 catalogue into AntCat
taxonomic histories, resolved from the July 2026 dump (`20260716-05_04_57-worldants.txt`).

**Counts:** 565/565 worklist rows written — 563 automated (1 canary + 8 in a LIMIT=10 staging pass
+ 554 in the full batch... i.e. 502 append + 61 create) plus 2 manual create-lines (Echinopla
arfaki, Myrmicocrypta weyrauchi — held out because they needed pre-2015 citations and, for
Myrmicocrypta, a human pick among 7 Kempf-1972 references). 0 errors. Reviewed by Bradley Reynolds
against original publications; 21 misspelling-target ids hand-corrected by him; 1 blank id
(Polyrhachis tyrannica → valid Taxon 446283) resolved via live console.

**Attribution / reversibility:** all writes as **AntCatBot (user id 62)**, `automated_edit = true`,
edit_summary "Bolton 2026 catalogue sync: add missing Status-as-species citations". Every change
paper_trail-versioned.

**Run markers (EXECUTE_SCRIPT activities) — for finding/reversing the run as a unit:**
- 249063 — LIMIT=10 staging pass
- 249617 — full automated batch (553 rows)
- 249620 — 2 manual create-lines
Per-item Activities (249618/249619 for the manual creates, versions 1127782/1127785; items
313726/313727) all carry the same attribution. Row-level record in `batch_write_log.csv`.

**Method:** dry-run → DigitalOcean snapshot → canary (1 append + 1 create, verified in UI +
Activity log) → 10-row batch → full batch → 2 manual rows. Writer used freeform-Taxt string edit
for appends and `HistoryItem.create!(type:'Taxt', ...)` for new lines, with idempotency +
citation-shape guards + per-row MATCH self-verification.

**Full procedure for the next (~6-month) run:** see `BOLTON_SYNC_RUNBOOK.md`. The AntCat data model
and provenance mechanism are documented in `LIVE_CONSOLE_FINDINGS.md` — next run needs no
re-investigation.

**Also this cycle:** errata sent to Barry Bolton (round 7: Strumigenys incerta, Dorylus perseus,
Solenopsis saudiensis, Seifert/"Siefert" typo) — separate from the batch he already corrected.
