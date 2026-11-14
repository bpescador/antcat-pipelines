# frozen_string_literal: true
#
# spelling_history_export.rb  (READ-ONLY)
#
# Exports the free-text history items about spellings that the history conversion left for the part-of-speech
# and spelling work (14 Nov 2026): emendations (justified and unjustified, including the gender-only
# "Justified emendation of spelling to X by B. Bolton" items) and incorrect spellings. Same matching rules as
# history_order/history_census2.rb: the text with {tags} replaced by X and a leading "[" removed.
#
# Output: /app/tmp/spelling_history.tsv, one row per item: item id, protonym id, rank group, kind, protonym
#         (original) name, terminal taxon, protonym part of speech (gender_agreement_type), position, the full
#         text with its tags. Prints the counts per kind and rank group (14 Nov handover: emendations
#         species-group 312, genus-group 14; incorrect spellings 176, 126, 15).
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/spelling_history_export.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'spelling_history.tsv').to_s

KINDS = [
  ['emendation', /^((Justified|Unjustified) emendation|X: (un)?justified emendation)/],
  ['incorrect spelling', /^(Misspelled as|X: incorrect (subsequent|original) spelling)/]
].freeze

def kind_of(text)
  t = text.to_s.gsub(/\{[a-z]+\d? [^}]*\}/, 'X').sub(/\A[\[ ]+/, '')
  KINDS.each { |k, re| return k if t.match?(re) }
  nil
end

def group_of(name_type)
  case name_type
  when 'SpeciesName', 'SubspeciesName', 'InfrasubspeciesName' then 'species-group'
  when 'GenusName', 'SubgenusName' then 'genus-group'
  else 'family-group'
  end
end

counts = Hash.new(0)
n = 0
File.open(OUT, 'w') do |f|
  f.puts %w[history_item_id protonym_id rank_group kind protonym_name terminal_taxon part_of_speech position
            text].join("\t")
  HistoryItem.where(type: History::Definitions::TAXT).preload(protonym: [:name, { terminal_taxon: :name }]).find_each do |hi|
    kind = kind_of(hi.taxt)
    next unless kind

    p = hi.protonym
    group = group_of(p.name.type)
    counts[[kind, group]] += 1
    f.puts [hi.id, p.id, group, kind, p.name.name, p.terminal_taxon&.name&.name, p.gender_agreement_type,
            hi.position, hi.taxt].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
    n += 1
  end
end
counts.sort.each { |(kind, group), c| puts format('%-20s %-14s %5d', kind, group, c) }
puts "Wrote #{n} items to #{OUT}"
