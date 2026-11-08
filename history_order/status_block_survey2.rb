# frozen_string_literal: true
#
# status_block_survey2.rb  (READ-ONLY)
#
# Follow-up to status_block_survey.rb, two questions:
# 1. "Subspecies of {tax N}" lines: is N the terminal taxon of its protonym? If so,
#    {prott <protonym of N>} shows the same name and conversion changes nothing visible.
# 2. Lines whose citations are not in date order: is it a real year inversion
#    (a later year listed before an earlier one), or only the order inside one year?
#
# Output: /app/tmp/status_block_survey2.tsv (rows needing a look) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/status_block_survey2.rb

OUT = Rails.root.join('tmp', 'status_block_survey2.tsv').to_s
F = Taxt::StandardHistoryItemFormats
STARTS = ['Status as species', 'Junior synonym of', 'Senior synonym of', 'Subspecies of']
LINE_RE = /\A(?<kind>Status as species|(?:Junior synonym of|Senior synonym of|Subspecies of) \{(?<tag>prott|prottac|tax|taxac) (?<oid>\d+)\}): (?<cites>#{F::CITATIONS})\.?\z/
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/

refs = {}
ref_info = ->(id) { refs.fetch(id) { refs[id] = Reference.where(id: id).pick(:year, :date) || [nil, nil] } }
stats = Hash.new(0)
rows = []
like = STARTS.map { 'taxt LIKE ?' }.join(' OR ')

HistoryItem.taxts_only.where(like, *STARTS.map { |s| "#{s}%" }).find_each do |hi|
  m = hi.taxt.match(LINE_RE) or next
  kind = STARTS.find { |s| m[:kind].start_with?(s) }

  if kind == 'Subspecies of' && %w[tax taxac].include?(m[:tag])
    taxon = Taxon.find_by(id: m[:oid].to_i)
    terminal = taxon&.protonym&.terminal_taxon
    result =
      if taxon.nil? then 'taxon missing'
      elsif terminal.nil? then 'protonym has no terminal taxon'
      elsif terminal.id == taxon.id then 'is terminal taxon (same display)'
      else 'not terminal (display would change)'
      end
    stats["Subspecies of {tax}: #{result}"] += 1
    unless result.start_with?('is terminal')
      rows << ['subspecies_tag', result, hi.protonym_id, hi.id, "#{taxon&.name_cache} -> #{terminal&.name_cache}", hi.taxt[0, 160]]
    end
  end

  infos = m[:cites].to_enum(:scan, CITE_RE).map { ref_info.(Regexp.last_match[:rid].to_i) }
  keys = infos.each_with_index.map { |(y, d), i| [(y || -1), (Integer(d.to_s, exception: false) || -1), i] }
  next if keys.sort == keys
  years = infos.map { |y, _| y || -1 }
  inversion = years.each_cons(2).any? { |a, b| a > b }
  missing_year = years.include?(-1)
  what = if missing_year then 'reference without year'
         elsif inversion then 'year inversion'
         else 'same-year order only'
         end
  stats["#{kind}: not in date order: #{what}"] += 1
  rows << ['date_order', what, hi.protonym_id, hi.id, years.join(' '), hi.taxt[0, 160]] unless what == 'same-year order only'
end

File.open(OUT, 'w') do |f|
  f.puts %w[check result protonym_id history_item_id detail taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
stats.sort.each { |k, v| puts format('  %-66s %6d', k, v) }
puts "Wrote #{OUT}"
