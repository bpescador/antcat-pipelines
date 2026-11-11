# frozen_string_literal: true
#
# relabel_ngc_labels.rb -- replace NGC-style labels in species-group type fields with AntCat's own.
#
# The rule Bradley agreed in week 3 (2026-11-10), the same as bolton/ngc_labels.py (the drafts he
# checked):
#   primary_type_information_taxt:   Type-X            -> Primary type X
#   secondary_type_information_taxt: Paratype-X, Type-X -> Secondary type X
#   X = material, locality, localities, depository, depositories, specimen, specimens
# Only a label at the start of the field or of a sentence. Labels without a hyphen ("Type depositories:")
# are AntCat's own and never changed; type notes are never changed.
#
# Per protonym, inside one transaction: draft the new text; assert that nothing but labels differs; save
# through the model; re-read and require the stored text to equal the draft (the save's own cleanups
# must not change anything else). Held, not written: a primary field whose material names paratypes
# (an AntCat error to split by hand, e.g. Harpagoxenus zaisanicus 163912).
# MODE=check always rolls back. MODE=write keeps the protonyms that pass.
#
# Env:    MODE=check (default) | MODE=write; ONLY=protonym ids; LIMIT=n
# Output: /app/tmp/relabel_ngc_labels_<MODE>_<uuid>.tsv (one row per changed field)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym.
# Rollback of a write: the dump taken before the run, or PaperTrail versions by request_uuid.
#
# Run (runbook procedure 16; staging first):
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e MODE=check antcat-app \
#     bundle exec rails runner tmp/relabel_ngc_labels.rb

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
EDIT_SUMMARY = '[automated] NGC-style type labels to AntCat labels, e.g. "Type-depository:" to "Primary type depository:"'

X = '(material|localit(?:y|ies)|depositor(?:y|ies)|specimens?)'
START = '(?:\A|(?<=[.;]\s))'
FIELDS = {
  'primary_type_information_taxt' => [/#{START}Type-#{X}:/, 'Primary type '],
  'secondary_type_information_taxt' => [/#{START}(?:Paratype|Type)-#{X}:/, 'Secondary type ']
}.freeze
ANY_LABEL = /#{START}(?:(?:Primary|Secondary) type |Paratype-|Type[- ])#{X}:/
SPECIES_GROUP = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze

class Reject < StandardError; end

def strip_labels(text) = text.gsub(ANY_LABEL, ':')

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "relabel_ngc_labels_#{MODE}_#{uuid}.tsv").to_s

scope = Protonym.joins(:name).where(names: { type: SPECIES_GROUP }).
  where('primary_type_information_taxt LIKE ? OR secondary_type_information_taxt LIKE ? OR secondary_type_information_taxt LIKE ?',
        '%Type-%', '%Type-%', '%Paratype-%')
ids = scope.order(:id).pluck(:id)
ids &= ONLY if ONLY
ids = ids.first(LIMIT) if LIMIT
puts "MODE=#{MODE} request_uuid=#{uuid} candidate protonyms=#{ids.size}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id field labels before after detail].join("\t")
ids.each do |pid|
  rows = []
  result = nil
  begin
    ActiveRecord::Base.transaction do
      p = Protonym.find(pid)
      changes = {}
      FIELDS.each do |field, (rx, prefix)|
        old = p.public_send(field).to_s
        labels = old.scan(rx).size
        next if labels.zero?
        new = old.gsub(rx) { "#{prefix}#{Regexp.last_match(1)}:" }
        raise Reject, "#{field}: a character other than a label would change" unless strip_labels(new) == strip_labels(old)
        if field.start_with?('primary') && new =~ /material:[^.]*paratype/i
          raise Reject, 'paratypes in the primary field (split by hand)'
        end
        changes[field] = new
        rows << [field, labels, old, new]
      end
      raise Reject, 'no hyphenated label at a sentence start' if changes.empty?
      p.update!(changes)
      p.reload
      changes.each do |field, new|
        raise Reject, "#{field}: stored text differs from the draft after save" unless p.public_send(field).to_s == new
      end
      p.create_activity(Activity::UPDATE, bot, edit_summary: EDIT_SUMMARY).update_columns(automated_edit: true)
      result = MODE == 'check' ? 'would_relabel' : 'relabelled'
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    result = 'held'
    rows = [['', 0, '', '', e.message]]
  rescue ActiveRecord::RecordInvalid => e
    result = 'error'
    rows = [['', 0, '', '', e.message]]
  end
  stats[result] += 1
  stats["#{result}: #{rows.first[4]}"] += 1 if %w[held error].include?(result)
  rows.each do |field, labels, before, after, detail|
    out.puts [result, pid, field, labels, before, after, detail].map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
    stats["fields: #{field}"] += 1 if field.present?
  end
end
out.close
stats.sort.each { |k, v| puts format('  %-70s %6d', k, v) }
puts "Wrote #{OUT}"
puts "request_uuid=#{uuid}"
