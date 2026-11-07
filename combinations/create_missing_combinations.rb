# frozen_string_literal: true
#
# create_missing_combinations.rb
#
# Creates obsolete-combination Species records from an approved list produced by
# missing_combinations_dryrun.rb and reviewed by hand. Same record shape as the
# editor's "create obsolete combination" button (Taxa::Operations::CreateObsoleteCombination):
# Species, status obsolete combination, same protonym, parent = obsolete genus,
# current_taxon = the protonym's terminal taxon. Spelling comes from the list.
#
# Every row is re-checked against live data before saving. Any failed check skips the row.
#
# Input:  /app/tmp/missing_combinations_approved.tsv
#         columns: proposed_name protonym_id genus_id current_taxon_id (others ignored)
# Env:    MODE=check (default; validates, saves nothing) | MODE=write
#         LIMIT=n    (process only the first n rows; canary)
#         ONLY=ids   (comma-separated protonym_ids to process; canary)
# Output: /app/tmp/create_missing_combinations_<MODE>_<uuid>.tsv (one line per row: result)
#
# Write mode: AntCatBot is the editor (PaperTrail whodunnit and Activity user),
# activities are automated_edit: true, and every Activity and PaperTrail version
# in the run carries one request_uuid (printed at start and end). Rollback:
# rollback_missing_combinations.rb with that UUID.
#
# Run:
#   docker exec -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/create_missing_combinations.rb

IN = Rails.root.join('tmp', 'missing_combinations_approved.tsv').to_s
MODE = ENV.fetch('MODE', 'check')
raise "MODE must be check or write" unless %w[check write].include?(MODE)
LIMIT = ENV['LIMIT']&.to_i
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
EDIT_SUMMARY = '[automated] Add missing obsolete combination from "Combination in" history item ' \
               '(claude/MISSING_COMBINATIONS_PLAN.md)'
ALLOWED_GENUS_STATUSES = [Status::VALID, Status::SYNONYM, Status::HOMONYM]

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "create_missing_combinations_#{MODE}_#{uuid}.tsv").to_s

lines = File.readlines(IN, chomp: true)
header = lines.shift.split("\t")
rows = lines.map { |l| header.zip(l.split("\t", -1)).to_h }
rows.select! { |r| ONLY.include?(r['protonym_id'].to_i) } if ONLY
rows = rows.first(LIMIT) if LIMIT

puts "MODE=#{MODE} request_uuid=#{uuid} rows=#{rows.size} editor=#{bot.name}(#{bot.id})"
stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result taxon_id proposed_name protonym_id genus_id current_taxon_id detail].join("\t")
log = ->(result, r, taxon_id = nil, detail = nil) do
  stats[result] += 1
  out.puts [result, taxon_id, r['proposed_name'], r['protonym_id'], r['genus_id'], r['current_taxon_id'],
            detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
end

rows.each do |r|
  name = r['proposed_name'].to_s.strip
  protonym = Protonym.find_by(id: r['protonym_id'])
  genus = Taxon.find_by(id: r['genus_id'])
  current = Taxon.find_by(id: r['current_taxon_id'])

  next log.('skip', r, nil, 'protonym not found') unless protonym
  next log.('skip', r, nil, 'genus not a Genus') unless genus.is_a?(Genus)
  next log.('skip', r, nil, "genus status #{genus.status}") unless ALLOWED_GENUS_STATUSES.include?(genus.status)
  next log.('skip', r, nil, 'current taxon not a Species') unless current.is_a?(Species)
  next log.('skip', r, nil, 'current taxon on another protonym') unless current.protonym_id == protonym.id
  next log.('skip', r, nil, "current taxon status #{current.status} not terminal") \
    unless Status::TERMINAL_STATUSES.include?(current.status)
  parts = name.split
  next log.('skip', r, nil, 'name is not a binomial') unless parts.size == 2
  next log.('skip', r, nil, 'genus part does not match genus') unless parts.first == genus.name.name
  next log.('skip', r, nil, 'already present: protonym has a taxon in this genus') \
    if Taxon.where(protonym_id: protonym.id, genus_id: genus.id).exists?
  next log.('skip', r, nil, 'name clash: name already in use') if Taxa::NameClash[name]

  taxon = Species.new
  taxon.name = SpeciesName.new(name: name)
  taxon.protonym = protonym
  taxon.parent = genus
  taxon.current_taxon = current
  taxon.status = Status::OBSOLETE_COMBINATION

  unless taxon.valid?
    next log.('invalid', r, nil, taxon.errors.full_messages.to_sentence)
  end

  if MODE == 'check'
    log.('would_create', r)
    next
  end

  begin
    ActiveRecord::Base.transaction do
      taxon.save!
      activity = taxon.create_activity(Activity::CREATE_OBSOLETE_COMBINATION, bot, edit_summary: EDIT_SUMMARY)
      activity.update!(automated_edit: true)
    end
    log.('created', r, taxon.id)
  rescue StandardError => e
    log.('error', r, nil, "#{e.class}: #{e.message}")
  end
end

out.close
stats.sort.each { |k, v| puts format('  %-20s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
