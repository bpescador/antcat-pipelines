# institutions_export.rb -- READ ONLY. Dumps the institutions table verbatim.
require 'json'
puts "columns: #{Institution.column_names.inspect}"
OUT = Rails.root.join('tmp', 'institutions.jsonl')
File.open(OUT, 'w') { |i_f| Institution.find_each { |i| i_f.puts i.attributes.to_json } }
puts "wrote #{Institution.count} rows to #{OUT}"
