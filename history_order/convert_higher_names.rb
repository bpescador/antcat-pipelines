# frozen_string_literal: true
#
# convert_higher_names.rb
#
# Step 2: converts the free-text history of genus- and family-group protonyms to the structured types
# added by AntCat PR #1614. Each line names its subject S first (Bolton's wording):
#   placement    {S} in PLACEMENT: CITATIONS.                                   -> PlacementIn (taxt = PLACEMENT)
#                PLACEMENT = one or more of {tax|taxac|unmissing|pro|prott ...}, comma-separated,
#                optionally followed by " genus group"
#   incertae     {S} <i>incertae sedis</i> in {tax N}: CITATIONS.               -> PlacementIncertaeSedisIn
#   as_genus     {S} as genus: CITATIONS.                                        -> AsGenus
#   as_rank      {S} as subgenus|tribe|subtribe|subfamily of {tax N}: CITATIONS. -> AsRankOf (subtype)
#   as_synonym   {S} as junior|senior synonym of {tax N}: CITATIONS.            -> AsSynonymOf (subtype)
# S is {tax T} or {taxac T}, T a taxon of this protonym; the structured line shows {prott P} ({prottac P}
# for taxac, with force_author_citation), so S must render the same name as P's terminal taxon.
# One item per citation.
#
# Per protonym, inside one transaction: render the page (HistoryPresenter); predict it (converted lines in
# structured form; adjacent lines with the same group key merge; citations by year, ties in editors'
# order); convert; render again; keep the change only if the page equals the prediction. Lines of one
# key that would merge across another line hold the protonym. Allowed visible changes (Brian,
# 2026-11-07): a final full stop added; adjacent same-key lines merged; citations in year order.
# Held: extra wording, citation notes ("[provisional]", "[{tax N}]"), "all authors", subjects that are not
# this protonym's terminal taxon.
# MODE=check always rolls back. MODE=write keeps the protonyms that pass.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=comma-separated subset of placement,incertae,as_genus,as_rank,as_synonym (default all)
#         ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/convert_higher_names_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: the dump taken before the run, or PaperTrail versions by request_uuid.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_higher_names.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text history lines to structured history items (claude/HISTORY_ORDER.md)'

D = History::Definitions
abort 'PR #1614 is not deployed (no PlacementIn type).' unless D::TYPE_DEFINITIONS.key?('PlacementIn')
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
SUBJ = '\{(?<stag>tax|taxac|prott|prottac) (?<sid>\d+)\}'
OBJ_TAG = '\{(?:tax|taxac|unmissing|pro|prott) [^{}]+\}'
PLACEMENT = "#{OBJ_TAG}(?:, #{OBJ_TAG})*(?: genus group)?"
END_RE = "(?<cites>#{CITES})(?<stop>\\.?)"
SPECIES_NAMES = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze

def subject_tag(fac, pid) = "{#{fac ? 'prottac' : 'prott'} #{pid}}"

KIND_DEFS = {
  'placement' => {
    type: D::PLACEMENT_IN,
    re: /\A#{SUBJ} in (?<path>#{PLACEMENT}): #{END_RE}\z/,
    key: ->(m, _obj, fac) { ['placement', m[:path], fac] },
    attrs: ->(m, _obj) { { taxt: m[:path] } },
    line: ->(key, _obj, body, pid) { "#{subject_tag(key.last, pid)} in #{key[1]}: #{body}." }
  },
  'incertae' => {
    type: D::PLACEMENT_INCERTAE_SEDIS_IN, object: :taxon,
    re: /\A#{SUBJ} <i>incertae sedis<\/i> in \{(?<tag>tax) (?<oid>\d+)\}: #{END_RE}\z/,
    key: ->(_m, obj, fac) { ['incertae', obj, fac] },
    attrs: ->(_m, obj) { { object_taxon_id: obj } },
    line: ->(key, obj, body, pid) { "#{subject_tag(key.last, pid)} <i>incertae sedis</i> in {tax #{obj}}: #{body}." }
  },
  'as_genus' => {
    type: D::AS_GENUS,
    re: /\A#{SUBJ} as genus: #{END_RE}\z/,
    key: ->(_m, _obj, fac) { ['as_genus', fac] },
    attrs: ->(_m, _obj) { {} },
    line: ->(key, _obj, body, pid) { "#{subject_tag(key.last, pid)} as genus: #{body}." }
  },
  'as_rank' => {
    type: D::AS_RANK_OF, object: :taxon,
    re: /\A#{SUBJ} as (?<rank>subgenus|tribe|subtribe|subfamily) of \{(?<tag>tax) (?<oid>\d+)\}: #{END_RE}\z/,
    key: ->(m, obj, fac) { ['as_rank', m[:rank], obj, fac] },
    attrs: ->(m, obj) { { subtype: D::AS_RANK_OF_RANKS.invert.fetch(m[:rank]), object_taxon_id: obj } },
    line: ->(key, obj, body, pid) { "#{subject_tag(key.last, pid)} as #{key[1]} of {tax #{obj}}: #{body}." }
  },
  'as_synonym' => {
    type: D::AS_SYNONYM_OF, object: :taxon,
    re: /\A#{SUBJ} as (?<kind>junior|senior) synonym of \{(?<tag>tax) (?<oid>\d+)\}: #{END_RE}\z/,
    key: ->(m, obj, fac) { ['as_synonym', m[:kind], obj, fac] },
    attrs: ->(m, obj) { { subtype: D::AS_SYNONYM_OF_KINDS.invert.fetch(m[:kind]), object_taxon_id: obj } },
    line: ->(key, obj, body, pid) { "#{subject_tag(key.last, pid)} as #{key[1]} synonym of {tax #{obj}}: #{body}." }
  }
}
KINDS = (ENV['KINDS']&.split(',') || KIND_DEFS.keys).tap { |k| raise "unknown KINDS #{k}" unless (k - KIND_DEFS.keys).empty? }

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_higher_names_#{MODE}_#{uuid}.tsv").to_s

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

# Parses a line of protonym `pid`. Returns nil (not ours), a reason (held), or a plan hash.
def plan_text(text, pid, kinds = KINDS)
  kinds.each do |kind|
    kd = KIND_DEFS[kind]
    m = text.to_s.match(kd[:re]) or next
    cites = cites_of(m[:cites]) or return 'citations not in the standard form'
    fac = m[:stag].end_with?('ac')
    if m[:stag].start_with?('prott')
      return 'subject is another protonym' unless m[:sid].to_i == pid
    else
      return 'subject is not a taxon of this protonym' unless Taxon.where(id: m[:sid].to_i, protonym_id: pid).exists?
      return 'subject name would change' if Detax["{#{m[:stag]} #{m[:sid]}}"].to_s != Detax[subject_tag(fac, pid)].to_s
    end
    obj = nil
    if kd[:object]
      return 'object taxon missing' unless Taxon.exists?(m[:oid].to_i)
      obj = m[:oid].to_i
    end
    return 'reference missing' unless cites.all? { |rid, _| ref_year(rid) }
    return 'citation note invalid' unless cites.all? { |_, _, note| NOTE_OK.(note) }
    return 'pages invalid' unless cites.all? do |_, pages|
      pages.length <= HistoryItem::PAGES_MAX_LENGTH && pages.match?(HistoryItem::VALID_PAGES_REGEX)
    end
    attrs = kd[:attrs].(m, obj).merge(force_author_citation: fac)
    return { kind: kind, key: kd[:key].(m, obj, fac), obj: obj, cites: cites, attrs: attrs }
  end
  nil
end

class Reject < StandardError; end

protonym_ids = HistoryItem.taxts_only.joins(protonym: :name).where.not(names: { type: SPECIES_NAMES }).
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
        plan = plan_text(g.items.first.taxt, pid)
        if plan.is_a?(String) then held << plan
        elsif plan then plans[g.items.first.id] = plan
        end
      end
      raise Reject, "nothing convertible#{held.any? ? " (#{held.uniq.join('; ')})" : ''}" if plans.empty?

      # Predict: converted lines in structured form; existing structured lines of our kinds take part in merging.
      predicted = groups.map do |g|
        item = g.items.first
        if (plan = plans[item.id])
          [plan[:key], plan]
        elsif g.items.none? { |i| i.type == D::TAXT } && (p = plan_text(g.taxt, pid, KIND_DEFS.keys)).is_a?(Hash) &&
              KIND_DEFS[p[:kind]][:type] == item.type
          [p[:key], p]
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
        KIND_DEFS[payload[:kind]][:line].(key, payload[:obj], body(payload[:cites]), pid)
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
