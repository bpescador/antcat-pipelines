# frozen_string_literal: true
#
# subgenus_tag_check.rb  (READ-ONLY)
#
# Sizes one risk in missing_combinations_dryrun.rb: free-text "Combination in {tax N}"
# where N is a Subgenus was mapped to the subgenus's genus. If the same name also
# exists as a Genus record (an old genus now ranked as a subgenus, e.g. Dendrolasius),
# the combination may have been published at genus rank (Dendrolasius x), and that
# binomial may be missing from AntCat.
#
# Output: /app/tmp/subgenus_tag_check.tsv and a summary.
# Run:
#   docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/subgenus_tag_check.rb

OUT = Rails.root.join('tmp', 'subgenus_tag_check.tsv').to_s
RE = /[Cc]ombination in (?:<i>)?\{(?:tax|taxac) (?<tid>\d+)\}/

sg_protonym_ids = Protonym.species_group_names.pluck(:id).to_set
genus_by_name = Genus.preload(:name).index_by { |g| g.name.name }
stats = Hash.new(0)
rows = []

HistoryItem.taxts_only.where('taxt LIKE ?', '%ombination in%').find_each do |hi|
  next unless sg_protonym_ids.include?(hi.protonym_id)
  hi.taxt.to_s.scan(RE).flatten.each do |tid|
    sub = Taxon.find_by(id: tid)
    next unless sub.is_a?(Subgenus)
    stats['subgenus tags'] += 1
    sub_epithet = sub.name.epithet.to_s.delete('()')
    same_name_genus = genus_by_name[sub_epithet]
    unless same_name_genus
      stats['no Genus record with the subgenus name'] += 1
      next
    end
    stats['a Genus record has the subgenus name'] += 1
    protonym_taxa = Taxon.where(protonym_id: hi.protonym_id)
    if protonym_taxa.where(genus_id: same_name_genus.id).exists?
      stats['  ...and protonym already has a taxon in that Genus'] += 1
      next
    end
    stats['  ...and protonym has NO taxon in that Genus (review)'] += 1
    rows << [hi.protonym_id, Protonym.find(hi.protonym_id).name.name, sub.id, sub.name.name,
             same_name_genus.id, sub_epithet, same_name_genus.status, hi.id, hi.taxt.truncate(200)]
  end
end

File.open(OUT, 'w') do |f|
  f.puts %w[protonym_id protonym subgenus_id subgenus genus_id genus_name genus_status history_item_id taxt].join("\t")
  rows.each { |r| f.puts r.map { |v| v.to_s.gsub(/[\t\r\n]+/, ' ') }.join("\t") }
end

stats.each { |k, v| puts format('%-60s %6d', k, v) }
puts "Wrote #{OUT}"
