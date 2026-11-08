# frozen_string_literal: true
#
# convert_combination_in.rb
#
# Step 2 of the missing-combinations project: converts free-text history items
# "Combination in {tax N}: {ref R}: pages[; {ref R}: pages ...]." into structured
# CombinationIn items (object_taxon N, reference R, pages), one per citation.
# The first citation reuses the free-text item (same id, position, rank); further
# citations become new items inserted right after it.
#
# Per protonym, inside one transaction:
#   1. render the history with AntCat's HistoryPresenter (the catalog page);
#   2. convert every convertible "Combination in" line of that protonym;
#   3. render again and keep the change only if both hold:
#      a. every line that is not a parsed "Combination in" line has the same text, in the same order;
#      b. the parsed "Combination in" citations (tag, genus, reference, pages) are exactly the same set.
#      Allowed visible changes (decided by Brian, 2026-11-07): a final full stop added; two lines for
#      the same genus merged into one (placed at the first); citations put in date order.
#      Otherwise that protonym is rolled back and logged.
#   {taxac N} lines are converted with force_author_citation (needs PR #1592 deployed; held otherwise).
# MODE=check runs all of this and then always rolls back: a full test with the real
# code that saves nothing. MODE=write keeps the protonyms that pass.
#
# Requires PR #1591 (display in editors' order) to be deployed; refuses to run otherwise.
#
# Env:    MODE=check (default) | MODE=write
#         ONLY=protonym ids (comma-separated); LIMIT=n (first n protonyms)
# Output: /app/tmp/convert_combination_in_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid; an `update` activity per
#         converted item and a `create` activity per new item, like the editors' screens.
# Rollback of a write: none automatic; restore from the dump taken before the run, or
#         revert by request_uuid with PaperTrail versions (each item's previous taxt is in its version).
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_combination_in.rb

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text "Combination in" to a structured history item ' \
               '(claude/MISSING_COMBINATIONS_PLAN.md, step 2)'

unless HistoryPresenter.private_method_defined?(:editor_sort_key)
  abort 'PR #1591 is not deployed (HistoryPresenter has no editor_sort_key); converting now would move lines.'
end

F = Taxt::StandardHistoryItemFormats
LINE_RE = /\ACombination in \{(?<tag>tax|taxac) (?<tid>\d+)\}: (?<cites>#{F::CITATIONS})(?<stop>\.?)\z/
TAXAC_SUPPORTED = History::Definitions::TYPE_DEFINITIONS[History::Definitions::COMBINATION_IN][:allow_force_author_citation]
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_combination_in_#{MODE}_#{uuid}.tsv").to_s

def rendered(protonym)
  HistoryPresenter.new(HistoryItem.where(protonym_id: protonym.id)).grouped_items.map(&:taxt)
end

# [[tag, genus id, reference id, pages], ...] for a rendered "Combination in" line, or nil.
def parse_combo(text)
  m = text.to_s.match(LINE_RE) or return
  cites = m[:cites].to_enum(:scan, CITE_RE).map { Regexp.last_match }
  return unless cites.map(&:to_s).join('; ') == m[:cites]
  cites.map { |c| [m[:tag], m[:tid].to_i, c[:rid].to_i, c[:pages]] }
end

def plan_line(hi)
  m = hi.taxt.to_s.match(LINE_RE) or return
  return if m[:tag] == 'taxac' && !TAXAC_SUPPORTED
  return unless Taxon.where(id: m[:tid].to_i, type: %w[Genus Subgenus]).exists?

  cites = m[:cites].to_enum(:scan, CITE_RE).map { Regexp.last_match }
  return if cites.empty? || cites.map(&:to_s).join('; ') != m[:cites]
  return unless cites.all? { |c| Reference.exists?(c[:rid].to_i) }
  return unless cites.all? do |c|
    c[:pages].length <= HistoryItem::PAGES_MAX_LENGTH && c[:pages].match?(HistoryItem::VALID_PAGES_REGEX)
  end

  { object_taxon_id: m[:tid].to_i, taxac: m[:tag] == 'taxac', cites: cites.map { |c| [c[:rid].to_i, c[:pages]] } }
end

class Reject < StandardError; end

protonym_ids = HistoryItem.taxts_only.where('taxt LIKE ?', 'Combination in%').distinct.order(:protonym_id).pluck(:protonym_id)
protonym_ids &= ONLY if ONLY
protonym_ids = protonym_ids.first(LIMIT) if LIMIT
puts "MODE=#{MODE} request_uuid=#{uuid} protonyms=#{protonym_ids.size}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id lines_converted items_created detail].join("\t")

protonym_ids.each do |pid|
  protonym = Protonym.find(pid)
  lines = items = 0
  result = nil
  detail = ''
  begin
    ActiveRecord::Base.transaction do
      before = rendered(protonym)
      planned = protonym.history_items.where(type: History::Definitions::TAXT).to_a.filter_map do |hi|
        (plan = plan_line(hi)) && [hi, plan]
      end
      raise Reject, 'nothing convertible' if planned.empty?

      planned.each do |hi, plan|
        (rid, pages), *rest = plan[:cites]
        hi.update!(type: History::Definitions::COMBINATION_IN, taxt: nil, force_author_citation: plan[:taxac],
                   object_taxon_id: plan[:object_taxon_id], reference_id: rid, pages: pages)
        hi.create_activity(Activity::UPDATE, bot, edit_summary: EDIT_SUMMARY).update!(automated_edit: true)
        lines += 1
        rest.each_with_index do |(r2, p2), k|
          extra = protonym.history_items.create!(type: History::Definitions::COMBINATION_IN, rank: hi.rank,
            force_author_citation: plan[:taxac], object_taxon_id: plan[:object_taxon_id], reference_id: r2, pages: p2)
          extra.insert_at(hi.reload.position + k + 1)
          extra.create_activity(Activity::CREATE, bot, edit_summary: EDIT_SUMMARY).update!(automated_edit: true)
          items += 1
        end
      end

      after = rendered(protonym.reload)
      other_before = before.reject { |t| parse_combo(t) }
      other_after = after.reject { |t| parse_combo(t) }
      raise Reject, 'other lines changed' unless other_before == other_after
      cites_before = before.filter_map { |t| parse_combo(t) }.flatten(1).sort_by(&:inspect)
      cites_after = after.filter_map { |t| parse_combo(t) }.flatten(1).sort_by(&:inspect)
      raise Reject, 'combination citations differ' unless cites_before == cites_after
      result =
        if after == before then 'identical'
        elsif after.size == before.size && after.zip(before).all? { |a, b| a == b || a == "#{b}." }
          'identical_except_full_stop'
        elsif after.size < before.size then 'lines_merged'
        else 'citations_reordered'
        end
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    result = 'held'
    detail = e.message
    lines = items = 0
  rescue ActiveRecord::RecordInvalid => e
    result = 'error'
    detail = e.message
    lines = items = 0
  end
  result = "#{MODE == 'check' ? 'would_convert' : 'converted'} (#{result})" unless %w[held error].include?(result)
  stats[result] += 1
  stats['lines converted'] += lines
  stats['items created (extra citations)'] += items
  out.puts [result, pid, lines, items, detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-50s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
