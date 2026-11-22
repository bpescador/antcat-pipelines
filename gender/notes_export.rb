# frozen_string_literal: true
#
# notes_export.rb -- read-only export of the explanatory text on named protonyms, exactly as stored: the protonym's
# notes_taxt and its "Notes on this name" page (AntCat #1623). Writes nothing to the database.
#
# Used before a revision of those texts, so that the revision's `old` values are the stored bytes, not a copy
# from an earlier draft (the input of apply_grouped_changes.rb asserts them exactly).
#
# Env:    PROTONYMS=protonym ids, comma-separated (required)
# Output: /app/tmp/notes_export_<timestamp>/ with, per protonym, <id>_notes_taxt.txt and <id>_notes_page.md
#         (absent when empty), and MANIFEST.tsv (protonym, name, notes_page id, file, bytes, md5); also printed.
require 'digest'
require 'fileutils'

ActiveRecord::Base.logger = nil
Rails.logger.level = :info

PROTONYMS = ENV.fetch('PROTONYMS').split(',').map { |s| Integer(s) }
abort 'No PROTONYMS' if PROTONYMS.empty?

DIR = Rails.root.join('tmp', "notes_export_#{Time.current.strftime('%Y%m%d%H%M%S')}").to_s
FileUtils.mkdir_p(DIR)
manifest = [%w[protonym_id name notes_page_id file bytes md5].join("\t")]

PROTONYMS.each do |pid|
  p = Protonym.find(pid)
  page = p.notes_page
  { "#{pid}_notes_taxt.txt" => p.notes_taxt, "#{pid}_notes_page.md" => page&.content }.each do |file, text|
    next if text.nil? || text.empty?
    File.binwrite(File.join(DIR, file), text)
    manifest << [pid, p.name.name, page&.id, file, text.bytesize, Digest::MD5.hexdigest(text)].join("\t")
  end
end

File.write(File.join(DIR, 'MANIFEST.tsv'), manifest.join("\n") + "\n")
puts manifest
puts "Wrote #{DIR}"
