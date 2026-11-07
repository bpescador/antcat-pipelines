# frozen_string_literal: true
#
# missing_combinations_dryrun.rb  (READ-ONLY: no database writes)
#
# Finds species-rank obsolete combinations that AntCat's own CombinationIn
# history items say exist in the literature, but that have no Taxon record.
# Example: protonym of Strumigenys ludovici has "Combination in Pyramica:
# Bolton, 2000" but no Taxon "Pyramica ludovici", so AntWeb cannot map a
# specimen identified as Pyramica ludovici.
#
# For each missing combination it proposes the spelling, with gender agreement
# (ICZN Art. 31.2, 34.2), and a confidence rule. Nothing is created.
# Output: /app/tmp/missing_combinations_dryrun.tsv plus a summary on stdout.
#
# Gender forms: port of TaxonWorks Utilities::Nomenclature.predict_three_forms
# (SpeciesFileGroup/taxonworks, lib/utilities/nomenclature.rb), irregular table omitted.
#
# Run (inside app container):
#   docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/missing_combinations_dryrun.rb

OUT = Rails.root.join('tmp', 'missing_combinations_dryrun.tsv').to_s
GENITIVE_RE = /(i|ae|orum|arum)\z/ # cannot be nominative adjectives
NOUNS = Protonym::UNCHANGEABLE_GENDER_AGREEMENT_TYPES
ADJS = Protonym::CHANGEABLE_GENDER_AGREEMENT_TYPES

def three_forms(e)
  m, f, n =
    case e
    when /(color|coloris)\z/ then [e, e, e]
    when /is\z/ then [e, e, e[0..-3] + 'e']
    when /e\z/ then [e[0..-2] + 'is', e[0..-2] + 'is', e]
    when /us\z/ then [e, e[0..-3] + 'a', e[0..-3] + 'um']
    when /(niger|integer)\z/ then [e, e[0..-3] + 'ra', e[0..-3] + 'rum']
    when /(fer|ger)\z/ then [e, e + 'a', e + 'um']
    when /er\z/ then [e, e[0..-3] + 'ra', e[0..-3] + 'rum']
    when /(ferum|gerum)\z/ then [e[0..-3], e[0..-3] + 'a', e]
    when /(gera|fera)\z/ then [e[0..-2], e, e[0..-2] + 'um']
    when /(brum|frum|grum)\z/ then [e[0..-4] + 'er', e[0..-3] + 'a', e]
    when /(bra|gra|fra)\z/ then [e[0..-3] + 'er', e, e[0..-2] + 'um']
    when /um\z/ then [e[0..-3] + 'us', e[0..-3] + 'a', e]
    when /a\z/ then [e[0..-2] + 'us', e, e[0..-2] + 'um']
    when /(nor|ior|jor)\z/ then [e, e, e[0..-3] + 'us']
    else [e, e, e]
    end
  { 'masculine' => m, 'feminine' => f, 'neuter' => n }
end

def gender_of(taxon)
  taxon&.genus&.name&.gender
end

# Returns [epithet or nil, rule, confidence]
def propose(protonym, current, genus)
  e_cur = current.name.epithet
  e_orig = protonym.name.epithet
  g_cur = gender_of(current)
  g_obs = genus.name.gender
  ptype = protonym.gender_agreement_type

  return [e_orig, 'noun_typed', 'high'] if NOUNS.include?(ptype)
  return [e_cur, 'genitive_ending', 'high'] if e_cur.match?(GENITIVE_RE)
  return [nil, 'genus_gender_missing', 'manual'] if g_cur.nil? || g_obs.nil?
  return [e_cur, 'same_gender', 'high'] if g_cur == g_obs

  forms = three_forms(e_cur)
  if ADJS.include?(ptype)
    return [nil, 'typed_adjective_but_current_disagrees', 'manual'] unless forms[g_cur] == e_cur
    return [forms[g_obs], 'adjective_typed', 'high']
  end

  return [e_cur, 'indeclinable_ending', 'high'] if forms.values.uniq.size == 1

  if e_cur.match?(/(is|e)\z/)
    # -is/-e: masculine and feminine forms are identical for adjectives, and
    # nouns never change, so m<->f is safe. Anything involving neuter is the trochis trap.
    return [e_cur, 'third_declension_m_f', 'high'] unless [g_cur, g_obs].include?('neuter')
    return [nil, 'is_e_with_neuter', 'manual']
  end

  return [nil, 'current_not_a_predicted_form', 'manual'] unless forms[g_cur] == e_cur

  # Evidence from the protonym's other taxa in genera of a different gender.
  evidence = protonym.taxa.filter_map do |t|
    g = gender_of(t)
    next if g.nil? || g == g_cur || !t.is_a?(Species)
    t.name.epithet == three_forms(e_cur)[g] ? :declined : (t.name.epithet == e_cur ? :unchanged : :other)
  end.uniq

  return [nil, 'unchanged_across_genders_noun_or_error', 'manual'] if evidence.include?(:unchanged)
  return [forms[g_obs], 'adjective_by_usage', 'high'] if evidence == [:declined]
  [forms[g_obs], 'adjective_by_ending', 'medium']
end

# --- Gather evidence: one entry per (protonym, genus) -------------------------
# Two sources:
#  (a) relational CombinationIn items (object_taxon = genus);
#  (b) free-text taxt items containing "Combination in {tax N}" / "{taxac N}",
#      the form most combinations are still stored in.
# In (b) the tag may point to a genus, a subgenus (use its genus), or a
# species-group taxon (the combined name itself, already present if it shares
# this protonym). {missing ...} tags mean the genus is not in AntCat.

COMBO_RE = /[Cc]ombination in (?:<i>)?(?:\{(?:tax|taxac) (?<tid>\d+)\}|\{missing\d? (?<miss>[^}]*)\})/

stats = Hash.new(0)
tag_targets = Hash.new(0)
evidence = Hash.new { |h, k| h[k] = { item_ids: [], cites: [] } } # [protonym_id, genus_id] => ...
rows = []

HistoryItem.where(type: History::Definitions::COMBINATION_IN).includes(:reference).find_each do |hi|
  next if hi.rank.present? && hi.rank != 'Species'
  e = evidence[[hi.protonym_id, hi.object_taxon_id]]
  e[:item_ids] << hi.id
  e[:cites] << "#{hi.reference&.key&.plain_text_key_with_suffixed_year}: #{hi.pages}"
  tag_targets['relational item'] += 1
end

taxt_scope = HistoryItem.taxts_only.where('taxt LIKE ?', '%ombination in%')
taxt_items = 0
unparsed = 0
taxt_scope.find_each do |hi|
  taxt_items += 1
  next (stats['taxt item: ranked non-species, skipped'] += 1) if hi.rank.present? && hi.rank != 'Species'
  matches = hi.taxt.to_s.to_enum(:scan, COMBO_RE).map { Regexp.last_match }
  if matches.empty?
    unparsed += 1
    next
  end
  matches.each do |m|
    if m[:miss]
      tag_targets['{missing} tag (genus not in AntCat)'] += 1
      next
    end
    target = Taxon.find_by(id: m[:tid])
    case target
    when nil
      tag_targets['tag to deleted taxon'] += 1
    when Genus
      tag_targets['Genus'] += 1
      e = evidence[[hi.protonym_id, target.id]]
      e[:item_ids] << hi.id
      e[:cites] << hi.taxt.truncate(200)
    when Subgenus
      tag_targets['Subgenus (mapped to its genus)'] += 1
      next unless target.genus
      e = evidence[[hi.protonym_id, target.genus_id]]
      e[:item_ids] << hi.id
      e[:cites] << hi.taxt.truncate(200)
    when SpeciesGroupTaxon
      if target.protonym_id == hi.protonym_id
        tag_targets['species-group taxon, same protonym (present)'] += 1
      else
        tag_targets['species-group taxon, OTHER protonym (manual)'] += 1
        rows << { action: 'manual', rule: 'tag_points_to_other_protonym', protonym_id: hi.protonym_id,
                  history_item_ids: hi.id, citations: hi.taxt.truncate(200) }
      end
    else
      tag_targets["#{target.type} (ignored)"] += 1
    end
  end
end

# --- Evaluate each (protonym, genus) pair ------------------------------------
# Species-group only: genus-group protonyms' taxa are genera (no `genus` association).
# Plain preloads only. `genus` is loaded lazily: it exists on species-group taxa
# but not on the base Taxon class, so it cannot be preloaded or joined safely.
sg_ids = Protonym.species_group_names.where(id: evidence.keys.map(&:first).uniq).pluck(:id)
protonyms = Protonym.where(id: sg_ids).preload(:name, taxa: :name).index_by(&:id)
genera = Genus.where(id: evidence.keys.map(&:last).compact.uniq).preload(:name).index_by(&:id)

evidence.each do |(pid, gid), ev|
  protonym = protonyms[pid]
  genus = genera[gid]
  base = { protonym_id: pid, protonym: protonym&.name&.name, genus_id: gid, genus: genus&.name&.name,
           history_item_ids: ev[:item_ids].uniq.join(' '), citations: ev[:cites].uniq.join(' | ') }
  skip = ->(why) { stats["skip: #{why}"] += 1; rows << base.merge(action: 'skip', rule: why) }

  next skip.('protonym not species-group (or missing)') unless protonym
  next skip.('object not a Genus') unless genus

  if protonym.taxa.any? { |t| t.is_a?(Species) && t.genus_id == genus.id }
    stats['already present'] += 1
    next
  end
  if protonym.taxa.any? { |t| t.genus_id == genus.id }
    next skip.('present only as subspecies/other rank in this genus')
  end

  current = protonym.taxa.find { |t| Status::TERMINAL_STATUSES.include?(t.status) }
  next skip.('no terminal taxon') unless current
  next skip.('terminal taxon not species rank (trinomial needed)') unless current.is_a?(Species)

  epithet, rule, conf = propose(protonym, current, genus)
  name = epithet && "#{genus.name.name} #{epithet}"
  clash = name && Taxon.where(name_cache: name).exists?
  action = if epithet.nil? then 'manual'
           elsif clash then 'manual_name_clash'
           else "create_#{conf}"
           end
  stats[action] += 1
  stats["rule: #{rule}"] += 1
  rows << base.merge(action: action, rule: rule, proposed_name: name,
    current_taxon_id: current.id, current_name: current.name.name, current_status: current.status,
    genus_status: genus.status, genus_gender: genus.name.gender, current_genus_gender: gender_of(current),
    gender_agreement_type: protonym.gender_agreement_type, protonym_epithet: protonym.name.epithet)
end

cols = %i[action rule proposed_name protonym_id protonym current_taxon_id current_name current_status
          genus_id genus genus_status genus_gender current_genus_gender gender_agreement_type
          protonym_epithet history_item_ids citations]
# Plain TSV (csv gem is not in the app bundle on Ruby 4). Tabs/newlines in values become spaces.
File.open(OUT, 'w') do |f|
  f.puts cols.join("\t")
  rows.sort_by { |r| [r[:action].to_s, r[:rule].to_s, r[:proposed_name].to_s] }.each do |r|
    f.puts cols.map { |c| r[c].to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t")
  end
end

puts "Taxt items mentioning 'ombination in': #{taxt_items} (no parsable tag: #{unparsed})"
puts "Combination tag targets:"
tag_targets.sort.each { |k, v| puts format('  %-50s %6d', k, v) }
puts "Protonym+genus pairs evaluated: #{evidence.size}"
stats.sort.each { |k, v| puts format('  %-50s %6d', k, v) }
puts "Wrote #{OUT}"
