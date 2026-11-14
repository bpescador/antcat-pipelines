# frozen_string_literal: true
#
# history_next_survey.rb  (READ-ONLY)
#
# Sizes the three candidates for the next step-2 work (2026-11-14):
#   A. New free text: history items created per month since 2025-11, free text vs structured, and who
#      created them (PaperTrail create versions: AntCatBot vs editors). Free-text items created since
#      2026-11-07 that already have the shape of a structured type.
#   B. Citation notes: free-text lines with " [...]" right after a citation's pages, by rank group and by
#      the kind of note ({tax}/{taxac}/{pro} name, provisional, by implication, other). And how many such
#      lines would be in a standard shape if the notes were removed.
#   C. The remaining species-group free text: top shapes of the lines that start like a structured kind
#      but are not standard (extra wording), and of the unclassified ones.
#
# Output: summary only.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/history_next_survey.rb

ActiveRecord::Base.logger = nil
F = Taxt::StandardHistoryItemFormats
TAXT = History::Definitions::TAXT
SPECIES = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze
GENUS = %w[GenusName SubgenusName].freeze
PAG = F::PAGINATION_MANY
NOTE_RE = /(?<cite>\{ref \d+\}: #{PAG}) \[(?<note>[^\[\]]*)\]/

def group_of(t) = SPECIES.include?(t) ? 'species' : (GENUS.include?(t) ? 'genus' : 'family')

def shape(text)
  text.gsub(/\{ref \d+\}: #{PAG}/, '{ref N}: P').gsub(/\{(misspelling|unmissing) [^}]*\}/, '{\1 X}').
    gsub(/\{([a-z]+) \d+\}/, '{\1 N}').gsub(/(\{ref N\}: P)(; \{ref N\}: P)+/, '\1; ...')
end

# Standard shapes the converters accept (citations only after the label), any rank.
STANDARD = [
  /\A\[?(Status as species|Junior synonym of \{[a-z]+ \d+\}|Senior synonym of \{[a-z]+ \d+\}|Subspecies of \{[a-z]+ \d+\}|Combination in \{[a-z]+ \d+\}|As unavailable \(infrasubspecific\) name|Declared as unavailable \(infrasubspecific\) name|Material referred to \{[a-z]+ \d+\} by|<i>Incertae sedis<\/i> in \{[a-z]+ \d+\}|Unidentifiable taxon; <i>incertae sedis<\/i> in \{[a-z]+ \d+\}|Misspelled as \{misspelling [^}]+\} by|Also described as new by|\{[a-z]+ \d+\} (in [^:]+|<i>incertae sedis<\/i> in \{[a-z]+ \d+\}|as genus|as (subgenus|tribe|subtribe|subfamily) of \{[a-z]+ \d+\}|as (junior|senior) synonym of \{[a-z]+ \d+\})):? (#{F::CITATIONS})\.?\]?\z/,
  /\A\{ref \d+\}: #{PAG} \([^()]+\)\.?\z/ # form descriptions
].freeze
def standard?(t) = STANDARD.any? { |re| t.match?(re) }

ranks = Protonym.joins(:name).pluck(:id, 'names.type').to_h
bot_id = User.find_by!(name: 'AntCatBot').id.to_s

puts '== A. New history items per month (created_at), free text vs structured'
HistoryItem.where('created_at >= ?', Date.new(2025, 11, 1)).
  group(Arel.sql("DATE_FORMAT(created_at, '%Y-%m')"), Arel.sql("type = '#{TAXT}'")).count.
  sort.group_by { |(m, _), _| m }.each do |m, rows|
    h = rows.to_h { |(_, taxt), n| [taxt.to_i == 1 ? 'free text' : 'structured', n] }
    puts format('  %s  free text %6d   structured %7d', m, h['free text'].to_i, h['structured'].to_i)
  end

since = Date.new(2026, 11, 7)
new_free = HistoryItem.taxts_only.where('created_at >= ?', since)
creators = PaperTrail::Version.where(item_type: 'HistoryItem', event: 'create', item_id: new_free.select(:id)).
  pluck(:item_id, :whodunnit).to_h
by_who = new_free.pluck(:id).group_by { |id| creators[id] == bot_id ? 'AntCatBot' : (creators[id] ? "user #{creators[id]}" : 'no version') }
puts "\nFree-text items created since #{since}: #{new_free.count}"
by_who.sort_by { -_2.size }.each { |w, ids| puts format('  %-14s %5d', w, ids.size) }
editor_new = new_free.where.not(id: by_who['AntCatBot'] || [])
std_new = editor_new.select { |hi| standard?(hi.taxt.to_s) }
puts "  of the editors' ones, already in a structured type's shape: #{std_new.size}"
std_new.first(8).each { |hi| puts "    #{hi.id} (protonym #{hi.protonym_id}): #{hi.taxt.to_s[0, 110]}" }
edited = PaperTrail::Version.where(item_type: 'HistoryItem', event: 'update').where('created_at >= ?', since).
  where.not(whodunnit: bot_id).distinct.count(:item_id)
puts "  history items edited by editors since #{since}: #{edited}"

puts "\n== B. Citation notes (\" [...]\" after a citation's pages) in free text"
notes = Hash.new(0)
lines = Hash.new(0)
fixable = Hash.new(0)
HistoryItem.taxts_only.pluck(:protonym_id, :taxt).each do |pid, t|
  t = t.to_s
  found = t.scan(NOTE_RE)
  next if found.empty?
  g = group_of(ranks[pid])
  lines[g] += 1
  found.each do |_, note|
    kind = if note.match?(/\A\{(tax|taxac|pro|prott|prottac|unmissing) [^}]+\}\z/) then 'a name ({tax} etc.)'
           elsif note.match?(/\Aprovisional\z/i) then 'provisional'
           elsif note.match?(/by implication/i) then 'by implication...'
           elsif note.match?(/\A(as |in )/) then 'as/in ...'
           else 'other'
           end
    notes[kind] += 1
  end
  fixable[g] += 1 if standard?(t.gsub(NOTE_RE, '\k<cite>'))
end
puts "  lines with notes: #{lines.sort.map { |g, n| "#{g} #{n}" }.join(', ')} (total #{lines.values.sum})"
puts "  standard shape once notes are removed: #{fixable.sort.map { |g, n| "#{g} #{n}" }.join(', ')} (total #{fixable.values.sum})"
puts "  notes by kind: #{notes.sort_by { -_2 }.map { |k, n| "#{k} #{n}" }.join('; ')}"

puts "\n== C. Species-group free text, by first words, and top shapes"
first = Hash.new(0)
shapes = Hash.new(0)
HistoryItem.taxts_only.pluck(:protonym_id, :taxt).each do |pid, t|
  next unless group_of(ranks[pid]) == 'species'
  t = t.to_s
  next if t.match?(NOTE_RE) || t.match?(/\A\[?Note/) || t.match?(/emendation|incorrect (subsequent|original) spelling|Misspelled/)
  lead = t.gsub(/\{[a-z]+\d? [^}]*\}/, 'X').sub(/\A[\[ ]+/, '')[/\A[^:;,.(]{0,40}/]
  first[lead.strip] += 1
  shapes[shape(t)] += 1
end
puts "  (citation notes, Notes and spelling lines left out)"
first.sort_by { -_2 }.first(30).each { |k, n| puts format('  %5d  %s', n, k) }
puts "  top shapes:"
shapes.sort_by { -_2 }.first(40).each { |k, n| puts format('  %5d  %s', n, k[0, 150]) }
