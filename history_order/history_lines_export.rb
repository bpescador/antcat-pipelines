# frozen_string_literal: true
#
# history_lines_export.rb  (READ-ONLY)
#
# Exports every history item with its protonym, editor position, type, rank,
# reference year and the start of its text, for deriving the canonical order of
# history-line kinds offline. Reads the real `position` column (the July 2026
# derivation used the rendered dump).
#
# Output: /app/tmp/history_lines.tsv
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/history_lines_export.rb

OUT = Rails.root.join('tmp', 'history_lines.tsv').to_s
n = 0
File.open(OUT, 'w') do |f|
  f.puts %w[protonym_id position id type rank reference_year protonym_rank text].join("\t")
  ranks = Protonym.joins(:name).pluck(:id, 'names.type').to_h
  HistoryItem.preload(:reference).find_each do |hi|
    text = hi.type == History::Definitions::TAXT ? hi.taxt.to_s : hi.to_taxt.to_s
    f.puts [hi.protonym_id, hi.position, hi.id, hi.type, hi.rank, hi.reference&.year, ranks[hi.protonym_id],
            text.gsub(/\s+/, ' ')[0, 300]].map { |v| v.to_s.tr("\t", ' ') }.join("\t")
    n += 1
  end
end
puts "Wrote #{n} history items to #{OUT}"
