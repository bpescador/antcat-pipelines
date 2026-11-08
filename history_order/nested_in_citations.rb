# frozen_string_literal: true
#
# nested_in_citations.rb
#
# Free-text history lines that cite a contribution inside another work as
#   "Author, in {ref P}: pages"      (e.g. "Bingham, in {ref 128157}: 98")
# cannot become structured items: a structured citation holds a reference and pages only. AntCat's
# way is a nested reference (author, year, title, "Pp. 97-99 in:" + parent P), cited as {ref N}.
#
# For each such citation this script looks for a nested reference under P whose authors include the
# author's surname (accents ignored) and whose pages include every cited page. Exactly one match ->
# the citation can be rewritten as "{ref N}: pages" (words before the author, e.g. "Also described
# as new by", stay). A line is rewritten only if every "in" citation in it has exactly one match.
# Everything else is listed for an editor: no nested reference (create it from the publication),
# no page match, or several matches.
#
# Displayed change (Brian, 2026-11-08: "good plan"): "Novák, in Novák & Sadil, 1941: 97" becomes
# "Novák, 1941: 97", linked to the nested reference (whose page says "in Novák & Sadil, 1941").
#
# Env:    MODE=check (default; saves nothing) | MODE=write (AntCatBot rewrites the matched lines)
#         ONLY=history item ids (comma-separated)
# Output: /app/tmp/nested_in_citations_<MODE>_<uuid>.tsv (one row per citation) and a summary.
# Edits:  AntCatBot, automated_edit: true, one request_uuid, an `update` activity per item.
#         A line is skipped if saving would also change other text (Taxt::Cleanup, Taxt::ConvertTags).
# Rollback of a write: PaperTrail versions by request_uuid (each version holds the previous taxt),
#         or the dump taken before the run.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/nested_in_citations.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
EDIT_SUMMARY = '[automated] Cite the nested reference instead of "Author, in {ref}" (claude/HISTORY_ORDER.md)'

F = Taxt::StandardHistoryItemFormats
IN_CITE = /(?<author>[[:upper:]][[:alpha:]'\-]*(?:(?: | & |-)[[:upper:]][[:alpha:]'\-]*)*), in \{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "nested_in_citations_#{MODE}_#{uuid}.tsv").to_s

def fold(text)
  I18n.transliterate(text.to_s).downcase
end

# Page numbers in a pagination string: "Pp. 9-102 in:" -> 9..102; "Pp. 144, 146, 147 in:" -> [144, 146, 147].
def page_set(pagination)
  pagination.to_s.scan(/(\d+)(?:\s*-\s*(\d+))?/).flat_map { |a, b| b ? (a.to_i..b.to_i).to_a : [a.to_i] }.to_set
end

def cited_pages(pages)
  pages.gsub(/\([^)]*\)/, '').scan(/\d+/).map(&:to_i)
end

def candidates(author, rid, pages)
  surname = fold(author.split(/ & |\s+/).last)
  nested = NestedReference.where(nesting_reference_id: rid).select { |n| fold(n.author_names_string_cache).include?(surname) }
  wanted = cited_pages(pages)
  by_page = nested.select { |n| wanted.any? && wanted.all? { |p| page_set(n.pagination).include?(p) } }
  [nested, by_page]
end

items = HistoryItem.taxts_only.where('taxt LIKE ?', '%, in {ref %')
items = items.where(id: ONLY) if ONLY
puts "MODE=#{MODE} request_uuid=#{uuid} items=#{items.count}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result history_item_id protonym_id author parent_ref parent pages nested_refs rewritten_to line].join("\t")

items.find_each do |hi|
  cites = hi.taxt.to_enum(:scan, IN_CITE).map { Regexp.last_match }
  next if cites.empty?
  new_taxt = hi.taxt.dup
  line_ok = true
  rows = cites.map do |c|
    rid = c[:rid].to_i
    nested, by_page = candidates(c[:author], rid, c[:pages])
    result =
      if nested.empty? then 'no nested reference'
      elsif by_page.empty? then 'no nested reference with these pages'
      elsif by_page.size > 1 then 'several nested references match'
      else 'match'
      end
    line_ok &&= result == 'match'
    new_taxt = new_taxt.sub(c[0], "{ref #{by_page.first.id}}: #{c[:pages]}") if result == 'match'
    [result, hi.id, hi.protonym_id, c[:author], rid, Reference.find_by(id: rid)&.key_with_suffixed_year,
     c[:pages], nested.map { |n| "#{n.id} #{n.key_with_suffixed_year} (#{n.pagination})" }.join('; '),
     result == 'match' ? by_page.first.id : '']
  end
  line_result =
    if !line_ok then 'line held'
    elsif Taxt::ConvertTags[Taxt::Cleanup[new_taxt]] != new_taxt then 'line held: saving would change other text'
    elsif MODE == 'write'
      hi.update!(taxt: new_taxt)
      hi.create_activity(Activity::UPDATE, bot, edit_summary: EDIT_SUMMARY).update_columns(automated_edit: true)
      'line rewritten'
    else 'line would be rewritten'
    end
  stats[line_result] += 1
  rows.each do |r|
    stats["citation: #{r[0]}"] += 1
    out.puts (r + [line_result]).map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
  end
end
out.close
stats.sort.each { |k, v| puts format('  %-60s %5d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
