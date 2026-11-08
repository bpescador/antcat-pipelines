# frozen_string_literal: true
#
# convert_small_kinds.rb
#
# Step 2, small kinds: converts free-text history items to their structured types, one item per line:
#   [Junior primary homonym of {taxac|prottac N}( ({ref R}: pages)).]    -> JuniorPrimaryHomonymOf
#   [Junior secondary homonym of {taxac|prottac N}( ({ref R}: pages)).]  -> JuniorSecondaryHomonymOf
#   Replacement name: {taxac|prottac N}( ({ref R}: pages))[.]            -> HomonymReplacedBy
#   Unavailable name( ({ref R}: pages))[.]                               -> UnavailableName
#   Replacement name for {taxac|prottac N}( ({ref R}: pages))[.] TRAILER -> ReplacementNameFor
# These types always render {taxac T}: a {prottac P} line is converted to T = the terminal taxon of P,
# and only if the name shown stays the same. {tax N} (no author citation) is not converted.
# ReplacementNameFor appends, as its trailer, the structured homonym items of the replaced taxon's
# protonym. So run KINDS=homonyms,replaced_by,unavailable first (pass 1), then KINDS=replacement_for
# (pass 2): the trailer then comes from the converted homonym items and must equal what editors typed.
# Pass 1 holds a protonym if a structured ReplacementNameFor elsewhere names one of its taxa (its line
# there would change, which this protonym's check cannot see).
#
# Per protonym, inside one transaction: render the page with AntCat's HistoryPresenter; predict it
# after conversion (each converted line in its structured form, every other line unchanged);
# convert; render again; keep the change only if the page equals the prediction. Allowed visible
# changes: a final full stop added (Brian, 2026-11-07); in a Replacement name for line, the generated
# trailer adds the citation of the replaced name's homonym item where the editors' trailer had none
# (Brian, 2026-11-08: "allow group A"). A different citation or a different homonym is held.
# Otherwise rolled back and logged.
# MODE=check runs all of this and always rolls back. MODE=write keeps the protonyms that pass.
#
# Env:    MODE=check (default) | MODE=write
#         KINDS=comma-separated subset of homonyms,replaced_by,unavailable,replacement_for
#               (default homonyms,replaced_by,unavailable: pass 1)
#         ONLY=protonym ids (comma-separated); LIMIT=n
# Output: /app/tmp/convert_small_kinds_<MODE>_<uuid>.tsv (one row per protonym)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: restore from the dump taken before the run, or revert by request_uuid with
#         PaperTrail versions.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/convert_small_kinds.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Convert free-text homonym, replacement-name and unavailable-name lines ' \
               'to structured history items (claude/HISTORY_ORDER.md)'

unless HistoryPresenter.private_method_defined?(:editor_sort_key)
  abort 'PR #1591 is not deployed (HistoryPresenter); converting now would move lines.'
end

D = History::Definitions
F = Taxt::StandardHistoryItemFormats
PAG = F::PAGINATION_MANY
CIT = "(?: \\(\\{ref (?<rid>\\d+)\\}: (?<pages>#{PAG})\\))?"
OBJ = "\\{(?<tag>taxac|prottac) (?<oid>\\d+)\\}"
KIND_DEFS = {
  'jph' => { group: 'homonyms', type: D::JUNIOR_PRIMARY_HOMONYM_OF, prefix: '[Junior primary homonym of',
             re: /\A\[Junior primary homonym of #{OBJ}#{CIT}\.\]\z/,
             render: ->(t, cit) { "[Junior primary homonym of {taxac #{t}}#{cit}.]" } },
  'jsh' => { group: 'homonyms', type: D::JUNIOR_SECONDARY_HOMONYM_OF, prefix: '[Junior secondary homonym of',
             re: /\A\[Junior secondary homonym of #{OBJ}#{CIT}\.\]\z/,
             render: ->(t, cit) { "[Junior secondary homonym of {taxac #{t}}#{cit}.]" } },
  'hrb' => { group: 'replaced_by', type: D::HOMONYM_REPLACED_BY, prefix: 'Replacement name:',
             re: /\AReplacement name: #{OBJ}#{CIT}\.?\z/,
             render: ->(t, cit) { "Replacement name: {taxac #{t}}#{cit}." } },
  'una' => { group: 'unavailable', type: D::UNAVAILABLE_NAME, prefix: 'Unavailable name',
             re: /\AUnavailable name#{CIT}\.?\z/,
             render: ->(_, cit) { "Unavailable name#{cit}." } },
  'rnf' => { group: 'replacement_for', type: D::REPLACEMENT_NAME_FOR, prefix: 'Replacement name for',
             re: /\AReplacement name for #{OBJ}#{CIT}\.?(?<trail>(?: .*)?)\z/,
             render: ->(t, cit) { "Replacement name for {taxac #{t}}#{cit}." } }
}
GROUPS = (ENV['KINDS']&.split(',') || %w[homonyms replaced_by unavailable])
raise "unknown KINDS #{GROUPS}" unless (GROUPS - KIND_DEFS.values.map { |d| d[:group] }.uniq).empty?
KINDS = KIND_DEFS.select { |_, d| GROUPS.include?(d[:group]) }.keys

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "convert_small_kinds_#{MODE}_#{uuid}.tsv").to_s

class Reject < StandardError; end

# A citation inside a homonym trailer: " ({ref R}: pages)" just before ".]".
TRAILER_CITATION = /(?<=\}) \(\{ref \d+\}: [^()\[\]]*\)(?=\.\])/

# Returns nil (not one of ours), a reason string (held), or a plan hash.
def plan_line(hi)
  kind, kd = KIND_DEFS.find { |k, d| KINDS.include?(k) && hi.taxt.start_with?(d[:prefix]) }
  return unless kind
  m = hi.taxt.match(kd[:re]) or return 'not in the structured form'
  rid = m[:rid]&.to_i
  pages = m[:pages]
  if rid
    return 'reference missing' unless Reference.exists?(rid)
    return 'pages invalid' unless pages.length <= HistoryItem::PAGES_MAX_LENGTH && pages.match?(HistoryItem::VALID_PAGES_REGEX)
  end
  taxon_id = nil
  if m.names.include?('oid')
    oid = m[:oid].to_i
    if m[:tag] == 'taxac'
      return 'object taxon missing' unless Taxon.exists?(oid)
      taxon_id = oid
    else
      protonym = Protonym.find_by(id: oid) or return 'object protonym missing'
      taxon_id = protonym.terminal_taxon&.id or return 'object protonym has no terminal taxon'
      return 'object name would change' if Detax["{prottac #{oid}}"].to_s != Detax["{taxac #{taxon_id}}"].to_s
    end
  end
  cit = rid ? " ({ref #{rid}}: #{pages})" : ''
  expected = kd[:render].(taxon_id, cit)
  expected += m[:trail] if m.names.include?('trail')
  { kind: kind, type: kd[:type], taxon_id: taxon_id, rid: rid, pages: pages, expected: expected }
end

def rendered(protonym)
  HistoryPresenter.new(HistoryItem.where(protonym_id: protonym.id)).grouped_items.map(&:taxt)
end

protonym_ids = HistoryItem.taxts_only.
  where(KINDS.map { 'taxt LIKE ?' }.join(' OR '), *KINDS.map { |k| "#{KIND_DEFS[k][:prefix]}%" }).
  distinct.order(:protonym_id).pluck(:protonym_id)
protonym_ids &= ONLY if ONLY
protonym_ids = protonym_ids.first(LIMIT) if LIMIT
puts "MODE=#{MODE} KINDS=#{GROUPS.join(',')} request_uuid=#{uuid} protonyms=#{protonym_ids.size}"

rnf_targets = HistoryItem.where(type: D::REPLACEMENT_NAME_FOR).pluck(:object_taxon_id).to_set
stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id lines_converted detail].join("\t")

protonym_ids.each do |pid|
  protonym = Protonym.find(pid)
  lines = 0
  result = nil
  detail = ''
  begin
    ActiveRecord::Base.transaction do
      groups = HistoryPresenter.new(HistoryItem.where(protonym_id: pid)).grouped_items
      before = groups.map(&:taxt)
      plans = {}
      held = []
      groups.each do |g|
        next unless g.items.size == 1 && g.items.first.type == D::TAXT
        plan = plan_line(g.items.first)
        if plan.is_a?(String) then held << plan
        elsif plan then plans[g.items.first.id] = plan
        end
      end
      raise Reject, "nothing convertible#{held.any? ? " (#{held.uniq.join('; ')})" : ''}" if plans.empty?
      if plans.values.any? { |p| %w[jph jsh].include?(p[:kind]) } &&
         Taxon.where(protonym_id: pid).pluck(:id).any? { |t| rnf_targets.include?(t) }
        raise Reject, 'a structured Replacement name for elsewhere names a taxon of this protonym'
      end
      expected = groups.map { |g| (p = plans[g.items.first.id]) ? p[:expected] : g.taxt }

      plans.each do |item_id, p|
        HistoryItem.find(item_id).update!(type: p[:type], taxt: nil, object_taxon_id: p[:taxon_id],
                                          reference_id: p[:rid], pages: p[:pages])
        lines += 1
      end
      protonym.create_activity(Activity::UPDATE, bot,
        edit_summary: "#{EDIT_SUMMARY} [#{lines} lines]").update_columns(automated_edit: true)

      after = rendered(protonym.reload)
      # Trailers: accept the generated trailer if it shows the same names as the typed one, or the same
      # names plus the citation(s) of the replaced name's homonym item(s) (group A). Compared as displayed.
      cited = []
      after.each_with_index do |a, i|
        e = expected[i]
        next if a == e || e.nil? || !a.start_with?('Replacement name for ')
        if Detax[a].to_s == Detax[e].to_s
          expected[i] = a # same names shown ({prottac P} typed, {taxac T} generated, T the terminal taxon of P)
        elsif !e.match?(TRAILER_CITATION) && Detax[a.gsub(TRAILER_CITATION, '')].to_s == Detax[e].to_s
          cited << i
          expected[i] = a
        end
      end
      unless after == expected
        first = after.zip(expected).index { |a, e| a != e } || [after.size, expected.size].min
        raise Reject, "page differs from prediction at line #{first + 1}: got #{after[first].to_s[0, 120].inspect}, " \
                      "expected #{expected[first].to_s[0, 120].inspect}"
      end
      shown = after.zip(before).each_with_index.map do |(a, b), i|
        if cited.include?(i) then :citation_added
        elsif Detax[a].to_s == Detax[b].to_s then :same
        elsif Detax[a].to_s == Detax["#{b}."].to_s then :full_stop
        else :changed
        end
      end
      result =
        if after.size != before.size || shown.include?(:changed) then 'changed'
        elsif shown.include?(:citation_added) then 'trailer_citation_added'
        elsif shown.include?(:full_stop) then 'identical_except_full_stop'
        else 'identical'
        end
      raise Reject, 'page changed beyond a full stop' if result == 'changed'
      detail = held.uniq.join('; ')
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    result = 'held'
    detail = e.message
    lines = 0
  rescue ActiveRecord::RecordInvalid => e
    result = 'error'
    detail = e.message
    lines = 0
  end
  label = %w[held error].include?(result) ? result : "#{MODE == 'check' ? 'would_convert' : 'converted'} (#{result})"
  stats[label] += 1
  stats['lines converted'] += lines
  stats["held: #{detail.sub(/ at line \d+.*/, '').sub(/ \(.*/, '')}"] += 1 if result == 'held'
  out.puts [label, pid, lines, detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-80s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
