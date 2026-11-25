#!/bin/bash
# run_readonly_export.sh -- one command on Brian's Mac for a READ-ONLY export from production.
#
# Why (Brian, 24 Nov 2026): one command per job, no paste per step. Writes go through run_grouped_write.sh; this is
# its counterpart for exports that change nothing: it sends one runner to antcat-prod, runs it in the app container
# as user antcat, brings the files it wrote to the Mac (md5 compared) and removes them and the runner from the server.
#
# Usage:
#   bash run_readonly_export.sh RUNNER.rb TAG OUTDIR
#     RUNNER.rb  a read-only runner that writes its files as "$OUT_PREFIX"_*  (OUT_PREFIX is set to /app/tmp/TAG)
#     TAG        short name, letters, digits and _ (names the remote files)
#     OUTDIR     folder on the Mac for the files
# The runner must not save records: this script refuses a runner that contains a save, update, destroy or delete call.
set -euo pipefail
test "$(uname)" = Darwin || { echo "Run this on the Mac."; exit 1; }
[ $# -eq 3 ] || { sed -n 2,14p "$0"; exit 1; }
RUNNER=$1; TAG=$2; OUT=$3
case "$TAG" in *[!A-Za-z0-9_]*|"") echo "TAG: letters, digits and _ only"; exit 1;; esac
test -f "$RUNNER" || { echo "missing $RUNNER"; exit 1; }
if grep -nE '\.(save|save!|update|update!|update_all|update_columns?|destroy|destroy!|destroy_all|delete|delete_all|create|create!|insert_all|upsert_all|touch)\b' "$RUNNER"; then
  echo "This runner calls a method that changes records. A read-only export must not."; exit 1
fi
PR=antcat; T=/var/www/antcat-2/tmp; RMD5=$(md5 -q "$RUNNER")
mkdir -p "$OUT"
echo "runner $(basename "$RUNNER") $RMD5  tag $TAG"
scp -q "$RUNNER" $PR:$T/$TAG.rb
ssh $PR "bash -s -- $TAG $RMD5" <<'REMOTE'
set -eo pipefail
TAG=$1; RMD5=$2; T=/var/www/antcat-2/tmp; cd $T
test "$(hostname)" = antcat-prod
printf '%s  %s\n' $RMD5 $TAG.rb | md5sum -c
chmod 644 $TAG.rb
docker exec -u antcat -w /app -e RAILS_ENV=production -e OUT_PREFIX=/app/tmp/$TAG antcat-app bundle exec rails runner tmp/$TAG.rb 2>&1 | grep -v DEBUG
ls ${TAG}_* >/dev/null
md5sum ${TAG}_* > $TAG.md5
REMOTE
scp -q "$PR:$T/${TAG}_*" "$PR:$T/$TAG.md5" "$OUT/"
( cd "$OUT" && while read -r sum name; do test "$(md5 -q "$name")" = "$sum" || { echo "md5 differs: $name"; exit 1; }; echo "on the Mac, md5 equal: $OUT/$name"; done < "$TAG.md5" && rm -f "$TAG.md5" )
ssh $PR "cd $T && rm -v $TAG.rb $TAG.md5 ${TAG}_* && ls"
echo "===== DONE: $TAG"
