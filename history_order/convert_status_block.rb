# frozen_string_literal: true
#
# convert_status_block.rb
#
# Step 2 of the missing-combinations project, status block: converts free-text history items
#   Status as species: CITATIONS.
#   Junior synonym of {prott|prottac N}: CITATIONS.
#   Senior synonym of {prott|prottac N}: CITATIONS.
#   Subspecies of {prott|prottac|tax|taxac N}: CITATIONS.
# into structured StatusAsSpecies, JuniorSynonymOf, SeniorSynonymOf and SubspeciesOf items,
# one per citation. The first citation reuses the free-text item (same id, position, rank);
# further citations become new items inserted right after it, in the line's order.
# A {tax N} / {taxac N} object is used only when taxon N is the terminal taxon of its protonym
# (then {prott P} shows the same name); otherwise the line is not converted.
#
# Per protonym, inside one transaction:
#   1. render the page with AntCat's HistoryPresenter;
#   2. predict the page after conversion: each line unchanged, except that lines of one kind and
#      object that are next to each other merge into one, and citations inside a line are sorted
#      by reference year, keeping the editors' order within a year (PR #1593);
#      pages where two such lines would merge with another line between them are held;
#   3. convert, render again, and keep the change only if the page is exactly the prediction,
#      and each converted line shows the same object name as before (tags resolved by Detax).
#   Allowed visible changes (Brian, 2026-11-07): a final full stop added; adjacent lines for one
#   object merged; citations put in year order. Otherwise the protonym is rolled back and logged.
# MODE=check runs all of this and always rolls back. MODE=write keeps the protonyms that pass.
#
# Requires PR #1591 and PR #1593 to be deployed; refuses to run otherwise.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=comma-separated subset of status,junior,senior,subspecies (default all)
#         ONLY=protonym ids (comma-separated); LIMIT=n (first n protonyms)
# Output: /app/tmp/convert_status_block_<MODE>_<uuid>.tsv (one row per protonym)
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
#     bundle exec rails runner tmp/convert_status_block.rb

# Staging logs every SQL statement (debug level); keep the terminal readable and the run fast.
ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text status history (Status as species, Junior/Senior synonym of, ' \
               'Subspecies of) to structured history items (claude/HISTORY_ORDER.md)'

unless HistoryPresenter.private_method_defined?(:editor_sort_key) &&
       HistoryPresenter.private_method_defined?(:year_then_editor_sort_key)
  abort 'PRs #1591 and #1593 are not both deployed (HistoryPresenter); converting now would move lines.'
end

D = History::Definitions
F = Taxt::StandardHistoryItemFormats
KIND_DEFS = {
  'status' => { label: 'Status as species', type: D::STATUS_AS_SPECIES, object: false },
  'junior' => { label: 'Junior synonym of', type: D::JUNIOR_SYNONYM_OF, object: true },
  'senior' => { label: 'Senior synonym of', type: D::SENIOR_SYNONYM_OF, object: true },
  'subspecies' => { label: 'Subspecies of', type: D::SUBSPECIES_OF, object: true }
}
KINDS = (ENV['KINDS']&.split(',') || KIND_DEFS.keys).tap { |k| raise "unknown KINDS #{k}" unless (k - KIND_DEFS.keys).empty? }
LINE_RE = /\A(?<label>Status as species|Junior synonym of|Senior synonym of|Subspecies of)(?: \{(?<tag>prott|prottac|tax|taxac) (?<oid>\d+)\})?: (?<cites>#{F::CITATIONS})(?<stop>\.?)\z/
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/
LABEL_KIND = KIND_DEFS.to_h { |k, d| [d[:label], k] }

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_status_block_#{MODE}_#{uuid}.tsv").to_s

REF_YEARS = {}
def ref_year(rid)
  REF_YEARS.fetch(rid) { REF_YEARS[rid] = Reference.where(id: rid).pick(:year) }
end

# Parses a rendered or free-text line. Returns nil, or
# { kind:, label:, tag:, oid:, cites: [[rid, pages], ...], stop: }.
def parse(text)
  m = text.to_s.match(LINE_RE) or return
  kind = LABEL_KIND[m[:label]]
  return if KIND_DEFS[kind][:object] != m[:tag].present?
  cites = m[:cites].to_enum(:scan, CITE_RE).map { Regexp.last_match }
  return unless cites.map(&:to_s).join('; ') == m[:cites]
  { kind: kind, label: m[:label], tag: m[:tag], oid: m[:oid]&.to_i, stop: m[:stop],
    cites: cites.map { |c| [c[:rid].to_i, c[:pages]] } }
end

# The structured object for a parsed line: [object_protonym_id, force_author_citation], or a reason string.
def structured_object(p)
  return [nil, false] unless KIND_DEFS[p[:kind]][:object]
  flag = p[:tag].end_with?('ac')
  if p[:tag].start_with?('prott')
    return 'object protonym missing' unless Protonym.exists?(p[:oid])
  return 'object is the protonym itself' if p[:oid] == p[:self_id]
    return [p[:oid], flag]
  end
  taxon = Taxon.find_by(id: p[:oid]) or return 'object taxon missing'
  terminal = taxon.protonym&.terminal_taxon
  return 'object taxon is not the terminal taxon of its protonym' unless terminal&.id == taxon.id
  return 'object is the protonym itself' if taxon.protonym_id == p[:self_id]
  [taxon.protonym_id, flag]
end

def prefix(kind, object_id, flag)
  label = KIND_DEFS[kind][:label]
  return label unless object_id
  "#{label} {#{flag ? 'prottac' : 'prott'} #{object_id}}"
end

def old_prefix(p)
  p[:tag] ? "#{p[:label]} {#{p[:tag]} #{p[:oid]}}" : p[:label]
end

def line_text(kind, object_id, flag, cites)
  sorted = cites.each_with_index.sort_by { |(rid, _), i| [ref_year(rid) || -1, i] }.map(&:first)
  "#{prefix(kind, object_id, flag)}: #{sorted.map { |rid, pages| "{ref #{rid}}: #{pages}" }.join('; ')}."
end

def plan_line(hi)
  p = parse(hi.taxt) or return
  return unless KINDS.include?(p[:kind])
  p[:self_id] = hi.protonym_id
  obj = structured_object(p)
  return obj if obj.is_a?(String)
  object_id, flag = obj
  return 'force_author_citation not allowed for this type' if flag && !D::TYPE_DEFINITIONS[KIND_DEFS[p[:kind]][:type]][:allow_force_author_citation]
  return 'reference missing' unless p[:cites].all? { |rid, _| ref_year(rid) }
  return 'pages invalid' unless p[:cites].all? do |_, pages|
    pages.length <= HistoryItem::PAGES_MAX_LENGTH && pages.match?(HistoryItem::VALID_PAGES_REGEX)
  end
  return 'object name would change' if Detax[old_prefix(p)].to_s != Detax[prefix(p[:kind], object_id, flag)].to_s
  { kind: p[:kind], object_id: object_id, flag: flag, cites: p[:cites] }
end

class Reject < StandardError; end

def rendered_groups(protonym)
  HistoryPresenter.new(HistoryItem.where(protonym_id: protonym.id)).grouped_items
end

labels = KINDS.map { |k| KIND_DEFS[k][:label] }
protonym_ids = HistoryItem.taxts_only.where(labels.map { 'taxt LIKE ?' }.join(' OR '), *labels.map { |l| "#{l}%" }).
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
          [[plan[:kind], plan[:object_id], plan[:flag]], plan[:cites]]
        elsif g.items.all? { |i| i.type != D::TAXT } && (p = parse(g.taxt)) && KINDS.include?(p[:kind]) &&
              KIND_DEFS[p[:kind]][:type] == item.type
          [[p[:kind], item.object_protonym_id, item.force_author_citation?], p[:cites]]
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
      expected = merged.map { |key, payload| key ? line_text(*key, payload) : payload }

      plans.each do |item_id, plan|
        hi = HistoryItem.find(item_id)
        (rid, pages), *rest = plan[:cites]
        hi.update!(type: KIND_DEFS[plan[:kind]][:type], taxt: nil, force_author_citation: plan[:flag],
                   object_protonym_id: plan[:object_id], reference_id: rid, pages: pages)
        lines += 1
        rest.each_with_index do |(r2, p2), k|
          extra = protonym.history_items.create!(type: KIND_DEFS[plan[:kind]][:type], rank: hi.rank,
            force_author_citation: plan[:flag], object_protonym_id: plan[:object_id], reference_id: r2, pages: p2)
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
