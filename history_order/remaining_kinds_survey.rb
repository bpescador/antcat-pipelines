# frozen_string_literal: true
#
# remaining_kinds_survey.rb  (READ-ONLY)
#
# Shapes of the free-text species- and genus-group history lines of the kinds that have no structured
# type yet, to design the types: Misspelling, Material referred, First available use, Unidentifiable /
# incertae sedis, Also described as new, Emendation, Unnecessary replacement name.
# Kinds are assigned with the census rules (history_census2.rb). For each kind: line count, rank groups,
# and the top shapes (tags as {tax N}, {misspelling X}, citations as {ref N}: P).
#
# Output: /app/tmp/remaining_kinds_survey.tsv (one row per line) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/remaining_kinds_survey.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'remaining_kinds_survey.tsv').to_s
F = Taxt::StandardHistoryItemFormats

RULES = [
  ['(skip: error note)', /\((error|errors)\)/],
  ['(skip: form descriptions)', /^X: [^;()]*\((?:(?:ergatoid |putative )?[wqmlkseda]+\.(?:[wqmlkseda]+\.)* ?)+\)/],
  ['(skip: structured kinds)', /^(Lectotype|Neotype) designation|^Combination in|^Subspecies of|^Status as species|^(Junior synonym of|X as junior synonym)|^(Senior synonym of|X as senior synonym)/],
  ['(skip: revived status)', /^(Revived (from synonymy|status)|Raised to species)/],
  ['Misspelling', /^(Misspelled as|X: incorrect (subsequent|original) spelling)/],
  ['Emendation', /^((Justified|Unjustified) emendation|X: (un)?justified emendation)/],
  ['First available use', /^First available use/],
  ['(skip: unavailable infrasubspecific)', /(^As unavailable \(infrasubspecific\)|^Declared as unavailable|unavailable \(infrasubspecific\))/],
  ['Also described as new', /^(Also described as new|X also described as new)/],
  ['(skip: replacement names)', /^Replacement name/],
  ['Unnecessary replacement name', /^Unnecessary/],
  ['(skip: junior homonym)', /(^Junior (primary |secondary )?homonym|^Unresolved junior|^X junior (primary |secondary )?homonym)/],
  ['Material referred', /^Material (referred|of the)/],
  ['(skip: unavailable name)', /(^<i>Nomen nudum|^Unavailable name|^Unavailable replacement)/],
  ['Unidentifiable / incertae sedis', /(^Unidentifiable|incertae sedis<\/i>|^<i>Incertae sedis)/]
]
WANTED = RULES.map(&:first).reject { |k| k.start_with?('(') }

def kind_of(text)
  t = text.to_s.gsub(/\{[a-z]+\d? [^}]*\}/, 'X').sub(/\A[\[ ]+/, '')
  RULES.each { |k, re| return k if t.match?(re) }
  nil
end

def shape(text)
  text.gsub(/\{ref \d+\}: #{F::PAGINATION_MANY}/, '{ref N}: P').
    gsub(/\{(misspelling|unmissing) [^}]*\}/, '{\1 X}').gsub(/\{([a-z]+) \d+\}/, '{\1 N}').
    gsub(/(\{ref N\}: P)(; \{ref N\}: P)+/, '\1; ...')
end

def group_of(rank)
  case rank
  when 'SpeciesName', 'SubspeciesName', 'InfrasubspeciesName' then 'species'
  when 'GenusName', 'SubgenusName' then 'genus'
  else 'family'
  end
end

ranks = Protonym.joins(:name).pluck(:id, 'names.type').to_h
by_kind = Hash.new { |h, k| h[k] = Hash.new(0) }
groups = Hash.new { |h, k| h[k] = Hash.new(0) }
rows = []
HistoryItem.taxts_only.pluck(:protonym_id, :id, :taxt).each do |pid, id, text|
  k = kind_of(text)
  next unless WANTED.include?(k)
  by_kind[k][shape(text.to_s)] += 1
  groups[k][group_of(ranks[pid])] += 1
  rows << [k, group_of(ranks[pid]), pid, id, text.to_s[0, 220]]
end

WANTED.each do |k|
  total = by_kind[k].values.sum
  puts "\n== #{k}: #{total} lines (#{groups[k].sort.map { |g, n| "#{g} #{n}" }.join(', ')})"
  by_kind[k].sort_by { -_2 }.first(12).each { |s, n| puts format('  %5d  %s', n, s[0, 140]) }
end

File.open(OUT, 'w') do |f|
  f.puts %w[kind group protonym_id history_item_id taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "\nWrote #{OUT}"
