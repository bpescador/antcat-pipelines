# frozen_string_literal: true
#
# convert_six_kinds.rb
#
# Step 2: converts free-text history items to the structured types added by AntCat PR #1598:
#   misspelled   [Misspelled as {misspelling X} by CITATIONS.]                      -> MisspelledAs
#   also         [Also described as new by CITATIONS.]                              -> AlsoDescribedAsNew
#   first_use    [First available use of {taxac|prottac N}; unavailable (infrasubspecific) name( ({ref R}: p)).]
#                                                                                   -> FirstAvailableUseUnavailableInfrasubspecific
#   material_to  Material referred to {tax|prott N} by CITATIONS.                   -> MaterialReferredTo
#   material_here Material of the unavailable name {tax N} referred here by CITATIONS. -> MaterialOfUnavailableNameReferredHere
#   incertae     <i>Incertae sedis</i> | Unidentifiable taxon; <i>incertae sedis</i> |
#                Unidentifiable to genus; <i>incertae sedis</i>  in {tax|prott N}: CITATIONS. -> IncertaeSedisIn
# One item per citation for the grouped types; first_use is one item per line (at most one citation).
# A {prott P} / {prottac P} object becomes the terminal taxon T of P, only if the name shown is the same.
#
# Per protonym, inside one transaction: render the page (HistoryPresenter); predict it (converted lines in
# structured form; adjacent lines with the same group key merge; citations by year, ties in editors'
# order); convert; render again; keep the change only if the page equals the prediction. Lines of one
# key that would merge across another line hold the protonym. Allowed visible changes (Brian,
# 2026-11-07): a final full stop added; adjacent same-key lines merged; citations in year order.
# MODE=check always rolls back. MODE=write keeps the protonyms that pass.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=comma-separated subset of misspelled,also,first_use,material_to,material_here,incertae (default all)
#         ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/convert_six_kinds_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: the dump taken before the run, or PaperTrail versions by request_uuid.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_six_kinds.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text history lines to structured history items (claude/HISTORY_ORDER.md)'

D = History::Definitions
abort 'PR #1598 is not deployed (no MisspelledAs type).' unless D::TYPE_DEFINITIONS.key?('MisspelledAs')
abort 'PR #1593 is not deployed.' unless HistoryPresenter.private_method_defined?(:year_then_editor_sort_key)

F = Taxt::StandardHistoryItemFormats
CITES = F::CITATIONS
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})/
PREFIXES = D::INCERTAE_SEDIS_IN_PREFIXES.invert # '<i>Incertae sedis</i>' => 'IncertaeSedis', ...

KIND_DEFS = {
  'misspelled' => {
    type: D::MISSPELLED_AS, grouped: true, like: '[Misspelled as {misspelling %',
    re: /\A\[Misspelled as \{misspelling (?<spelling>[^{}]+)\} by (?<cites>#{CITES})(?<stop>\.?)\]\z/,
    key: ->(m, _obj) { ['misspelled', m[:spelling]] },
    attrs: ->(m, _obj) { { text_value: m[:spelling] } },
    line: ->(key, _obj, body) { "[Misspelled as {misspelling #{key[1]}} by #{body}.]" }
  },
  'also' => {
    type: D::ALSO_DESCRIBED_AS_NEW, grouped: true, like: '[Also described as new by {ref %',
    re: /\A\[Also described as new by (?<cites>#{CITES})(?<stop>\.?)\]\z/,
    key: ->(_m, _obj) { ['also'] },
    attrs: ->(_m, _obj) { {} },
    line: ->(_key, _obj, body) { "[Also described as new by #{body}.]" }
  },
  'first_use' => {
    type: D::FIRST_AVAILABLE_USE_UNAVAILABLE_INFRASUBSPECIFIC, grouped: false, like: '[First available use of {%',
    re: /\A\[First available use of \{(?<tag>taxac|prottac) (?<oid>\d+)\}; unavailable \(infrasubspecific\) name(?: \((?<cites>\{ref \d+\}: #{F::PAGINATION_MANY})\))?\.\]\z/,
    object: :taxon_with_author,
    attrs: ->(_m, obj) { { object_taxon_id: obj } },
    line: ->(_key, obj, body) { "[First available use of {taxac #{obj}}; unavailable (infrasubspecific) name#{body ? " (#{body})" : ''}.]" }
  },
  'material_to' => {
    type: D::MATERIAL_REFERRED_TO, grouped: true, like: 'Material referred to {%',
    re: /\AMaterial referred to \{(?<tag>tax|prott) (?<oid>\d+)\} by (?<cites>#{CITES})(?<stop>\.?)\z/,
    object: :taxon,
    key: ->(_m, obj) { ['material_to', obj] },
    attrs: ->(_m, obj) { { object_taxon_id: obj } },
    line: ->(_key, obj, body) { "Material referred to {tax #{obj}} by #{body}." }
  },
  'material_here' => {
    type: D::MATERIAL_OF_UNAVAILABLE_NAME_REFERRED_HERE, grouped: true, like: 'Material of the unavailable name {%',
    re: /\AMaterial of the unavailable name \{(?<tag>tax) (?<oid>\d+)\} referred here by (?<cites>#{CITES})(?<stop>\.?)\z/,
    object: :taxon,
    key: ->(_m, obj) { ['material_here', obj] },
    attrs: ->(_m, obj) { { object_taxon_id: obj } },
    line: ->(_key, obj, body) { "Material of the unavailable name {tax #{obj}} referred here by #{body}." }
  },
  'incertae' => {
    type: D::INCERTAE_SEDIS_IN, grouped: true, like: ['<i>Incertae sedis</i> in {%', 'Unidentifiable t%'],
    re: /\A(?<prefix>#{PREFIXES.keys.map { |p| Regexp.escape(p) }.join('|')}) in \{(?<tag>tax|prott) (?<oid>\d+)\}: (?<cites>#{CITES})(?<stop>\.?)\z/,
    object: :taxon,
    key: ->(m, obj) { ['incertae', PREFIXES.fetch(m[:prefix]), obj] },
    attrs: ->(m, obj) { { subtype: PREFIXES.fetch(m[:prefix]), object_taxon_id: obj } },
    line: ->(key, obj, body) { "#{D::INCERTAE_SEDIS_IN_PREFIXES.fetch(key[1])} in {tax #{obj}}: #{body}." }
  }
}
KINDS = (ENV['KINDS']&.split(',') || KIND_DEFS.keys).tap { |k| raise "unknown KINDS #{k}" unless (k - KIND_DEFS.keys).empty? }

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_six_kinds_#{MODE}_#{uuid}.tsv").to_s

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
        else 'year_order_fixed'
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
