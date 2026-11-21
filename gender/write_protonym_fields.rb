# frozen_string_literal: true
#
# write_protonym_fields.rb -- the general write runner of the pattern-by-pattern work (Brian, 14 Nov 2026 21:43):
# AntCat derivation, part of speech, its basis and the interpretation status, each validated on its own.
#
# One input row per protonym and field. A protonym's rows are written in one transaction, but each field gets
# its own result: one field can be written while another is held. Nothing is ever overwritten: a field that
# already holds the proposed value is "already"; one that holds another value is held. The basis and the
# status only go with the part of speech they were proposed for. Every row names a rule; the rule fixes
# which fields and which values it may write and the edit summary. A rule is added here only after Brian has
# approved the pattern (its wording, its rules and a sample).
#
# Per protonym, held (nothing written) when:
#   - the protonym or name differs from the input
#   - the type locality differs from the one the proposal rests on (locality_md5, when given)
#   - the rule holds names with a sourced etymology (`etymology_taxt`) and the protonym has one
#   - the interpretation status is disputed or unresolved (a human judged the reading open)
#   - the save would change any column besides the rule's fields, validation fails, or a stored value differs
#     from the input after the save
#
# Env:    MODE=check (default; always rolls back) | MODE=write; INPUT=/app/tmp/protonym_fields_input.tsv (default);
#         ONLY=protonym ids; LIMIT=n (protonyms)
# Input:  TSV protonym_id, protonym_name, rule, field, value, locality_md5 (blank: no locality check)
# Output: /app/tmp/write_protonym_fields_<MODE>_<uuid>.tsv: result, protonym_id, name, field, old, new, rule, detail
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `update` activity per protonym written.
# Rollback: the dump taken before the run, or PaperTrail versions by request_uuid (fields written were empty).
#
# No csv: Ruby 3.4 made it a bundled gem and AntCat's Gemfile does not list it (see write_etymology_sources.rb).
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'protonym_fields_input.tsv').to_s)
ONLY = ENV['ONLY']&.split(',')&.map(&:to_i)
LIMIT = ENV['LIMIT']&.to_i
INPUT_COLUMNS = %w[protonym_id protonym_name rule field value locality_md5].freeze
PART_OF_SPEECH = 'gender_agreement_type'
DEPENDENT_FIELDS = %w[part_of_speech_basis interpretation_status].freeze

# Approved rules only. fields: each field the rule may write, with the values it may write.
RULES = {
  # Brian, 14 Nov 2026 21:43: "A verified geographic stem combined with the Latin adjectival suffix -ensis
  # supports classification as an adjective. Record basis 'grammatical form' and status 'demonstrated' when
  # the construction is unambiguous." Existing derivations are not rewritten.
  'toponym_ensis_pos' => {
    fields: {
      'gender_agreement_type' => %w[adjective],
      'part_of_speech_basis' => %w[grammatical_form],
      'interpretation_status' => %w[demonstrated]
    },
    hold_sourced_etymology: true,
    summary: '[automated] Part of speech recorded: adjective (geographic stem with the Latin adjectival suffix ' \
             '-ensis), basis grammatical form, demonstrated; under the AntCat policy on name grammar and spelling. ' \
             'Etymology, derivation and spelling unchanged'
  },
  # Brian, 14 Nov 2026 21:59, asked Claude to answer from the Code and the literature whether every -ensis/-ense
  # epithet is an adjective by form. Yes: -ensis forms Latin adjectives (Allen & Greenough sect. 249; Pellizzari &
  # Williams 2013, Table 2; Stearn 1973 via Manara 1992), Art. 31.2, policy Rule 1.1. Proposals screened by
  # gender/propose_part_of_speech_by_form.py (a published etymology calling it a noun is held for a note first).
  'ensis_form_pos' => {
    fields: {
      'gender_agreement_type' => %w[adjective],
      'part_of_speech_basis' => %w[grammatical_form author_stated],
      'interpretation_status' => %w[demonstrated]
    },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: adjective (the Latin adjectival suffix -ensis/-ense; Art. 31.2), ' \
             'demonstrated; under the AntCat policy on name grammar and spelling. Etymology, derivation and spelling ' \
             'unchanged'
  },
  # Same question for the toponym derivations in -anus: yes, -anus on a verified place stem is the Latin adjective
  # "belonging to" (Allen & Greenough sect. 249.2; Stearn 1973 via Manara 1992: mexicanus).
  'toponym_anus_pos' => {
    fields: {
      'gender_agreement_type' => %w[adjective],
      'part_of_speech_basis' => %w[grammatical_form],
      'interpretation_status' => %w[demonstrated]
    },
    hold_sourced_etymology: true,
    summary: '[automated] Part of speech recorded: adjective (verified place stem with the Latin adjectival suffix ' \
             '-anus; Art. 31.2), basis grammatical form, demonstrated; under the AntCat policy on name grammar and ' \
             'spelling. Etymology, derivation and spelling unchanged'
  }
}.merge(
  # The combined write (Brian, 15 Nov 2026 07:47 and 07:56: "hold back those on this list but take care of all the
  # rest"). Proposals by gender/propose_all.py; rules and evidence in gender/ETYMOLOGY_GRAMMAR_RUNBOOK.md, sect. 5.
  # Personal-name genitives (Art. 31.1.2; Brian's three levels, 14 Nov 21:43; wiki 17 rule 6 for the derivation).
  'patronym_genitive' => {
    fields: {
      'gender_agreement_type' => %w[noun_in_genitive_case],
      'part_of_speech_basis' => %w[grammatical_form author_stated],
      'interpretation_status' => %w[demonstrated reasonably_inferred],
      'etymology_derivation' => %r{\APersonal name: formed as the genitive \(Latin <i>-(?:i|ii|ae|orum|arum)</i>\) of the surname [^<>\t]{2,60}\.\z}
    },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: noun in the genitive case (a personal-name genitive, Art. 31.1); ' \
             'with an AntCat derivation where the stem is a documented personal name; under the AntCat policies on ' \
             'name grammar and spelling and on derived etymologies. Spelling unchanged'
  },
  # A Latin word in Lewis & Short with only adjective or participle readings (Art. 31.2; policy Rule 1.1).
  'latin_form_pos' => {
    fields: { 'gender_agreement_type' => %w[adjective participle], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded from the Latin form (Lewis & Short: adjective or participle only); ' \
             'demonstrated; under the AntCat policy on name grammar and spelling. Spelling unchanged'
  },
  # A Latin common noun as spelled, or a proper noun (Art. 31.2.1, Simia diana): noun in apposition.
  'latin_noun_pos' => {
    fields: { 'gender_agreement_type' => %w[noun_in_apposition], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: noun in apposition (Lewis & Short: a Latin noun as spelled; ' \
             'Art. 31.2.1); demonstrated; under the AntCat policy on name grammar and spelling. Spelling unchanged'
  },
  'latin_proper_noun_pos' => {
    fields: { 'gender_agreement_type' => %w[noun_in_apposition], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: noun in apposition (a Latin proper noun; Art. 31.2.1, Simia diana); ' \
             'demonstrated; under the AntCat policy on name grammar and spelling. Spelling unchanged'
  },
  # Both an adjective and a noun in Lewis & Short, no author indication: policy Rule 1.5 (Art. 31.2.2) default.
  # Brian 15 Nov 07:47 did not object to the default.
  'latin_ambiguous_default_pos' => {
    fields: { 'gender_agreement_type' => %w[noun_in_apposition], 'part_of_speech_basis' => %w[noun_by_default],
              'interpretation_status' => %w[reasonably_inferred] },
    hold_sourced_etymology: true,
    summary: '[automated] Part of speech recorded: noun in apposition by default (the word is both a Latin adjective ' \
             'and a noun; Art. 31.2.2, policy Rule 1.5); reasonably inferred. Spelling unchanged'
  },
  # Compounds and derived adjectives (compounds.py; Rule 1.6; Poultney 1953; A&G 241-249).
  'compound_adjective_pos' => {
    fields: { 'gender_agreement_type' => %w[adjective], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated reasonably_inferred] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: adjective (a compound whose final element is adjectival, or a ' \
             'Latin stem with an adjective-forming suffix; policy Rule 1.6). Spelling unchanged'
  },
  # -anus, -icus, -acus, -inus on a place in the AntCat locality (A&G 249; Manara 1992).
  'place_adjective_pos' => {
    fields: { 'gender_agreement_type' => %w[adjective], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: adjective (a place in the type locality with a Latin adjectival ' \
             'suffix); demonstrated. Spelling unchanged'
  },
  # Words no dictionary lists, with an adjectival suffix (-icus demonstrated; -anus, -inus, -osus, -ica inferred;
  # -escens a present participle).
  'suffix_form_pos' => {
    fields: { 'gender_agreement_type' => %w[adjective participle], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated reasonably_inferred] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded from a Latin adjectival suffix or participle ending; under the ' \
             'AntCat policy on name grammar and spelling. Spelling unchanged'
  },
  # Greek words Latinized (Art. 31.2.3, melaena): adjective; Greek nouns: noun in apposition.
  'greek_form_pos' => {
    fields: { 'gender_agreement_type' => %w[adjective noun_in_apposition], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[demonstrated reasonably_inferred] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded from the Greek word (Liddell-Scott-Jones); under the ' \
             'AntCat policy on name grammar and spelling. Spelling unchanged'
  },
  # Brian, 16 Nov 2026 10:40: "I can't review all these names: you have to use insect knowledge: refer to TW ..., the
  # ocr of the literature ..., the pdfs in Background reading for ICZN ... we may only offer a wiki for the difficult
  # ones". From then Claude decides the held names by gender/resolve_held.py; its tables and reasons are the record.
  # What the original description itself says (gender/extract_stated_grammar.py): noun in apposition, adjective, or an
  # arbitrary combination of letters (indeclinable, Art. 31.2.3).
  'author_stated_pos' => {
    fields: { 'gender_agreement_type' => %w[noun_in_apposition adjective participle indeclinable],
              'part_of_speech_basis' => %w[author_stated not_latin],
              'interpretation_status' => %w[demonstrated] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded as stated in the original description; demonstrated; under the ' \
             'AntCat policy on name grammar and spelling. Spelling unchanged'
  },
  # Art. 31.2.2 as read by David & Gosselin 2011 (AntCat's adopted reading, 13 Nov), policy Rules 1.5 and 1.6: a name
  # spelled as a noun in its own nominative (a compound ending in such a noun, a Latin noun that is also an adjective,
  # a proper noun, a place name used unchanged), with no indication of an adjective in the original description.
  # Never written where the accepted spelling differs from the original (wiki list).
  'noun_by_default_pos' => {
    fields: { 'gender_agreement_type' => %w[noun_in_apposition noun_in_genitive_case],
              'part_of_speech_basis' => %w[noun_by_default grammatical_form],
              'interpretation_status' => %w[reasonably_inferred] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: noun in apposition by default (the epithet is spelled as a noun and ' \
             'the original description gives no indication of an adjective; Art. 31.2.2, policy Rules 1.5 and 1.6); ' \
             'reasonably inferred. Spelling unchanged'
  },
  # Word-by-word judgments (tables in gender/resolve_held.py): a Latin adjective or participle whose noun homonym is
  # its verbal noun or an unrelated word (ornatus, latus, striata), an adjective formed on a noun stem (castaneus,
  # ophthalmica), the feminine of a geographical adjective (corsica, argentina).
  # Genus-group derivations from Wheeler 1956, Myrmecological orthoepy and onomatology (AntCat reference 129837),
  # and (21 Nov, same format) from its second edition, Wheeler & Wheeler 1984b (reference 129916),
  # with the gender and its basis under ICZN Art. 30 (Brian, 21 Nov 2026 13:12: "yes" to the format; files in
  # gender/genus_derivations_wheeler1956.py). The text's gender must equal the gender every taxon of the
  # protonym carries (check_genus_gender); names whose gender is open (wiki list) carry the derivation only.
  'wheeler1956_genus_derivation' => {
    fields: {
      'etymology_derivation' => %r{\A(?:[^<>\t]|<i>|</i>){8,900} \((?:Wheeler, 1956|Wheeler & Wheeler, 1984b): \d{1,2}\)\.(?: Gender (?:masculine|feminine|neuter): (?:[^<>\t]|<i>|</i>){10,500} \(ICZN Art\. 30\.[12](?:\.\d){1,2}\)\.)?\z}
    },
    hold_sourced_etymology: true,
    check_genus_gender: true,
    # AntCat's own save tidies taxt (Taxt::Cleanup); 64 genus protonyms' notes begin with a space (staging
    # 21 Nov). That one change is let through when it alters whitespace only; anything else is still held.
    whitespace_tidy_ok: %w[notes_taxt],
    summary: '[automated] AntCat derivation recorded for the genus-group name, from Wheeler 1956 (Myrmecological ' \
             'orthoepy and onomatology), with the gender and its basis under ICZN Art. 30; under the AntCat policy ' \
             'on derived etymologies. Gender and spelling unchanged (a leading space in the protonym notes, where ' \
             'present, removed by the save)'
  },
  'judged_adjective_pos' => {
    fields: { 'gender_agreement_type' => %w[adjective participle], 'part_of_speech_basis' => %w[grammatical_form],
              'interpretation_status' => %w[reasonably_inferred] },
    hold_sourced_etymology: false,
    summary: '[automated] Part of speech recorded: a Latin adjective or participle (a noun of the same spelling is a ' \
             'possible alternative); reasonably inferred; under the AntCat policy on name grammar and spelling. ' \
             'Spelling unchanged'
  }
).freeze

abort 'PR #1607 is not deployed (no interpretation_status).' unless Protonym.column_names.include?('interpretation_status')
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

# Every row must fit its rule before anything is read from the database: a misfit is a fault in the input.
rows.each do |r|
  rule = RULES[r['rule']] or abort "Unknown rule #{r['rule'].inspect} (protonym #{r['protonym_id']})"
  allowed = rule[:fields][r['field']] or abort "Rule #{r['rule']} may not write #{r['field']} (protonym #{r['protonym_id']})"
  ok = allowed.is_a?(Regexp) ? allowed.match?(r['value']) : allowed.include?(r['value'])
  abort "Rule #{r['rule']} may not write #{r['field']}=#{r['value'].inspect} (protonym #{r['protonym_id']})" unless ok
end
groups = rows.group_by { |r| r['protonym_id'].to_i }
groups.each do |pid, g|
  abort "Protonym #{pid}: one rule per protonym" unless g.map { |r| r['rule'] }.uniq.size == 1
  abort "Protonym #{pid}: one locality_md5 per protonym" unless g.map { |r| r['locality_md5'] }.uniq.size == 1
  abort "Protonym #{pid}: a field twice" unless g.map { |r| r['field'] }.uniq.size == g.size
end
groups = groups.select { |pid, _| ONLY.include?(pid) } if ONLY
groups = groups.first(LIMIT).to_h if LIMIT

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s
OUT = Rails.root.join('tmp', "write_protonym_fields_#{MODE}_#{uuid}.tsv").to_s
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{Digest::MD5.file(INPUT).hexdigest} " \
     "protonyms=#{groups.size} rows=#{groups.values.sum(&:size)}"

stats = Hash.new(0)
out = File.open(OUT, 'w')
out.puts %w[result protonym_id name field old new rule detail].join("\t")

groups.each do |pid, g|
  rule_name = g.first['rule']
  rule = RULES[rule_name]
  name = nil
  results = g.to_h { |r| [r['field'], { old: nil, result: '', detail: '' }] }
  begin
    ActiveRecord::Base.transaction do
      p = Protonym.find_by(id: pid)
      raise Reject, 'protonym not found' unless p
      name = p.name.name
      g.each { |r| results[r['field']][:old] = p[r['field']] }
      raise Reject, "name differs (#{name} vs #{g.first['protonym_name']})" unless name == g.first['protonym_name']
      md5 = g.first['locality_md5']
      raise Reject, 'type locality differs from the one the proposal rests on' if
        md5.present? && Digest::MD5.hexdigest(clean(p.locality)) != md5
      raise Reject, 'has a sourced etymology' if rule[:hold_sourced_etymology] && p.etymology_taxt.present?
      if rule[:check_genus_gender]
        stated = g.map { |r| r['value'][/ Gender (masculine|feminine|neuter):/, 1] }.compact.uniq
        recorded = p.taxa.map { |t| t.name.gender.to_s }.uniq
        raise Reject, "gender in the text (#{stated.join(', ')}) differs from the taxa (#{recorded.join(', ')})" if
          stated.any? && recorded != stated
        raise Reject, 'not a genus-group protonym' unless p.taxa.all? { |t| t.type.in?(%w[Genus Subgenus]) }
      end
      # someone has judged the reading open: only Brian changes that
      raise Reject, "interpretation is #{p.interpretation_status}" if
        p.interpretation_status.in?(Protonym::SCRIPTED_SPELLING_CHANGE_BLOCKED_STATUSES)

      proposed_pos = g.find { |r| r['field'] == PART_OF_SPEECH }&.dig('value')
      assign = {}
      g.each do |r|
        f = r['field']
        cur = p[f].to_s
        if cur == r['value']
          results[f].merge!(result: 'already')
        elsif cur.present?
          results[f].merge!(result: 'held', detail: "already set to #{cur}")
        elsif f == 'etymology_derivation' && p.etymology_taxt.present?
          # wiki 17: a derivation is never shown next to a sourced etymology
          results[f].merge!(result: 'held', detail: 'has a sourced etymology')
        elsif DEPENDENT_FIELDS.include?(f) && proposed_pos && p[PART_OF_SPEECH].present? && p[PART_OF_SPEECH] != proposed_pos
          results[f].merge!(result: 'held', detail: "part of speech is #{p[PART_OF_SPEECH]}, not #{proposed_pos}")
        elsif DEPENDENT_FIELDS.include?(f) && !proposed_pos && p[PART_OF_SPEECH].blank?
          results[f].merge!(result: 'held', detail: 'no part of speech recorded')
        else
          assign[f] = r['value']
        end
      end
      # a dependent field rides on the part of speech it was proposed with: if that one is held, so is it
      if proposed_pos && results[PART_OF_SPEECH][:result] == 'held'
        DEPENDENT_FIELDS.each do |f|
          next unless assign.key?(f)
          assign.delete(f)
          results[f].merge!(result: 'held', detail: 'its part of speech is held')
        end
      end

      if assign.any?
        p.assign_attributes(assign)
        raise Reject, "invalid: #{p.errors.full_messages.join('; ')}" unless p.valid?
        extra = p.changes.keys - assign.keys
        tidied = extra.select do |c|
          rule.fetch(:whitespace_tidy_ok, []).include?(c) &&
            p.public_send(c).to_s.gsub(/\s+/, '') == p.public_send("#{c}_was").to_s.gsub(/\s+/, '')
        end
        extra -= tidied
        raise Reject, "the save would also change #{extra.join(', ')}" if extra.any?

        p.save!
        changed = p.saved_changes.keys - assign.keys - %w[updated_at] - tidied
        raise Reject, "saved changes beyond the rule's fields: #{changed.join(', ')}" if changed.any?
        p.reload
        assign.each { |f, v| raise Reject, "stored #{f} differs from the input" unless p[f].to_s == v }

        p.create_activity(Activity::UPDATE, bot, edit_summary: rule[:summary]).update_columns(automated_edit: true)
        assign.each_key do |f|
          results[f].merge!(result: MODE == 'check' ? 'would_write' : 'written',
                            detail: tidied.any? ? "#{tidied.join(', ')}: whitespace tidied by AntCat's save" : '')
        end
      end
      raise ActiveRecord::Rollback if MODE == 'check'
    end
  rescue Reject => e
    # a hold of the whole protonym: nothing was written, so no field keeps another result
    results.each_value { |v| v.merge!(result: 'held', detail: e.message) }
  rescue ActiveRecord::ActiveRecordError => e
    results.each_value { |v| v.merge!(result: 'error', detail: "#{e.class}: #{e.message}") }
  end
  g.each do |r|
    v = results[r['field']]
    stats["#{r['field']}: #{v[:result]}#{v[:result] == 'held' ? " (#{v[:detail].sub(/ \(.*/, '').sub(/ to .*/, '')})" : ''}"] += 1
    out.puts [v[:result], pid, name, r['field'], v[:old], r['value'], rule_name, v[:detail]].map { |x| clean(x) }.join("\t")
  end
end
out.close
stats.sort.each { |k, v| puts format('  %-78s %6d', k, v) }
puts "request_uuid=#{uuid}"
puts "Wrote #{OUT}"
