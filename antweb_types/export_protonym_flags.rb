# export_protonym_flags.rb -- READ ONLY. One JSON object per species-group protonym with the facts
# needed to apply AntCat's type-information conventions before anything is drafted for a reviewer
# (Bradley, 2026-10-30): AntCat gives no type information under replacement names, nomina nuda,
# unavailable names (e.g. proposed in synonymy), or quadrinomials whose name was later used at
# another rank. Used by antweb_types/build_inserts.py --flags=...
#
# Run on the server inside the app container (runbook procedure 16):
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/export_protonym_flags.rb
# Tested on antcat-staging 2026-11-03 (commit 9d35f7e): 24,376 of 24,376 written, 0 errors; 373 replacement
# names, 491 with replacement-name history text, 314 nomina nuda, 1,396 all-unavailable, 1,215 quadrinomials.
# Output (host): /var/www/antcat-2/tmp/protonym_flags.jsonl
#
# Fields (checked against calacademy-research/antcat at 90407c3d9, 2026-11-03):
#   name_type              Name STI type: SpeciesName, SubspeciesName or InfrasubspeciesName
#   nomen_nudum            protonyms.nomen_nudum
#   replacement_name       a 'ReplacementNameFor' history item on this protonym, or one of its taxa
#                          is the homonym_replaced_by of another taxon
#   replacement_name_taxt  a free-text 'Taxt' history item on this protonym says "replacement name for"
#   taxon_statuses         distinct statuses of the protonym's taxa (Status::STATUSES)

require 'json'
require 'set'

SPECIES_GROUP = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze
OUT = Rails.root.join('tmp', 'protonym_flags.jsonl')
FileUtils.mkdir_p(File.dirname(OUT))
ActiveRecord::Base.logger = nil   # staging logs every SQL query at DEBUG; 300 KB of output on 2026-11-03

scope = Protonym.joins(:name).where(names: { type: SPECIES_GROUP }).includes(:name, :taxa)
total = scope.count
puts "Species-group protonyms: #{total}"

repl_items = HistoryItem.where(type: 'ReplacementNameFor').distinct.pluck(:protonym_id).to_set
repl_taxa  = Taxon.where.not(homonym_replaced_by_id: nil).distinct.pluck(:homonym_replaced_by_id)
repl_links = Taxon.where(id: repl_taxa).distinct.pluck(:protonym_id).to_set
repl_taxt  = HistoryItem.where(type: 'Taxt').where('taxt LIKE ?', '%eplacement name for%').distinct.pluck(:protonym_id).to_set
puts "Replacement-name protonyms: history items #{repl_items.size}, homonym links #{repl_links.size}, free text #{repl_taxt.size}"

n = 0; n_err = 0; counts = Hash.new(0)
File.open(OUT, 'w') do |f|
  scope.find_each(batch_size: 500) do |p|
    begin
      rec = {
        protonym_id: p.id,
        name_type: p.name.type,
        nomen_nudum: p.nomen_nudum,
        replacement_name: repl_items.include?(p.id) || repl_links.include?(p.id),
        replacement_name_taxt: repl_taxt.include?(p.id),
        taxon_statuses: p.taxa.map(&:status).uniq.sort
      }
      f.puts(rec.to_json)
      n += 1
      counts['nomen_nudum'] += 1 if rec[:nomen_nudum]
      counts['replacement_name'] += 1 if rec[:replacement_name]
      counts['replacement_name_taxt'] += 1 if rec[:replacement_name_taxt]
      counts['InfrasubspeciesName'] += 1 if rec[:name_type] == 'InfrasubspeciesName'
      counts['all_unavailable'] += 1 if rec[:taxon_statuses].any? && rec[:taxon_statuses].all? { |s| s == 'unavailable' }
    rescue => e
      n_err += 1
      warn "ERR protonym #{p.id}: #{e.class} #{e.message}" if n_err <= 20
    end
  end
end

puts "Wrote #{n} of #{total} to #{OUT} (errors: #{n_err})"
counts.sort.each { |k, v| puts "  #{k}: #{v}" }
puts "FLAGS EXPORT INCOMPLETE" if n != total || n_err > 0
