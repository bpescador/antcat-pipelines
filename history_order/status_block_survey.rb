# frozen_string_literal: true
#
# status_block_survey.rb  (READ-ONLY)
#
# Sizes step 2 for the status block: free-text history lines
#   Status as species: CITATIONS.
#   Junior synonym of {prott N}: CITATIONS.
#   Senior synonym of {prott N}: CITATIONS.
#   Subspecies of {tax|prott N}: CITATIONS.
# Reports, per kind: lines, how many parse in the standard format, the tag used,
# citations per line, citations already in date order (reference year, then date),
# pages that would fail validation, and pages where two lines of one kind and object
# would merge although other lines sit between them (status block chronology).
#
# Output: /app/tmp/status_block_survey.tsv (one row per line) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/status_block_survey.rb

OUT = Rails.root.join('tmp', 'status_block_survey.tsv').to_s
F = Taxt::StandardHistoryItemFormats
KINDS = {
  'Status as species' => /\AStatus as species: (?<cites>.*?)(?<stop>\.?)\z/,
  'Junior synonym of' => /\AJunior synonym of \{(?<tag>prott|prottac|tax|taxac) (?<oid>\d+)\}: (?<cites>.*?)(?<stop>\.?)\z/,
  'Senior synonym of' => /\ASenior synonym of \{(?<tag>prott|prottac|tax|taxac) (?<oid>\d+)\}: (?<cites>.*?)(?<stop>\.?)\z/,
  'Subspecies of' => /\ASubspecies of \{(?<tag>prott|prottac|tax|taxac) (?<oid>\d+)\}: (?<cites>.*?)(?<stop>\.?)\z/
}
STARTS = KINDS.keys
CITES_RE = /\A#{F::CITATIONS}\z/
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/

refs = {}
ref_info = ->(id) { refs.fetch(id) { refs[id] = Reference.where(id: id).pick(:year, :date) } }
taxon_protonym = {}
tp = ->(id) { taxon_protonym.fetch(id) { taxon_protonym[id] = Taxon.where(id: id).pick(:protonym_id) } }

def year_key(info, idx)
  year, date = info
  [(year || -1), (Integer(date.to_s, exception: false) || -1), idx]
end

stats = Hash.new(0)
rows = []
like = STARTS.map { 'taxt LIKE ?' }.join(' OR ')
items = HistoryItem.taxts_only.where(like, *STARTS.map { |s| "#{s}%" }).order(:protonym_id, :position, :id).to_a
by_protonym = HistoryItem.where(protonym_id: items.map(&:protonym_id).uniq).order(:position, :id).group_by(&:protonym_id)

items.each do |hi|
  kind = STARTS.find { |s| hi.taxt.start_with?(s) }
  m = hi.taxt.match(KINDS[kind])
  stats["#{kind}: lines"] += 1
  unless m && m[:cites].match?(CITES_RE)
    stats["#{kind}: not standard (extra wording)"] += 1
    rows << [kind, 'not_standard', hi.protonym_id, hi.id, '', '', '', hi.taxt[0, 200]]
    next
  end
  tag = m.names.include?('tag') ? m[:tag] : '-'
  stats["#{kind}: tag #{tag}"] += 1
  cites = m[:cites].to_enum(:scan, CITE_RE).map { Regexp.last_match }
  n = cites.size
  stats["#{kind}: citations"] += n
  stats["#{kind}: lines with 1 citation"] += 1 if n == 1
  problems = []
  problems << 'reference missing' if cites.any? { |c| ref_info.(c[:rid].to_i).nil? }
  problems << 'pages invalid' if cites.any? { |c| c[:pages].length > HistoryItem::PAGES_MAX_LENGTH || !c[:pages].match?(HistoryItem::VALID_PAGES_REGEX) }
  if %w[tax taxac].include?(tag)
    pid = tp.(m[:oid].to_i)
    problems << (pid ? 'tax tag (needs protonym)' : 'tax tag, taxon missing')
  end
  infos = cites.map { |c| ref_info.(c[:rid].to_i) || [nil, nil] }
  sorted = (0...n).sort_by { |i| year_key(infos[i], i) }
  in_order = sorted == (0...n).to_a
  stats["#{kind}: citations in date order"] += 1 if in_order
  stats["#{kind}: citations NOT in date order"] += 1 unless in_order
  same_year_tie = infos.map(&:first).compact.tally.values.any? { |v| v > 1 }
  stats["#{kind}: has two citations of one year"] += 1 if same_year_tie
  problems.each { |p| stats["#{kind}: #{p}"] += 1 }
  rows << [kind, problems.empty? ? 'standard' : problems.join('; '), hi.protonym_id, hi.id, tag, n, in_order ? 'in_order' : 'not_in_order', hi.taxt[0, 200]]
end

# Lines of one kind and object on one page that would merge, with other lines between.
items.group_by(&:protonym_id).each do |pid, list|
  page = by_protonym[pid].map(&:id)
  list.group_by do |hi|
    kind = STARTS.find { |s| hi.taxt.start_with?(s) }
    m = hi.taxt.match(KINDS[kind])
    oid = m && m.names.include?('oid') ? m[:oid] : nil
    [kind, oid]
  end.each do |(kind, _), same|
    next if same.size < 2
    idx = same.map { |hi| page.index(hi.id) }.sort
    adjacent = idx.each_cons(2).all? { |a, b| b == a + 1 }
    stats["#{kind}: pages with 2+ lines to merge, adjacent"] += 1 if adjacent
    stats["#{kind}: pages with 2+ lines to merge, NOT adjacent"] += 1 unless adjacent
  end
end

File.open(OUT, 'w') do |f|
  f.puts %w[kind result protonym_id history_item_id tag citations date_order taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "Free-text status-block lines: #{items.size} on #{by_protonym.size} protonyms"
stats.sort.each { |k, v| puts format('  %-62s %6d', k, v) }
puts "Wrote #{OUT}"
