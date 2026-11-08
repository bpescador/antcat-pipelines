# frozen_string_literal: true
#
# unavailable_infrasubspecific_survey.rb  (READ-ONLY)
#
# Shapes of the free-text "unavailable (infrasubspecific)" history lines, to design a structured type.
# Selection: the census rule (history_census2.rb): text starting "As unavailable (infrasubspecific)",
# "Declared as unavailable", or containing "unavailable (infrasubspecific)".
# For each line: a shape (tags as {tax N}, citations as {ref N}: P), whether it is
# "<label>: CITATIONS." with only standard citations, the label, the citation count, and the rank
# group and status of the protonym's terminal taxon.
#
# Output: /app/tmp/unavailable_infrasubspecific_survey.tsv (one row per line) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/unavailable_infrasubspecific_survey.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'unavailable_infrasubspecific_survey.tsv').to_s
F = Taxt::StandardHistoryItemFormats
STANDARD = /\A(?<label>[^{}:]+?): (?<cites>#{F::CITATIONS})(?<stop>\.?)\z/

def shape(text)
  text.gsub(/\{ref \d+\}: #{F::PAGINATION_MANY}/, '{ref N}: P').gsub(/\{([a-z]+) \d+\}/, '{\1 N}').
    gsub(/(\{ref N\}: P)(; \{ref N\}: P)+/, '\1; ...')
end

items = HistoryItem.taxts_only.where(
  "taxt LIKE 'As unavailable (infrasubspecific)%' OR taxt LIKE 'Declared as unavailable%' OR " \
  "taxt LIKE '%unavailable (infrasubspecific)%' OR taxt LIKE '[As unavailable (infrasubspecific)%'"
).includes(protonym: [:name, :terminal_taxa])

shapes = Hash.new(0)
labels = Hash.new(0)
stats = Hash.new(0)
rows = []
items.find_each do |hi|
  t = hi.taxt.to_s
  stats['lines'] += 1
  shapes[shape(t)] += 1
  m = t.match(STANDARD)
  if m
    labels[m[:label]] += 1
    n = m[:cites].scan(/\{ref \d+\}/).size
    stats['standard "<label>: CITATIONS."'] += 1
    stats['  with 1 citation'] += 1 if n == 1
    stats['  without final full stop'] += 1 if m[:stop].empty?
  else
    stats['other shapes'] += 1
  end
  stats["protonym rank: #{hi.protonym&.name&.type}"] += 1
  statuses = hi.protonym&.terminal_taxa&.map(&:status)&.uniq&.join('/')
  stats["terminal taxon status: #{statuses.presence || 'none'}"] += 1
  rows << [m ? 'standard' : 'other', m ? m[:label] : '', hi.protonym_id, hi.id, hi.position, t[0, 220]]
end

stats.sort.each { |k, v| puts format('  %-60s %6d', k, v) }
puts "\nLabels of the standard lines:"
labels.sort_by { -_2 }.first(15).each { |l, n| puts format('  %6d  %s', n, l) }
puts "\nTop shapes:"
shapes.sort_by { -_2 }.first(30).each { |s, n| puts format('  %6d  %s', n, s[0, 150]) }

File.open(OUT, 'w') do |f|
  f.puts %w[result label protonym_id history_item_id position taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "Wrote #{OUT}"
