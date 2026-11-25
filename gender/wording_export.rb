# frozen_string_literal: true

# wording_export.rb -- READ ONLY. Lists the protonyms whose AntCat derivation says the word, the element or the
# origin is "not identified" (and near wordings), and the protonyms whose public notes mention "Spelling", for the
# wording review of 25 Nov 2026 (items D4 and D10): Brian reviews the actual text before any change.
#
# Run inside the app container (rails runner), as user antcat. Writes one file, JSON lines (a text keeps its line
# breaks, tabs and quotes exactly, so it can serve as the exact old value of a later write):
#   ENV OUT_PREFIX (default /app/tmp/wording_export) + "_<UTC stamp>.jsonl"
# Each line: kind ("derivation" | "note"), protonym_id, name, rank ("genus_group" | "species_group" | other),
# pattern (the wording found), text (the whole field).
ActiveRecord::Base.logger = nil

DERIVATION_PATTERNS = ['not identified', 'not established', 'unknown', 'not known', 'uncertain', 'unclear'].freeze

def rank_of protonym
  if protonym.respond_to?(:species_group_name?) && protonym.species_group_name? then 'species_group'
  elsif protonym.respond_to?(:genus_group_name?) && protonym.genus_group_name? then 'genus_group'
  else protonym.name.class.name
  end
end

path = "#{ENV.fetch('OUT_PREFIX', '/app/tmp/wording_export')}_#{Time.now.utc.strftime('%Y%m%d%H%M%S')}.jsonl"
counts = Hash.new(0)
File.open(path, 'w') do |out|
  Protonym.where.not(etymology_derivation: [nil, '']).includes(:name).find_each do |protonym|
    counts['derivations in all'] += 1
    pattern = DERIVATION_PATTERNS.find { |p| protonym.etymology_derivation.include?(p) }
    next unless pattern

    counts["derivation: #{pattern}"] += 1
    out.puts({ kind: 'derivation', protonym_id: protonym.id, name: protonym.name.name, rank: rank_of(protonym),
               pattern: pattern, text: protonym.etymology_derivation }.to_json)
  end
  Protonym.where("notes_taxt LIKE ?", '%Spelling%').includes(:name).find_each do |protonym|
    pattern = protonym.notes_taxt.lstrip.start_with?('Spelling') ? 'begins with Spelling' : 'mentions Spelling'
    counts["note: #{pattern}"] += 1
    out.puts({ kind: 'note', protonym_id: protonym.id, name: protonym.name.name, rank: rank_of(protonym),
               pattern: pattern, text: protonym.notes_taxt }.to_json)
  end
end
counts.sort.each { |k, v| puts format('  %-40s %6d', k, v) }
puts "Wrote #{path}"
