# frozen_string_literal: true
#
# convert_forms_and_types.rb
#
# Step 2, next kinds: converts free-text history items
#   {ref R}: pages (forms)[; {ref R}: pages (forms) ...]      -> FormDescriptions, one item per citation
#   Lectotype designation: {ref R}: pages.                     -> TypeSpecimenDesignation (LectotypeDesignation)
#   Neotype designation: {ref R}: pages.                       -> TypeSpecimenDesignation (NeotypeDesignation)
# Form descriptions group by type alone (all on a page show as one line); type designations do not group
# and hold one citation, so only single-citation designation lines are converted.
# Same method as convert_status_block.rb (2026-11-08):
#
# Per protonym, inside one transaction:
#   1. render the page with AntCat's HistoryPresenter;
#   2. predict the page after conversion: each line unchanged, except that lines of one kind and
#      object that are next to each other merge into one, and citations inside a line are sorted
#      by reference year, keeping the editors' order within a year (PR #1593);
#      pages where two such lines would merge with another line between them are held;
#   3. convert, render again, and keep the change only if the page is exactly the prediction,
#      (result labels compare the page as displayed, tags resolved by Detax).
#   Allowed visible changes (Brian, 2026-11-07): a final full stop added; adjacent form-description
#   lines merged; citations put in year order. Otherwise the protonym is rolled back and logged.
# MODE=check runs all of this and always rolls back. MODE=write keeps the protonyms that pass.
#
# Requires PR #1591 and PR #1593 to be deployed; refuses to run otherwise.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=comma-separated subset of forms,lectotype,neotype (default all)
#         ONLY=protonym ids (comma-separated); LIMIT=n (first n protonyms)
# Output: /app/tmp/convert_forms_and_types_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid. One `update` activity per protonym
#         (not per item: about 164,000 items would flood the activity feed), written without an
#         extra version. PaperTrail versions record every item (update or create); the position
#         shift of a new item is not versioned separately.
# Result: compares the page as displayed (tags resolved to names): {tax N} to {prott P} with the
#         same name counts as identical.
# Rollback of a write: restore from the dump taken before the run, or revert by request_uuid
#         with PaperTrail versions (each converted item's version holds its previous taxt).
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_forms_and_types.rb

# Staging logs every SQL statement (debug level); keep the terminal readable and the run fast.
ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text form descriptions and lectotype/neotype designations ' \
               'to structured history items (claude/HISTORY_ORDER.md)'

unless HistoryPresenter.private_method_defined?(:editor_sort_key) &&
       HistoryPresenter.private_method_defined?(:year_then_editor_sort_key)
  abort 'PRs #1591 and #1593 are not both deployed (HistoryPresenter); converting now would move lines.'
end

D = History::Definitions
F = Taxt::StandardHistoryItemFormats
KIND_DEFS = {
  'forms' => { type: D::FORM_DESCRIPTIONS, groups: true },
  'lectotype' => { type: D::TYPE_SPECIMEN_DESIGNATION, subtype: D::LECTOTYPE_DESIGNATION, label: 'Lectotype designation' },
  'neotype' => { type: D::TYPE_SPECIMEN_DESIGNATION, subtype: D::NEOTYPE_DESIGNATION, label: 'Neotype designation' }
}
KINDS = (ENV['KINDS']&.split(',') || KIND_DEFS.keys).tap { |k| raise "unknown KINDS #{k}" unless (k - KIND_DEFS.keys).empty? }
FORM_CITE = "\\{ref (?<rid>\\d+)\\}: (?<pages>#{F::PAGINATION_MANY}) \\((?<forms>[^;(){}]+)\\)"
FORM_CITE_PLAIN = FORM_CITE.gsub(/\(\?<\w+>/, '(?:')
FORMS_RE = /\A(?<cites>#{FORM_CITE_PLAIN}(?:; #{FORM_CITE_PLAIN})*)(?<stop>\.?)\z/
FORM_CITE_RE = /#{FORM_CITE}/
# What may stand in the brackets: form abbreviations (w. q. m. l. k. e. s. d. a., combined, e.g. q.m.) and
# AntCat's known form words (Taxt::StandardHistoryItemFormats FORMS_NON_STANDARD).
FORM_WORDS = %w[ergatoid putative polymorphic subapterous brachypterous gynandromorph ergatandromorph pseudogyne gynecoid]
FORM_TOKEN = /\A(?:(?:[a-z]{1,2}\.)+|#{FORM_WORDS.join('|')})\z/
def forms_ok?(text)
  tokens = text.split(' ')
  tokens.any? && tokens.all? { |t| t.match?(FORM_TOKEN) }
end
DESIG_RE = /\A(?<label>Lectotype designation|Neotype designation): \{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})(?<stop>\.?)\z/

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_forms_and_types_#{MODE}_#{uuid}.tsv").to_s

REF_YEARS = {}
def ref_year(rid)
  REF_YEARS.fetch(rid) { REF_YEARS[rid] = Reference.where(id: rid).pick(:year) }
end

# Parses a rendered or free-text line: nil, or { kind:, cites: [[rid, pages, forms_or_nil], ...] }.
def parse(text)
  t = text.to_s
  if (m = t.match(DESIG_RE))
    kind = m[:label].start_with?('Lecto') ? 'lectotype' : 'neotype'
    return { kind: kind, cites: [[m[:rid].to_i, m[:pages], nil]] }
  end
  m = t.match(FORMS_RE) or return
  cites = m[:cites].to_enum(:scan, FORM_CITE_RE).map { Regexp.last_match }
  return unless cites.map(&:to_s).join('; ') == m[:cites]
  { kind: 'forms', cites: cites.map { |c| [c[:rid].to_i, c[:pages], c[:forms]] } }
end

def cite_text(rid, pages, forms)
  forms ? "{ref #{rid}}: #{pages} (#{forms})" : "{ref #{rid}}: #{pages}"
end

def line_text(kind, cites)
  sorted = cites.each_with_index.sort_by { |(rid, _, _), i| [ref_year(rid) || -1, i] }.map(&:first)
  body = sorted.map { |c| cite_text(*c) }.join('; ')
  KIND_DEFS[kind][:label] ? "#{KIND_DEFS[kind][:label]}: #{body}." : "#{body}."
end

def plan_line(hi)
  p = parse(hi.taxt) or return
  return unless KINDS.include?(p[:kind])
  return 'designation with more than one citation' if !KIND_DEFS[p[:kind]][:groups] && p[:cites].size > 1
  return 'reference missing' unless p[:cites].all? { |rid, _, _| ref_year(rid) }
  return 'pages invalid' unless p[:cites].all? do |_, pages, _|
    pages.length <= HistoryItem::PAGES_MAX_LENGTH && pages.match?(HistoryItem::VALID_PAGES_REGEX)
  end
  return 'forms not recognised' unless p[:cites].all? { |_, _, forms| forms.nil? || forms_ok?(forms) }
  return 'forms invalid' unless p[:cites].all? do |_, _, forms|
    forms.nil? || (forms.strip == forms && forms.length <= HistoryItem::TEXT_VALUE_MAX_LENGTH &&
                   forms.match?(HistoryItem::VALID_TEXT_VALUE_REGEX))
  end
  { kind: p[:kind], cites: p[:cites] }
end

class Reject < StandardError; end

def rendered_groups(protonym)
  HistoryPresenter.new(HistoryItem.where(protonym_id: protonym.id)).grouped_items
end

likes = []
likes << '{ref %' if KINDS.include?('forms')
likes << 'Lectotype designation: %' if KINDS.include?('lectotype')
likes << 'Neotype designation: %' if KINDS.include?('neotype')
protonym_ids = HistoryItem.taxts_only.where(likes.map { 'taxt LIKE ?' }.join(' OR '), *likes).
  distinct.order(:protonym_id).pluck(:protonym_id)
protonym_ids &= ONLY if ONLY
protonym_ids = protonym_ids.first(LIMIT) if LIMIT
puts "MODE=#{MODE} KINDS=#{KINDS.join(',')} request_uuid=#{uuid} protonyms=#{protonym_ids.size}"

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
      groups = rendered_groups(protonym)
      before = groups.map(&:taxt)
      plans = {}
      held_lines = []
      groups.each do |g|
        next unless g.items.size == 1 && g.items.first.type == D::TAXT
        plan = plan_line(g.items.first)
        if plan.is_a?(String) then held_lines << plan
        elsif plan then plans[g.items.first.id] = plan
        end
      end
      raise Reject, "nothing convertible#{held_lines.any? ? " (#{held_lines.uniq.join('; ')})" : ''}" if plans.empty?

      # Predict the page: [key or nil, text] per line, then merge adjacent lines with the same key.
      predicted = groups.map do |g|
        item = g.items.first
        if (plan = plans[item.id])
          [KIND_DEFS[plan[:kind]][:groups] ? [plan[:kind]] : [plan[:kind], item.id], plan[:cites]]
        elsif g.items.all? { |i| i.type != D::TAXT } && (p = parse(g.taxt)) && KINDS.include?(p[:kind]) &&
              KIND_DEFS[p[:kind]][:type] == item.type
          [KIND_DEFS[p[:kind]][:groups] ? [p[:kind]] : [p[:kind], item.id], p[:cites]]
        else
          [nil, g.taxt]
        end
      end
      merged = []
      predicted.each do |key, payload|
        if key && merged.last && merged.last[0] == key
          merged.last[1] += payload
        else
          raise Reject, 'lines of one kind and object would merge across another line' if key && merged.any? { |k, _| k == key }
          merged << [key, key ? payload.dup : payload]
        end
      end
      expected = merged.map { |key, payload| key ? line_text(key.first, payload) : payload }

      plans.each do |item_id, plan|
        hi = HistoryItem.find(item_id)
        kd = KIND_DEFS[plan[:kind]]
        (rid, pages, forms), *rest = plan[:cites]
        hi.update!(type: kd[:type], subtype: kd[:subtype], taxt: nil, text_value: forms, reference_id: rid, pages: pages)
        lines += 1
        rest.each_with_index do |(r2, p2, f2), k|
          extra = protonym.history_items.create!(type: kd[:type], subtype: kd[:subtype], rank: hi.rank,
            text_value: f2, reference_id: r2, pages: p2)
          PaperTrail.request(enabled: false) { extra.insert_at(hi.reload.position + k + 1) }
          items += 1
        end
      end

      protonym.create_activity(Activity::UPDATE, bot,
        edit_summary: "#{EDIT_SUMMARY} [#{lines} lines, #{lines + items} items]").update_columns(automated_edit: true)

      after = rendered_groups(protonym.reload).map(&:taxt)
      unless after == expected
        first = after.zip(expected).index { |a, e| a != e } || [after.size, expected.size].min
        raise Reject, "page differs from prediction at line #{first + 1}: got #{after[first].to_s[0, 120].inspect}"
      end
      shown_before = before.map { |t| Detax[t].to_s }
      shown_after = after.map { |t| Detax[t].to_s }
      result =
        if shown_after == shown_before then 'identical'
        elsif shown_after.size == shown_before.size &&
              shown_after.zip(shown_before).all? { |a, b| a == b || a == "#{b}." }
          'identical_except_full_stop'
        elsif after.size < before.size then 'lines_merged'
        else 'year_order_fixed'
        end
      detail = held_lines.uniq.join('; ')
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
  label = %w[held error].include?(result) ? result : "#{MODE == 'check' ? 'would_convert' : 'converted'} (#{result})"
  stats[label] += 1
  stats['lines converted'] += lines
  stats['items created (extra citations)'] += items
  stats["held: #{detail.sub(/ at line \d+.*/, '').sub(/ \(.*/, '')}"] += 1 if result == 'held'
  out.puts [label, pid, lines, items, detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-70s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
