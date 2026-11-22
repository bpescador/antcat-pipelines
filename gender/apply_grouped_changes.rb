# frozen_string_literal: true
#
# apply_grouped_changes.rb -- applies reviewed, exact old-to-new changes in groups: every row of a group is written
# together in one transaction, or none is. For decisions Brian has approved name by name (first use: 22 Nov 2026,
# the masculine gender of Ishakidris, Baracidris, Kartidris and Quadrulicapito with the agreeing spellings
# hastifer, pilosus, sparsipilus and longus; Hong's published etymologies of three -capito genera; corrected
# Art. 30 citations in 18 derivations). Record: claude/gender-etymology-2026-11-16.md.
#
# Input TSV columns: group, kind, record_id, label, field, old, new   (empty old = the field is empty now)
#   kind name_gender  record_id = genus-group taxon id; field gender: names.gender of the taxon's name record
#   kind taxon_name   record_id = species-group taxon id; field name: names.name of the taxon's own name record
#                     (epithet, cleaned name and the taxon's name cache follow). The protonym's name record, which
#                     holds the original spelling, is never touched: the row is held if the record is shared.
#   kind protonym     record_id = protonym id; field one of PROTONYM_FIELDS; rows of one protonym are saved together
#   kind taxon_delete record_id = taxon id; field status; old = 'unavailable misspelling', new empty. Deletes a
#                     misspelling record only: held unless its status and name are as given and nothing links to it
#                     (Taxon#what_links_here, as the taxon form's Delete). Before the delete the whole record (taxon,
#                     name, protonym id, what-links-here) is written to /app/tmp/deleted_taxon_<id>_<uuid>.json.
#                     Approved 22 Nov 2026 (Brian) for misspelling records that hold a correct original spelling.
# `label` is the record's name as AntCat has it (the taxon's or protonym's name before the run).
#
# A group is held (nothing in it written) when any of its rows fails: record or label differs, the stored value is
# not exactly `old`, a name record is shared (with a protonym or with a taxon outside the group), validation fails,
# the save would change any column not in the input (apart from AntCat's whitespace tidy of notes_taxt), a stored
# value differs from `new` afterwards, or -- for a group with a name_gender row -- any species-group taxon in that
# genus is then not spelled for the genus's gender (the condition of the database script "Species-group taxa not
# spelled for their genus gender"), or any species-group name in it changed that is not a row of the group.
# Historical records are not checked for agreement (Brian, 22 Nov 2026: obsolete combinations keep the spelling of
# their source; unavailable names and misspellings are not current combinations): see HISTORICAL_STATUSES.
#
# Env:    MODE=check (default; always rolls back) | MODE=write; INPUT=/app/tmp/grouped_changes.tsv; ONLY=groups
#         NAME_GENDER_SUMMARY, TAXON_NAME_SUMMARY, PROTONYM_SUMMARY, TAXON_DELETE_SUMMARY: edit summaries (required
#         for the kinds used)
# Output: /app/tmp/apply_grouped_changes_<MODE>_<uuid>.tsv: result, group, kind, record_id, label, field, old, new,
#         detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per record changed (the taxon
#         for a name_gender row, the name record for a taxon_name row, as the name form does; the protonym).
# Rollback: the dump taken before the run, or PaperTrail versions by request_uuid (old values in the input).
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'grouped_changes.tsv').to_s)
ONLY = ENV['ONLY']&.split(',')&.map(&:strip)
INPUT_COLUMNS = %w[group kind record_id label field old new].freeze
KIND_FIELDS = { 'name_gender' => %w[gender], 'taxon_name' => %w[name], 'taxon_delete' => %w[status] }.freeze
# notes_taxt: the public protonym note, added 22 Nov 2026 (Brian) to replace the four "Not resolved" gender notes;
# like the other fields, written only from an exact old value.
PROTONYM_FIELDS = %w[gender_agreement_type part_of_speech_basis interpretation_status masculine_epithet
                     feminine_epithet neuter_epithet spelling_basis etymology_taxt etymology_source
                     etymology_pages etymology_translation etymology_derivation notes_taxt].freeze
SUMMARY = { 'name_gender' => ENV['NAME_GENDER_SUMMARY'], 'taxon_name' => ENV['TAXON_NAME_SUMMARY'],
            'protonym' => ENV['PROTONYM_SUMMARY'], 'taxon_delete' => ENV['TAXON_DELETE_SUMMARY'] }.freeze
SPECIES_GROUP_TYPES = %w[Species Subspecies Infrasubspecies].freeze
HISTORICAL_STATUSES = [Status::OBSOLETE_COMBINATION, Status::UNAVAILABLE, Status::UNAVAILABLE_MISSPELLING].freeze

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
  allowed = KIND_FIELDS[r['kind']] || (r['kind'] == 'protonym' ? PROTONYM_FIELDS : nil)
  abort "Unknown kind #{r['kind']}" unless allowed
  abort "Field #{r['field']} not allowed for #{r['kind']}" unless allowed.include?(r['field'])
  abort "No edit summary for #{r['kind']} (set #{r['kind'].upcase}_SUMMARY)" if SUMMARY[r['kind']].to_s.strip.empty?
  abort "Unknown gender #{r['new']}" if r['kind'] == 'name_gender' && !Name::GENDERS.include?(r['new'])
  abort "A delete row must have old 'unavailable misspelling' and an empty new" if r['kind'] == 'taxon_delete' &&
    (r['old'] != Status::UNAVAILABLE_MISSPELLING || !r['new'].empty?)
  abort "Derivation with markup other than <i>: #{r['record_id']}" if r['field'] == 'etymology_derivation' &&
                                                                      r['new'].gsub(%r{</?i>}, '').match?(/[<>]/)
end
dup = rows.group_by { |r| [r['kind'], r['record_id'], r['field']] }.select { |_, v| v.size > 1 }.keys
abort "Duplicate rows for #{dup.first.inspect}" if dup.any?
groups = rows.group_by { |r| r['group'] }
groups = groups.slice(*ONLY) if ONLY

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "apply_grouped_changes_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} " \
     "groups=#{groups.size} rows=#{groups.values.sum(&:size)}"

def blank_to_nil(value)
  value.to_s.empty? ? nil : value
end

def same?(stored, expected)
  stored.to_s == expected.to_s
end

def species_group_taxa_in(genus)
  scope = genus.type == 'Subgenus' ? Taxon.where(subgenus_id: genus.id) : Taxon.where(genus_id: genus.id)
  scope.where(type: SPECIES_GROUP_TYPES).includes(:name, :protonym).order(:id).to_a
end

def tidied_notes(record)
  return [] unless record.is_a?(Protonym) && record.notes_taxt_changed?
  record.notes_taxt.to_s.gsub(/\s+/, '') == record.notes_taxt_was.to_s.gsub(/\s+/, '') ? %w[notes_taxt] : []
end

def check_save!(record, fields, extra_allowed = [])
  raise Reject, "invalid: #{record.errors.full_messages.join('; ')}" unless record.valid?
  tidied = tidied_notes(record)
  extra = record.changes.keys - fields - extra_allowed - tidied
  raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?
  record.save!
  changed = record.saved_changes.keys - fields - extra_allowed - tidied - %w[updated_at]
  raise Reject, "saved changes beyond the input: #{changed.join(', ')}" if changed.any?
  tidied
end

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result group kind record_id label field old new detail].join("\t")

groups.each do |group, grows|
  result = 'held'
  details = {}
  begin
    ActiveRecord::Base.transaction do
      genus_rows = grows.select { |r| r['kind'] == 'name_gender' }
      name_rows = grows.select { |r| r['kind'] == 'taxon_name' }
      group_taxon_ids = (genus_rows + name_rows).map { |r| r['record_id'].to_i }
      genera = genus_rows.map { |r| Taxon.find_by(id: r['record_id'].to_i) or raise(Reject, "taxon #{r['record_id']} not found") }
      before = genera.to_h { |g| [g.id, species_group_taxa_in(g).to_h { |t| [t.id, t.name.name] }] }

      genus_rows.each do |r|
        taxon = Taxon.find(r['record_id'].to_i)
        raise Reject, "#{taxon.id}: not a genus or subgenus (#{taxon.type})" unless %w[Genus Subgenus].include?(taxon.type)
        name = taxon.name
        raise Reject, "#{taxon.id}: name differs (#{name.name} vs #{r['label']})" unless name.name == r['label']
        raise Reject, "#{taxon.id}: gender is #{name.gender.inspect}, not #{r['old'].inspect}" unless same?(name.gender, r['old'])
        others = Taxon.where(name_id: name.id).where.not(id: group_taxon_ids).pluck(:id)
        raise Reject, "#{taxon.id}: name record shared with taxa outside the group: #{others.first(5).join(', ')}" if others.any?
        raise Reject, "#{taxon.id}: name record used by a protonym" if Protonym.exists?(name_id: name.id)
        name.gender = r['new']
        check_save!(name, %w[gender])
        raise Reject, "#{taxon.id}: stored gender differs" unless name.reload.gender == r['new']
        taxon.create_activity(Activity::UPDATE, bot, edit_summary: SUMMARY['name_gender']).update_columns(automated_edit: true)
      end

      name_rows.each do |r|
        taxon = Taxon.find_by(id: r['record_id'].to_i) or raise Reject, "taxon #{r['record_id']} not found"
        raise Reject, "#{taxon.id}: not a species-group taxon (#{taxon.type})" unless SPECIES_GROUP_TYPES.include?(taxon.type)
        name = taxon.name
        raise Reject, "#{taxon.id}: name differs (#{name.name} vs #{r['label']})" unless name.name == r['label']
        raise Reject, "#{taxon.id}: name is not the expected old spelling" unless same?(name.name, r['old'])
        raise Reject, "#{taxon.id}: name record used by a protonym (it holds the original spelling)" if Protonym.exists?(name_id: name.id)
        others = Taxon.where(name_id: name.id).where.not(id: taxon.id).pluck(:id)
        raise Reject, "#{taxon.id}: name record shared with taxa #{others.first(5).join(', ')}" if others.any?
        name.name = r['new']
        check_save!(name, %w[name], %w[epithet cleaned_name])
        raise Reject, "#{taxon.id}: stored name differs" unless name.reload.name == r['new']
        raise Reject, "#{taxon.id}: name cache not updated" unless taxon.reload.name_cache == r['new']
        name.create_activity(Activity::UPDATE, bot, edit_summary: SUMMARY['taxon_name']).update_columns(automated_edit: true)
      end

      grows.select { |r| r['kind'] == 'taxon_delete' }.each do |r|
        taxon = Taxon.find_by(id: r['record_id'].to_i) or raise Reject, "taxon #{r['record_id']} not found"
        raise Reject, "#{taxon.id}: status is #{taxon.status}, not #{r['old']}" unless taxon.status == r['old']
        raise Reject, "#{taxon.id}: name differs (#{taxon.name.name} vs #{r['label']})" unless taxon.name.name == r['label']
        links = taxon.what_links_here.all
        raise Reject, "#{taxon.id}: other records refer to it (#{links.size})" if taxon.what_links_here.any?
        record = { taxon: taxon.attributes, name: taxon.name.attributes, protonym_id: taxon.protonym_id,
                   what_links_here: links.map(&:to_s), versions: PaperTrail::Version.where(item_type: 'Taxon', item_id: taxon.id).count }
        File.write(Rails.root.join('tmp', "deleted_taxon_#{taxon.id}_#{uuid}.json").to_s, JSON.pretty_generate(record))
        name_id = taxon.name_id
        raise Reject, "#{taxon.id}: destroy failed: #{taxon.errors.full_messages.join('; ')}" unless taxon.destroy
        raise Reject, "#{taxon.id}: still present after destroy" if Taxon.exists?(taxon.id)
        details[taxon.id] = "deleted; name record #{name_id} #{Name.exists?(name_id) ? 'kept (shared)' : 'deleted with it'}"
        taxon.create_activity(Activity::DESTROY, bot, edit_summary: SUMMARY['taxon_delete']).update_columns(automated_edit: true)
      end

      grows.select { |r| r['kind'] == 'protonym' }.group_by { |r| r['record_id'].to_i }.each do |pid, prows|
        p = Protonym.find_by(id: pid) or raise Reject, "protonym #{pid} not found"
        prows.each do |r|
          raise Reject, "#{pid}: name differs (#{p.name.name} vs #{r['label']})" unless p.name.name == r['label']
          raise Reject, "#{pid}: #{r['field']} is not the expected old value" unless same?(p[r['field']], r['old'])
          p[r['field']] = blank_to_nil(r['new'])
        end
        fields = prows.map { |r| r['field'] }
        tidied = check_save!(p, fields)
        p.reload
        prows.each do |r|
          raise Reject, "#{pid}: stored #{r['field']} differs from the input" unless same?(p[r['field']], r['new'])
        end
        details[pid] = 'notes_taxt: whitespace tidied by the save' if tidied.any?
        p.create_activity(Activity::UPDATE, bot, edit_summary: SUMMARY['protonym']).update_columns(automated_edit: true)
      end

      genera.each do |g|
        g.reload
        gender = g.name.gender
        taxa = species_group_taxa_in(g)
        changed = taxa.select { |t| before[g.id][t.id] != t.name.name }.map(&:id) - group_taxon_ids
        raise Reject, "#{g.id}: names changed outside the group: #{changed.first(5).join(', ')}" if changed.any?
        unagreeing = taxa.reject { |t| HISTORICAL_STATUSES.include?(t.status) }.select do |t|
          p = t.protonym
          spelling = p.epithet_for_gender(gender)
          spelling.present? && !p.spelling_kept_against_agreement? && t.name.epithet != spelling
        end
        if unagreeing.any?
          raise Reject, "#{g.id}: not spelled for #{gender}: " +
                        unagreeing.first(5).map { |t| "#{t.id} #{t.name.name}" }.join(', ')
        end
        details[:genus] = "#{g.name.name}: #{taxa.size} species-group taxa, all spelled for #{gender}"
      end

      result = MODE == 'check' ? 'would_write' : 'written'
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    result = 'held'
    details = { held: e.message }
  rescue ActiveRecord::ActiveRecordError => e
    result = 'error'
    details = { error: "#{e.class}: #{e.message}" }
  end
  stats[result] += 1
  grows.each do |r|
    detail = details[:held] || details[:error] || details[r['record_id'].to_i] || ''
    out.puts [result, group, r['kind'], r['record_id'], r['label'], r['field'], r['old'], r['new'], detail]
      .map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
  end
  puts "  #{result} #{group} (#{grows.size} rows) #{details[:held] || details[:error] || details[:genus]}"
end
out.close
stats.sort.each { |k, v| puts format('  groups %-20s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
