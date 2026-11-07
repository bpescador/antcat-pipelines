# frozen_string_literal: true
#
# verify_created_combinations.rb  (READ-ONLY)
#
# Lists the taxa created by one run of create_missing_combinations.rb (found by
# request_uuid on PaperTrail create versions) and checks each against the intended
# record shape. Prints one line per taxon and a summary.
#
# Env: UUID=<request_uuid>
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e UUID=... antcat-app \
#     bundle exec rails runner tmp/verify_created_combinations.rb

UUID = ENV.fetch('UUID')
ids = PaperTrail::Version.where(request_uuid: UUID, item_type: 'Taxon', event: 'create').pluck(:item_id).uniq
bot = User.find_by!(name: 'AntCatBot')
stats = Hash.new(0)

puts "UUID=#{UUID} taxa created: #{ids.size}"
# Plain lookups only (genus is not an association of base Taxon; see dry-run v3/v4 failures).
Taxon.where(id: ids).find_each do |t|
  stats['not a Species'] += 1 unless t.is_a?(Species)
  problems = []
  problems << "type #{t.type}" unless t.is_a?(Species)
  problems << "status #{t.status}" unless t.status == Status::OBSOLETE_COMBINATION
  problems << 'no current taxon' unless t.current_taxon
  problems << 'current taxon on other protonym' if t.current_taxon && t.current_taxon.protonym_id != t.protonym_id
  problems << 'genus part mismatch' unless t.name.name.split.first == t.genus&.name&.name
  problems << 'original_combination set' if t.original_combination
  acts = Activity.where(trackable_type: 'Taxon', trackable_id: t.id)
  problems << 'no activity' if acts.empty?
  problems << 'activity not automated' unless acts.all?(&:automated_edit)
  problems << 'activity not by AntCatBot' unless acts.all? { |a| a.user_id == bot.id }
  problems << 'activity uuid mismatch' unless acts.all? { |a| a.request_uuid == UUID }
  name_versions = PaperTrail::Version.where(item_type: 'Name', item_id: t.name_id, event: 'create')
  problems << 'name version uuid mismatch' unless name_versions.all? { |v| v.request_uuid == UUID }

  stats[problems.empty? ? 'ok' : 'PROBLEM'] += 1
  puts [t.id, t.name.name, "-> #{t.current_taxon&.name&.name} (#{t.current_taxon&.status})",
        "genus #{t.genus&.name&.name} (#{t.genus&.status})", "protonym #{t.protonym_id}",
        (problems.empty? ? 'ok' : "PROBLEM: #{problems.join('; ')}")].join(' | ')
end
stats.each { |k, v| puts "#{k}: #{v}" }
