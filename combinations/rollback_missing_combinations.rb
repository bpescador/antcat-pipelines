# frozen_string_literal: true
#
# rollback_missing_combinations.rb
#
# Removes the taxa created by one run of create_missing_combinations.rb, found by
# the run's request_uuid on PaperTrail "create" versions. Each taxon is removed only if:
#   - it is still an obsolete combination created in that run, and
#   - nothing links to it (Taxa::WhatLinksHere: columns and taxt tags).
# Anything that fails a check is listed and left alone. Its name record goes with it
# (Taxon belongs_to :name, dependent: :destroy). Each removal gets a destroy Activity
# by AntCatBot, automated_edit: true.
#
# Env: UUID=<request_uuid> (required); MODE=check (default) | MODE=write
# Run:
#   docker exec -w /app -e RAILS_ENV=production -e UUID=... -e MODE=check antcat-app \
#     bundle exec rails runner tmp/rollback_missing_combinations.rb

UUID = ENV.fetch('UUID')
MODE = ENV.fetch('MODE', 'check')
raise "MODE must be check or write" unless %w[check write].include?(MODE)

bot = User.find_by!(name: 'AntCatBot')
RequestStore.store[:current_request_uuid] = SecureRandom.uuid
PaperTrail.request.whodunnit = bot.id.to_s

ids = PaperTrail::Version.where(request_uuid: UUID, item_type: 'Taxon', event: 'create').pluck(:item_id).uniq
puts "MODE=#{MODE} UUID=#{UUID} taxa created in run: #{ids.size}"
stats = Hash.new(0)

ids.each do |id|
  taxon = Taxon.find_by(id: id)
  if taxon.nil?
    stats['already gone'] += 1
    next
  end
  unless taxon.status == Status::OBSOLETE_COMBINATION
    stats['kept: status changed'] += 1
    puts "kept #{id} #{taxon.name_cache}: status now #{taxon.status}"
    next
  end
  if taxon.what_links_here.any?
    stats['kept: something links here'] += 1
    puts "kept #{id} #{taxon.name_cache}: linked from elsewhere"
    next
  end
  if MODE == 'check'
    stats['would remove'] += 1
    next
  end
  ActiveRecord::Base.transaction do
    taxon.destroy!
    taxon.create_activity(Activity::DESTROY, bot, edit_summary: "[automated] Roll back run #{UUID}").
      update!(automated_edit: true)
  end
  stats['removed'] += 1
end

stats.sort.each { |k, v| puts format('  %-30s %6d', k, v) }
