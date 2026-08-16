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
dump=$(ls -t antcat.antweb*.txt *worldants*.txt 2>/dev/null | head -1)
csv=$(ls -t antcat_references*.csv 2>/dev/null | head -1)
echo; [ -n "$dump" ] && [ -n "$csv" ] || { echo "PAIR: cannot check -- need one dump and one reference CSV in $D"; exit 0; }
dm=$(mt "$dump"); cm=$(mt "$csv")
if [ "$dm" -le "$cm" ]; then echo "PAIR OK: $dump (dump) is older than $csv (CSV) -- same-moment rule satisfied"
else echo "PAIR FAIL: $csv predates $dump -- STALE CSV. Re-run Stage 1 export; do not reuse."; exit 1; fi
