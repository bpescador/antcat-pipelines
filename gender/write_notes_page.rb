# frozen_string_literal: true
#
# write_notes_page.rb -- puts one reviewed document on AntCat as the notes on a name ("Notes on this name",
# AntCat #1623: table notes_pages, one page per protonym, Markdown, shown at /protonyms/<id>/notes).
# One protonym per run. Nothing else is written: no protonym field, no taxon, no history item.
#
# First use: the Temnothorax crassispinus analysis (protonym 175373), approved by Brian on 16 Nov 2026.
# A page goes on antcat.org only with Brian's sign-off of that document.
#
# Held, not written, when:
#   - AntCat #1623 is not deployed (no NotesPage)
#   - the input's md5 differs from MD5 (the file is not the one that was reviewed)
#   - the input is empty, not UTF-8, or has no "## " section heading
#   - the protonym is not found, or its name differs from NAME
#   - the protonym already has notes (nothing is overwritten: edit the page on the site, its history keeps both)
#   - validation fails, or the stored text differs from the input after the save
#
# Env:    MODE=check (default; rolls back) | MODE=write
#         PROTONYM_ID, NAME (the protonym's name as AntCat has it), MD5 (of the reviewed file): all required
#         INPUT=/app/tmp/notes_page.md (default)
#         SUMMARY=edit summary (default below)
# Edits:  AntCatBot, automated_edit: true, one request_uuid, one `create` activity.
# Rollback: delete the page on the site (editors: Delete on the notes page), or the dump taken before the run.
require 'digest'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

MODE = ENV.fetch('MODE', 'check')
raise 'MODE must be check or write' unless %w[check write].include?(MODE)
INPUT = ENV.fetch('INPUT', Rails.root.join('tmp', 'notes_page.md').to_s)
PROTONYM_ID = Integer(ENV.fetch('PROTONYM_ID'))
NAME = ENV.fetch('NAME')
MD5 = ENV.fetch('MD5')
SUMMARY = ENV.fetch('SUMMARY', '[automated] notes on this name added from a reviewed document')

abort 'AntCat #1623 is not deployed (no NotesPage).' unless defined?(NotesPage) && NotesPage.table_exists?
abort "No input file #{INPUT}" unless File.exist?(INPUT)

class Reject < StandardError; end

bot = User.find_by!(name: 'AntCatBot')
uuid = SecureRandom.uuid
RequestStore.store[:current_request_uuid] = uuid
PaperTrail.request.whodunnit = bot.id.to_s

md5 = Digest::MD5.file(INPUT).hexdigest
text = File.read(INPUT, mode: 'rb').force_encoding('UTF-8')
puts "MODE=#{MODE} request_uuid=#{uuid} input=#{INPUT} md5=#{md5} bytes=#{text.bytesize} protonym=#{PROTONYM_ID}"

result = detail = ''
begin
  ActiveRecord::Base.transaction do
    raise Reject, "input md5 #{md5} is not the reviewed file's #{MD5}" unless md5 == MD5
    raise Reject, 'input is not UTF-8' unless text.valid_encoding?
    raise Reject, 'input is empty' if text.strip.empty?

    protonym = Protonym.find_by(id: PROTONYM_ID)
    raise Reject, 'protonym not found' unless protonym
    raise Reject, "name differs (#{protonym.name.name} vs #{NAME})" unless protonym.name.name == NAME
    raise Reject, "the protonym already has notes (notes page #{protonym.notes_page.id})" if protonym.notes_page

    notes_page = NotesPage.new(protonym: protonym, content: text)
    raise Reject, "invalid: #{notes_page.errors.full_messages.join('; ')}" unless notes_page.valid?
    raise Reject, 'no "## " section heading (the link text on the name\'s pages comes from them)' if
      notes_page.section_titles.empty?

    notes_page.save!
    stored = notes_page.reload.content
    raise Reject, 'stored text differs from the input' unless stored == text.gsub(/\r\n?/, "\n")

    notes_page.create_activity(Activity::CREATE, bot, edit_summary: SUMMARY).update_columns(automated_edit: true)
    puts "  notes page #{notes_page.id}: #{protonym.name.name}; sections: #{notes_page.section_titles.join(', ')}; " \
         "#{stored.bytesize} bytes; /protonyms/#{protonym.id}/notes"
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

puts "RESULT: #{result}#{detail.empty? ? '' : " (#{detail})"}"
puts "notes pages in the database: #{NotesPage.count}"
puts "request_uuid=#{uuid}"
