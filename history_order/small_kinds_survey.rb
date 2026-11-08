# frozen_string_literal: true
#
# small_kinds_survey.rb  (READ-ONLY)
#
# Sizes step 2 for the small kinds that have structured types:
#   [Junior primary homonym of {taxac N} ({ref R}: pages).]   -> JuniorPrimaryHomonymOf
#   [Junior secondary homonym of {taxac N} ({ref R}: pages).] -> JuniorSecondaryHomonymOf
#   Replacement name: {taxac N} ({ref R}: pages).             -> HomonymReplacedBy
#   Replacement name for {taxac N} ({ref R}: pages).          -> ReplacementNameFor
#   Unavailable name ({ref R}: pages).                        -> UnavailableName
# The citation is optional in every structured form. These types always render {taxac}.
# Reports per kind: lines with the prefix, lines in exactly the structured form, tag used ({tax} would
# gain an author citation), with/without citation, and the variants that are not in the structured form.
# Also the cross-page effect: a structured ReplacementNameFor appends the homonym lines of the replaced
# taxon's protonym, but only structured ones; so converting a homonym line can change another page.
#
# Output: /app/tmp/small_kinds_survey.tsv (one row per line) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/small_kinds_survey.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'small_kinds_survey.tsv').to_s
F = Taxt::StandardHistoryItemFormats
PAG = F::PAGINATION_MANY
CIT = "(?: \\(\\{ref (?<rid>\\d+)\\}: (?<pages>#{PAG})\\))?"
OBJ = "\\{(?<tag>taxac|tax) (?<oid>\\d+)\\}"
KINDS = {
  'Junior primary homonym of' => [/\A\[Junior primary homonym of #{OBJ}#{CIT}\.\]\z/, '[Junior primary homonym of'],
  'Junior secondary homonym of' => [/\A\[Junior secondary homonym of #{OBJ}#{CIT}\.\]\z/, '[Junior secondary homonym of'],
  'Replacement name (homonym replaced by)' => [/\AReplacement name: #{OBJ}#{CIT}\.\z/, 'Replacement name:'],
  'Replacement name for' => [/\AReplacement name for #{OBJ}#{CIT}\.(?<trail>.*)\z/, 'Replacement name for'],
  'Unavailable name' => [/\AUnavailable name#{CIT}\.\z/, 'Unavailable name']
}

def shape(text)
  text.gsub(/\{([a-z]+) \d+\}/, '{\1 N}').gsub(/\{ref N\}: [^;)\]]+/, '{ref N}: P')[0, 90]
end

stats = Hash.new(0)
variants = Hash.new { |h, k| h[k] = Hash.new(0) }
rows = []
homonym_taxa = Hash.new { |h, k| h[k] = [] } # protonym id -> lines converting to homonym types

KINDS.each do |kind, (re, prefix)|
  HistoryItem.taxts_only.where('taxt LIKE ?', "#{prefix}%").find_each do |hi|
    stats["#{kind}: lines with prefix"] += 1
    m = hi.taxt.match(re)
    unless m
      variants[kind][shape(hi.taxt)] += 1
      rows << [kind, 'not standard', hi.protonym_id, hi.id, hi.taxt[0, 200]]
      next
    end
    tag = m.names.include?('tag') ? m[:tag] : '-'
    stats["#{kind}: standard, tag #{tag}"] += 1
    stats["#{kind}: standard, #{m[:rid] ? 'with' : 'without'} citation"] += 1
    if m.names.include?('trail')
      stats["#{kind}: standard, #{m[:trail].empty? ? 'no trailer' : 'trailer text after the line'}"] += 1
    end
    problems = []
    problems << 'reference missing' if m[:rid] && !Reference.exists?(m[:rid].to_i)
    problems << 'pages invalid' if m[:rid] && !m[:pages].match?(HistoryItem::VALID_PAGES_REGEX)
    problems << 'object taxon missing' if m.names.include?('oid') && !Taxon.exists?(m[:oid].to_i)
    problems.each { |p| stats["#{kind}: #{p}"] += 1 }
    homonym_taxa[hi.protonym_id] << hi.id if kind.start_with?('Junior')
    rows << [kind, problems.empty? ? "standard #{tag}" : problems.join('; '), hi.protonym_id, hi.id, hi.taxt[0, 200]]
  end
end

# Cross-page effect: pages whose "Replacement name for {taxac T}" (free text or structured) names a taxon
# of a protonym that has a homonym line we would convert.
taxon_protonym = Taxon.where(protonym_id: homonym_taxa.keys).pluck(:id, :protonym_id).to_h
rnf_free = HistoryItem.taxts_only.where('taxt LIKE ?', 'Replacement name for {%').pluck(:protonym_id, :taxt)
rnf_struct = HistoryItem.where(type: History::Definitions::REPLACEMENT_NAME_FOR).pluck(:protonym_id, :object_taxon_id)
affected_free = rnf_free.count { |_, t| (id = t[/\AReplacement name for \{(?:taxac|tax) (\d+)\}/, 1]) && taxon_protonym[id.to_i] }
affected_struct = rnf_struct.count { |_, tid| taxon_protonym[tid] }
stats['cross-page: free-text Replacement name for lines naming such a taxon'] = affected_free
stats['cross-page: structured ReplacementNameFor items naming such a taxon'] = affected_struct
stats['structured items now: ' + History::Definitions::REPLACEMENT_NAME_FOR] = rnf_struct.size

File.open(OUT, 'w') do |f|
  f.puts %w[kind result protonym_id history_item_id taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
stats.sort.each { |k, v| puts format('  %-78s %6d', k, v) }
variants.each do |kind, h|
  puts "Top non-standard shapes, #{kind}:"
  h.sort_by { |_, n| -n }.first(6).each { |s, n| puts format('  %5d  %s', n, s) }
end
puts "Wrote #{OUT}"
