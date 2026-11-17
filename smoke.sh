#!/usr/bin/env bash
# smoke.sh -- pre-commit sanity for antcat-pipelines. Run from repo root: bash smoke.sh
# Catches: truncated/damaged files (syntax), and regressions of known-critical fixes
# (signatures). NOT a substitute for the counts oracle or Stage-2 gates.
set -u; fail=0
for f in $(find . -name "*.py" -not -path "./.git/*"); do
  python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null || { echo "SYNTAX FAIL $f"; fail=1; }
done
for f in $(find . -name "*.sh" -not -path "./.git/*"); do
  bash -n "$f" || { echo "SYNTAX FAIL $f"; fail=1; }
done
command -v ruby >/dev/null && for f in $(find . -name "*.rb" -not -path "./.git/*"); do
  ruby -c "$f" >/dev/null || { echo "SYNTAX FAIL $f"; fail=1; }
done
# environment: the Stage-2 gate needs bibtexparser v1 (requirements.txt)
python3 -c "import bibtexparser as b; assert b.__version__.startswith('1.'), b.__version__" 2>/dev/null \
  || echo "WARN: bibtexparser v1 not importable here -- pip install -r requirements.txt before Stage 2 (not a commit blocker)"
# regression tripwires -- each grep must hit or a hard-won fix has been lost
grep -q 'PDF|' export_antcat_names.py            || { echo "TRIPWIRE: PAGE_RE DOI/PDF fix missing from export_antcat_names.py"; fail=1; }
# original-description page (2026-11-11): only the protonym's own citation counts; roman,
# plate-only and unpaginated pages are blank, never a number taken from a later citation
PYTHONPATH=. python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: original_page() regression in export_antcat_names.py"; fail=1; }
from export_antcat_names import original_page as P
cases = {
 'Myrmica rolandi var. reticulata Stärcke, 1942d : xxv (w.q.m.) FRANCE. Primary type material: lectotype worker (by designation of Seifert, 2026b 10.25674/526 : 5).': '',
 'Myrmica reticulata Smith, 1862b : 33 (w.) PANAMA.': '33',
 'Acanthomyrmex malikuli Jaitrong & Asanok, 2019 10.3897/zookeys.842.33609 : 116, figs. 1-3': '116',
 'Messor obscurior Sharaf, 2018 10.1080/09397140.2018.1442301 : 10 (s.) IRAQ.': '10',
 'Formica x Smith, 1858 PDF: 45 (w.)': '45',
 'Formica y Smith, 1858 10.1234/abc.1 PDF : 7 (w.)': '7',
 'Formica lignitum Germar, 1837 : pl. 19, fig. 19 (q.). Combination in Camponotus: Mayr, 1867b : 51.': '',
 'Formica rubripes Drury, 1770 : - Formica rubripes sensu Roger, 1863b : 2': '',
 'Formica z Smith, 1858 (w.) USA. Lectotype designation: Jones, 1990 : 12.': '',
 'Gnamptogenys piei Dias & Lattke, 2019 https://doi.org/10.1016/j.rbe.2018.10.002 : 31, fig. 1 (w.)': '31',
 'Cataglyphis bazoftensis Khalili-Moghadam et al., 2021 doi: 10.3897/zookeys.1009.59205 : 6, figs. 1-8': '6',
 'Formica w Smith, 2015 http://dx.doi.org/10.1234/x.5 : 77 (w.)': '77',
 'Formica v Smith, 2015 doi.org/10.1234/x.5 (w.) USA. Lectotype designation: Jones, 2020 : 12.': '',
}
bad = {t[:40]: (P(t), want) for t, want in cases.items() if P(t) != want}
assert not bad, bad
PY
# homonym replacement (2026-11-11): when one epithet, author and year fits homonyms in several
# genera (Forel, 1915 mjobergi), the genus named in "Replacement name for ..." decides
PYTHONPATH=. python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: homonym replacement ignores the named genus in export_antcat_names.py"; fail=1; }
from export_antcat_names import build_replacement_map as B
H = ['antcat id', 'genus', 'species', 'subspecies', 'year', 'status', 'taxonomic history html']
ix = {h: i for i, h in enumerate(H)}
rows = [
 ['1', 'Leptogenys', 'mjobergi', '', '1915', 'homonym', 'Dorylozelus mjobergi Forel, 1915: 61 (w.) AUSTRALIA.'],
 ['2', 'Prolasius', 'mjobergi', '', '1915', 'homonym', 'Prenolepis mjobergi Forel, 1915: 70 (w.) AUSTRALIA.'],
 ['3', 'Leptogenys', 'tricosa', '', '1969', 'valid', 'Leptogenys tricosa Taylor, 1969: 1 (w.). Replacement name for Leptogenys mjobergi (Forel, 1915).'],
 ['4', 'Prolasius', 'mjoebergellus', '', '1951', 'valid', 'Prolasius mjoebergellus Taylor, 1951: 2 (w.). Replacement name for Prolasius mjobergi (Forel, 1915).'],
]
r, _ = B(rows, ix, 6)
assert r == {'1': '3', '2': '4'}, r
PY
# part of speech (2026-11-12): TW's three-form rule ported; the genus-gender check catches calvus
PYTHONPATH=gender python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: gender/propose_part_of_speech.py rules regressed"; fail=1; }
from propose_part_of_speech import predict_three_forms as F, classify as C
assert F('crassispina') == ('crassispinus', 'crassispina', 'crassispinum')
assert F('niger') == ('niger', 'nigra', 'nigrum') and F('trochis')[2] == 'troche'
assert F('acris') == ('acer', 'acris', 'acre')                          # TW's irregular-adjective table is used
assert F('alboniger') == ('alboniger', 'albonigra', 'albonigrum')        # TW's -niger rule covers compounds
assert F('corniger') == ('corniger', 'cornigera', 'cornigerum') and F('conigera')[2] == 'conigerum'  # -iger is not -niger
assert C('trochis', 'troche')[1] == 'manual'                 # the trochis trap goes to a person
assert C('pomonae', 'pomone')[1] == 'noun_in_genitive_case'
assert C('calva', 'calvus', 'feminine')[3].startswith('ending disagrees')
assert C('sphagnicolus', 'sphagnicola', 'masculine')[1] == 'manual'  # -cola is a noun: not rule 4
assert C('howense', 'howensis')[:2] == (2, 'adjective')                # -ense is rule 2, not the -e trap
assert C('melanocephala', 'melanocephalum')[1] == 'manual'             # noun-ending compound: policy, not rule 4
assert C('obscura', 'obscurus')[:2] == (4, 'adjective')                # ...but a plain adjective stays rule 4
PY
# recount (2026-11-12): a later "Subspecies of" citation restores a name once synonymized (Formica cinerea iberica)
PYTHONPATH=. python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: tw_status_diff.antcat_check flags revived subspecies again"; fail=1; }
from tw_status_diff import antcat_check as C
assert C('valid', 'Junior synonym of F. cinerea : Seifert, 2002 : 251. | Subspecies of F. cinerea : Schultz & Seifert, 2026 : 33.') == ''
assert C('valid', 'Junior synonym of F. cinerea : Seifert, 2002 : 251.').startswith('AntCat valid')
PY
# literature/page_locator.py (2026-11-14): printed page numbers vote for the offset; a dropped digit counts half
grep -q "nesting.get(ref_id)" literature/page_locator.py || { echo "TRIPWIRE: literature/page_locator.py no longer reads the nesting reference's PDF for a nested reference"; fail=1; }
PYTHONPATH=literature python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: page offset detection broken in literature/page_locator.py"; fail=1; }
from page_locator import offsets_for as O, RefText as R
t = {1: 'Bull. Soc. 141\ntext', 2: '— 42 —\ntext', 3: '_ 143 —\nAtta crassispina n. sp.', 4: '144\ntext'}
assert O(t)[0][0] == 140
assert R(t).epithet_pages('crassispina') == {3: 'exact'} and R(t).epithet_pages('crassispinas') == {3: 'fuzzy'}
# PeerJ numbering "184/462" (Prebus 2021b; the offset came out -9 before 14 Nov): N/total votes for offset 0
p = {i: f'text\nmore\nlines\nhere\nand\nmore\nPrebus (2021), PeerJ   {i}/4' for i in range(1, 5)}
assert O(p)[0][0] == 0
PY
# gender/etymology_sources.py and verify (2026-11-14 sample): an offset most pages do not carry gives no printed
# page; a later work earlier than the original is never chosen; a later work that quotes an earlier text is held
grep -q 'votes >= 0.5 \* pdf_pages' gender/etymology_sources.py || { echo "TRIPWIRE: weak page offsets trusted in gender/etymology_sources.py"; fail=1; }
grep -q 'ref_year\[ref\] < year' gender/etymology_sources.py || { echo "TRIPWIRE: earlier papers accepted as later works in gender/etymology_sources.py"; fail=1; }
# Toponym pilot (14 Nov): Barro Colorado is not Colorado; Brunei only loosely brunensis (Brno?); stems dropping -s
PYTHONPATH=gender python3 -c "
from propose_toponym_derivations import match as M, place_check as P
assert M('arizon', 'arizona') == 'close' and M('sulawesi', 'sulawesi') == 'exact' and M('philippin', 'philippines') == 'close'
assert M('brun', 'brunei') == '' and M('korean', 'korea') == ''
assert P('Colorado', 'Panama (Barro Colorado)') and P('Colorado', 'U.S.A. (Colorado)') == '' and P('Liaoning', 'China (Liaoning, Fushun Amber, Eocene)') == ''
from propose_toponym_derivations import locality_place as L
assert L('Norfolk', 'Australia (Norfolk I.)') == 'Norfolk Island' and L('Norfolk', 'U.K. (Norfolk)') is None and L('Java', 'Indonesia (Java)') == 'Java'
" 2>/dev/null || { echo "TRIPWIRE: toponym matching rules in gender/propose_toponym_derivations.py"; fail=1; }
# Ruby 4 runners under bundle exec: a plain require 'csv' raises LoadError (staging dry run, 14 Nov)
# The general write runner (14 Nov 2026): never overwrites, holds open readings, each field its own result.
if ruby -e 'exit(RUBY_VERSION >= "3.0" ? 0 : 1)' 2>/dev/null; then
  ruby gender/selftest_write_protonym_fields.rb >/dev/null 2>&1 || { echo "TRIPWIRE: gender/selftest_write_protonym_fields.rb fails (field results of write_protonym_fields.rb)"; fail=1; }
  # The correction runner (16 Nov 2026): touches only what the write set, never a value someone else entered
  ruby gender/selftest_correct_protonym_fields.rb >/dev/null 2>&1 || { echo "TRIPWIRE: gender/selftest_correct_protonym_fields.rb fails (field results of correct_protonym_fields.rb)"; fail=1; }
else
  echo "WARN: ruby 3 not found -- gender/selftest_*_protonym_fields.rb skipped (not a commit blocker)"
fi
# Audit of the combined write (16 Nov 2026): L&S proper nouns printed in lower case (icarus) and a derived word's
# adj. (Icarius) made adjectives; Afer, fra, frum stays one; false compound splits (abd + ominalis, lith + ophila);
# third-declension genitives (victoris, stipitum) are not compounds; L&S false readings (type="spur") are no entries
PYTHONPATH=gender python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: dictionary-reading or compound fixes of 16 Nov lost in gender/lexicon.py or gender/compounds.py"; fail=1; }
from lexicon import kind_of as K, headword_segment as H
from compounds import Parser
assert K('i', 'm.', '', '<orth>x</orth>', 'īcărus', 'Icarus') == 'proper noun'
assert K('fra, frum', 'm.', 'adj.', '', 'āfer', 'Afer') == 'adjective'
b = '<orth>īcărus</orth>, <itype>i</itype>, <gen>m.</gen> <sense n="I">A son of Daedalus.</sense><sense n="1"> <orth>īcărĭus</orth>, <itype>a, um</itype>, <pos>adj.</pos></sense>'
assert '<pos>' not in H(b) and '<gen>' in H(b)
p = object.__new__(Parser)
assert not p.junction('abd', 'ominalis', []) and not p.junction('lith', 'ophila', []) and p.junction('lamelli', 'cornis', [])
assert p.junction('micr', 'ophthalma', []) and p.junction('formic', 'oides', [])
p.gen_endings = {'oris': [('victor', {})], 'itis': [('stipes', {})], 'dentis': [('dens', {})]}
assert p.genitive('victoris') is not None and p.genitive('stipitum') is not None and p.genitive('dentis') is not None
p.gen_endings.update({'alis': [('cervical', {})], 'inis': [('caligo', {})]})
assert p.genitive('nigricornis') is None and p.genitive('cervicalis') is None and p.genitive('calinum') is None
PY
# Second audit, 16 Nov 2026 (Brian: decide the held names from the evidence): -philus, -collis, -genis, -gerus are
# adjectival finals; a listed final outranks a longer chance word (chrys + urus, not chry + surus); the author's
# statement is read from the species' own account; resolve_held never writes a noun whose spelling was changed
PYTHONPATH=gender python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: compound finals or stated-grammar reading of 16 Nov lost (gender/compounds.py, extract_stated_grammar.py, resolve_held.py)"; fail=1; }
from compounds import NOUN_FINALS, FINALS_INFERRED
for f in ('philus', 'phila', 'collis', 'genis', 'gerus', 'ferus', 'nota', 'ophthalma'):
    assert f in NOUN_FINALS and NOUN_FINALS[f][2] == (), f
assert NOUN_FINALS['spina'][2] == ('spina',) and 'nota' in FINALS_INFERRED
from extract_stated_grammar import STATED, HEADING
flags = lambda t: {n for n, rx in STATED if rx.search(t)}
assert 'noun_in_apposition' in flags('The name is a noun in apposition and thus invariant')
assert 'arbitrary' in flags('The species epithet is an arbitrary combination of letters')
assert 'adjective' in flags('Latin griseus; adjective in the nominative singular') and HEADING.search('Etymology. Named for')
import resolve_held as R
assert R.EXPLICIT_NOUN.search('to be treated as a noun in apposition') and not R.EXPLICIT_NOUN.search('Non-Latin noun, named after the collector')
assert R.OTHER_NAME.match('C. flavopectus derives from Latin').group(1) == 'flavopectus'
assert 'faber' in R.BOTH_NOUN and 'ornatus' not in R.BOTH_NOUN and R.ALTERED['inca'] == 'N'
PY
grep -q "noun_spelling_changed" gender/resolve_held.py || { echo "TRIPWIRE: gender/resolve_held.py writes nouns whose accepted spelling was changed"; fail=1; }
# Third reading, 16 Nov 2026, before production: a later work's table is not the author's statement (Monomorium
# kiliani, leae); "noun in the genitive case" is a genitive (loarelae, trinacriae); a name used unchanged is no
# genitive (Lasius fuji, Tetramorium kali); -phora and -ura are adjectival, spongia and Molossus are nouns
PYTHONPATH=gender python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: the 16 Nov pre-production reading lost in gender/resolve_held.py (later_work, SAYS_GENITIVE, names used unchanged)"; fail=1; }
import inspect, resolve_held as R
src = inspect.getsource(R)
assert 'def later_work(p)' in src and "not later_work(p)" in src and 'the name is used unchanged, not in the genitive' in src
assert R.SAYS_GENITIVE.search('to be treated as a noun in the genitive case') and R.SAYS_GENITIVE.search('is a patronymic')
assert R.EPITHET['eriophora'][0] == 'adjective' and R.EPITHET['micrura'][0] == 'adjective'
assert R.EPITHET['subspongia'][0] == 'noun_in_apposition' and R.EPITHET['molossus'][0] == 'noun_in_apposition'
assert 'euryscopa' in R.CHANCE
assert 'IN THE ORDER THEY RAN' in src and R.DECIDED['202524'][0] == 'noun_in_apposition' and R.DECIDED['171024'][0] == 'adjective'
PY
grep -q "a.get('type') == 'spur'" gender/lexicon.py || { echo "TRIPWIRE: L&S false readings (type=spur) indexed again in gender/lexicon.py"; fail=1; }
grep -q 'the protonym already has notes' gender/write_notes_page.rb && grep -q "is not the reviewed file's" gender/write_notes_page.rb || { echo "TRIPWIRE: gender/write_notes_page.rb no longer holds an existing page or an unreviewed file"; fail=1; }
grep -q "'Myrmotrema': ('neuter'" gender/propose_genus_gender.py && grep -q "'Myrmopsamma': ('feminine'" gender/propose_genus_gender.py || { echo "TRIPWIRE: gender/propose_genus_gender.py lets the ending outrank the word's own gender (Myrmotrema, Myrmopsamma)"; fail=1; }
for f in gender/write_etymology_sources.rb gender/write_etymology_derivations.rb gender/write_protonym_fields.rb gender/correct_protonym_fields.rb gender/write_notes_page.rb; do ! grep -q "^require 'csv'" "$f" || { echo "TRIPWIRE: $f requires csv (LoadError under bundle exec on Ruby 4)"; fail=1; }; done
PYTHONPATH=gender:literature python3 -c "from verify_etymology_sources import quoted as Q; assert Q('Etymology: “This singular ant is dedicated to Dr. H. KUTTER', 'dedicated to dr h kutter') and not Q('Etymology: Dedicated to Dr. H. Kutter', 'dedicated to dr h kutter')" 2>/dev/null || { echo "TRIPWIRE: quoted later-work passages not detected in gender/verify_etymology_sources.py"; fail=1; }
# AntCat #1617: status "unjustified emendation" maps to TW's UnjustifiedEmendation relationship
PYTHONPATH=. python3 - <<'PY' 2>/dev/null || { echo "TRIPWIRE: tw_status_diff lost the unjustified-emendation mapping"; fail=1; }
from tw_status_diff import tw_status as S, action_for as A
st, _, f = S({'classifications': '', 'is_valid': 'false', 'valid_taxon_name_id': '1',
              'status_relationships': 'Iczn::Invalidating::Synonym::Objective::UnjustifiedEmendation -> 1 Aus bus'})
assert f['unjustified_emendation'] and st == 'synonym'
assert 'UnjustifiedEmendation' in A('status: AntCat unjustified emendation, TW valid', 'unjustified emendation', {'valid_name': 'Aus bus'})[0]
PY
grep -q 'from parse_antcat import' bolton/diff_history.py || { echo "TRIPWIRE: bolton/diff_history.py is not the canonical 761-line branch"; fail=1; }
grep -q '_drop_unmatched' export_antcat_bibtex.py || { echo "TRIPWIRE: bracket-balancing missing from export_antcat_bibtex.py"; fail=1; }
grep -q 'def name_relation' antweb_types/reconcile_types.py || { echo "TRIPWIRE: genus+last-epithet name comparison missing from antweb_types/reconcile_types.py"; fail=1; }
grep -q "needs_locality='yes (from publication)'" antweb_types/build_inserts.py || { echo "TRIPWIRE: no-AntWeb-locality rule missing from antweb_types/build_inserts.py"; fail=1; }
PYTHONPATH=.:bolton python3 -c "from diff_depositories import literal_codes as L; assert L(['INBio','CASC','NMNH NASU'])==['INBio','NMNH NASU']" 2>/dev/null || { echo "TRIPWIRE: mixed-case codes (INBio) not read by bolton/diff_depositories.py"; fail=1; }
grep -q 'def use_codes' bolton/split_depository_specimens.py || { echo "TRIPWIRE: mixed-case codes missing from bolton/split_depository_specimens.py"; fail=1; }
# behaviour check on a made-up fixture (stdlib only, temp folder): the June 2026 decisions
python3 antweb_types/selftest.py | grep -q 'SELFTEST PASS' || { echo "SELFTEST FAIL: run python3 antweb_types/selftest.py"; fail=1; }
[ $fail -eq 0 ] && echo "SMOKE PASS" || { echo "SMOKE FAIL -- do not commit"; exit 1; }
