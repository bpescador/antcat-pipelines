# frozen_string_literal: true
#
# spelling_evidence_export.rb -- for a list of species-group protonyms, every reference AntCat cites for
# the name and its taxa, so the spelling each author used can be checked in the PDFs. Read only.
#
# Why: Brian, 13 Nov 2026. Part of speech is decided by ICZN Art. 31.2.2 where a name is ambiguous:
# a noun in apposition unless the evidence of usage is decisive. A spelling kept by prevailing usage
# (Arts. 33.2.3.1, 33.3.1) needs the most recent authors concerned with the taxon. Both need, per name,
# who wrote about it and which spelling they printed. AntCat's citations list the authors; the PDFs
# (pdfs/fetch_reference_pdfs.rb) show the spelling.
#
# Env:    PROTONYM_IDS=comma-separated protonym ids (required; at most 500)
# Output: tmp/spelling_evidence_names.tsv  one row per taxon of each protonym (name, status, genus gender)
#         tmp/spelling_evidence_refs.tsv   one row per protonym x reference: where AntCat cites it
#                                          (authorship, history item type, item on another protonym),
#                                          year, and whether AntCat holds a PDF
#         tmp/spelling_evidence_history.tsv every history item on the protonyms, as text
#         tmp/spelling_evidence_pdf_ids.txt the reference ids that have a PDF, comma-separated, ready for
#                                          fetch_reference_pdfs.rb ONLY="$(cat ...)"
# Run (runbook procedure 16):
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e PROTONYM_IDS=... antcat-app \
#     bundle exec rails runner tmp/spelling_evidence_export.rb

ActiveRecord::Base.logger = nil

ids = ENV.fetch('PROTONYM_IDS', '').split(',').map(&:strip).reject(&:empty?).map(&:to_i).uniq
abort 'PROTONYM_IDS=<protonym ids> is required' if ids.empty?
abort "#{ids.size} ids; at most 500 a run" if ids.size > 500

REF_TAG = /\{ref (\d+)\}/
clean = ->(v) { v.to_s.gsub(/[\t\r\n]+/, ' ') }
tsv = lambda do |name, header|
  path = Rails.root.join('tmp', name).to_s
  f = File.open(path, 'w')
  f.puts header.join("\t")
  [f, path]
end

names_f, names_path = tsv.call('spelling_evidence_names.tsv',
  %w[protonym_id original_name taxon_id taxon_name status original_combination genus genus_gender])
refs_f, refs_path = tsv.call('spelling_evidence_refs.tsv',
  %w[protonym_id original_epithet reference_id citation year where has_pdf])
hist_f, hist_path = tsv.call('spelling_evidence_history.tsv',
  %w[protonym_id history_item_id position type text])

pdf_refs = Set.new
stats = Hash.new(0)

ids.each do |pid|
  protonym = Protonym.find_by(id: pid)
  unless protonym
    puts "#{pid}\tno protonym"
    stats['missing'] += 1
    next
  end
  stats['protonyms'] += 1
  epithet = protonym.name.epithet

  protonym.taxa.includes(:name).find_each do |t|
    genus = t.respond_to?(:genus) ? t.genus : nil
    names_f.puts [pid, protonym.name.name, t.id, t.name.name, t.status, t.original_combination?,
                  genus&.name&.name, genus&.name&.gender].map(&clean).join("\t")
  end

  cited = Hash.new { |h, k| h[k] = [] } # reference_id => where
  cited[protonym.authorship.reference_id] << 'authorship'

  protonym.history_items.each do |item|
    text = item.to_taxt.to_s
    hist_f.puts [pid, item.id, item.position, item.type, text].map(&clean).join("\t")
    cited[item.reference_id] << item.type if item.reference_id
    text.scan(REF_TAG).flatten.each { |rid| cited[rid.to_i] << "#{item.type} (in text)" unless rid.to_i == item.reference_id }
  end

  taxon_ids = protonym.taxa.pluck(:id)
  HistoryItem.where(object_protonym_id: pid).or(HistoryItem.where(object_taxon_id: taxon_ids)).
    where.not(protonym_id: pid).find_each do |item|
    cited[item.reference_id] << "#{item.type} on protonym #{item.protonym_id}" if item.reference_id
  end
  taxon_ids.each do |tid|
    HistoryItem.where.not(protonym_id: pid).where('taxt LIKE ?', "%{tax #{tid}}%").limit(200).each do |item|
      item.taxt.to_s.scan(REF_TAG).flatten.each do |rid|
        cited[rid.to_i] << "#{item.type} on protonym #{item.protonym_id} (in text)"
      end
    end
  end

  %i[notes_taxt etymology_taxt primary_type_information_taxt secondary_type_information_taxt type_notes_taxt].each do |field|
    protonym.public_send(field).to_s.scan(REF_TAG).flatten.each { |rid| cited[rid.to_i] << field.to_s }
  end

  Reference.where(id: cited.keys).includes(:document).find_each do |ref|
    has_pdf = ref.document&.file_file_name.present?
    pdf_refs << ref.id if has_pdf
    refs_f.puts [pid, epithet, ref.id, ref.plain_text_key_with_suffixed_year, ref.year,
                 cited[ref.id].uniq.join('; '), has_pdf].map(&clean).join("\t")
    stats['protonym x reference'] += 1
  end
end

[names_f, refs_f, hist_f].each(&:close)
stats.each { |k, v| puts format('%-22s %d', k, v) }
puts "references with a PDF: #{pdf_refs.size}"
puts "Files: #{names_path}, #{refs_path}, #{hist_path}"
only_path = Rails.root.join('tmp', 'spelling_evidence_pdf_ids.txt').to_s
File.write(only_path, pdf_refs.to_a.sort.join(','))
puts "Reference ids with a PDF (for fetch_reference_pdfs.rb ONLY=): #{only_path}"
