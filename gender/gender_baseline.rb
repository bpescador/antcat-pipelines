# frozen_string_literal: true
#
# gender_baseline.rb -- how much of AntCat's gender and part-of-speech data is filled. Read only.
#
# Needed for the AntCat -> TaxonWorks copy: TW works out current spellings from genus gender and the
# protonym's part of speech, so every gap here is a spelling TW can get wrong (trochis/troche).
# Plan: claude/GENDER_AGREEMENT_PLAN.md (section 11 baseline, extended with genus gender).
#
# Prints counts; writes tmp/genera_without_gender.tsv (genus-group taxa whose name has no gender),
# tmp/genus_gender.tsv (every genus-group taxon with its gender) and tmp/part_of_speech_set.tsv
# (species-group taxa whose protonym already has a part of speech).
# Run (runbook procedure 16):
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app \
#     bundle exec rails runner tmp/gender_baseline.rb

ActiveRecord::Base.logger = nil

puts '== Genus gender (names.gender on the taxon name; what AntCat shows and uses)'
gg = Taxon.where(type: %w[Genus Subgenus]).joins(:name)
blank = gg.where(names: { gender: [nil, ''] })
puts "genus-group taxa: #{gg.count} (#{gg.group(:status).count.sort.to_h})"
puts "  without gender: #{blank.count} (#{blank.group(:status).count.sort.to_h})"
puts "  valid genera without gender: #{blank.where(type: 'Genus', status: 'valid').count}"
out = Rails.root.join('tmp', 'genera_without_gender.tsv').to_s
# Plain TSV: csv is not in the app bundle under Ruby 4 (see export_references.rb).
File.open(out, 'w') do |csv|
  def csv.<<(row) = puts(row.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t"))
  csv << %w[taxon_id rank name status fossil authorship protonym_id species_group_taxa_in_it]
  blank.includes(protonym: { authorship: :reference }).order('names.name').each do |t|
    inside = t.type == 'Subgenus' ? Taxon.where(subgenus_id: t.id).count : Taxon.where(genus_id: t.id).count
    csv << [t.id, t.type, t.name.name, t.status, t.protonym&.fossil?,
            t.protonym&.authorship_reference&.plain_text_key_with_suffixed_year, t.protonym_id, inside]
  end
end
puts "  list: #{out}"
all = Rails.root.join('tmp', 'genus_gender.tsv').to_s
File.open(all, 'w') do |f|
  f.puts %w[taxon_id rank name status gender].join("\t")
  gg.order('names.name').pluck(:id, :type, 'names.name', :status, 'names.gender').each { |row| f.puts row.join("\t") }
end
puts "  all genus-group genders: #{all} (for gender/propose_part_of_speech.py --genus-gender)"

puts '== Part of speech and etymology on species-group protonyms'
sg = Protonym.species_group_names
puts "species-group protonyms: #{sg.count}"
puts "  gender_agreement_type: #{sg.group(:gender_agreement_type).count.inspect}"
puts "  with etymology: #{sg.where.not(etymology_taxt: [nil, '']).count}"

diff = Taxon.where(status: 'valid').joins(:name, protonym: :name).
  where(names: { type: Name::SPECIES_GROUP_NAMES }).
  where('names.epithet <> names_protonyms.epithet')
puts "valid species-group taxa spelled differently from their protonym: #{diff.count}"
puts "  protonym has a part of speech: #{diff.where.not(protonyms: { gender_agreement_type: nil }).count}"
puts "  original ends -is or -e (manual bucket, upper bound; includes -ensis): " \
     "#{diff.where("names_protonyms.epithet LIKE '%is' OR names_protonyms.epithet LIKE '%e'").count}"
puts "  original ends -i or -ae (genitive nouns: changed spelling probably an error): " \
     "#{diff.where("names_protonyms.epithet LIKE '%i' OR names_protonyms.epithet LIKE '%ae'").count}"
puts "  typed as a noun but spelling changed (errors): " \
     "#{diff.where(protonyms: { gender_agreement_type: Protonym::UNCHANGEABLE_GENDER_AGREEMENT_TYPES }).count}"
puts "unavailable misspelling taxa: #{Taxon.where(status: 'unavailable misspelling').count}"

# Every species-group taxon whose protonym has a part of speech (about 310 protonyms in Nov 2026):
# names the noun-typed protonyms with a changed spelling, and checks the scripted proposals
# (gender/propose_part_of_speech.py) against what editors already set.
pos = Rails.root.join('tmp', 'part_of_speech_set.tsv').to_s
File.open(pos, 'w') do |f|
  f.puts %w[protonym_id protonym_name gender_agreement_type taxon_id taxon_name status spelling_changed].join("\t")
  Taxon.joins(:name, protonym: :name).where(names: { type: Name::SPECIES_GROUP_NAMES }).
    where.not(protonyms: { gender_agreement_type: nil }).order('names_protonyms.name', 'names.name').
    pluck('protonyms.id', 'names_protonyms.name', 'protonyms.gender_agreement_type', 'taxa.id', 'names.name',
          'taxa.status', Arel.sql('names.epithet <> names_protonyms.epithet')).
    each { |row| f.puts row.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end
puts "  part of speech already set: #{pos}"
