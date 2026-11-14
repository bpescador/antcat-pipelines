# frozen_string_literal: true
#
# protonym_pages_export.rb  (READ-ONLY)
#
# Exports every species-group protonym with what the literature library needs to find its original description
# (authorship reference and cited pages) and the etymology fields to be sorted against that page (14 Nov 2026,
# Brian: find each name's original-description page, then sort the existing etymologies into the fields that
# came with AntCat #1607).
#
# Output: /app/tmp/protonym_pages.tsv, one row per protonym: protonym id, original name, epithet, authorship
#         reference id and cited pages, plain author citation, year, part of speech, interpretation status,
#         the etymology fields (etymology_taxt, etymology_source, etymology_reference_id, etymology_pages,
#         etymology_translation, etymology_derivation), the locality as recorded, and the terminal taxon.
#         Tabs and line breaks inside values become spaces. Prints the counts.
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/protonym_pages_export.rb

ActiveRecord::Base.logger = nil
OUT = Rails.root.join('tmp', 'protonym_pages.tsv').to_s
SPECIES_GROUP = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze
COLUMNS = %w[protonym_id protonym_name epithet authorship_reference_id authorship_pages author_citation year
             part_of_speech interpretation_status etymology_taxt etymology_source etymology_reference_id
             etymology_pages etymology_translation etymology_derivation locality terminal_taxon_id
             terminal_taxon_name].freeze

def clean(value)
  value.to_s.gsub(/[\t\r\n]+/, ' ')
end

n = 0
with_etymology = 0
without_reference = 0
File.open(OUT, 'w') do |f|
  f.puts COLUMNS.join("\t")
  Protonym.joins(:name).where(names: { type: SPECIES_GROUP }).
    preload(:name, { authorship: :reference }, { terminal_taxon: :name }).find_each do |p|
    reference = p.authorship&.reference
    without_reference += 1 unless reference
    with_etymology += 1 if p.etymology_taxt.present?
    f.puts [
      p.id, p.name.name, p.name.epithet, reference&.id, p.authorship&.pages,
      (reference ? reference.key.plain_text_key_with_year : ''), reference&.year,
      p.gender_agreement_type, p.interpretation_status, p.etymology_taxt, p.etymology_source,
      p.etymology_reference_id, p.etymology_pages, p.etymology_translation, p.etymology_derivation,
      p.locality, p.terminal_taxon&.id, p.terminal_taxon&.name&.name
    ].map { |v| clean(v) }.join("\t")
    n += 1
  end
end
puts "species-group protonyms: #{n}; with etymology_taxt: #{with_etymology}; without authorship reference: #{without_reference}"
puts "Wrote #{OUT}"
