# frozen_string_literal: true
#
# correct_genus_gender.rb -- changes the recorded gender of named genus-group names, and the AntCat derivation
# of their protonyms, from one exact value to another. Only after Brian's decision for these names (21 Nov 2026,
# 14:45: the -idris names whose original authors did not treat them as feminine, Art. 30.1.4.2, and Promyopias,
# Art. 30.1.2; record in claude/gender-etymology-2026-11-16.md).
#
# Input TSV columns: kind, record_id, name, old, new
#   kind gender      record_id = taxon id; changes names.gender of the taxon's name record from old to new
#   kind derivation  record_id = protonym id; changes protonyms.etymology_derivation from old to new
# Every row is held (nothing written for it) when the record or name differs from the input, the stored value is
# not exactly `old`, the save would change any other column (apart from AntCat's whitespace tidy of notes_taxt
# on a protonym save), validation fails, or the stored value differs from `new` afterwards. A gender row is also
# held when its name record is used by a taxon not in the input. Species-group names are never touched: the run
# prints, for each gender row, how many species-group taxa sit in that genus-group taxon and that their names
# are unchanged after the save.
#
# Env:    MODE=check (default; always rolls back) | MODE=write; INPUT=/app/tmp/genus_gender_corrections.tsv;
#         ONLY=record ids
# Output: /app/tmp/correct_genus_gender_<MODE>_<uuid>.tsv: result, kind, record_id, name, old, new, detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per record.
# Rollback: the dump taken before the run, or PaperTrail versions by request_uuid (old values in the input).
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'genus_gender_corrections.tsv').to_s)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
INPUT_COLUMNS = %w[kind record_id name old new].freeze
# The summaries of the first run (21 Nov 14:53, the -idris names and Promyopias) named those cases; from the second
# run (21 Nov, group 1 of the 54 open genders) they are general, and the basis of each name is in its derivation.
SUMMARY = {
  'gender' => '[automated] Gender of the genus-group name corrected under ICZN Art. 30; the grammatical basis and ' \
              'the article are in the AntCat derivation. No species-group name or spelling changed',
  'derivation' => '[automated] AntCat derivation: gender sentence added, giving the basis of the gender (ICZN Art. 30)'
}.freeze

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
rows.each do |r|
  abort "Unknown kind #{r['kind']}" unless SUMMARY.key?(r['kind'])
  abort "Unknown gender #{r['new']}" if r['kind'] == 'gender' && !Name::GENDERS.include?(r['new'])
  abort "Derivation with markup other than <i>: #{r['record_id']}" if r['kind'] == 'derivation' &&
                                                                      r['new'].gsub(%r{</?i>}, '').match?(/[<>]/)
end
gender_taxon_ids = rows.select { |r| r['kind'] == 'gender' }.map { |r| r['record_id'].to_i }
rows = rows.select { |r| ONLY.include?(r['record_id'].to_i) } if ONLY

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "correct_genus_gender_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} rows=#{rows.size}"

def species_group_names_in taxon
  scope = taxon.type == 'Subgenus' ? Taxon.where(subgenus_id: taxon.id) : Taxon.where(genus_id: taxon.id)
  scope.where(type: %w[Species Subspecies Infrasubspecies]).joins(:name).order(:id).pluck(:id, 'names.name')
end

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result kind record_id name old new detail].join("\t")

rows.each do |r|
  id = r['record_id'].to_i
  result = detail = ''
  begin
    ActiveRecord::Base.transaction do
      if r['kind'] == 'gender'
        taxon = Taxon.find_by(id: id) or raise Reject, 'taxon not found'
        raise Reject, "not a genus or subgenus (#{taxon.type})" unless %w[Genus Subgenus].include?(taxon.type)

        name = taxon.name
        raise Reject, "name differs (#{name.name} vs #{r['name']})" unless name.name == r['name']
        raise Reject, "gender is #{name.gender.inspect}, not #{r['old']}" unless name.gender.to_s == r['old']

        others = Taxon.where(name_id: name.id).where.not(id: gender_taxon_ids).pluck(:id)
        raise Reject, "name record shared with taxa not in the input: #{others.first(5).join(', ')}" if others.any?

        before = species_group_names_in(taxon)
        name.gender = r['new']
        raise Reject, "invalid: #{name.errors.full_messages.join('; ')}" unless name.valid?
        extra = name.changes.keys - %w[gender]
        raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

        name.save!
        changed = name.saved_changes.keys - %w[gender updated_at]
        raise Reject, "saved changes beyond the gender: #{changed.join(', ')}" if changed.any?
        raise Reject, 'stored gender differs from the input' unless name.reload.gender == r['new']
        after = species_group_names_in(taxon)
        raise Reject, 'a species-group name changed' unless before == after

        taxon.create_activity(Activity::UPDATE, bot, edit_summary: SUMMARY['gender']).update_columns(automated_edit: true)
        detail = "#{before.size} species-group taxa in it, names unchanged"
      else
        p = Protonym.find_by(id: id) or raise Reject, 'protonym not found'
        raise Reject, "name differs (#{p.name.name} vs #{r['name']})" unless p.name.name == r['name']
        raise Reject, 'derivation is not the expected old text' unless p.etymology_derivation.to_s == r['old']

        p.etymology_derivation = r['new']
        raise Reject, "invalid: #{p.errors.full_messages.join('; ')}" unless p.valid?
        extra = p.changes.keys - %w[etymology_derivation]
        tidied = extra.select { |c| c == 'notes_taxt' && p.notes_taxt.to_s.gsub(/\s+/, '') == p.notes_taxt_was.to_s.gsub(/\s+/, '') }
        extra -= tidied
        raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

        p.save!
        changed = p.saved_changes.keys - %w[etymology_derivation updated_at] - tidied
        raise Reject, "saved changes beyond the derivation: #{changed.join(', ')}" if changed.any?
        raise Reject, 'stored derivation differs from the input' unless p.reload.etymology_derivation == r['new']

        p.create_activity(Activity::UPDATE, bot, edit_summary: SUMMARY['derivation']).update_columns(automated_edit: true)
        detail = tidied.any? ? 'notes_taxt: whitespace tidied by the save' : ''
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
  stats["#{r['kind']}: #{result}#{result == 'held' ? " (#{detail.sub(/ \(.*/, '')})" : ''}"] += 1
  out.puts [result, r['kind'], id, r['name'], r['old'], r['new'], detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
  puts "  #{result} #{r['kind']} #{id} #{r['name']} #{detail}"
end
out.close
stats.sort.each { |k, v| puts format('  %-60s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
