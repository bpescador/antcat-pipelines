# frozen_string_literal: true

# completeness_export.rb -- READ ONLY. One line per genus-group and species-group protonym with everything the
# completeness work (Brian Fisher, 23 and 27 Nov 2026) needs to sort the names into batches: the grammar fields,
# the etymology fields, the original description (reference, pages, whether AntCat holds its PDF, directly or
# through the nesting reference), and the protonym's taxa with the gender of each one's genus.
#
# Run inside the app container (rails runner), as user antcat, by run_readonly_export.sh. Writes one file,
# JSON lines (texts keep their exact characters, so a later write can use them as old values):
#   ENV OUT_PREFIX (default /app/tmp/completeness_export) + "_<UTC stamp>.jsonl"
# Reads with pluck only; changes nothing.
ActiveRecord::Base.logger = nil

GROUPS = (Name::GENUS_GROUP_NAMES + Name::SPECIES_GROUP_NAMES).freeze
P_COLS = %w[id name_id authorship_id fossil sic nomen_nudum locality notes_taxt etymology_taxt gender_agreement_type
            masculine_epithet feminine_epithet neuter_epithet part_of_speech_basis spelling_basis interpretation_status
            etymology_source etymology_reference_id etymology_pages etymology_translation etymology_derivation].freeze

names = Name.where(type: Name::GENUS_GROUP_NAMES + Name::SPECIES_GROUP_NAMES)
  .pluck(:id, :type, :name, :epithet, :gender).to_h { |id, *rest| [id, rest] }
docs = ReferenceDocument.pluck(:reference_id, :file_file_name, :url)
  .each_with_object({}) { |(rid, file, url), h| h[rid] = file.present? ? 'pdf' : (url.present? ? 'link' : '') }
refs = Reference.pluck(:id, :year, :nesting_reference_id, :key_with_suffixed_year_cache, :pagination)
  .to_h { |id, *rest| [id, rest] }
cites = Citation.pluck(:id, :reference_id, :pages).to_h { |id, *rest| [id, rest] }
notes_pages = NotesPage.pluck(:protonym_id).to_set
taxa = Hash.new { |h, k| h[k] = [] }
taxon_name = {}
Taxon.pluck(:id, :type, :status, :name_id, :genus_id, :subgenus_id, :protonym_id, :original_combination)
  .each do |id, type, status, name_id, genus_id, subgenus_id, protonym_id, oc|
    taxon_name[id] = name_id
    taxa[protonym_id] << { id: id, type: type, status: status, name_id: name_id, genus_id: genus_id,
                           subgenus_id: subgenus_id, original_combination: oc }
  end
gender_of_taxon = ->(tid) { tid && names.dig(taxon_name[tid], 3) }
name_of_taxon = ->(tid) { tid && names.dig(taxon_name[tid], 1) }

# The PDF AntCat shows for a reference: its own, or else the nearest nesting reference's (as AntCat's pages do).
pdf_of = lambda do |rid|
  seen = []
  while rid && !seen.include?(rid)
    return [docs[rid], rid] if docs[rid].present?

    seen << rid
    rid = refs.dig(rid, 1)
  end
  ['', nil]
end

path = "#{ENV.fetch('OUT_PREFIX', '/app/tmp/completeness_export')}_#{Time.now.utc.strftime('%Y%m%d%H%M%S')}.jsonl"
counts = Hash.new(0)
File.open(path, 'w') do |out|
  Protonym.joins(:name).where(names: { type: GROUPS }).order(:id).pluck(*P_COLS.map { |c| "protonyms.#{c}" })
    .each do |row|
      p = P_COLS.zip(row).to_h
      ntype, nname, epithet, ngender = names[p['name_id']]
      group = Name::GENUS_GROUP_NAMES.include?(ntype) ? 'genus_group' : 'species_group'
      rid, pages = cites[p['authorship_id']]
      year, nesting, key, pagination = refs[rid]
      pdf, pdf_rid = pdf_of.call(rid)
      ts = taxa[p['id']].map do |t|
        t.merge(name: name_of_taxon.call(t[:id]), name_gender: names.dig(t[:name_id], 3),
                genus: name_of_taxon.call(t[:genus_id]), genus_gender: gender_of_taxon.call(t[:genus_id]))
      end
      out.puts({ protonym_id: p['id'], group: group, name_type: ntype, name: nname, epithet: epithet,
                 name_gender: ngender, has_notes_page: notes_pages.include?(p['id']),
                 authorship_reference_id: rid, authorship_key: key, year: year, pages: pages,
                 reference_pagination: pagination, nesting_reference_id: nesting,
                 pdf: pdf, pdf_reference_id: pdf_rid, taxa: ts }
        .merge(p.except('id', 'name_id', 'authorship_id')).to_json)
      counts["#{group} protonyms"] += 1
      counts["#{group} pdf=#{pdf.presence || 'none'}"] += 1
      if group == 'species_group'
        counts['species_group no part of speech'] += 1 if p['gender_agreement_type'].blank?
        counts['species_group no etymology and no derivation'] += 1 if p['etymology_taxt'].blank? && p['etymology_derivation'].blank?
      else
        counts['genus_group a taxon without gender'] += 1 if ts.any? { |t| t[:name_gender].blank? }
        counts['genus_group no etymology and no derivation'] += 1 if p['etymology_taxt'].blank? && p['etymology_derivation'].blank?
      end
    end
end
counts.sort.each { |k, v| puts format('  %-50s %6d', k, v) }
puts "Wrote #{path}"
