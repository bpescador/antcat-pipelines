# export_references.rb  (canonical -- supersedes the pre-container version)
#
# Dumps the AntCat reference table to CSV, WITH the nested-reference container
# resolved. This is the one exporter to run; there is no separate _v2 step.
# Adds the NESTED-REFERENCE CONTAINER,
# which the original runner drops -- the "species author != publication author"
# case TaxonWorks needs at the Source level (Q2 of the references memo).
#
# AntCat's NestedReference has a `nesting_reference` association (the containing
# Reference). The original runner never pulls it, so the CSV's `journal` is blank
# for nested works and the container is lost. This adds four columns:
#     nesting_reference_id, nesting_title, nesting_authors, nesting_pages
#
# EVERY accessor is guarded (safe/…): if a method name is wrong for this AntCat
# build, that field comes back blank instead of raising, so a first run can't fail
# on a schema mismatch -- inspect the output, then tighten the method names.
#
# Run on the production droplet (WORKFLOW.md Stage 1):
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app \
#       bundle exec rails runner /app/export_references.rb
# Output (host): /var/www/antcat-2/antcat_references.csv

# csv: Ruby 3.4 moved it from a default gem to a bundled gem. AntCat runs Ruby 4.0 and its
# Gemfile does not list csv, so under `bundle exec` a plain `require 'csv'` raises LoadError
# and nothing is written (TaxonWorks sync, 2026-11-11). The gem still ships with Ruby, so put
# its newest copy on the load path here, without touching the app or its Gemfile.
begin
  require 'csv'
rescue LoadError
  dirs = Dir.glob(File.join(Gem.default_dir, 'gems', 'csv-*', 'lib'))
  abort "export_references.rb: no csv gem under #{Gem.default_dir}/gems; nothing written" if dirs.empty?
  version = ->(d) { Gem::Version.new(File.basename(File.dirname(d)).delete_prefix('csv-')) rescue Gem::Version.new('0') }
  $LOAD_PATH.unshift(dirs.max_by(&version))
  require 'csv'
end

OUT = '/app/antcat_references.csv'
# Written first to Rails' tmp/ (owned by the app user since AntCat #1578) and copied over OUT
# only when the export has finished: a run that fails part-way never leaves a partial file
# under the real name with today's date. A copy, not a rename, so the app user needs no write
# permission on /app itself, only on the CSV, exactly as before.
TMP = Rails.root.join('tmp', 'antcat_references.csv.tmp').to_s

def safe(obj, *methods)
  return '' if obj.nil?
  methods.each do |m|
    next unless obj.respond_to?(m)
    v = obj.public_send(m)
    return v if v.present?
  end
  ''
rescue StandardError
  ''
end

# Try, in order, the association names AntCat has used for a nested reference's
# container across versions. Whichever exists and returns a Reference wins.
def nesting_of(r)
  %i[nesting_reference nested_reference container_reference book_reference parent_reference]
    .each do |assoc|
      next unless r.respond_to?(assoc)
      v = r.public_send(assoc)
      return v if v.present?
    end
  nil
rescue StandardError
  nil
end

count = 0
nested_with_container = 0
CSV.open(TMP, 'w') do |csv|
  csv << %w[id type authors citation_year year title journal pagination citation
            nesting_reference_id nesting_title nesting_authors nesting_pages]
  Reference.find_each(batch_size: 1000) do |r|
    authors = safe(r, :author_names_string, :author_names_string_cache)
    cyear   = safe(r, :citation_year)
    year    = safe(r, :year)
    title   = safe(r, :title)
    journal = safe(r, :journal_name, :journal)
    journal = safe(journal, :name) if journal.respond_to?(:name)
    pages   = safe(r, :pagination)

    nest = nesting_of(r)
    if nest.present?
      nest_id      = safe(nest, :id)
      nest_title   = safe(nest, :title)
      nest_authors = safe(nest, :author_names_string, :author_names_string_cache)
      # the containing work's own journal/publisher line, if any
      nest_journal = safe(nest, :journal_name, :journal)
      nest_journal = safe(nest_journal, :name) if nest_journal.respond_to?(:name)
      nest_title   = [nest_title, nest_journal].reject { |x| x.to_s.strip.empty? }.join('. ')
      # the page RANGE within the container is often on the nested ref's pagination
      nest_pages   = pages
      nested_with_container += 1 if nest_id.present?
    else
      nest_id = nest_title = nest_authors = nest_pages = ''
    end

    citation = [authors, (cyear.presence || year), title, journal, pages]
               .reject { |x| x.to_s.strip.empty? }.join('. ')
    csv << [r.id, r.class.name, authors, cyear, year, title, journal, pages, citation,
            nest_id, nest_title, nest_authors, nest_pages]
    count += 1
  end
end
FileUtils.cp(TMP, OUT)
File.delete(TMP)

puts "Wrote #{count} references to #{OUT} (csv #{CSV::VERSION})"
puts "  nested references with a resolved container: #{nested_with_container}"
puts '  (if this is ~0, the association name is wrong for this build -- check a'
puts "   NestedReference in `rails console`: r = Reference.where(type: 'NestedReference').first; r.methods.grep(/nest|contain|book|parent/))"
