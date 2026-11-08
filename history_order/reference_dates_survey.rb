# frozen_string_literal: true
#
# reference_dates_survey.rb  (READ-ONLY)
#
# Publication dates of references (`references.date`). For references without a date:
# their type, whether they are nested and the parent (nesting reference) has a date,
# and whether history items cite them. Also: dates whose year differs from the
# reference's year, and the precision of the dates (year, month, day).
#
# Output: /app/tmp/reference_dates_survey.tsv (references without an effective date,
#         cited by history items, most cited first) and a summary.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/reference_dates_survey.rb

OUT = Rails.root.join('tmp', 'reference_dates_survey.tsv').to_s

def norm(date)
  return if date.blank?
  digits = date.delete('-?')
  digits if digits.match?(/\A\d{4}(\d\d){0,2}\z/)
end

refs = Reference.pluck(:id, :type, :year, :date, :nesting_reference_id, :key_with_suffixed_year_cache)
by_id = refs.to_h { |r| [r[0], r] }
cited = HistoryItem.where.not(reference_id: nil).group(:reference_id).count
cited_in_taxt = Hash.new(0)
HistoryItem.taxts_only.where('taxt LIKE ?', '%{ref %').pluck(:taxt).each do |t|
  t.scan(/\{ref (\d+)\}/) { cited_in_taxt[Regexp.last_match(1).to_i] += 1 }
end

stats = Hash.new(0)
rows = []
refs.each do |id, type, year, date, parent_id, key|
  own = norm(date)
  stats["all: #{type}"] += 1
  if own
    stats["dated: precision #{{ 4 => 'year', 6 => 'month', 8 => 'day' }[own.size]}"] += 1
    stats['dated: year differs from reference year'] += 1 if own[0, 4].to_i != year
    next
  end
  stats["no own date: #{type}#{date.present? ? ' (unreadable)' : ''}"] += 1
  parent = by_id[parent_id]
  parent_date = parent && norm(parent[3])
  effective = parent_date ? 'parent has date' : (parent ? 'parent has no date' : 'not nested')
  stats["no own date: #{effective}"] += 1
  uses = cited[id].to_i + cited_in_taxt[id]
  stats["no own date, cited in history: #{effective}"] += 1 if uses.positive?
  stats["no own date, history citations: #{effective}"] += uses
  next if parent_date || uses.zero?
  rows << [id, type, year, date.inspect, parent_id, uses, key]
end

File.open(OUT, 'w') do |f|
  f.puts %w[reference_id type year date nesting_reference_id history_citations key].join("\t")
  rows.sort_by { |r| -r[5] }.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "References: #{refs.size}"
stats.sort.each { |k, v| puts format('  %-60s %7d', k, v) }
puts "Wrote #{OUT}"
