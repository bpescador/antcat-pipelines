# AntCat etymology and grammar: the runbook

How to fill, for every AntCat species-group protonym, the etymology (published, or an AntCat derivation) and
the grammatical treatment (part of speech, its basis, the interpretation status), pattern by pattern, with as
few decisions as possible left to Brian. Written 15 Nov 2026 at Brian's request ("you need to develop the
complete skill document for this, not me"). The same text is the skill `antcat-etymology-grammar`.

## 1. Goal and definition of done (Brian, 14 Nov 2026 21:43)

Every species-group name has a verified sourced etymology, a defensible AntCat derivation, or a recorded reason
why neither can currently be supplied; and its grammatical treatment has been evaluated, with unresolved cases
explicitly recorded. Progress is counted in unique protonyms, never by adding pattern counts. Brian's own aim
for an etymology: say whether the epithet is changeable (adjective, participle) or unchangeable (noun in
apposition, noun in the genitive, indeclinable), and why.

## 2. Who decides what

The cost of this work is Brian's time, not the number of names. Every write cycle costs him about 30 minutes
whatever its size, and every question costs him a context switch. So:

1. **Claude decides and writes** (within the gates) whenever the Code, the two AntCat policies and an approved
   rule settle the name. Evidence and rule id go in the logs; nothing needs Brian's eye.
2. **Claude answers rule-level questions that the Code and the literature settle**, with citations, records
   the answer in the runner's `RULES` comment and in the roadmap, and tells Brian in one line; he can veto.
   (Done 15 Nov for -ensis and the -anus toponyms.)
3. **Brian decides only:**
   - a new pattern's rule, once, from a 30-name sample;
   - any change to an accepted spelling (Art. 33 first);
   - overriding a value a person entered (the runner never overwrites);
   - names where neither the Code, the policies nor a default settle the reading. He gets them on one sheet,
     grouped, with Claude's proposed reading and the policy default filled in, so most rows are a glance.
4. **Batch size:** never run a write cycle for fewer than about 1,000 names unless it is a pilot of a new rule;
   fold small groups into the next cycle. Combine staging dry run and write in one block.

## 3. Authorities, in order

1. **The Code** (ICZN, 4th edition): Art. 11.3 (arbitrary combinations), 11.9 (species-group name forms),
   26 (a name spelled as a Greek or Latin word is that word), 30 (genus gender), 31.1 (names from personal
   names: genitive, apposition, adjective; 31.1.2 endings -i, -ae, -orum, -arum; 31.1.3 original spelling
   preserved), 31.2 (adjectives and participles agree), 31.2.1 (nouns in apposition do not), 31.2.2
   (ambiguous: noun in apposition), 31.2.3 (non-Latin: indeclinable; melaena vs melaina), 32 to 34
   (spellings, emendations, mandatory changes). Rulings of the Commission prevail.
2. **AntCat policy on name grammar and spelling**, https://antcat.org/wiki/16: Rule 1.1 adjectives agree;
   1.2 nouns keep their ending; 1.3 Art. 26; 1.4 indeclinable; **1.5 ambiguous noun/adjective with no author
   indication and no decisive original usage: noun in apposition**; 1.6 compounds examined individually (an
   ending that can only be adjectival in the identified construction is evidence; -spina is the noun's own form,
   -nota is also a noun); 1.7 rank terms do not govern agreement. Usage under Art. 31.2.2 means the original
   author's use in the original publication (David & Gosselin 2011). An author's explicit part of speech is
   recorded even when AntCat adopts another, and the disagreement is explained publicly.
3. **AntCat policy on derived etymologies**, https://antcat.org/wiki/17: categories, the three certainty levels
   (plain, apparently, possibly), glosses in single quotes, Latin and Greek in italics (`<i>`), the person is
   never named as honoree without evidence, unsupported derivations stay blank.
4. **Decisions on record** (roadmap `claude/gender-etymology-roadmap-2026-11-12.md`): a Latin adjective or
   participle form agrees whatever its author said (Chelaner precedent, 12 Nov; manuense, exstinctum); noun
   compounds keep their spellings with a "Spelling:" note and no part of speech forced (12 Nov); no history item
   for a gender change; an erroneous change is "Misspelled as"; prometea and medusus restored; the derivation
   is removed when a sourced etymology is found.
5. **Grammar and dictionaries:** Allen & Greenough, New Latin Grammar, sect. 249 (adjectives "belonging to":
   -anus, -enus, -inus, -as, -ensis, -cus, -icus, especially from proper nouns); Lewis & Short and
   Liddell-Scott-Jones, Perseus editions (https://github.com/PerseusDL/lexica, CC BY-SA 4.0; attribution:
   Perseus Digital Library); Brown 1956 supplementary only.
6. **Literature in Brian's folder** (Dropbox `AntCat/Background reading for ICZN`; read for analysis, never
   copied into git or onto public pages):
   - Manara 1992 (Taxon 41: 524): geographical epithets in -ensis, -anus, -inus, -icus are adjectives; stems.
   - Pellizzari & Williams 2013 (Zootaxa 3710): adjective classes (one termination -ax, -ex, -ox, -ix, -ens,
     -ans; two terminations -is/-e, -ensis/-ense; three -us/-a/-um, -er/-ra/-rum, -fer, -ger); -fer/-ger with
     no author statement are treated as nouns under 31.2.2.
   - Poultney 1953 (AJP 74: 367): Latin compound adjectives from noun stems take -us/-a/-um (Type A) or
     -is/-e (Type B: imberbis from barba); the noun's own ending in a compound is not an adjectival form.
   - Dubois 2007 (Zootaxa 1550: 49): genitives from personal names are not emended; the original spelling
     stands.
   - "Patronyms (for aspiring taxonomists)" and "Patronyms Nomenclature": Art. 31.1.2 endings; Latinized names
     (Linnaei, Fabricii); modern names not newly Latinized.
   - Nicolson 1974a, b (Taxon 23): stems and compound words; Latinization of personal names.
   - David & Gosselin 2011, Schodde & Bock 2017, Dickinson et al. 2017 (BBOC): Art. 31.2.2 readings.
   - Vendetti & Garland 2019 (J. Nat. Hist. 53): name formation, kinds of nouns and adjectives.
   - Brian's ZooKeys etymology guidance and examples: state the part of speech, changeable or unchangeable.
   - Not text-searchable yet: `Formation_of_names.pdf`, Wheeler's "Myrmecological orthoepy" (OCR them first).

## 4. Data and tools (antcat-pipelines)

| What | Where |
|---|---|
| Protonym export (epithet, year, part of speech, status, etymology fields, derivation, locality, terminal taxon) | `gender/protonym_pages_export.rb` on prod, TSV to `~/antcat/taxonworks_sync/` |
| Type information, collectors | `bolton/export_protonyms.rb` (types exports in `~/antcat/snapshots/types-*/`) |
| AntCat authors | references export (`export_references.rb`) |
| Literature library, page images | `~/antcat/literature` on the Mac (`pages/<ref_id>/pNNNN.txt`), `literature/page_locator.py` |
| Published etymology matching and checks | `gender/etymology_sources.py`, `gender/verify_etymology_sources.py` |
| Toponym derivations | `gender/propose_toponym_derivations.py` |
| Part of speech by form (-ensis, -anus toponyms) | `gender/propose_part_of_speech_by_form.py` |
| Latin readings | `gender/lexicon.py build/lookup` (index from Lewis & Short, kept out of git) |
| The write runner | `gender/write_protonym_fields.rb` (rules table; selftest `gender/selftest_write_protonym_fields.rb` in smoke) |
| Older runners | `write_etymology_sources.rb` (provenance), `write_etymology_derivations.rb` (toponym pilot) |

**The runner** writes `etymology_derivation`, `gender_agreement_type`, `part_of_speech_basis` and
`interpretation_status`, one input row per protonym and field (`protonym_id, protonym_name, rule, field, value,
locality_md5`). It never overwrites; it holds disputed or unresolved readings, conflicting parts of speech, a
changed name or locality, and any save that would touch another column; each field gets its own result. A rule
is a `RULES` entry (fields, allowed values, whether a sourced etymology holds the name, edit summary) with the
approval or the evidence quoted above it. Adding a rule: code, selftest, `bash smoke.sh`, commit, push; the
server fetches the runner from the pinned raw URL and checks its md5.

## 5. The queues

Each protonym has one primary queue (the first that applies, in this order); secondary matches are kept in the
proposals file. A queue's script writes a proposals TSV (every candidate, result, reason) and the runner input.

### Q1. Published etymologies (in parallel with everything else)

- **Candidates:** names described since 1990 (6,122), then older ones whose original description has an
  Etymology heading; plus existing etymologies without a source.
- **Extraction:** the original-description page from the page locator; the etymology paragraph under the
  species' own heading; the text exactly as printed (no edits); source original_description, pages.
- **Checks before writing** (`verify_etymology_sources.py`): printed page on the page; the paragraph belongs to
  this species (not a neighbour, figure caption or key); a later work is later and does not merely quote the
  original; quotation exact against the page image for a sample of each batch.
- **Part of speech from the text:** an explicit statement ("adjective", "noun in apposition", "genitive") is
  basis `author_stated`; a dedication ("named for Dr X") with an -i/-ae ending is a genitive, basis
  `grammatical_form`, demonstrated. **The Code governs:** a Latin adjective or participle form agrees even if
  the author called it a noun; such a name gets the adjective plus a public note (hold it for the note first).
- **Effect on other queues:** a sourced etymology removes the name from derivation queues (a derivation is never
  written next to it) and outranks any derivation already written (remove it, keep the history).

### Q2. Toponyms

- **Part of speech by form, -ensis/-ense (done 15 Nov, rule `ensis_form_pos`):** always an adjective
  (A&G 249; Manara 1992; Pellizzari & Williams 2013), demonstrated; basis `author_stated` where the published
  etymology says adjective, else `grammatical_form`. Latin has no noun in -ensis but ensis 'sword'. Held: a noun
  already recorded (to Brian), a published etymology calling it a noun with no part of speech yet (note first).
- **-anus, -inus, -icus:** adjective only when the stem is a verified place in the AntCat locality (rule
  `toponym_anus_pos` for the 98 derived ones) or Lewis & Short gives the whole word as an adjective. Not
  automatic otherwise: Latin nouns in -anus, -inus, -icus exist (medicus, pinus) and personal names end in -ana.
- **Derivations** (`propose_toponym_derivations.py`): the stem matches a place in the locality (exact; place +
  one vowel; stem = place + i; place + s/es/os/as/us). Held: loose stems, several places, island groups, part of
  a longer place name, adjectives standing for places, Latin words (pratensis), a part of speech other than
  adjective, described since 1990 or with an Etymology heading near the description (published etymology first).
  Wording: "Toponym: Formed from X with the Latin adjectival suffix <i>-ensis</i>, 'of X'. The type locality
  recorded in AntCat is in X." ("the" for the Philippines, the Comoros...; "on" for islands that are not
  countries or states; Norfolk Island, Cocos Island, Verlaten Island, Farquhar Atoll in full).

### Q3. Personal-name genitives (-i, -ii, -ae, -orum, -arum; 6,048)

- **Not every ending is a genitive of a person.** First exclude: the epithet is a Latin word or form in
  Lewis & Short (a common-noun genitive such as formicae goes to Q4); the stem is a place in the locality.
- **Documented personal name** (any one): the published etymology names the person; the stem is a surname of an
  AntCat author; the stem is a collector in the protonym's type records or locality; the stem is a person named
  on the original-description pages. A documented name supports the stem, not the honoree.
- **Levels:**
  - demonstrated: the published etymology or the original description states the dedication or the genitive;
  - reasonably inferred: documented stem, the ending fits Art. 31.1.2 (-i one man, -ae one woman, -orum
    several with a man, -arum several women; -ii a Latinized name), and no competing reading;
  - unresolved: ambiguous form or undocumented stem. Kept in the proposals file with its reason, not written
    to AntCat until the queue's evidence sources are exhausted (the runner treats a recorded "unresolved" as a
    person's judgment and stops all scripted changes to it).
- **Fields:** noun_in_genitive_case; basis grammatical_form (author_stated where the author says genitive);
  status demonstrated or reasonably_inferred.
- **Derivation** only for a documented stem: "Personal name: formed as the genitive (Latin <i>-i</i>) of the
  surname X." (-ae, -orum, -arum likewise; -ii: "of X, Latinized as Xius"). Never "named for" without a
  published statement; never the person's sex unless the author gives it.
- **Spelling:** never emended (Art. 31.1.3; Dubois 2007), even when the ending looks "wrong" for the person.

### Q4. Latin and Greek words (12,328 on the 14 Nov export)

`lexicon.py lookup` gives every reading. First pass (15 Nov): 41% adjective or participle only, 4% noun only,
2% both, 1% noun with an altered ending, 2% proper noun only, 49% not found (mostly compounds such as
brevicornis and basispinosus, Greek, and spelling variants such as laevigatus/levigatus).

| Readings | Treatment | Status, basis | Derivation |
|---|---|---|---|
| adjective (any nominative form) only | adjective | demonstrated, grammatical_form | "Descriptive: Latin <i>rufus</i>, 'red, reddish'." |
| participle of a verb only | participle | demonstrated, grammatical_form | "Descriptive: Latin <i>striatus</i>, 'furrowed', participle of <i>strio</i>." |
| noun only, as spelled | noun_in_apposition | demonstrated, grammatical_form | "Descriptive: Latin <i>spina</i>, 'thorn' (noun)." |
| adjective and noun | Rule 1.5 default noun_in_apposition unless the author's statement or original usage decides | reasonably_inferred, noun_by_default (or original_usage) | as above, with both readings named |
| noun whose ending was changed (globus -> globa) | to Brian: a probable misspelling or unjustified change | none until decided | none |
| proper noun only (Diana, Niger) | noun_in_apposition (Art. 31.2.1, Simia diana) | demonstrated | "Mythological or literary name:" or "Toponym:" after checking the locality |
| not found | compound parser, then LSJ, then Q5 | | |

- Glosses: short, written by Claude from the first sense, checked against the entry; the entry id goes in the
  proposals file. Greek: Liddell-Scott-Jones; a Greek word with a Latin adjectival ending is a Latinized
  adjective (Art. 31.2.3, melaena), a Greek noun is a noun.
- One-termination adjectives and participles (-ax, -ex, -ox, -ix, -ens, -ans) are adjectives or participles but
  their spelling never changes.

### Q5. Compounds and other names (compounds ending in a noun 824; other or non-Latin 1,860)

- Claude assembles, per name: the parts (prefix, numeral or adjective stem + final element), each in Lewis &
  Short or LSJ, the final element's own nominative (spina, nodus, scapus, cornu), whether the epithet's ending
  is the noun's own form or an adjectival form (Type A -us/-a/-um, Type B -is/-e: longicornis), the original
  combination's genus gender, the author's statement, and the 12 Nov noun-compound decisions.
- Proposed reading per Rule 1.6, with the Rule 1.5 default where it applies; Brian decides from one sheet
  grouped by final element. Recorded noun compounds keep their spellings and Spelling notes.
- Non-Latin words: indeclinable (Art. 31.2.3) when not Latinized; the language named in the derivation
  ("Non-Latin word (Malagasy): ..."), sourced from a documented dictionary or gazetteer.
- Arbitrary combinations only with explicit evidence (Art. 11.3; wiki 17 rule 8).

### Q6. Gender forms and spelling

Masculine, feminine and neuter forms by script only for a demonstrated adjective or participle with verified
forms and an approved spelling basis (TaxonWorks' prediction, `Protonyms::PredictGenderEpithets`). A mismatch
with the genus is not an error until Art. 33 has been checked; agreement follows the genus, not the subgenus;
the runner never changes a disputed or unresolved name's spelling. Spelling changes go to Brian.

### Q7. TaxonWorks

Part of speech, etymology, notes and gender forms to TaxonWorks with the TW skills, then the regular cycle
(export, recount, apply, fix AntCat errors in AntCat).

## 6. Derivation wording (wiki 17)

- One category first: Personal name, Toponym, Descriptive, Compound, Non-Latin word (language), Mythological or
  literary name. One or two sentences. Glosses in single quotes; Latin and Greek in `<i>`.
- Certainty: plain statement (construction established); "apparently" (form and independent evidence, not
  certain); "possibly" (a specific linguistic basis, weaker). Never "possibly" for the merely conceivable.
- Compound: "Compound: Latin <i>crassus</i>, 'thick', and <i>spina</i>, 'thorn'."
- Leave blank when no interpretation has meaningful support; record the reason in the proposals file.

## 7. A write cycle

Pick 1,000 to 3,000 names under approved rules. Build the input, copy it to the Mac and **check its md5 on the
Mac** (a second copy of the same path once arrived stale; copy under a new name if it is wrong). Note staging use
on the coordination board. Blocks for Brian, one machine each, `&&`-chained, server blocks starting with
`test "$(hostname)" = <server> &&`:

1. Mac: `test "$(md5 -q FILE)" = <md5> && scp FILE <server>:/root/`.
2. Staging (one block): input md5; curl the runner from the pinned raw URL; runner md5; `docker cp`; `chown
   antcat:antcat`; `MODE=check`; then `MODE=write`; the changeset tally by request_uuid; three page lines by curl
   inside the container.
3. Production: backup (mysqldump with `set -o pipefail`, `umask 077`, `gunzip -t`); runner and input; dry run;
   canary of 3 or 4 by `ONLY=` (one per rule); Claude reads the pages on antcat.org in Brian's Chrome (protonym
   row and sidebar box, catalog editors' sidebar); about 10 by `ONLY=` ids (never `LIMIT`); the rest; a final
   dry run that holds everything as already recorded, and counts.
4. Logs to the Mac (`~/antcat/taxonworks_sync/etymology_write_logs/`), checked; then clear runner, input and logs
   in `/app/tmp/` and `/root/` on both servers (leave other projects' files).
5. Record the same day: the AntCat server log (What with commit and md5, Tested, Rollback), the board, the
   tracker (unique protonyms), the roadmap section, the dump in `antcat_open_items.md`'s delete list.

## 8. Guards learned the hard way

- Never overwrite a value; never touch disputed or unresolved names; check name and locality before writing.
- Ruby 4 under bundle exec has no csv: parse TSV by hand. `docker cp` leaves root mode 600: chown.
- A block run in the wrong terminal: the hostname test. A batch "of about 10" by LIMIT gave 28: use ONLY ids.
- Do not trust an offset or a match that few pages support; a later work printed earlier is not a later work.
- AntCat wiki pages: headings `#####` and `######` only, one paragraph per line, quotes as `<blockquote>`.
- Every claim about a page is read on the page; every count comes from the database, not from the input.
- Copyrighted literature stays out of git and off public pages; only citations and short glosses.
