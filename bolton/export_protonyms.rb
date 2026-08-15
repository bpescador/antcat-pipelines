# export_protonyms.rb
# Dumps one JSON object per SPECIES-GROUP protonym with its structured type fields.
# Run on the server inside the app container:
#   docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner export_protonyms.rb
# Output (host): /var/www/antcat-2/tmp/protonyms_species_typeinfo.jsonl
# Read-only: this script only SELECTs. No writes to the database.

require 'json'

SPECIES_GROUP = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze
OUT = Rails.root.join('tmp', 'protonyms_species_typeinfo.jsonl')
FileUtils.mkdir_p(File.dirname(OUT))

# robustly pull "author" + "year" from the authorship's reference, trying a few method names
def author_year(p)
  ref = p.authorship&.reference rescue nil
  return [nil, nil] unless ref
  author =
    (ref.author_names_string         rescue nil) ||
    (ref.principal_author_last_name  rescue nil) ||
    (ref.author_names.map { |a| a.last_name }.join(', ') rescue nil)
  year =
    (ref.year        rescue nil) ||
    (ref.citation_year rescue nil)
  [author, year]
end

scope = Protonym.joins(:name).where(names: { type: SPECIES_GROUP })
total = scope.count
puts "Species-group protonyms to export: #{total}"

n = 0; n_primary = 0; n_casent = 0; n_err = 0
File.open(OUT, 'w') do |f|
  scope.find_each(batch_size: 500) do |p|
    begin
      name_str = (p.name.name rescue nil) || (p.name.name_cache rescue nil)
      author, year = author_year(p)
      prim = p.primary_type_information_taxt
      seco = p.secondary_type_information_taxt
      rec = {
        protonym_id: p.id,
        name:        name_str,
        author:      author,
        year:        year,
        fossil:      p.fossil,
        nomen_nudum: p.nomen_nudum,
        sic:         p.sic,
        locality:    p.locality,
        bioregion:   p.bioregion,
        primary_type_taxt:   prim,
        secondary_type_taxt: seco,
        type_notes_taxt:     p.type_notes_taxt
      }
      f.puts(rec.to_json)
      n += 1
      n_primary += 1 if prim.present?
      n_casent  += 1 if (prim.to_s + seco.to_s).match?(/CASENT\d+/)
    rescue => e
      n_err += 1
      warn "ERR protonym #{p.id}: #{e.class} #{e.message}" if n_err <= 20
    end
    puts "  ...#{n}" if (n % 5000).zero? && n.positive?
  end
end

puts "Done. Wrote #{n} rows to #{OUT}"
puts "  with primary type info: #{n_primary}"
puts "  with a CASENT code:     #{n_casent}"
puts "  errors (skipped):       #{n_err}"
