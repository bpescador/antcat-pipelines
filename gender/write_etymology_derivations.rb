# frozen_string_literal: true
#
# write_etymology_derivations.rb -- writes AntCat derivations (`etymology_derivation`) under the AntCat policy on
# derived etymologies. Nothing else.
#
# First use: the toponym pilot approved by Brian on 14 Nov 2026 (20:16), from
# gender/propose_toponym_derivations.py --write-input. Staging first; production only after Brian has seen the
# staging dry run and examples.
#
# Per protonym, inside one transaction (MODE=check always rolls back). Held, not written, when:
#   - the protonym or name differs from the input
#   - the protonym has a sourced etymology (`etymology_taxt`): a published etymology takes precedence
#   - a derivation is already recorded (nothing is overwritten)
#   - the type locality differs from the one the derivation rests on (md5 of the locality as exported)
#   - the recorded part of speech is set and is not adjective (the toponym pilot states an adjectival suffix)
#   - the save would change any column besides `etymology_derivation` (the model's taxt cleanups run on save)
#   - validation fails, or the stored value differs from the input after the save
#
# Env:    MODE=check (default) | MODE=write; INPUT=/app/tmp/etymology_derivations_write_input.tsv (default);
#         ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/write_etymology_derivations_<MODE>_<uuid>.tsv: result, protonym_id, name, old derivation,
#         new derivation, detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback: the dump taken before the run, or PaperTrail versions by request_uuid (the field was empty before).
#
# No csv: Ruby 3.4 made it a bundled gem and AntCat's Gemfile does not list it (see write_etymology_sources.rb).
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'etymology_derivations_write_input.tsv').to_s)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] AntCat derivation recorded (toponym pilot), under the AntCat policy on derived ' \
               'etymologies; the published etymology fields, part of speech and spelling unchanged'
ALLOWED = %w[etymology_derivation].freeze
INPUT_COLUMNS = %w[protonym_id protonym_name derivation locality_md5].freeze

abort 'PR #1607 is not deployed (no etymology_derivation).' unless Protonym.column_names.include?('etymology_derivation')
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
rows = rows.select { |r| ONLY.include?(r['protonym_id'].to_i) } if ONLY
rows = rows.first(LIMIT) if LIMIT

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "write_etymology_derivations_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} rows=#{rows.size}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id name old_derivation new_derivation detail].join("\t")

rows.each do |r|
  pid = r['protonym_id'].to_i
  derivation = r['derivation']
  name = old = nil
  result = detail = ''
  begin
    ActiveRecord::Base.transaction do
      p = Protonym.find_by(id: pid)
      raise Reject, 'protonym not found' unless p
      name = p.name.name
      old = p.etymology_derivation
      raise Reject, "name differs (#{name} vs #{r['protonym_name']})" unless name == r['protonym_name']
      raise Reject, 'has a sourced etymology' if p.etymology_taxt.present?
      raise Reject, 'a derivation is already recorded' if old.present?
      raise Reject, 'type locality differs from the one the derivation rests on' unless
        Digest::MD5.hexdigest(clean(p.locality)) == r['locality_md5']
      if p.gender_agreement_type.present? && p.gender_agreement_type != 'adjective'
        raise Reject, "part of speech is #{p.gender_agreement_type}"
      end
      raise Reject, 'empty derivation' if derivation.blank?

      p.assign_attributes('etymology_derivation' => derivation)
      raise Reject, "invalid: #{p.errors.full_messages.join('; ')}" unless p.valid?
      extra = p.changes.keys - ALLOWED
      raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

      p.save!
      changed = p.saved_changes.keys - ALLOWED - %w[updated_at]
      raise Reject, "saved changes beyond the derivation: #{changed.join(', ')}" if changed.any?
      raise Reject, 'stored derivation differs from the input' unless p.reload.etymology_derivation == derivation

      p.create_activity(Activity::UPDATE, bot, edit_summary: EDIT_SUMMARY).update_columns(automated_edit: true)
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
  stats["#{result}#{result == 'held' ? ": #{detail.sub(/ \(.*/, '').sub(/ is [a-z_]+$/, '')}" : ''}"] += 1
  out.puts [result, pid, name, old.to_s, derivation, detail].map { |v| clean(v) }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-70s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
