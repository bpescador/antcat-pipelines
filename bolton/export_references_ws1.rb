# export_references.rb
#
# Dumps the AntCat reference table to CSV so the catalogue diff can find which
# Bolton bibliography entries AntCat is missing. The worldants.txt dump carries
# only a reference_id per name -- not the bibliographic text -- so this is the
# one piece the diff needs straight from the database.
#
# Run on the production droplet exactly like export_protonyms.rb:
#
#   docker exec -w /app -e RAILS_ENV=production antcat-app \
#       bundle exec rails runner /app/export_references.rb
#
# Output (inside container): /app/antcat_references.csv
#          (on the host):    /var/www/antcat-2/antcat_references.csv
#
# Then copy it next to the Bolton CSVs and re-run:
#   python3 diff_catalogue.py --antcat-dir antcat_out --bolton-dir bolton_out \
#       --out-dir diff_out --antcat-refs antcat_references.csv

require 'csv'

OUT = '/app/antcat_references.csv'

def safe(obj, *methods)
  methods.each do |m|
    next unless obj.respond_to?(m)
    v = obj.public_send(m)
    return v if v.present?
  end
  ''
rescue StandardError
  ''
end

count = 0
CSV.open(OUT, 'w') do |csv|
  csv << %w[id type authors citation_year year title journal pagination citation]
  Reference.find_each(batch_size: 1000) do |r|
    authors = safe(r, :author_names_string, :author_names_string_cache)
    cyear   = safe(r, :citation_year)                 # e.g. "1995a"
    year    = safe(r, :year)                          # integer
    title   = safe(r, :title)
    journal = safe(r, :journal_name, :journal)        # journal object or name
    journal = safe(journal, :name) if journal.respond_to?(:name)
    pages   = safe(r, :pagination)
    # a flat citation string for human reading in the diff output
    citation = [authors, (cyear.presence || year), title, journal, pages]
               .reject { |x| x.to_s.strip.empty? }.join('. ')
    csv << [r.id, r.class.name, authors, cyear, year, title, journal, pages, citation]
    count += 1
  end
end

puts "wrote #{count} references to #{OUT}"
