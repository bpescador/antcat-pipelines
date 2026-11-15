# frozen_string_literal: true
#
# write_etymology_sources.rb -- records where each existing etymology was printed: the source (original
# description or later work), the reference of a later work, and the printed page. Nothing else.
#
# Brian's approval of 14 Nov 2026 (17:43), with his conditions: only rows whose printed page is confidently
# established; the etymology text is never changed; no unrelated field is changed; a log of every protonym with its
# old and new values and every failure. The rows come from gender/etymology_sources.py and passed
# gender/verify_etymology_sources.py (verdict ok) and a page-image sample; the input file is built from them by
# gender/build_etymology_write_input.py.
#
# Per protonym, inside one transaction (MODE=check always rolls back). Held, not written, when:
#   - the etymology text is not the one matched (md5 of the text as exported), or the protonym or name differs
#   - a source, reference or page is already recorded (nothing is overwritten)
#   - original description: the authorship reference is not the one in the input
#   - later work: the reference does not exist, or is the authorship reference
#   - the save would change any column besides etymology_source, etymology_reference_id, etymology_pages
#     (the model's taxt cleanups run on save; they must not touch the etymology or the type fields)
#   - validation fails; or the stored values differ from the input after the save
#
# Env:    MODE=check (default) | MODE=write; INPUT=/app/tmp/etymology_sources_write_input.tsv (default);
#         ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/write_etymology_sources_<MODE>_<uuid>.tsv, one row per protonym:
#         result, protonym_id, name, old source/reference/pages, new source/reference/pages, detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: the dump taken before the run, or PaperTrail versions by request_uuid (the three columns
# were empty before; setting them back to nil restores the protonym).
#
# Run (runbook procedure 16; staging first):
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/write_etymology_sources.rb

# No csv: Ruby 3.4 made it a bundled gem and AntCat's Gemfile does not list it, so `require 'csv'` fails under
# bundle exec (the staging dry run of 14 Nov; export_references.rb has the same note). The input is plain TSV.
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'etymology_sources_write_input.tsv').to_s)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] Etymology source recorded: where the etymology was printed (source, reference, page); ' \
               'text unchanged (claude/gender-etymology-roadmap-2026-11-12.md)'
ALLOWED = %w[etymology_source etymology_reference_id etymology_pages].freeze
INPUT_COLUMNS = %w[protonym_id protonym_name source reference_id pages etymology_md5].freeze

abort 'PR #1607 is not deployed (no etymology source fields).' unless Protonym.column_names.include?('etymology_source')
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
OUT = Rails.root.join('tmp', "write_etymology_sources_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} rows=#{rows.size}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id name old_source old_reference_id old_pages
            new_source new_reference_id new_pages detail].join("\t")

rows.each do |r|
  pid = r['protonym_id'].to_i
  source = r['source']
  reference_id = r['reference_id'].presence&.to_i
  pages = r['pages']
  name = old = nil
  result = detail = ''
  begin
    ActiveRecord::Base.transaction do
      p = Protonym.find_by(id: pid)
      raise Reject, 'protonym not found' unless p
      name = p.name.name
      old = [p.etymology_source, p.etymology_reference_id, p.etymology_pages]
      raise Reject, "name differs (#{name} vs #{r['protonym_name']})" unless name == r['protonym_name']
      raise Reject, 'etymology text differs from the one matched' unless
        Digest::MD5.hexdigest(clean(p.etymology_taxt)) == r['etymology_md5']
      raise Reject, 'a source, reference or page is already recorded' if old.any?(&:present?)
      raise Reject, "unknown source #{source.inspect}" unless Protonym::ETYMOLOGY_SOURCES.key?(source)
      raise Reject, 'no page' if pages.blank?

      attrs = { 'etymology_source' => source, 'etymology_pages' => pages }
      if source == 'original_description'
        raise Reject, "authorship reference is #{p.authorship_reference&.id}, input #{reference_id}" unless
          p.authorship_reference&.id == reference_id
      else
        raise Reject, "reference #{reference_id} not found" unless Reference.exists?(reference_id)
        raise Reject, 'later-work reference is the authorship reference' if p.authorship_reference&.id == reference_id
        attrs['etymology_reference_id'] = reference_id
      end

      p.assign_attributes(attrs)
      raise Reject, "invalid: #{p.errors.full_messages.join('; ')}" unless p.valid?
      extra = p.changes.keys - ALLOWED
      raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

      p.save!
      changed = p.saved_changes.keys - ALLOWED - %w[updated_at]
      raise Reject, "saved changes beyond the three columns: #{changed.join(', ')}" if changed.any?
      p.reload
      stored = [p.etymology_source, p.etymology_reference_id, p.etymology_pages]
      expected = [source, (source == 'later_work' ? reference_id : nil), pages]
      raise Reject, "stored #{stored.inspect}, expected #{expected.inspect}" unless stored == expected
      raise Reject, 'etymology text changed on save' unless
        Digest::MD5.hexdigest(clean(p.etymology_taxt)) == r['etymology_md5']

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
  stats["#{result}#{result == 'held' ? ": #{detail.sub(/ \(.*/, '').sub(/ is \d.*/, '')}" : ''}"] += 1
  stats["#{result}: #{source}"] += 1 unless result == 'held'
  new_ref = source == 'later_work' ? reference_id : ''
  out.puts [result, pid, name, *(old || ['', '', '']), source, new_ref, pages, detail].
    map { |v| clean(v) }.join("\t")
end
out.close
stats.sort.each { |k, v| puts format('  %-70s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
