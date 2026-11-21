# frozen_string_literal: true
#
# genus_protonym_export.rb -- every genus-group taxon record with its protonym, type species and etymology
# fields. Read only (writes one TSV in tmp/).
#
# For the genus-group provenance work (Brian, 16 Nov 2026 19:55: a gender alone is the bare minimum; record
# the derivation and its source, starting from Wheeler 1956, Myrmecological orthoepy and onomatology):
#   - protonym_id and protonym_name are what write_protonym_fields.rb checks before it writes a derivation
#   - the type species in its ORIGINAL combination shows how the author treated the gender of a name of common
#     or variable gender (ICZN Art. 30.1.4.2, 30.1.4.4) or of a name not from Latin or Greek (Art. 30.2.3);
#     the catalog page shows the type species under its current name, which follows AntCat's gender
#   - the etymology fields already filled are never overwritten
#
# Also prints the reference(s) whose title contains "orthoepy" (Wheeler 1956), for the citation.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app \
#     bundle exec rails runner tmp/genus_protonym_export.rb
# Output: tmp/genus_protonyms.tsv, one row per genus-group taxon record.

ActiveRecord::Base.logger = nil

def clean(value)
  value.to_s.gsub(/[\t\r\n]+/, ' ').strip
end

columns = %w[
  taxon_id rank taxon_name status gender taxon_name_id
  protonym_id protonym_name authorship authorship_reference_id authorship_pages fossil nomen_nudum
  type_taxon_id type_taxon_name type_taxon_status type_original_combination type_fixation
  etymology_taxt etymology_source etymology_reference_id etymology_pages etymology_derivation
  has_notes_page valid_species_group_taxa
]

taxa = Taxon.where(type: %w[Genus Subgenus]).joins(:name).order('names.name', 'taxa.id').
  includes(:name, protonym: [:name, :notes_page, { authorship: :reference }, { type_name: { taxon: [:name, { protonym: :name }] } }])

out = Rails.root.join('tmp', 'genus_protonyms.tsv').to_s
rows = 0
File.open(out, 'w') do |f|
  f.puts columns.join("\t")
  taxa.each do |t|
    p = t.protonym
    type_name = p&.type_name
    type_taxon = type_name&.taxon
    inside = if t.type == 'Subgenus'
               Taxon.where(subgenus_id: t.id, status: 'valid').count
             else
               Taxon.where(genus_id: t.id, status: 'valid', type: %w[Species Subspecies]).count
             end
    row = [
      t.id, t.type, t.name.name, t.status, t.name.gender, t.name_id,
      p&.id, p&.name&.name, p&.authorship_reference&.plain_text_key_with_suffixed_year,
      p&.authorship&.reference_id, p&.authorship&.pages, p&.fossil?, p&.nomen_nudum?,
      type_taxon&.id, type_taxon&.name&.name, type_taxon&.status, type_taxon&.protonym&.name&.name,
      type_name&.fixation_method,
      p&.etymology_taxt, p&.etymology_source, p&.etymology_reference_id, p&.etymology_pages, p&.etymology_derivation,
      p&.notes_page ? 'yes' : '', inside
    ]
    raise "row has #{row.size} fields, header #{columns.size}" unless row.size == columns.size

    f.puts row.map { |v| clean(v) }.join("\t")
    rows += 1
  end
end

protonyms = taxa.map(&:protonym_id).uniq.size
puts "genus-group taxon records: #{rows}; protonyms: #{protonyms}"
puts "  with etymology_taxt: #{Protonym.genus_group_names.where.not(etymology_taxt: [nil, '']).count}"
puts "  with etymology_derivation: #{Protonym.genus_group_names.where.not(etymology_derivation: [nil, '']).count}"
puts "  with a type name: #{Protonym.genus_group_names.where.not(type_name_id: nil).count}"
puts "file: #{out}"

puts '== References with "orthoepy" in the title'
Reference.where('title LIKE ?', '%orthoepy%').find_each do |r|
  puts [r.id, r.plain_text_key_with_suffixed_year, clean(r.title)[0, 90], r.pagination].join(' | ')
end
