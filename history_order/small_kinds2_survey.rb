# frozen_string_literal: true
#
# small_kinds2_survey.rb  (READ-ONLY)
#
# Exact shapes of the small species-group kinds left after 14 Nov 2026, to design one PR of types:
# unresolved junior homonyms, nomen nudum lines, unnecessary replacement names, unidentifiable taxon (no object),
# duplicated in, subgenus indeterminate, also cited as new; plus Combination in and lectotype/neotype lines that
# differ only by a citation note. For each kind: lines, top shapes, and how many match a strict candidate pattern
# (citations may carry a note).
#
# Output: summary only.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/small_kinds2_survey.rb

ActiveRecord::Base.logger = nil
F = Taxt::StandardHistoryItemFormats
PAG = F::PAGINATION_MANY
NOTE = '(?: (?:\\[[^\\[\\];]*\\]|\\([^();]*\\)))?'
CITE = "\\{ref \\d+\\}: #{PAG}#{NOTE}"
CITES = "#{CITE}(?:; #{CITE})*"
TAX = '\\{(?:tax|taxac|prott|prottac) \\d+\\}'
SPECIES = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze

KINDS = {
  'unresolved homonym' => [/\A\[?Unresolved junior (primary|secondary) homonym/,
                           /\A\[Unresolved junior (?:primary|secondary) homonym of #{TAX}(?: \((?:#{CITES})\))?\.\]\z/],
  'nomen nudum line' => [/<i>Nom(en|ina) nud(um|a)<\/i>/,
                         /\A\[\{(?:unmissing|missing\d?) [^{}]+\} #{CITES}\. <i>Nomen nudum<\/i>(?: \(attributed to [A-Z][^()]*\))?\.\]\z/],
  'unnecessary replacement' => [/\AUnnecessary replacement name for/,
                                /\AUnnecessary replacement name for #{TAX}(?:: #{CITES})?\.?\z/],
  'unidentifiable taxon (no object)' => [/\AUnidentifiable taxon:/,
                                         /\AUnidentifiable taxon: #{CITES}\.?\z/],
  'duplicated in' => [/\A\[Duplicated in/, /\A\[Duplicated in #{CITES}\.\]\z/],
  'subgenus indeterminate' => [/\ASubgenus indeterminate/, /\ASubgenus indeterminate: #{CITES}\.?\z/],
  'also cited as new' => [/\A\[Also cited as new/, /\A\[Also cited as new in #{CITES}\.\]\z/],
  'combination in, with a note' => [/\ACombination in .*\{ref \d+\}: [^;]*[\])]/,
                                    /\ACombination in #{TAX}: #{CITES}\.?\z/],
  'lecto/neotype, with a note' => [/\A(Lectotype|Neotype) designation: \{ref \d+\}: [^;]*[\])]/,
                                   /\A(Lectotype|Neotype) designation: #{CITES}\.?\z/]
}.freeze

def shape(text)
  text.gsub(/\{ref \d+\}: #{PAG}/, '{ref N}: P').gsub(/\{(misspelling|unmissing|missing\d?) [^}]*\}/, '{\1 X}').
    gsub(/\{([a-z]+) \d+\}/, '{\1 N}').gsub(/(\{ref N\}: P)(; \{ref N\}: P)+/, '\1; ...')
end

ranks = Protonym.joins(:name).pluck(:id, 'names.type').to_h
stats = Hash.new { |h, k| h[k] = { lines: 0, strict: 0, shapes: Hash.new(0), ranks: Hash.new(0) } }
HistoryItem.taxts_only.pluck(:protonym_id, :taxt).each do |pid, t|
  t = t.to_s
  KINDS.each do |kind, (sel, strict)|
    next unless t.match?(sel)
    s = stats[kind]
    s[:lines] += 1
    s[:strict] += 1 if t.match?(strict)
    s[:shapes][shape(t)] += 1
    s[:ranks][SPECIES.include?(ranks[pid]) ? 'species' : 'higher'] += 1
    break
  end
end

KINDS.each_key do |kind|
  s = stats[kind]
  puts "\n== #{kind}: #{s[:lines]} lines (#{s[:ranks].sort.map { |g, n| "#{g} #{n}" }.join(', ')}); strict pattern #{s[:strict]}"
  s[:shapes].sort_by { -_2 }.first(10).each { |sh, n| puts format('  %4d  %s', n, sh[0, 150]) }
end
