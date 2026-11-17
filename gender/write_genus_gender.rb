# frozen_string_literal: true
#
# write_genus_gender.rb -- records the grammatical gender of genus-group names that have none (names.gender on the
# taxon's name record, which is what AntCat shows and uses). Nothing else.
#
# Input: gender/propose_genus_gender.py output (taxon_id, rank, name, status, subject, proposed, tier, basis).
# Rows without a proposal (tier C) are skipped. The gender is that of the genus-group name itself (ICZN Art. 30):
# a subgenus record takes the gender of the subgenus name. Species-group names agree with the genus (Art. 31.2),
# so a subgenus's gender changes no spelling; a GENUS's gender can change what AntCat's agreement check reports
# for its species, so read the dry run's "species in it" column for valid genera before writing.
#
# Per taxon, inside one transaction (MODE=check always rolls back). Held, not written, when:
#   - the taxon is not found, is not a genus or subgenus, or its name differs from the input
#   - the name already has a gender (nothing is overwritten)
#   - the same name record is used by another taxon or by a protonym whose taxon is not in the input
#     (the gender would change there too; listed for a look)
#   - the save would change any column besides `gender`, or validation fails
#
# Env:    MODE=check (default) | MODE=write; INPUT=/app/tmp/genus_gender_input.tsv (default);
#         ONLY=taxon ids; TIERS=A,B,... (default A,B,B2,K,M)
# Output: /app/tmp/write_genus_gender_<MODE>_<uuid>.tsv: result, taxon_id, name, name_id, gender, tier, detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per taxon.
# Rollback: the dump taken before the run, or PaperTrail versions by request_uuid (the field was empty before).
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'genus_gender_input.tsv').to_s)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
TIERS = ENV.fetch('TIERS', 'A,B,B2,K,M').split(',')
INPUT_COLUMNS = %w[taxon_id rank name status subject proposed tier basis].freeze
EDIT_SUMMARY = '[automated] Gender of the genus-group name recorded (ICZN Art. 30). No spelling changed'

abort "No input file #{INPUT}" unless File.exist?(INPUT)

class Reject < StandardError; end

lines = File.readlines(INPUT, chomp: true, encoding: 'UTF-8').reject(&:empty?)
header = lines.shift.split("\t", -1)
abort "Input columns must be #{INPUT_COLUMNS.join(', ')}" unless header == INPUT_COLUMNS
rows = lines.map do |line|
  fields = line.split("\t", -1)
  abort "Input line with #{fields.size} fields: #{line[0, 80]}" unless fields.size == header.size
  header.zip(fields).to_h
end
skipped = rows.count { |r| r['proposed'].empty? || TIERS.exclude?(r['tier']) }
rows = rows.reject { |r| r['proposed'].empty? || TIERS.exclude?(r['tier']) }
rows = rows.select { |r| ONLY.include?(r['taxon_id'].to_i) } if ONLY
input_taxon_ids = rows.map { |r| r['taxon_id'].to_i }

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "write_genus_gender_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} " \
     "rows=#{rows.size} skipped_without_proposal_or_tier=#{skipped} tiers=#{TIERS.join(',')}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result taxon_id name name_id gender tier detail].join("\t")

rows.each do |r|
  tid = r['taxon_id'].to_i
  gender = r['proposed']
  name_id = nil
  result = detail = ''
  begin
    ActiveRecord::Base.transaction do
      taxon = Taxon.find_by(id: tid)
      raise Reject, 'taxon not found' unless taxon
      raise Reject, "not a genus or subgenus (#{taxon.type})" unless %w[Genus Subgenus].include?(taxon.type)

      name = taxon.name
      name_id = name.id
      raise Reject, "name differs (#{name.name} vs #{r['name']})" unless name.name == r['name']
      raise Reject, "already has a gender (#{name.gender})" if name.gender.present?
      raise Reject, "unknown gender #{gender.inspect}" unless Name::GENDERS.include?(gender)

      others = Taxon.where(name_id: name.id).where.not(id: input_taxon_ids).pluck(:id)
      raise Reject, "the name record is shared with taxa not in the input: #{others.first(5).join(', ')}" if others.any?

      name.gender = gender
      raise Reject, "invalid: #{name.errors.full_messages.join('; ')}" unless name.valid?
      extra = name.changes.keys - %w[gender]
      raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

      name.save!
      changed = name.saved_changes.keys - %w[gender updated_at]
      raise Reject, "saved changes beyond the gender: #{changed.join(', ')}" if changed.any?
      raise Reject, 'stored gender differs from the input' unless name.reload.gender == gender

      taxon.create_activity(Activity::UPDATE, bot, edit_summary: EDIT_SUMMARY).update_columns(automated_edit: true)
      if taxon.type == 'Genus' && taxon.status == 'valid'
        detail = "valid genus: #{Taxon.where(genus_id: taxon.id, type: %w[Species Subspecies]).count} species-group taxa in it"
      end
      result = MODE == 'check' ? 'would_write' : 'written'
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    result = 'held'
    detail = e.message
  rescue ActiveRecord::ActiveRecordError => e
    result = 'error'
    detail = "#{e.class}: #{e.message}"
  end
  key = result == 'held' ? "held: #{detail.sub(/ \(.*/, '').sub(/:.*/, '')}" : "#{result} #{gender} (tier #{r['tier']})"
  stats[key] += 1
  out.puts [result, tid, r['name'], name_id, gender, r['tier'], detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-70s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
