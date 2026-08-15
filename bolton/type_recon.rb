# type_recon.rb -- READ ONLY. No writes. Confirms field names, shows the raw
# stored taxt format, and sizes coverage on species-group protonyms.
#   docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/type_recon.rb

SPECIES_GROUP = %w[SpeciesName SubspeciesName InfrasubspeciesName].freeze
FIELDS = %w[primary_type_information_taxt secondary_type_information_taxt type_notes_taxt].freeze

puts "== 1. field check =="
FIELDS.each do |m|
  puts "   #{m}: #{Protonym.new.respond_to?(m) ? 'OK' : 'MISSING <-- STOP'}"
end
puts "   Protonym columns matching /type/: #{Protonym.column_names.grep(/type/).inspect}"

scope = Protonym.joins(:name).where(names: { type: SPECIES_GROUP })
puts "\n== 2. coverage (species-group protonyms) =="
puts "   total: #{scope.count}"
FIELDS.each do |f|
  n = scope.where("#{f} IS NOT NULL AND #{f} != ''").count
  puts "   with #{f}: #{n}"
end
empty_n = scope.where('primary_type_information_taxt IS NULL OR primary_type_information_taxt = ?', '').count
puts "   primary EMPTY (fill candidates): #{empty_n}"

puts "\n== 3. raw taxt samples (exact stored strings) =="
scope.where("secondary_type_information_taxt IS NOT NULL AND secondary_type_information_taxt != ''")
     .limit(3).each do |p|
  puts "--- protonym #{p.id}  #{(p.name.name rescue '?')}"
  FIELDS.each { |f| puts "   #{f} = #{p.send(f).inspect}" }
end

puts "\n== 4. a sample WITH type notes =="
p2 = scope.where("type_notes_taxt IS NOT NULL AND type_notes_taxt != ''").first
if p2
  puts "--- protonym #{p2.id}  #{(p2.name.name rescue '?')}"
  FIELDS.each { |f| puts "   #{f} = #{p2.send(f).inspect}" }
end
puts "\nDONE (read-only)."
