# frozen_string_literal: true
#
# reorder_history_by_kind.rb
#
# Reorders history items on protonyms whose order breaks the canonical order of
# history-line kinds accepted by Brian on 2026-11-07 (claude/HISTORY_ORDER.md).
# Uses AntCat's own Protonyms::Operations::ReorderHistoryItems (the editors'
# "Reorder history items" screen) and records a reorder_history_items activity.
#
# Input:  /app/tmp/history_reorder_approved.tsv  (protonym_id, current_ids, new_ids, violations)
#         Each row is skipped unless the protonym's items are still exactly current_ids, in that order,
#         and unless saving would leave every item's text unchanged (saving runs Taxt::Cleanup and
#         Taxt::ConvertTags; this script changes order only).
# Env:    MODE=check (default; saves nothing) | MODE=write
#         ONLY=protonym ids (comma-separated) for a canary
#         REVERSE=1 swaps current_ids and new_ids: rolls back a write, using the same file.
# Output: /app/tmp/reorder_history_<MODE>_<uuid>.tsv
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/reorder_history_by_kind.rb

IN = Rails.root.join('tmp', 'history_reorder_approved.tsv').to_s
MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
REVERSE = ENV['REVERSE'] == '1'
EDIT_SUMMARY = '[automated] Reorder history to the canonical order of kinds (claude/HISTORY_ORDER.md)'

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "reorder_history_#{MODE}_#{uuid}.tsv").to_s

lines = File.readlines(IN, chomp: true)
header = lines.shift.split("\t")
rows = lines.map { |l| header.zip(l.split("\t", -1)).to_h }
rows.select! { |r| ONLY.include?(r['protonym_id'].to_i) } if ONLY

puts "MODE=#{MODE} REVERSE=#{REVERSE} request_uuid=#{uuid} rows=#{rows.size}"
stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id expected_ids target_ids detail].join("\t")

def text_would_change protonym
  protonym.history_items.select do |item|
    item.taxt.present? && Taxt::ConvertTags[Taxt::Cleanup[item.taxt]] != item.taxt
  end.map(&:id)
end

rows.each do |r|
  expected = r[REVERSE ? 'new_ids' : 'current_ids'].split(',').map(&:to_i)
  target = r[REVERSE ? 'current_ids' : 'new_ids'].split(',').map(&:to_i)
  protonym = Protonym.find_by(id: r['protonym_id'])
  result, detail =
    if protonym.nil?
      ['skip', 'protonym not found']
    elsif (now = protonym.history_items.pluck(:id)) != expected
      ['skip', "items changed since export: now #{now.join(',')}"]
    elsif expected.sort != target.sort
      ['skip', 'target is not a permutation of current items']
    elsif (changed = text_would_change(protonym)).any?
      # Saving runs Taxt::Cleanup and Taxt::ConvertTags; refuse rather than also rewrite text.
      ['skip', "saving would also change the text of item(s) #{changed.join(',')}"]
    elsif MODE == 'check'
      ['would_reorder', '']
    elsif Protonyms::Operations::ReorderHistoryItems[protonym, target.map(&:to_s)]
      activity = protonym.create_activity(Activity::REORDER_HISTORY_ITEMS, bot, edit_summary: EDIT_SUMMARY)
      activity.update!(automated_edit: true)
      ['reordered', '']
    else
      ['error', protonym.errors.full_messages.to_sentence]
    end
  stats[result] += 1
  out.puts [result, r['protonym_id'], expected.join(','), target.join(','), detail].map { |v| v.to_s.tr("\t", ' ') }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-15s %4d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
