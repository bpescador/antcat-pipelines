# frozen_string_literal: true
#
# convert_small_kinds_2.rb
#
# Step 2: converts small species-group kinds to structured history items (AntCat #1618 for the new types; #1616
# for citation notes):
#   unresolved   [Unresolved junior primary|secondary homonym of {taxac|prottac N}( (CITATION)).]  -> UnresolvedJuniorHomonymOf
#   unnecessary  Unnecessary replacement name for {taxac|prottac N}( (CITATION)).               -> UnnecessaryReplacementNameFor
#   unidentifiable  Unidentifiable taxon: CITATIONS.                                             -> UnplacedUnidentifiableTaxon (#1619)
#   subgenus     Subgenus indeterminate: CITATIONS.                                              -> SubgenusIndeterminate
#   duplicated   [Duplicated in CITATIONS.]                                                      -> DuplicatedIn
#   nomen_nudum  [{unmissing NAME} CITATIONS. <i>Nomen nudum</i>.]                               -> NomenNudumCitation
#   combination  Combination in {tax|taxac N}: CITATIONS.  (lines held on 7 Nov only for a note)  -> CombinationIn
#   designation  Lectotype|Neotype designation: CITATION.  (held on 8 Nov only for a note)        -> TypeSpecimenDesignation
# A citation may carry a note ("(redundant)", "(in {tax N} species group)"), kept as citation_note.
# A {prottac P} object becomes the terminal taxon T of P, only if the name shown is the same.
#
# Per protonym, inside one transaction: render the page; predict it (adjacent same-key lines merge; citations
# by year, ties in editors' order); convert; render again; keep the change only if the page equals the
# prediction AND every changed line has the same words and the same citations as before (only a final full
# stop or the order of citations may change; Brian, 2026-11-07).
# MODE=check always rolls back. MODE=write keeps the protonyms that pass.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=comma-separated subset of unresolved,unnecessary,unidentifiable,subgenus,duplicated,nomen_nudum,
#               combination,designation (default all)
#         ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/convert_small_kinds_2_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: the dump taken before the run, or PaperTrail versions by request_uuid.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_small_kinds_2.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text history lines to structured history items (claude/HISTORY_ORDER.md)'

D = History::Definitions
abort 'PR #1619 is not deployed (no UnplacedUnidentifiableTaxon type).' unless D::TYPE_DEFINITIONS.key?('UnplacedUnidentifiableTaxon')
abort 'PR #1616 is not deployed (no citation_note).' unless HistoryItem.column_names.include?('citation_note')
abort 'PR #1593 is not deployed.' unless HistoryPresenter.private_method_defined?(:year_then_editor_sort_key)

F = Taxt::StandardHistoryItemFormats
# A note printed right after a citation ("[Myrmicidae]", "[provisional]", "(see note in bibliography)") goes to
# the item's citation_note (AntCat #1616), so the page stays the same.
NOTE = '(?: (?<note>\\[[^\\[\\];]*\\]|\\([^();]*\\)))?'
NOTE_ANON = '(?: (?:\\[[^\\[\\];]*\\]|\\([^();]*\\)))?'
CITE_ANON = "\\{ref \\d+\\}: #{F::PAGINATION_MANY}#{NOTE_ANON}"
CITATIONS_WITH_NOTES = "#{CITE_ANON}(?:; #{CITE_ANON})*"
CITE_RE = /\{ref (?<rid>\d+)\}: (?<pages>#{F::PAGINATION_MANY})#{NOTE}/
NOTE_OK = ->(note) { note.nil? || (note.length <= HistoryItem::CITATION_NOTE_MAX_LENGTH && note.match?(HistoryItem::VALID_CITATION_NOTE_REGEX)) }
def cite_text(rid, pages, note) = "{ref #{rid}}: #{pages}#{" #{note}" if note}"
CITES = CITATIONS_WITH_NOTES
CITE_ONE = CITE_ANON
END_RE = "(?<cites>#{CITES})(?<stop>\\.?)"
OPT_CITE = "(?: \\((?<cites>#{CITE_ONE})\\))?"
DESIG = { 'Lectotype designation' => 'LectotypeDesignation', 'Neotype designation' => 'NeotypeDesignation' }.freeze
UNRESOLVED = D::UNRESOLVED_HOMONYM_KINDS.invert # 'primary' => 'Primary'

KIND_DEFS = {
  'unresolved' => {
    type: D::UNRESOLVED_JUNIOR_HOMONYM_OF, object: :taxon_with_author,
    re: /\A\[Unresolved junior (?<kind>primary|secondary) homonym of \{(?<tag>taxac|prottac) (?<oid>\d+)\}#{OPT_CITE}\.\]\z/,
    attrs: ->(m, obj) { { subtype: UNRESOLVED.fetch(m[:kind]), object_taxon_id: obj } },
    line: ->(m, obj, body) { "[Unresolved junior #{m[:kind]} homonym of {taxac #{obj}}#{" (#{body})" if body}.]" }
  },
  'unnecessary' => {
    type: D::UNNECESSARY_REPLACEMENT_NAME_FOR, object: :taxon_with_author,
    re: /\AUnnecessary replacement name for \{(?<tag>taxac|prottac) (?<oid>\d+)\}#{OPT_CITE}(?<stop>\.?)\z/,
    attrs: ->(_m, obj) { { object_taxon_id: obj } },
    line: ->(_m, obj, body) { "Unnecessary replacement name for {taxac #{obj}}#{" (#{body})" if body}." }
  },
  'unidentifiable' => {
    type: D::UNPLACED_UNIDENTIFIABLE_TAXON, grouped: true,
    re: /\AUnidentifiable taxon: #{END_RE}\z/,
    key: ->(_m, _obj) { ['unidentifiable'] },
    attrs: ->(_m, _obj) { {} },
    gline: ->(_key, _obj, body) { "Unidentifiable taxon: #{body}." }
  },
  'subgenus' => {
    type: D::SUBGENUS_INDETERMINATE, grouped: true,
    re: /\ASubgenus indeterminate: #{END_RE}\z/,
    key: ->(_m, _obj) { ['subgenus'] },
    attrs: ->(_m, _obj) { {} },
    gline: ->(_key, _obj, body) { "Subgenus indeterminate: #{body}." }
  },
  'duplicated' => {
    type: D::DUPLICATED_IN, grouped: true,
    re: /\A\[Duplicated in (?<cites>#{CITES})\.\]\z/,
    key: ->(_m, _obj) { ['duplicated'] },
    attrs: ->(_m, _obj) { {} },
    gline: ->(_key, _obj, body) { "[Duplicated in #{body}.]" }
  },
  'nomen_nudum' => {
    type: D::NOMEN_NUDUM_CITATION, grouped: true,
    re: /\A\[\{unmissing (?<name>[^{}]+)\} (?<cites>#{CITES})\. <i>Nomen nudum<\/i>\.\]\z/,
    key: ->(m, _obj) { ['nomen_nudum', m[:name]] },
    attrs: ->(m, _obj) { { text_value: m[:name] } },
    gline: ->(key, _obj, body) { "[{unmissing #{key[1]}} #{body}. <i>Nomen nudum</i>.]" }
  },
  'combination' => {
    type: D::COMBINATION_IN, grouped: true, object: :taxon_any,
    re: /\ACombination in \{(?<tag>tax|taxac) (?<oid>\d+)\}: #{END_RE}\z/,
    key: ->(m, obj) { ['combination', obj, m[:tag] == 'taxac'] },
    attrs: ->(m, obj) { { object_taxon_id: obj, force_author_citation: m[:tag] == 'taxac' } },
    gline: ->(key, obj, body) { "Combination in {#{key[2] ? 'taxac' : 'tax'} #{obj}}: #{body}." }
  },
  'designation' => {
    type: D::TYPE_SPECIMEN_DESIGNATION,
    re: /\A(?<label>Lectotype designation|Neotype designation): (?<cites>#{CITE_ONE})(?<stop>\.?)\z/,
    attrs: ->(m, _obj) { { subtype: DESIG.fetch(m[:label]) } },
    line: ->(m, _obj, body) { "#{m[:label]}: #{body}." }
  }
}
KINDS = (ENV['KINDS']&.split(',') || KIND_DEFS.keys).tap { |k| raise "unknown KINDS #{k}" unless (k - KIND_DEFS.keys).empty? }

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_small_kinds_2_#{MODE}_#{uuid}.tsv").to_s

REF_YEARS = {}
def ref_year(rid)
  REF_YEARS.fetch(rid) { REF_YEARS[rid] = Reference.where(id: rid).pick(:year) }
end

def cites_of(text)
  return [] if text.nil?
  list = text.to_enum(:scan, CITE_RE).map { Regexp.last_match }
  return if list.map(&:to_s).join('; ') != text
  list.map { |c| [c[:rid].to_i, c[:pages], c[:note]] }
end

def body(cites)
  return nil if cites.empty?
  cites.each_with_index.sort_by { |(rid, _), i| [ref_year(rid) || -1, i] }.map(&:first).
    map { |rid, pages, note| cite_text(rid, pages, note) }.join('; ')
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
        return 'object name would change' if Detax["{#{m[:tag]} #{oid}}"].to_s != Detax["{taxac #{obj}}"].to_s
      else
        return 'object taxon missing' unless Taxon.exists?(oid)
        obj = oid
      end
    end
    return 'reference missing' unless cites.all? { |rid, _| ref_year(rid) }
    return 'citation note invalid' unless cites.all? { |_, _, note| NOTE_OK.(note) }
    return 'pages invalid' unless cites.all? do |_, pages|
      pages.length <= HistoryItem::PAGES_MAX_LENGTH && pages.match?(HistoryItem::VALID_PAGES_REGEX)
    end
    attrs = kd[:attrs].(m, obj)
    if (tv = attrs[:text_value])
      return 'name invalid' unless tv.length <= HistoryItem::TEXT_VALUE_MAX_LENGTH && tv.match?(HistoryItem::VALID_TEXT_VALUE_REGEX)
      return 'name invalid' unless tv.match?(HistoryItem::NOMEN_NUDUM_NAME_REGEX)
    end
    return { kind: kind, m: m, key: (kd[:key].(m, obj) if kd[:grouped]), obj: obj, cites: cites, attrs: attrs }
  end
  nil
end

# The words of a rendered line with its citations taken out, and its citations as a sorted list: a converted
# line may differ from the old one only in a final full stop and the order of its citations.
def words_and_cites(taxt)
  text = Detax[taxt].to_s
  cites = []
  words = text.gsub(/[^;:()\[\]]+?, \d{4}[a-z]?: [^;)\]]+/) { |c| cites << c.strip; 'CITE' }
  [words.sub(/\.\z/, '').squeeze(' '), cites.sort]
end

class Reject < StandardError; end

protonym_ids = HistoryItem.taxts_only.distinct.order(:protonym_id).pluck(:protonym_id)
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
        elsif g.items.none? { |i| i.type == D::TAXT } && KIND_DEFS.values.any? { |kd| kd[:grouped] && kd[:type] == item.type } &&
              (p = plan_text(g.taxt, KIND_DEFS.select { |_, kd| kd[:grouped] }.keys)).is_a?(Hash) &&
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
        (kd = KIND_DEFS[payload[:kind]])[:grouped] ? kd[:gline].(key, payload[:obj], body(payload[:cites])) : kd[:line].(payload[:m], payload[:obj], body(payload[:cites]))
      end

      plans.each do |item_id, plan|
        kd = KIND_DEFS[plan[:kind]]
        hi = HistoryItem.find(item_id)
        (rid, pages, note), *rest = plan[:cites]
        hi.update!({ type: kd[:type], taxt: nil, reference_id: rid, pages: pages, citation_note: note }.merge(plan[:attrs]))
        lines += 1
        per_kind[plan[:kind]] += 1
        rest.each_with_index do |(r2, p2, n2), k|
          extra = protonym.history_items.create!({ type: kd[:type], rank: hi.rank, reference_id: r2, pages: p2, citation_note: n2 }.merge(plan[:attrs]))
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
      if shown.include?(:other)
        before.zip(after).each do |b, a|
          next if Detax[a].to_s == Detax[b].to_s || Detax[a].to_s == Detax["#{b}."].to_s
          raise Reject, "wording would change: #{Detax[b].to_s[0, 90].inspect}" unless words_and_cites(a) == words_and_cites(b)
        end
      end
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
