# frozen_string_literal: true
#
# history_census.rb  (READ-ONLY)
#
# Step 2 of the missing-combinations project: sizes the conversion of free-text
# (Taxt) history items to structured (relational) items.
#
# 1. Classifies every Taxt history item with AntCat's own recognizer
#    (Taxt::StandardHistoryItemFormats): convertible now (a relational type exists),
#    recognized but no relational type yet (candidate), deprecated, or free text.
#    "Combination in" lines with several citations, which the recognizer rejects,
#    are counted separately.
# 2. Per protonym: whether all its items would be structured after converting
#    what is convertible now.
# 3. Display-order impact. AntCat sorts history by type (structured types in a
#    fixed order, free text last at 999), then reference year, then position.
#    For each protonym with a "Combination in" line, it simulates converting only
#    the combination lines, and separately converting everything convertible,
#    and counts protonyms whose displayed order would change.
#
# Output: summary on stdout; /app/tmp/history_census_examples.tsv (sample rows per class).
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/history_census.rb

OUT = Rails.root.join('tmp', 'history_census_examples.tsv').to_s
F = Taxt::StandardHistoryItemFormats
TYPES = History::Definitions::TYPES
TAXT = History::Definitions::TAXT
COMBO = History::Definitions::COMBINATION_IN
MULTI_COMBO_RE = /\ACombination in \{(?:tax|taxac) \d+\}: #{F::CITATIONS}\.?\z/

def group_order_of(type)
  History::Definitions::TYPE_DEFINITIONS.fetch(type).fetch(:group_order)
end

stats = Hash.new(0)
by_type = Hash.new(0)
examples = Hash.new { |h, k| h[k] = [] }
per_protonym = Hash.new { |h, k| h[k] = [] } # protonym_id => [[id, current_type, convert_type, year, date, position, is_combo]]

HistoryItem.preload(:reference).find_each do |hi|
  year = hi.reference&.year
  date = hi.reference&.date
  if hi.type != TAXT
    stats['relational already'] += 1
    by_type["relational: #{hi.type}"] += 1
    per_protonym[hi.protonym_id] << [hi.id, hi.type, hi.type, year, date, hi.position, false]
    next
  end

  stats['taxt'] += 1
  f = F.new(hi.taxt)
  t = f.identified_type
  combo_line = hi.taxt.to_s.start_with?('Combination in ')
  convert_to =
    if t == TAXT && hi.taxt.to_s.match?(MULTI_COMBO_RE)
      klass = 'taxt: Combination in, several citations (convertible by splitting)'
      COMBO
    elsif t == TAXT
      klass = combo_line ? 'taxt: Combination in, other wording (not convertible as is)' : 'taxt: free text'
      nil
    elsif f.deprecated?
      klass = "taxt: deprecated format #{t}"
      nil
    elsif TYPES.include?(t)
      klass = "taxt: convertible now -> #{t}"
      t
    else
      klass = "taxt: recognized, no relational type yet (#{t})"
      nil
    end
  by_type[klass] += 1
  examples[klass] << [hi.id, hi.protonym_id, hi.taxt.to_s.truncate(160)] if examples[klass].size < 15
  # For the simulation the year of a taxt line is the reference year AntCat already uses (none for taxt:
  # taxt items have no reference row, so year is nil and they sort by position).
  per_protonym[hi.protonym_id] << [hi.id, TAXT, convert_to, nil, nil, hi.position, combo_line && convert_to == COMBO]
end

# Years for converted items: a converted item would carry the reference of its first citation.
# Approximation: take the first {ref N} in the line and look up its year.
ref_ids = []
HistoryItem.taxts_only.where('taxt LIKE ?', 'Combination in%').pluck(:id, :taxt).each do |id, taxt|
  rid = taxt[/\{ref (\d+)\}/, 1]
  ref_ids << [id, rid.to_i] if rid
end
ref_year = Reference.where(id: ref_ids.map(&:last).uniq).pluck(:id, :year, :date).to_h { |id, y, d| [id, [y, d]] }
combo_ref = ref_ids.to_h { |id, rid| [id, ref_year[rid]] }

sort_key = lambda do |type, year, date, position, id|
  [group_order_of(type), (year || -1), (Integer(date, exception: false) || -1).to_s, position || 0, id]
end
order = lambda do |rows, mode|
  rows.map do |id, cur, conv, year, date, pos, is_combo|
    type = cur
    y, d = year, date
    if cur == TAXT && conv && (mode == :all || (mode == :combo && conv == COMBO))
      type = conv
      y, d = combo_ref[id] || [nil, nil] if conv == COMBO
    end
    [sort_key.(type, y, d, pos, id), id]
  end.sort_by(&:first).map(&:last)
end

with_combo = per_protonym.select { |_, rows| rows.any? { |r| r[1] == TAXT && r[2] == COMBO } }
changed_combo = 0
changed_all = 0
fully_structured_after_all = 0
with_combo.each do |_pid, rows|
  now = order.(rows, :none)
  changed_combo += 1 if order.(rows, :combo) != now
  changed_all += 1 if order.(rows, :all) != now
  fully_structured_after_all += 1 if rows.all? { |r| r[1] != TAXT || r[2] }
end

protonyms_total = per_protonym.size
protonyms_all_convertible = per_protonym.count { |_, rows| rows.all? { |r| r[1] != TAXT || r[2] } }

File.open(OUT, 'w') do |f|
  f.puts %w[class history_item_id protonym_id taxt].join("\t")
  examples.each { |k, rows| rows.each { |r| f.puts [k, *r].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") } }
end

puts "History items: relational #{stats['relational already']}, taxt #{stats['taxt']}"
by_type.sort_by { |k, v| [k.start_with?('relational') ? 0 : 1, -v] }.each { |k, v| puts format('  %-85s %6d', k, v) }
puts "Protonyms with history: #{protonyms_total}; all items structured after converting what is convertible now: #{protonyms_all_convertible}"
puts "Protonyms with a convertible 'Combination in' line: #{with_combo.size}"
puts "  displayed order changes if ONLY combination lines are converted: #{changed_combo}"
puts "  displayed order changes if EVERYTHING convertible is converted:   #{changed_all}"
puts "  of these protonyms, fully structured after converting everything: #{fully_structured_after_all}"
puts "Wrote #{OUT}"
