# frozen_string_literal: true
#
# agreement_export.rb -- read-only export of what a coordinated gender-and-spelling change would touch, for
# named genus-group taxa and protonyms. Writes nothing.
#
# For each genus-group taxon in GENERA (taxon ids): its name record, gender, protonym and the protonym's derivation;
# every species-group taxon in it (by genus_id or subgenus_id), with status, name record, whether that name record
# is used by any protonym or another taxon, and the protonym's grammar fields and three spellings.
# For each protonym in PROTONYMS: its etymology fields.
#
# Env:    GENERA=taxon ids, comma-separated; PROTONYMS=protonym ids, comma-separated (either may be empty)
# Output: /app/tmp/agreement_export_<timestamp>.tsv (kind, ids, then field=value pairs); also printed.
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

GENERA = ENV.fetch('GENERA', '').split(',').map(&:to_i)
PROTONYMS = ENV.fetch('PROTONYMS', '').split(',').map(&:to_i)
PROTONYM_FIELDS = %w[gender_agreement_type part_of_speech_basis interpretation_status masculine_epithet
                     feminine_epithet neuter_epithet spelling_basis etymology_taxt etymology_source
                     etymology_reference_id etymology_pages etymology_translation etymology_derivation].freeze

OUT = Rails.root.join('tmp', "agreement_export_#{Time.current.strftime('%Y%m%d%H%M%S')}.tsv").to_s
out = File.open(OUT, 'w')

def emit(out, *cols)
  line = cols.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
  out.puts line
  puts line
end

def protonym_cols(p)
  PROTONYM_FIELDS.map { |f| "#{f}=#{p[f]}" }
end

GENERA.each do |gid|
  g = Taxon.find(gid)
  emit out, 'genus', g.id, g.type, g.status, "name_id=#{g.name_id}", "name=#{g.name.name}", "gender=#{g.name.gender}",
       "name_shared_with_taxa=#{Taxon.where(name_id: g.name_id).where.not(id: g.id).pluck(:id).join(',')}",
       "protonym_id=#{g.protonym_id}", "protonym_derivation=#{g.protonym.etymology_derivation}"
  scope = g.type == 'Subgenus' ? Taxon.where(subgenus_id: g.id) : Taxon.where(genus_id: g.id)
  scope.where(type: %w[Species Subspecies Infrasubspecies]).order(:id).each do |t|
    n = t.name
    emit out, 'species', t.id, t.type, t.status, "name_id=#{n.id}", "name=#{n.name}", "epithet=#{n.epithet}",
         "name_cache=#{t.name_cache}",
         "name_used_by_protonyms=#{Protonym.where(name_id: n.id).pluck(:id).join(',')}",
         "name_used_by_other_taxa=#{Taxon.where(name_id: n.id).where.not(id: t.id).pluck(:id).join(',')}",
         "protonym_id=#{t.protonym_id}", "protonym_name=#{t.protonym.name.name}", *protonym_cols(t.protonym)
  end
end

PROTONYMS.each do |pid|
  p = Protonym.find(pid)
  emit out, 'protonym', p.id, "name=#{p.name.name}", "authorship_reference_id=#{p.authorship_reference.id}",
       "authorship_pages=#{p.authorship_pages}", "notes_page=#{p.notes_page&.id}", *protonym_cols(p)
end
out.close
puts "Wrote #{OUT}"
