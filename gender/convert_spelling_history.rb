# frozen_string_literal: true
#
# convert_spelling_history.rb
#
# Converts free-text incorrect-spelling history lines (left by the history conversion for the spelling work,
# 14 Nov 2026) to AntCat's structured type MisspelledAs (#1598), one item per citation (ICZN Art. 33.3: an
# incorrect subsequent spelling):
#   incorrect   [{misspelling X}: incorrect subsequent spelling by CITATIONS.]   -> [Misspelled as {misspelling X} by CITATIONS.]
#   misspelled  [Misspelled as {misspelling X} by CITATIONS.]                    -> the same, structured
# Lines with anything else ("and others", captions, notes) are not touched; they are listed for hand work.
# The machinery is history_order/convert_six_kinds.rb's (antcat-pipelines 06cf23f), unchanged:
# per protonym, inside one transaction, the page is rendered before, predicted, converted and rendered again,
# and the change is kept only if the page equals the prediction. Allowed visible changes: the wording above
# (Brian, 14 Nov 2026: incorrect subsequent spellings become "Misspelled as"), a final full stop, adjacent lines
# of one spelling merged, citations in year order. MODE=check always rolls back.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=incorrect,misspelled (default both); ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/convert_spelling_history_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: the dump taken before the run, or PaperTrail versions by request_uuid.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_spelling_history.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Incorrect subsequent spellings to structured "Misspelled as" items (ICZN Art. 33.3; claude/gender-etymology-roadmap-2026-11-12.md)'

D = History::Definitions
abort 'PR #1598 is not deployed (no MisspelledAs type).' unless D::TYPE_DEFINITIONS.key?('MisspelledAs')
abort 'PR #1593 is not deployed.' unless HistoryPresenter.private_method_defined?(:year_then_editor_sort_key)

F = Taxt::StandardHistoryItemFormats
CITES = F::CITATIONS
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/

KIND_DEFS = {
  'incorrect' => {
    type: D::MISSPELLED_AS, grouped: true, like: '[{misspelling %',
    re: /\A\[\{misspelling (?<spelling>[^{}]+)\}: incorrect subsequent spelling by (?<cites>#{CITES})(?<stop>\.?)\]\z/,
    key: ->(m, _obj) { ['misspelled', m[:spelling]] },
    attrs: ->(m, _obj) { { text_value: m[:spelling] } },
    line: ->(key, _obj, body) { "[Misspelled as {misspelling #{key[1]}} by #{body}.]" }
  },
  'misspelled' => {
    type: D::MISSPELLED_AS, grouped: true, like: '[Misspelled as {misspelling %',
    re: /\A\[Misspelled as \{misspelling (?<spelling>[^{}]+)\} by (?<cites>#{CITES})(?<stop>\.?)\]\z/,
    key: ->(m, _obj) { ['misspelled', m[:spelling]] },
    attrs: ->(m, _obj) { { text_value: m[:spelling] } },
    line: ->(key, _obj, body) { "[Misspelled as {misspelling #{key[1]}} by #{body}.]" }
  }
}
KINDS = (ENV['KINDS']&.split(',') || KIND_DEFS.keys).tap { |k| raise "unknown KINDS #{k}" unless (k - KIND_DEFS.keys).empty? }

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_spelling_history_#{MODE}_#{uuid}.tsv").to_s

REF_YEARS = {}
def ref_year(rid)
  REF_YEARS.fetch(rid) { REF_YEARS[rid] = Reference.where(id: rid).pick(:year) }
end

def cites_of(text)
  return [] if text.nil?
  list = text.to_enum(:scan, CITE_RE).map { Regexp.last_match }
  return if list.map(&:to_s).join('; ') != text
  list.map { |c| [c[:rid].to_i, c[:pages]] }
end

def body(cites)
  return nil if cites.empty?
  cites.each_with_index.sort_by { |(rid, _), i| [ref_year(rid) || -1, i] }.map(&:first).
    map { |rid, pages| "{ref #{rid}}: #{pages}" }.join('; ')
end

# Parses a line. Returns nil (not ours), a reason (held), or a plan hash.
def plan_text(text, kinds = KINDS)
  kinds.each do |kind|
    kd = KIND_DEFS[kind]
    m = text.to_s.match(kd[:re]) or next
    cites = cites_of(m[:cites]) or return 'citations not in the standard form'
    obj = nil
    if kd[:object]
      oid = m[:oid].to_i
      if m[:tag].start_with?('prott')
        protonym = Protonym.find_by(id: oid) or return 'object protonym missing'
        obj = protonym.terminal_taxon&.id or return 'object protonym has no terminal taxon'
        shown = kd[:object] == :taxon_with_author ? "{taxac #{obj}}" : "{tax #{obj}}"
        return 'object name would change' if Detax["{#{m[:tag]} #{oid}}"].to_s != Detax[shown].to_s
      else
        return 'object taxon missing' unless Taxon.exists?(oid)
        obj = oid
      end
    end
    return 'reference missing' unless cites.all? { |rid, _| ref_year(rid) }
    return 'pages invalid' unless cites.all? do |_, pages|
      pages.length <= HistoryItem::PAGES_MAX_LENGTH && pages.match?(HistoryItem::VALID_PAGES_REGEX)
    end
    if kd[:attrs].(m, obj)[:text_value]
      tv = kd[:attrs].(m, obj)[:text_value]
      return 'spelling invalid' unless tv.length <= HistoryItem::TEXT_VALUE_MAX_LENGTH && tv.match?(HistoryItem::VALID_TEXT_VALUE_REGEX)
    end
    key = kd[:grouped] ? kd[:key].(m, obj) : nil
    return { kind: kind, key: key, obj: obj, cites: cites, attrs: kd[:attrs].(m, obj) }
  end
  nil
end

class Reject < StandardError; end

likes = KINDS.flat_map { |k| Array(KIND_DEFS[k][:like]) }
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
  per_kind = Hash.new(0)
  begin
    ActiveRecord::Base.transaction do
      groups = HistoryPresenter.new(HistoryItem.where(protonym_id: pid)).grouped_items
      before = groups.map(&:taxt)
      plans = {}
      held = []
      groups.each do |g|
        next unless g.items.size == 1 && g.items.first.type == D::TAXT
        plan = plan_text(g.items.first.taxt)
        if plan.is_a?(String) then held << plan
        elsif plan then plans[g.items.first.id] = plan
        end
      end
      raise Reject, "nothing convertible#{held.any? ? " (#{held.uniq.join('; ')})" : ''}" if plans.empty?

      # Predict: converted lines in structured form; existing structured lines of our kinds take part in merging.
      predicted = groups.map do |g|
        item = g.items.first
        if (plan = plans[item.id])
          [plan[:key] || [plan[:kind], 'item', item.id], plan]
        elsif g.items.none? { |i| i.type == D::TAXT } && (p = plan_text(g.taxt, KIND_DEFS.keys)).is_a?(Hash) &&
              KIND_DEFS[p[:kind]][:type] == item.type
          [p[:key] || [p[:kind], 'item', item.id], p]
        else
          [nil, g.taxt]
        end
      end
      merged = []
      predicted.each do |key, payload|
        if key && merged.last && merged.last[0] == key
          merged.last[1] = merged.last[1].merge(cites: merged.last[1][:cites] + payload[:cites])
        else
          raise Reject, 'lines of one kind and key would merge across another line' if key && merged.any? { |k, _| k == key }
          merged << [key, payload]
        end
      end
      expected = merged.map do |key, payload|
        next payload unless key
        KIND_DEFS[payload[:kind]][:line].(key, payload[:obj], body(payload[:cites]))
      end

      plans.each do |item_id, plan|
        kd = KIND_DEFS[plan[:kind]]
        hi = HistoryItem.find(item_id)
        (rid, pages), *rest = plan[:cites]
        hi.update!({ type: kd[:type], taxt: nil, reference_id: rid, pages: pages }.merge(plan[:attrs]))
        lines += 1
        per_kind[plan[:kind]] += 1
        rest.each_with_index do |(r2, p2), k|
          extra = protonym.history_items.create!({ type: kd[:type], rank: hi.rank, reference_id: r2, pages: p2 }.merge(plan[:attrs]))
          PaperTrail.request(enabled: false) { extra.insert_at(hi.reload.position + k + 1) }
          items += 1
        end
      end
      protonym.create_activity(Activity::UPDATE, bot,
        edit_summary: "#{EDIT_SUMMARY} [#{lines} lines, #{lines + items} items]").update_columns(automated_edit: true)

      after = HistoryPresenter.new(HistoryItem.where(protonym_id: pid)).grouped_items.map(&:taxt)
      unless after == expected
        first = after.zip(expected).index { |a, e| a != e } || [after.size, expected.size].min
        raise Reject, "page differs from prediction at line #{first + 1}: got #{after[first].to_s[0, 110].inspect}, " \
                      "expected #{expected[first].to_s[0, 110].inspect}"
      end
      shown = after.size == before.size ? after.zip(before).map { |a, b| Detax[a].to_s == Detax[b].to_s ? :same : (Detax[a].to_s == Detax["#{b}."].to_s ? :stop : :other) } : []
      result =
        if after.size < before.size then 'lines_merged'
        elsif shown.all?(:same) then 'identical'
        elsif shown.none?(:other) then 'identical_except_full_stop'
        else 'reworded_or_year_order'
        end
      detail = held.uniq.join('; ')
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    result = 'held'
    detail = e.message
    lines = items = 0
    per_kind.clear
  rescue ActiveRecord::RecordInvalid => e
    result = 'error'
    detail = e.message
    lines = items = 0
    per_kind.clear
  end
  label = %w[held error].include?(result) ? result : "#{MODE == 'check' ? 'would_convert' : 'converted'} (#{result})"
  stats[label] += 1
  stats['lines converted'] += lines
  stats['items created (extra citations)'] += items
  per_kind.each { |k, v| stats["lines converted: #{k}"] += v }
  stats["held: #{detail.sub(/ at line \d+.*/, '').sub(/ \(.*/, '')}"] += 1 if result == 'held'
  out.puts [label, pid, lines, items, detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-70s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
