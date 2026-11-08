# frozen_string_literal: true
#
# status_block_survey3.rb  (READ-ONLY)
#
# Same-year citation order in status-block lines. AntCat's display breaks same-year
# ties by the reference's publication date (`references.date`, read as a number),
# then by the editors' order. For each same-year pair the display would swap, says
# whether both references have a readable date (a real chronological fix) or not.
# Also shows the formats found in references.date.
#
# Output: /app/tmp/status_block_survey3.tsv (one row per swapped pair) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/status_block_survey3.rb

OUT = Rails.root.join('tmp', 'status_block_survey3.tsv').to_s
F = Taxt::StandardHistoryItemFormats
STARTS = ['Status as species', 'Junior synonym of', 'Senior synonym of', 'Subspecies of']
LINE_RE = /\A(?:Status as species|(?:Junior synonym of|Senior synonym of|Subspecies of) \{(?:prott|prottac|tax|taxac) \d+\}): (?<cites>#{F::CITATIONS})\.?\z/
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/

def shape(date)
  return 'empty' if date.blank?
  date.to_s.gsub(/\d/, '9')
end

puts 'references.date formats (all references):'
Reference.pluck(:date).map { |d| shape(d) }.tally.sort_by { |_, n| -n }.first(12).each { |s, n| puts format('  %-20s %7d', s, n) }

refs = {}
info = ->(id) { refs.fetch(id) { refs[id] = Reference.where(id: id).pick(:year, :date, :year_suffix) || [nil, nil, nil] } }
num = ->(d) { Integer(d.to_s, exception: false) }
stats = Hash.new(0)
rows = []
like = STARTS.map { 'taxt LIKE ?' }.join(' OR ')

HistoryItem.taxts_only.where(like, *STARTS.map { |s| "#{s}%" }).find_each do |hi|
  m = hi.taxt.match(LINE_RE) or next
  rids = m[:cites].to_enum(:scan, CITE_RE).map { Regexp.last_match[:rid].to_i }
  infos = rids.map { |r| info.(r) }
  kind = STARTS.find { |s| hi.taxt.start_with?(s) }
  line_kinds = []
  rids.each_index.to_a.combination(2).each do |i, j|
    yi, di, si = infos[i]
    yj, dj, sj = infos[j]
    next unless yi && yi == yj
    ki = num.(di) || -1
    kj = num.(dj) || -1
    next unless ki > kj # editors put i before j; display puts j first
    why =
      if num.(di) && num.(dj) then 'both dates readable'
      elsif di.blank? || dj.blank? then 'a date is empty'
      else 'a date is unreadable'
      end
    suffix = si.present? && sj.present? ? (si < sj ? 'editors follow year suffix' : 'editors against year suffix') : 'no suffix on one'
    line_kinds << why
    stats["pairs: #{why}"] += 1
    stats["pairs: #{why}; #{suffix}"] += 1
    rows << [kind, hi.protonym_id, hi.id, why, suffix, "#{yi}#{si} #{di.inspect}", "#{yj}#{sj} #{dj.inspect}"]
  end
  next if line_kinds.empty?
  stats["lines: #{kind}: #{line_kinds.uniq.size == 1 && line_kinds.first == 'both dates readable' ? 'all swaps have both dates' : 'some swap lacks a readable date'}"] += 1
end

File.open(OUT, 'w') do |f|
  f.puts %w[kind protonym_id history_item_id why suffix editors_first display_first].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
stats.sort.each { |k, v| puts format('  %-75s %6d', k, v) }
puts "Wrote #{OUT}"
