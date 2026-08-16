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
grep -q 'from parse_antcat import' bolton/diff_history.py || { echo "TRIPWIRE: bolton/diff_history.py is not the canonical 761-line branch"; fail=1; }
grep -q '_drop_unmatched' export_antcat_bibtex.py || { echo "TRIPWIRE: bracket-balancing missing from export_antcat_bibtex.py"; fail=1; }
[ $fail -eq 0 ] && echo "SMOKE PASS" || { echo "SMOKE FAIL -- do not commit"; exit 1; }
