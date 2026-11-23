# frozen_string_literal: true
#
# noun_policy_export.rb -- read-only export for the AntCat policy question on author-designated nouns in apposition
# that have Latin adjectival forms (Brian, 22 Nov 2026). Writes nothing to the database.
#
# Lists every species-group protonym where
#   (A) the sourced etymology calls the name a noun ("noun", "apposition", "substantive"), or
#   (B) AntCat records it as a noun in apposition on the author's statement (part_of_speech_basis author_stated), or
#   (C) the protonym note mentions the authors calling it a noun (an AntCat override),
# with the epithet's ending class and every current taxon of the protonym (name, status, genus gender), so the
# paper can count which names each policy would spell differently.
#
# Output: /app/tmp/noun_policy_export_<timestamp>.tsv
ActiveRecord::Base.logger = nil
Rails.logger.level = :info

NOUN = /\b(noun|apposition|substantiv)/i
ADJ_ENDINGS = { 'us/a/um' => /(us|a|um)\z/, 'er' => /(er|ra|rum)\z/, 'is/e' => /(is|e)\z/, 'ns/x' => /(ns|x)\z/ }.freeze

def ending_class(epithet)
  return 'ensis' if epithet.end_with?('ensis', 'ense')
  ADJ_ENDINGS.each { |k, re| return k if epithet.match?(re) }
  'other'
end

def flat(text)
  text.to_s.gsub(/[\t\r\n]+/, ' ')
end

scope = Protonym.joins(:name).where(names: { type: %w[SpeciesName SubspeciesName InfrasubspeciesName] })
picked = scope.where('etymology_taxt REGEXP ?', 'noun|apposition|substantiv')
              .or(scope.where(part_of_speech_basis: 'author_stated'))
              .or(scope.where('notes_taxt REGEXP ?', 'call[s]? .* (a )?(Latin )?noun|noun in apposition'))
              .includes(:name).order(:id)

out = Rails.root.join('tmp', "noun_policy_export_#{Time.current.strftime('%Y%m%d%H%M%S')}.tsv").to_s
cols = %w[protonym_id protonym_name epithet ending_class source_flags gender_agreement_type part_of_speech_basis
          interpretation_status taxa etymology_taxt notes_taxt]
n = 0
File.open(out, 'w') do |f|
  f.puts cols.join("\t")
  picked.find_each do |p|
    ep = p.name.epithet.to_s
    flags = []
    flags << 'A' if p.etymology_taxt.to_s.match?(NOUN)
    flags << 'B' if p.part_of_speech_basis == 'author_stated'
    flags << 'C' if p.notes_taxt.to_s.match?(/noun/i)
    taxa = Taxon.where(protonym_id: p.id).includes(:name).map do |t|
      genus = t.respond_to?(:genus) ? t.genus : nil
      "#{t.id} #{t.name.name} [#{t.status}; genus #{genus&.name&.gender || '-'}]"
    end
    f.puts [p.id, p.name.name, ep, ending_class(ep), flags.join, p.gender_agreement_type, p.part_of_speech_basis,
            p.interpretation_status, taxa.join(' | '), flat(p.etymology_taxt), flat(p.notes_taxt)].join("\t")
    n += 1
  end
end
puts "protonyms: #{n}"
puts "Wrote #{out}"
