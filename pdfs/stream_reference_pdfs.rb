# frozen_string_literal: true
#
# stream_reference_pdfs.rb -- send reference PDFs from AntCat's S3 bucket off the server as one tar stream
# on stdout, without writing them to the server's disk.
#
# Why (13 Nov 2026): fetch_reference_pdfs.rb writes each run to /app/tmp first, and antcat-prod's 24 GB disk
# allows only about 250 recent PDFs a run (run 1: 356 PDFs, 4.5 GB, disk 62% to 82%). The 3,269 authorship
# references still to fetch would take 14 runs. This script reads each PDF from S3 straight into the stream,
# so the server's disk is not used and one command fetches the whole list.
#
# Read only: no database writes; S3 head and get only; nothing written on the server.
# Env:    ONLY_FILE=file of reference ids (commas or whitespace), relative to /app
# Output: stdout = MARKER, then a tar archive with one entry per PDF, named <reference id>__<file name>
#         (names longer than tar's 100 bytes are shortened, keeping the id and the extension). Anything Rails
#         prints to stdout while booting comes before MARKER, so extract_streamed_pdfs.py skips it.
#         stderr = one line per id as in fetch_reference_pdfs.rb (bytes / no document / link only /
#         S3 error / INCOMPLETE), then the totals.
# Run from the Mac (runbook: literature/README.md), never with stdout on a terminal:
#   ssh antcat 'docker exec -u antcat -w /app -e RAILS_ENV=production -e ONLY_FILE=tmp/stream_ids.txt \
#     antcat-app bundle exec rails runner tmp/stream_reference_pdfs.rb' 2> stream.log \
#     | python3 pdfs/extract_streamed_pdfs.py DIR

require 'rubygems/package'

MARKER = "\n__ANTCAT_PDF_TAR_STREAM__\n"
TAR_NAME_MAX = 100

# Nothing but the archive may reach stdout from here on: logs and puts go to stderr.
tar_io = $stdout
abort 'stdout is a terminal; pipe it into extract_streamed_pdfs.py' if tar_io.tty?
tar_io.binmode
$stdout = $stderr
ActiveRecord::Base.logger = nil
Rails.logger = ActiveSupport::Logger.new($stderr, level: :warn)

def tar_name(rid, file_name)
  name = "#{rid}__#{file_name}".tr('/', '_')
  return name if name.bytesize <= TAR_NAME_MAX

  ext = File.extname(name)
  "#{name.byteslice(0, TAR_NAME_MAX - ext.bytesize).scrub('')}#{ext}"
end

path = ENV.fetch('ONLY_FILE') { abort 'ONLY_FILE=<file of reference ids, relative to /app> is required' }
ids = File.read(Rails.root.join(path)).split(/[\s,]+/).reject(&:empty?).map { |id| Integer(id) }
abort "no ids in #{path}" if ids.empty?

client = References::DocumentStorage.client
bucket = Settings.s3.bucket
stats = Hash.new(0)
total = 0
started = Time.now

tar_io.write MARKER
Gem::Package::TarWriter.new(tar_io) do |tar|
  ids.each_with_index do |rid, i|
    doc = Reference.find_by(id: rid)&.document
    if doc.nil?
      puts "#{rid}\tno document"
      stats['no document'] += 1
      next
    end
    if doc.file_file_name.blank?
      puts "#{rid}\tlink only: #{doc.url}"
      stats['link only'] += 1
      next
    end

    key = doc.send(:s3_key)
    name = tar_name(rid, doc.file_file_name)
    begin
      size = client.head_object(bucket: bucket, key: key).content_length
    rescue Aws::S3::Errors::ServiceError => e
      puts "#{rid}\tS3 error: #{e.class.name.demodulize}"
      stats['S3 error'] += 1
      next
    end

    # The tar header already holds the size, so an error mid-file must not escape the entry: TarWriter then
    # pads the entry to its size and the archive stays readable; the entry is reported INCOMPLETE.
    written = 0
    error = nil
    tar.add_file_simple(name, 0o644, size) do |io|
      client.get_object(bucket: bucket, key: key) do |chunk|
        io.write(chunk)
        written += chunk.bytesize
      end
    rescue Aws::S3::Errors::ServiceError, Seahorse::Client::NetworkingError, Gem::Package::TarWriter::FileOverflow => e
      error = e
    end

    if error || written != size
      puts "#{rid}\t#{name}\tINCOMPLETE #{written} of #{size} bytes#{": #{error.class.name.demodulize}" if error}"
      stats['INCOMPLETE'] += 1
    else
      puts "#{rid}\t#{name}\t#{written} bytes"
      stats['copied'] += 1
      total += written
    end
    $stderr.puts "# #{i + 1} of #{ids.size}, #{(total / 1e9).round(2)} GB, #{(Time.now - started).round} s" if ((i + 1) % 100).zero?
  end
end
tar_io.flush

stats.each { |k, v| puts format('%-12s %d', k, v) }
puts format('%-12s %d', 'bytes', total)
puts "ids          #{ids.size} from #{path}"
