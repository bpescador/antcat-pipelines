# frozen_string_literal: true
#
# higher_names_survey.rb  (READ-ONLY)
#
# Free-text history of genus-group and family-group protonyms, to decide which lines can become
# structured items and with which types.
#   1. Top shapes per rank group (tags as {tax N}, citations as {ref N}: P).
#   2. Lines of the form "<SUBJECT> <connector> [<OBJECT>][ (<extra>)]: CITATIONS." where SUBJECT is a
#      {tax}/{taxac} tag, e.g. "{tax A} in {tax B}: ...", "{tax A} as subgenus of {tax B}: ...",
#      "{tax A} as junior synonym of {tax B}: ...", "{tax A} as genus: ...". For each connector:
#      lines, citations only (no extra wording), subject = the protonym's terminal taxon, subject is
#      another taxon of this protonym (an earlier rank or combination), object rank, object's protonym
#      (for synonyms), adjacent same-key lines (would merge).
#   3. Lines already in the shape of an existing structured type (Junior/Senior synonym of {prott},
#      Misspelled as, Incertae sedis, Unidentifiable, homonyms) that were not converted.
#
# Output: /app/tmp/higher_names_survey.tsv (one row per line) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/higher_names_survey.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'higher_names_survey.tsv').to_s
F = Taxt::StandardHistoryItemFormats

GENUS = %w[GenusName SubgenusName].freeze
SPECIES = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze

def group_of(name_type)
  return 'species' if SPECIES.include?(name_type)
  GENUS.include?(name_type) ? 'genus' : 'family'
end

def shape(text)
  text.gsub(/\{ref \d+\}: #{F::PAGINATION_MANY}/, '{ref N}: P').
    gsub(/\{(misspelling|unmissing) [^}]*\}/, '{\1 X}').gsub(/\{([a-z]+) \d+\}/, '{\1 N}').
    gsub(/(\{ref N\}: P)(; \{ref N\}: P)+/, '\1; ...')
end

SUBJ = /\A\[?\{(?<stag>tax|taxac) (?<sid>\d+)\} /
# connector, then optional object tag, then optional extra words, then ": citations"
LINE = /\A(?<open>\[?)\{(?<stag>tax|taxac) (?<sid>\d+)\} (?<conn>[^{}:]*?)(?: \{(?<otag>tax|taxac|prott|prottac) (?<oid>\d+)\})?(?<extra>[^{}:]*?): (?<cites>#{F::CITATIONS})(?<stop>\.?)(?<close>\]?)\z/

protonyms = Protonym.joins(:name).where.not(names: { type: SPECIES }).pluck(:id, 'names.type').to_h
terminal = Taxon.where(protonym_id: protonyms.keys, status: Status::TERMINAL_STATUSES).group_by(&:protonym_id)
own_taxa = Taxon.where(protonym_id: protonyms.keys).pluck(:id, :protonym_id).to_h
items = HistoryItem.taxts_only.where(protonym_id: protonyms.keys).order(:protonym_id, :position).to_a
puts "Free-text items on genus- and family-group protonyms: #{items.size} (#{protonyms.size} protonyms)"

tag_ids = items.flat_map { |hi| hi.taxt.to_s.scan(/\{(?:tax|taxac) (\d+)\}/).flatten.map(&:to_i) }.uniq
taxa = Taxon.where(id: tag_ids).pluck(:id, :type, :name_cache, :protonym_id).to_h { |id, *rest| [id, rest] }

shapes = Hash.new { |h, k| h[k] = Hash.new(0) }
conn = Hash.new { |h, k| h[k] = Hash.new(0) }
rows = []
prev_key = {}
items.each do |hi|
  g = group_of(protonyms[hi.protonym_id])
  t = hi.taxt.to_s
  shapes[g][shape(t)] += 1
  m = t.match(LINE)
  unless m
    rows << [g, hi.protonym_id, hi.id, hi.position, 'other', '', '', '', '', '', t[0, 240]]
    prev_key[hi.protonym_id] = nil
    next
  end
  c = m[:conn].strip
  c = '(no connector)' if c.empty?
  label = "#{g}: #{c}#{m[:oid] ? ' {OBJ}' : ''}#{m[:extra].strip.empty? ? '' : ' +extra'}"
  sid = m[:sid].to_i
  term_ids = (terminal[hi.protonym_id] || []).map(&:id)
  subj =
    if term_ids.include?(sid) then 'terminal'
    elsif own_taxa[sid] == hi.protonym_id then 'own non-terminal'
    elsif taxa[sid] then 'other protonym'
    else 'missing'
    end
  orank = if m[:oid].nil? then '-'
          elsif %w[prott prottac].include?(m[:otag]) then 'protonym'
          else taxa[m[:oid].to_i]&.first || 'missing'
          end
  key = [label, sid, m[:oid]]
  merge = prev_key[hi.protonym_id] == key
  prev_key[hi.protonym_id] = key
  s = conn[label]
  s['lines'] += 1
  s['brackets'] += 1 if m[:open] == '['
  s['no final stop'] += 1 if m[:stop].empty?
  s["subject #{subj}"] += 1
  s["object #{orank}"] += 1
  s['adjacent same key (merge)'] += 1 if merge
  s["#{m[:stag]} subject"] += 1
  rows << [g, hi.protonym_id, hi.id, hi.position, label, subj, orank, m[:oid], merge ? 'merge' : '',
           m[:cites].scan(/\{ref \d+\}/).size, t[0, 240]]
end

%w[genus family].each do |g|
  n = shapes[g].values.sum
  puts "\n== #{g}-group: #{n} lines; top shapes"
  shapes[g].sort_by { -_2 }.first(40).each { |sh, k| puts format('  %5d  %s', k, sh[0, 150]) }
end

puts "\n== Lines '<subject> <connector> [<object>]: CITATIONS.' by connector (#{conn.values.sum { _1['lines'] }} lines)"
conn.sort_by { -_2['lines'] }.first(40).each do |label, s|
  puts format('  %5d  %s', s['lines'], label)
  puts "         #{s.except('lines').sort.map { |k, v| "#{k} #{v}" }.join('; ')}"
end

File.open(OUT, 'w') do |f|
  f.puts %w[group protonym_id history_item_id position label subject object_rank object_id merge citations taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "\nWrote #{OUT}"
