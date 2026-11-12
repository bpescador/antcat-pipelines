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
assert C('trochis', 'troche')[1] == 'manual'                 # the trochis trap goes to a person
assert C('pomonae', 'pomone')[1] == 'noun_in_genitive_case'
assert C('calva', 'calvus', 'feminine')[3].startswith('ending disagrees')
assert C('sphagnicolus', 'sphagnicola', 'masculine')[1] == 'manual'  # -cola is a noun: not rule 4
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
