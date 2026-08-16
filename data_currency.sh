#!/usr/bin/env bash
# data_currency.sh -- what data files do I actually have, how old, and are they a valid pair?
# Run BEFORE attaching inputs to a session or pairing them for a build.
#   bash data_currency.sh [dir]     default dir: ~/antcat/taxonworks_sync
# Prints every data file with age and md5, then applies the same-moment rule to the newest
# dump and newest reference CSV: the dump must be OLDER than the CSV (dump ~03:00 PT from
# the bridge box; a CSV exported later that day is the safe direction).
D="${1:-$HOME/antcat/taxonworks_sync}"; cd "$D" || { echo "no such dir: $D"; exit 1; }
now=$(date +%s)
if [ "$(uname)" = "Darwin" ]; then mt() { stat -f %m "$1"; }; h5() { md5 -q "$1"; }
else mt() { stat -c %Y "$1"; }; h5() { md5sum "$1" | cut -c1-32; }; fi
printf "%-45s %8s  %-32s\n" "file" "age" "md5"
for f in $(find . -maxdepth 2 -type f \( -name "*.txt" -o -name "*.csv" -o -name "*.tsv" -o -name "*.bib" \) | sort); do
  m=$(mt "$f"); age=$(( (now - m) / 3600 )); h=$(h5 "$f")
  printf "%-45s %6sh  %s\n" "$f" "$age" "$h"
done
newest() { find . -maxdepth 2 -type f \( "$@" \) -exec bash -c 'echo "$(mt "$1") $1"' _ {} \; 2>/dev/null | sort -rn | head -1 | cut -d" " -f2-; }
export -f mt 2>/dev/null
dump=$(newest -name "antcat.antweb*.txt" -o -name "*worldants*.txt")
csv=$(newest -name "antcat_references*.csv")
echo; [ -n "$dump" ] && [ -n "$csv" ] || { echo "PAIR: cannot check -- need one dump and one reference CSV in $D"; exit 0; }
dm=$(mt "$dump"); cm=$(mt "$csv")
if [ "$dm" -le "$cm" ]; then echo "PAIR OK: $dump (dump) is older than $csv (CSV) -- same-moment rule satisfied"
else echo "PAIR FAIL: $csv predates $dump -- STALE CSV. Re-run Stage 1 export; do not reuse."; exit 1; fi
# byte-identical copies under different names/ages: flag them so superseded ones get archived
echo; sort -k3 < <(for f in $(find . -maxdepth 2 -type f -name "*.csv" -o -maxdepth 2 -type f -name "*.txt" -o -maxdepth 2 -type f -name "*.tsv" -o -maxdepth 2 -type f -name "*.bib"); do echo "$f $(mt "$f") $(h5 "$f")"; done) \
  | awk '{n[$3]++; l[$3]=l[$3]" "$1} END{for(h in n) if(n[h]>1) print "DUPLICATE CONTENT (same md5, keep the newest, snapshot the rest):" l[h]}'
