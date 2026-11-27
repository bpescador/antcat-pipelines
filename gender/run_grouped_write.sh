#!/bin/bash
# run_grouped_write.sh -- one command on Brian's Mac for a reviewed apply_grouped_changes.rb write.
#
# Why (Brian, 24 Nov 2026): a paste per step and per machine was burning him out. The gates stay; the pasting goes.
# One run does, in order, and stops at the first failure:
#   1 send the runner, the input and the edit summaries to antcat-staging and antcat-prod (md5 checked there)
#   2 staging: hold file, check, write (groups staging's older data lacks are held; that is expected)
#   3 production: mysqldump, then the dry run with every row printed (rolls back, writes nothing)
#   4 ask "yes"; production canary (one group); ask "yes" after Brian has looked at the page
#   5 production: the rest (the canary group shows as held: already written)
#   6 logs to the Mac, md5 compared with the servers'
#   7 cleanup of both servers by name, staging hold removed
# Anything but "yes" stops the run with nothing further written; files and the hold then stay for a rerun.
#
# Usage:
#   bash run_grouped_write.sh INPUT.tsv TAG CANARY_GROUP SUMMARIES.env CANARY_URL [RUNNER.rb]
#     INPUT.tsv      the reviewed input (group, kind, record_id, label, field, old, new)
#     TAG            short name without spaces, e.g. idris3_20261124 (names the dump, the logs and the remote files)
#     CANARY_GROUP   the group written first, exactly as in the input
#     SUMMARIES.env  one KEY=value per line, no quotes: NAME_GENDER_SUMMARY=..., TAXON_NAME_SUMMARY=..., PROTONYM_SUMMARY=...
#                    (docker --env-file format, so parentheses and spaces need no quoting)
#     CANARY_URL     the antcat.org page to look at after the canary
#     RUNNER.rb      default: apply_grouped_changes.rb beside this script
# Before running: the board note (staging in use) is posted and Brian has approved the input.
set -euo pipefail
test "$(uname)" = Darwin || { echo "Run this on the Mac."; exit 1; }
[ $# -ge 5 ] || { sed -n 2,26p "$0"; exit 1; }
INPUT=$1; TAG=$2; CANARY=$3; SUMS=$4; URL=$5
RUNNER=${6:-$(cd "$(dirname "$0")" && pwd)/apply_grouped_changes.rb}
case "$TAG" in *[!A-Za-z0-9_]*|"") echo "TAG: letters, digits and _ only"; exit 1;; esac
for f in "$INPUT" "$SUMS" "$RUNNER"; do test -f "$f" || { echo "missing $f"; exit 1; }; done
awk -F'\t' -v c="$CANARY" '$1==c{f=1} END{exit !f}' "$INPUT" || { echo "canary group not in the input: $CANARY"; exit 1; }
ST=root@143.244.182.132; PR=antcat; T=/var/www/antcat-2/tmp
IMD5=$(md5 -q "$INPUT"); RMD5=$(md5 -q "$RUNNER"); SMD5=$(md5 -q "$SUMS")
CAN=$(mktemp); printf 'ONLY=%s\n' "$CANARY" > "$CAN"
echo "input $IMD5 ($(($(wc -l < "$INPUT") - 1)) rows)  runner $RMD5  tag $TAG  canary: $CANARY"
for h in $ST $PR; do
  scp -q "$RUNNER" $h:$T/apply_grouped_changes.rb; scp -q "$INPUT" $h:$T/$TAG.tsv
  scp -q "$SUMS" $h:$T/$TAG.env; scp -q "$CAN" $h:$T/$TAG.canary.env
done
rm -f "$CAN"

# The remote part: same text for both servers; the first argument picks the step.
remote() { # host step
  ssh "$1" "bash -s -- $2 $TAG $IMD5 $RMD5 $SMD5" <<'REMOTE'
set -eo pipefail
STEP=$1; TAG=$2; IMD5=$3; RMD5=$4; SMD5=$5; T=/var/www/antcat-2/tmp; cd $T
run() { docker exec -u antcat -w /app -e RAILS_ENV=production -e INPUT=/app/tmp/$TAG.tsv --env-file $T/$TAG.env "$@" antcat-app bundle exec rails runner tmp/apply_grouped_changes.rb 2>&1 | grep -v DEBUG | grep -E "held|error|groups|written|would_write|Wrote" | short; }
# a large set prints its first 30 written groups, then every held or error line and the totals (27 Nov 2026: 10,759 groups)
short() { awk '/^  (written|would_write) /{n++; if (n<=30) print; else if (n==31) print "  ... (written groups after the first 30 not shown; totals below)"; next} {print}'; }
verify() { printf '%s  %s\n' $RMD5 apply_grouped_changes.rb $IMD5 $TAG.tsv $SMD5 $TAG.env | md5sum -c; chmod 644 apply_grouped_changes.rb $TAG.tsv $TAG.env $TAG.canary.env; }
case $STEP in
  staging)
    test "$(hostname)" = antcat-staging
    echo "AntCat chat: grouped write $TAG" > /root/antcat-staging-hold
    verify; echo "-- staging check"; run -e MODE=check; echo "-- staging write"; run -e MODE=write ;;
  prodcheck)
    test "$(hostname)" = antcat-prod
    D=/var/backups/antcat-db/antcat-manual-pre-$TAG.sql.gz
    (umask 077 && docker exec antcat-db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction antcat' 2>/dev/null | gzip > $D)
    gzip -t $D; ls -l $D
    verify; run -e MODE=check
    F="$(ls -t apply_grouped_changes_check_*.tsv | head -1)"
    cut -f1,2,3,6,7,8 "$F" | head -41 | cut -c1-170
    [ "$(wc -l < "$F")" -gt 41 ] && { echo "  ... $(($(wc -l < "$F") - 41)) more rows in $F; held rows:"; cut -f1,2,3,6,7,8,9 "$F" | grep -v '^would_write' | tail -n +2 | cut -c1-200; } || true ;;
  canary)   test "$(hostname)" = antcat-prod; run -e MODE=write --env-file $T/$TAG.canary.env ;;
  rest)     test "$(hostname)" = antcat-prod; run -e MODE=write ;;
  logs)     tar czf ${TAG}_logs_$(hostname).tgz apply_grouped_changes_check_*.tsv apply_grouped_changes_write_*.tsv $(ls deleted_taxon_*.json type_name_*.json 2>/dev/null); md5sum ${TAG}_logs_$(hostname).tgz | cut -c1-32 ;;
  cleanup)
    rm -v apply_grouped_changes.rb $TAG.tsv $TAG.env $TAG.canary.env ${TAG}_logs_$(hostname).tgz apply_grouped_changes_check_*.tsv apply_grouped_changes_write_*.tsv
    rm -fv deleted_taxon_*.json type_name_*.json
    if [ "$(hostname)" = antcat-staging ]; then rm -v /root/antcat-staging-hold; else ls; fi ;;
esac
REMOTE
}

echo "===== 1. STAGING (check, then write)";                         remote $ST staging
echo "===== 2. PRODUCTION: dump, then dry run (writes nothing)";     remote $PR prodcheck
read -r -p "Write the canary ($CANARY) to production? Type yes: " A
[ "$A" = yes ] || { echo "Stopped. Nothing written to production. Files and the staging hold stay for a rerun."; exit 0; }
echo "===== 3. PRODUCTION CANARY: $CANARY";                          remote $PR canary
echo "Look at $URL"
read -r -p "Canary correct? Type yes to write the rest: " B
[ "$B" = yes ] || { echo "Stopped after the canary. Files and the staging hold stay."; exit 0; }
echo "===== 4. PRODUCTION REST (the canary group shows as held)";    remote $PR rest
echo "===== 5. LOGS TO THE MAC"
L=~/antcat/taxonworks_sync/etymology_write_logs; mkdir -p $L
MP=$(remote $PR logs); MS=$(remote $ST logs)
scp -q $PR:$T/${TAG}_logs_antcat-prod.tgz $L/; scp -q $ST:$T/${TAG}_logs_antcat-staging.tgz $L/
test "$(md5 -q $L/${TAG}_logs_antcat-prod.tgz)" = "$MP"; test "$(md5 -q $L/${TAG}_logs_antcat-staging.tgz)" = "$MS"
echo "logs on the Mac, md5 equal: prod $MP staging $MS"
echo "===== 6. CLEANUP";                                             remote $PR cleanup; remote $ST cleanup
echo "===== ALL DONE: $TAG"
