#!/usr/bin/env bash
# build_tw_exports.sh -- one command -> the two files TaxonWorks needs, correct,
# with no manual post-steps.
#
#   ./build_tw_exports.sh <worldants.txt> <antcat_references.csv> [out_dir]
#
# where:
#   worldants.txt          a fresh AntCat dump
#   antcat_references.csv  output of export_references.rb (the CANONICAL runner --
#                          the one that resolves nested containers). Run it first on
#                          the droplet:
#     docker exec -w /app -e RAILS_ENV=production antcat-app \
#         bundle exec rails runner /app/export_references.rb
#
# Produces in out_dir (default ./tw_out):
#   antcat_names.tsv        names, one row per protonym identity, with valid_name_id,
#                           target_kind, reference_id, reference_pages
#   antcat_references.bib   references as BibTeX, nested containers via crossref,
#                           AntCat id on both sides, brace-safe for BibTeX-Ruby
#
# then it validates the .bib the way TaxonWorks will (strict parse, zero errors).

set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
worldants="${1:?usage: build_tw_exports.sh <worldants.txt> <antcat_references.csv> [out_dir]}"
refs="${2:?need the antcat_references.csv from export_references.rb}"
out="${3:-./tw_out}"
mkdir -p "$out"

echo "== names -> $out/antcat_names.tsv =="
python3 "$here/export_antcat_names.py" --worldants "$worldants" --out "$out/antcat_names.tsv"

echo
echo "== references -> $out/antcat_references.bib =="
python3 "$here/export_antcat_bibtex.py" --refs "$refs" --out "$out/antcat_references.bib"

echo
echo "== validate the .bib (strict parse, as TaxonWorks' BibTeX-Ruby will) =="
python3 - "$out/antcat_references.bib" <<'PY'
import sys, re, bibtexparser
raw = open(sys.argv[1]).read()
db = bibtexparser.loads(raw)
n_at = len(re.findall(r'^@', raw, re.M))
bad = sum(1 for e in db.entries for v in e.values() if v.count('{') != v.count('}'))
targets = set(re.findall(r'crossref = \{(antcat\d+)\}', raw))
keys = {e['ID'] for e in db.entries}
ok = (len(db.entries) == n_at) and bad == 0 and targets <= keys
print(f"  entries in file / parsed: {n_at} / {len(db.entries)}")
print(f"  unbalanced-brace values:  {bad}")
print(f"  crossref targets present: {targets <= keys} (missing {len(targets - keys)})")
print("  RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
PY

echo
echo "== cross-file join check =="
python3 - "$out/antcat_names.tsv" "$out/antcat_references.bib" <<'PY'
import sys, re, csv
names = list(csv.DictReader(open(sys.argv[1]), delimiter='\t'))
keys = set(re.findall(r'@\w+\{(antcat\d+),', open(sys.argv[2]).read()))
have = sum(1 for n in names if 'antcat' + n['reference_id'] in keys)
print(f"  names: {len(names)}; reference_id -> BibTeX key: {have} ({100*have/len(names):.2f}%)")
PY
echo
echo "Done. Load $out/antcat_references.bib as Sources, then $out/antcat_names.tsv as names."
