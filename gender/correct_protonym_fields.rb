# frozen_string_literal: true
#
# correct_protonym_fields.rb -- corrects fields written by gender/write_protonym_fields.rb after an audit found an
# error in the proposals (16 Nov 2026: Lewis & Short proper nouns read as adjectives, false compound splits). Two
# actions, one input row per protonym and field:
#   revert  put back the value the field held before the write (PaperTrail; empty for nearly all)
#   update  replace the written value with a corrected one (only the values listed in UPDATE_VALUES)
#
# Only what the write itself set is touched. Per field, held when the write did not change that field (it was
# "already" set, by someone else); per protonym, nothing is changed when:
#   - the protonym or name differs from the input
#   - a field no longer holds the value the write stored (someone edited it since)
#   - the interpretation status is disputed or unresolved
#   - the save would change any column besides the input's fields, or validation fails, or a stored value differs
#     from the target after the save
#
# Env:    MODE=check (default; always rolls back) | MODE=write; INPUT=/app/tmp/protonym_fields_corrections.tsv
#         (default); WRITE_REQUESTS=the write's request_uuids, comma-separated (required); ONLY=ids; LIMIT=n
# Input:  TSV protonym_id, protonym_name, action, field, written_value, new_value, reason
# Output: /app/tmp/correct_protonym_fields_<MODE>_<uuid>.tsv: result, protonym_id, name, field, old, new, action,
#         detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym corrected.
# Rollback: the dump taken before the run, or PaperTrail versions by this run's request_uuid.
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'protonym_fields_corrections.tsv').to_s)
WRITE_REQUESTS = ENV.fetch('WRITE_REQUESTS', '').split(',').map(&:strip).reject(&:empty?)
abort 'WRITE_REQUESTS (the request_uuids of the write being corrected) is required' if WRITE_REQUESTS.empty?
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
INPUT_COLUMNS = %w[protonym_id protonym_name action field written_value new_value reason].freeze
FIELDS = %w[gender_agreement_type part_of_speech_basis interpretation_status etymology_derivation].freeze
UPDATE_VALUES = {
  'gender_agreement_type' => %w[adjective participle noun_in_apposition],
  'part_of_speech_basis' => %w[grammatical_form author_stated noun_by_default],
  'interpretation_status' => %w[demonstrated reasonably_inferred]
}.freeze
SUMMARY = {
  'revert' => '[automated] Correction after an audit (16 Nov 2026): the part of speech, its basis and the ' \
              'interpretation status recorded earlier today are removed; the reading was not confirmed (a false ' \
              'compound split or a misread dictionary entry) and is held for review. Spelling unchanged',
  'update' => '[automated] Correction after an audit (16 Nov 2026) of the dictionary readings, the compound parses ' \
              'and the original descriptions: the part of speech, its basis or the interpretation status recorded ' \
              'by AntCatBot is corrected; under the AntCat policy on name grammar and spelling. Spelling unchanged'
}.freeze

DONE = { 'revert' => 'reverted', 'update' => 'updated' }.freeze

abort "No input file #{INPUT}" unless File.exist?(INPUT)

class Reject < StandardError; end

def clean(value)
  value.to_s.gsub(/[\t\r\n]+/, ' ')
end

lines = File.readlines(INPUT, chomp: true, encoding: 'UTF-8').reject(&:empty?)
header = lines.shift.split("\t", -1)
abort "Input columns must be #{INPUT_COLUMNS.join(', ')}" unless header == INPUT_COLUMNS
rows = lines.map do |line|
  fields = line.split("\t", -1)
  abort "Input line with #{fields.size} fields: #{line[0, 80]}" unless fields.size == header.size
  header.zip(fields).to_h
end

rows.each do |r|
  where = "(protonym #{r['protonym_id']}, #{r['field']})"
  abort "Unknown field #{where}" unless FIELDS.include?(r['field'])
  abort "Unknown action #{r['action'].inspect} #{where}" unless SUMMARY.key?(r['action'])
  abort "No written_value #{where}" if r['written_value'].empty?
  if r['action'] == 'update'
    allowed = UPDATE_VALUES[r['field']] or abort "update may not change #{where}"
    abort "update may not write #{r['new_value'].inspect} #{where}" unless allowed.include?(r['new_value'])
  else
    abort "revert takes no new_value #{where}" unless r['new_value'].empty?
  end
end
groups = rows.group_by { |r| r['protonym_id'].to_i }
groups.each do |pid, g|
  abort "Protonym #{pid}: one action per protonym" unless g.map { |r| r['action'] }.uniq.size == 1
  abort "Protonym #{pid}: a field twice" unless g.map { |r| r['field'] }.uniq.size == g.size
  # a revert removes everything the write set on the protonym, so basis and status never outlive their part of speech
  abort "Protonym #{pid}: a revert must include the part of speech, its basis and its status" if
    g.first['action'] == 'revert' && (%w[gender_agreement_type part_of_speech_basis interpretation_status] - g.map { |r| r['field'] }).any?
end
groups = groups.select { |pid, _| ONLY.include?(pid) } if ONLY
groups = groups.first(LIMIT).to_h if LIMIT

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "correct_protonym_fields_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} " \
     "write_requests=#{WRITE_REQUESTS.join(',')} protonyms=#{groups.size} rows=#{groups.values.sum(&:size)}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id name field old new action detail].join("\t")

groups.each do |pid, g|
  action = g.first['action']
  name = nil
  results = g.to_h { |r| [r['field'], { old: nil, new: r['new_value'], result: '', detail: '' }] }
  begin
    ActiveRecord::Base.transaction do
      p = Protonym.find_by(id: pid)
      raise Reject, 'protonym not found' unless p
      name = p.name.name
      g.each { |r| results[r['field']][:old] = p[r['field']] }
      raise Reject, "name differs (#{name} vs #{g.first['protonym_name']})" unless name == g.first['protonym_name']
      raise Reject, "interpretation is #{p.interpretation_status}" if
        p.interpretation_status.in?(Protonym::SCRIPTED_SPELLING_CHANGE_BLOCKED_STATUSES)
      g.each do |r|
        raise Reject, "#{r['field']} is #{p[r['field']].inspect} now, not the written #{r['written_value'].inspect}" unless
          p[r['field']].to_s == r['written_value']
      end
      versions = PaperTrail::Version.where(item_type: 'Protonym', item_id: pid, request_uuid: WRITE_REQUESTS).order(:id).to_a
      raise Reject, 'no version from the write' if versions.empty?

      assign = {}
      g.each do |r|
        f = r['field']
        changes = versions.map { |v| v.changeset[f] }.compact
        change = changes.last
        if change.nil?
          # "already": the value was there before the write; not the write's to correct, and never replaced
          raise Reject, "#{f} was set before the write" if action == 'update'

          results[f].merge!(result: 'kept', detail: 'not set by the write')
        elsif change.last.to_s != r['written_value']
          raise Reject, "the write stored #{change.last.inspect} in #{f}, not #{r['written_value'].inspect}"
        else
          # a revert goes back to the value before the first of the listed requests (a write, then a correction)
          target = action == 'revert' ? changes.first.first : r['new_value']
          results[f][:new] = target
          assign[f] = target
        end
      end
      if assign.any?
        p.assign_attributes(assign)
        raise Reject, "invalid: #{p.errors.full_messages.join('; ')}" unless p.valid?
        extra = p.changes.keys - assign.keys
        raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

        p.save!
        changed = p.saved_changes.keys - assign.keys - %w[updated_at]
        raise Reject, "saved changes beyond the input's fields: #{changed.join(', ')}" if changed.any?
        p.reload
        assign.each { |f, v| raise Reject, "stored #{f} differs from the target" unless p[f].to_s == v.to_s }

        p.create_activity(Activity::UPDATE, bot, edit_summary: SUMMARY[action]).update_columns(automated_edit: true)
        assign.each_key { |f| results[f].merge!(result: MODE == 'check' ? "would_#{action}" : DONE[action]) }
      end
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    results.each_value { |v| v.merge!(result: 'held', detail: e.message) }
  rescue ActiveRecord::ActiveRecordError => e
    results.each_value { |v| v.merge!(result: 'error', detail: "#{e.class}: #{e.message}") }
  end
  g.each do |r|
    v = results[r['field']]
    stats["#{r['field']}: #{v[:result]}#{v[:result] == 'held' ? " (#{v[:detail].sub(/ \(.*/, '').sub(/ now.*| from .*/, '')})" : ''}"] += 1
    out.puts [v[:result], pid, name, r['field'], v[:old], v[:new], action, v[:detail]].map { |x| clean(x) }.join("\t")
  end
end
out.close
stats.sort.each { |k, v| puts format('  %-78s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
