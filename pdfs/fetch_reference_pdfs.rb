# frozen_string_literal: true
#
# fetch_reference_pdfs.rb -- copy reference PDFs from AntCat's S3 bucket into /app/tmp/<OUT>/.
#
# Read only: no database writes; S3 get only. Replaces the June copy_reference_pdfs.rb, which used
# Paperclip (removed in AntCat #1555, Oct 2026). Uses AntCat's own References::DocumentStorage client and
# the document's S3 key ("<reference_document.id>/<file_file_name>"), so it follows any change there.
#
# Env:    ONLY=reference ids, comma-separated (required; at most 500 a run); OUT=folder under tmp
#         (default reference_pdfs)
# Output: tmp/<OUT>/<reference id>__<file name>; one line per id; documents that are only a link are listed
#         with their link, not fetched.
# Run (runbook procedure 16), then copy the folder off the droplet and clear it:
#   docker exec -u antcat -w /app -e RAILS_ENV=production -e ONLY=144366,144377 antcat-app \
#     bundle exec rails runner tmp/fetch_reference_pdfs.rb
#   on the host the files are in /var/www/antcat-2/tmp/reference_pdfs/

ActiveRecord::Base.logger = nil

ids = ENV.fetch('ONLY', '').split(',').map(&:strip).reject(&:empty?).map(&:to_i)
abort 'ONLY=<reference ids> is required' if ids.empty?
abort "#{ids.size} ids; at most 500 a run" if ids.size > 500

out = Rails.root.join('tmp', ENV.fetch('OUT', 'reference_pdfs'))
FileUtils.mkdir_p(out)
client = References::DocumentStorage.client
bucket = Settings.s3.bucket
stats = Hash.new(0)

ids.each do |rid|
  doc = Reference.find_by(id: rid)&.document
  if doc.nil?
    puts "#{rid}\tno document"
    stats['no document'] += 1
  elsif doc.file_file_name.blank?
    puts "#{rid}\tlink only: #{doc.url}"
    stats['link only'] += 1
  else
    path = out.join("#{rid}__#{doc.file_file_name}")
    begin
      client.get_object(bucket: bucket, key: doc.send(:s3_key), response_target: path.to_s)
      puts "#{rid}\t#{path.basename}\t#{File.size(path)} bytes"
      stats['copied'] += 1
    rescue Aws::S3::Errors::ServiceError => e
      puts "#{rid}\tS3 error: #{e.class.name.demodulize}"
      stats['S3 error'] += 1
    end
  end
end

stats.each { |k, v| puts format('%-12s %d', k, v) }
puts "Folder: #{out}"
