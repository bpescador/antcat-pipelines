# frozen_string_literal: true
#
# history_census2.rb  (READ-ONLY)
#
# Progress census for step 2 (structured history items), after the conversions of 7 and 8 Nov 2026.
#   1. History items by type (structured types, and free text).
#   2. Free-text lines classified by kind, per rank group (species-group, genus-group, family-group),
#      with the same rules as history_order/history_order_classify.py; and whether AntCat has a
#      structured type for that kind.
#   3. Protonyms: how many have only structured history, only free text, or both.
#
# Output: /app/tmp/history_census2.tsv (one row per free-text item: protonym, rank, kind, text start)
#         and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/history_census2.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'history_census2.tsv').to_s

RULES = [ # [kind, regex on the text with tags replaced by X and a leading "[" removed, structured type exists?]
  ['OTHER (error note)', /\((error|errors)\)/, false],
  ['Form descriptions', /^X: [^;()]*\((?:(?:ergatoid |putative )?[wqmlkseda]+\.(?:[wqmlkseda]+\.)* ?)+\)/, true],
  ['Lecto/neotype designation', /^(Lectotype|Neotype) designation/, true],
  ['Combination in', /^Combination in/, true],
  ['Subspecies of', /^Subspecies of/, true],
  ['Status as species', /^Status as species/, true],
  ['Revived status / raised to species', /^(Revived (from synonymy|status)|Raised to species)/, false],
  ['Junior synonym of', /^(Junior synonym of|X as junior synonym)/, true],
  ['Senior synonym of', /^(Senior synonym of|X as senior synonym)/, true],
  ['Misspelling / incorrect spelling', /^(Misspelled as|X: incorrect (subsequent|original) spelling)/, false],
  ['Emendation', /^((Justified|Unjustified) emendation|X: (un)?justified emendation)/, false],
  ['First available use', /^First available use/, false],
  ['Unavailable infrasubspecific', /(^As unavailable \(infrasubspecific\)|^Declared as unavailable|unavailable \(infrasubspecific\))/, false],
  ['Also described as new', /^(Also described as new|X also described as new)/, false],
  ['Replacement name for', /^Replacement name for/, true],
  ['Replacement name (homonym replaced by)', /^Replacement name:/, true],
  ['Unnecessary replacement name', /^Unnecessary/, false],
  ['Junior homonym', /(^Junior (primary |secondary )?homonym|^Unresolved junior|^X junior (primary |secondary )?homonym)/, true],
  ['Material referred', /^Material (referred|of the)/, false],
  ['Unavailable name / nomen nudum', /(^<i>Nomen nudum|^Unavailable name|^Unavailable replacement)/, true],
  ['Unidentifiable / incertae sedis', /(^Unidentifiable|incertae sedis<\/i>|^<i>Incertae sedis)/, false],
  ['Excluded', /(excluded from|^Excluded from)/, false],
  ['Higher placement (X in X, X as genus ...)', /^X (in X|as (genus|subgenus|tribe|subtribe|subfamily|family|group))/, false],
  ['Type-species', /^Type-species/, false],
  ['Note', /^Note/, false],
  ['Transferred to', /^Transferred to/, false]
]

def kind_of(text)
  t = text.to_s.gsub(/\{[a-z]+\d? [^}]*\}/, 'X').sub(/\A[\[ ]+/, '')
  RULES.each { |k, re, structured| return [k, structured] if t.match?(re) }
  ['OTHER', false]
end

def group_of(rank)
  case rank
  when 'SpeciesName', 'SubspeciesName', 'InfrasubspeciesName' then 'species-group'
  when 'GenusName', 'SubgenusName' then 'genus-group'
  else 'family-group'
  end
end

taxt = History::Definitions::TAXT
by_type = HistoryItem.group(:type).count
total = by_type.values.sum
puts "History items: #{total}"
puts "  structured: #{total - by_type[taxt].to_i}   free text: #{by_type[taxt].to_i}"
by_type.sort_by { -_2 }.each { |t, n| puts format('    %-40s %7d', t, n) }

ranks = Protonym.joins(:name).pluck(:id, 'names.type').to_h
kinds = Hash.new(0)
convertible_type = Hash.new(0)
rows = []
HistoryItem.where(type: taxt).pluck(:protonym_id, :id, :taxt).each do |pid, id, text|
  g = group_of(ranks[pid])
  k, structured = kind_of(text)
  kinds[[g, k, structured]] += 1
  rows << [pid, g, k, structured ? 'type exists' : 'no type', id, text.to_s[0, 160]]
end

%w[species-group genus-group family-group].each do |g|
  n = kinds.select { |(gg, _, _), _| gg == g }.values.sum
  puts "\nFree text, #{g}: #{n} lines"
  kinds.select { |(gg, _, _), _| gg == g }.sort_by { -_2 }.each do |(_, k, s), v|
    puts format('  %6d  %-46s %s', v, k, s ? '(structured type exists: extra wording or held)' : '')
  end
end

per = HistoryItem.group(:protonym_id).pluck(:protonym_id, Arel.sql("SUM(type = '#{taxt}')"), Arel.sql("SUM(type <> '#{taxt}')"))
fully = per.count { |_, f, s| f.to_i.zero? && s.to_i.positive? }
none = per.count { |_, f, s| s.to_i.zero? }
mixed = per.size - fully - none
puts "\nProtonyms with history: #{per.size}"
puts "  only structured: #{fully}   both: #{mixed}   only free text: #{none}"
per_group = Hash.new { |h, k| h[k] = [0, 0, 0] }
per.each do |pid, f, s|
  i = f.to_i.zero? ? 0 : (s.to_i.zero? ? 2 : 1)
  per_group[group_of(ranks[pid])][i] += 1
end
per_group.sort.each { |g, (a, b, c)| puts format('    %-14s only structured %6d  both %6d  only free text %6d', g, a, b, c) }

File.open(OUT, 'w') do |f|
  f.puts %w[protonym_id group kind type_status history_item_id taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "Wrote #{OUT}"
