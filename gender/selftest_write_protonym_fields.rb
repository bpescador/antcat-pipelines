# frozen_string_literal: true
#
# selftest_write_protonym_fields.rb -- runs gender/write_protonym_fields.rb against stand-ins for Rails and the
# Protonym model (no database) and checks each field's result: written, already, held, and why. Run by smoke.sh:
#   ruby gender/selftest_write_protonym_fields.rb
require 'securerandom'
require 'pathname'
require 'tmpdir'
require 'digest'

class Object
  def blank? = respond_to?(:empty?) ? empty? : !self
  def present? = !blank?
  def in?(collection) = collection.include?(self)
end

class NilClass
  def blank? = true
end

module ActiveRecord
  class Rollback < StandardError; end
  class ActiveRecordError < StandardError; end

  class Base
    class << self
      attr_accessor :logger
    end

    def self.transaction
      yield
    rescue ActiveRecord::Rollback
      nil
    end
  end
end

module Rails
  def self.logger = (@logger ||= Struct.new(:level).new)
  def self.root = Pathname.new(ENV.fetch('SELFTEST_ROOT'))
end

module RequestStore
  def self.store = (@store ||= {})
end

module PaperTrail
  def self.request = (@request ||= Struct.new(:whodunnit).new)
end

class Activity
  UPDATE = 'update'
end

class User
  def self.find_by!(**) = new
  def id = 1
end

class Protonym
  SCRIPTED_SPELLING_CHANGE_BLOCKED_STATUSES = %w[disputed unresolved].freeze
  DB = {}
  attr_reader :etymology_taxt, :locality

  def self.column_names = %w[gender_agreement_type part_of_speech_basis interpretation_status etymology_derivation]
  def self.find_by(id:) = DB[id]

  def initialize(id, name, attrs, locality: 'MEXICO', ety: nil)
    @id = id
    @name = name
    @attrs = attrs.dup
    @locality = locality
    @etymology_taxt = ety
    @changes = {}
  end

  def name = Struct.new(:name).new(@name)
  def [](key) = @attrs[key]
  def interpretation_status = @attrs['interpretation_status']
  def changes = @changes
  def saved_changes = @saved_changes
  def reload = self
  def errors = Struct.new(:full_messages).new(@errors)

  def assign_attributes(hash)
    hash.each do |k, v|
      @changes[k] = [@attrs[k], v] unless @attrs[k] == v
      @attrs[k] = v
    end
  end

  def valid?
    @errors = @attrs['part_of_speech_basis'] && !@attrs['gender_agreement_type'] ? ['basis needs part of speech'] : []
    @errors.empty?
  end

  def save!
    @saved_changes = @changes.merge('updated_at' => [1, 2])
    @changes = {}
  end

  def create_activity(*) = Struct.new(:x) { def update_columns(**) = nil }.new(1)
end

ADJ = { 'gender_agreement_type' => 'adjective' }.freeze
FULL = ADJ.merge('part_of_speech_basis' => 'grammatical_form', 'interpretation_status' => 'demonstrated').freeze
Protonym::DB.merge!(
  1 => Protonym.new(1, 'A aensis', {}),
  2 => Protonym.new(2, 'B bensis', ADJ),
  3 => Protonym.new(3, 'C censis', { 'gender_agreement_type' => 'noun_in_apposition' }),
  4 => Protonym.new(4, 'D densis', {}, ety: 'Named after the place.'),
  5 => Protonym.new(5, 'E eensis', {}, locality: 'PERU'),
  6 => Protonym.new(6, 'F fensis', FULL),
  7 => Protonym.new(7, 'G gensis', { 'interpretation_status' => 'unresolved' })
)
EXPECTED = {
  1 => %w[written written written],
  2 => %w[already written written],
  3 => %w[held held held],
  4 => %w[held held held],
  5 => %w[held held held],
  6 => %w[already already already],
  7 => %w[held held held],
  8 => %w[held held held]
}.freeze

Dir.mktmpdir do |dir|
  ENV['SELFTEST_ROOT'] = dir
  Dir.mkdir(File.join(dir, 'tmp'))
  input = File.join(dir, 'tmp', 'in.tsv')
  md5 = Digest::MD5.hexdigest('MEXICO')
  names = { 1 => 'A aensis', 2 => 'B bensis', 3 => 'C censis', 4 => 'D densis', 5 => 'E eensis', 6 => 'F fensis',
            7 => 'G gensis', 8 => 'H gone' }
  File.write(input, "protonym_id\tprotonym_name\trule\tfield\tvalue\tlocality_md5\n" + names.flat_map do |id, n|
    FULL.map { |f, v| [id, n, 'toponym_ensis_pos', f, v, md5].join("\t") }
  end.join("\n") + "\n")
  ENV['INPUT'] = input
  ENV['MODE'] = 'write'
  $stdout = File.open(File::NULL, 'w')
  load File.expand_path('write_protonym_fields.rb', __dir__)
  $stdout = STDOUT
  log = Dir[File.join(dir, 'tmp', 'write_protonym_fields_write_*.tsv')].first
  got = File.readlines(log, chomp: true).drop(1).map { |l| l.split("\t", -1) }.group_by { |c| c[1].to_i }
  failures = EXPECTED.reject { |id, want| got.fetch(id, []).map(&:first) == want }
  abort "selftest_write_protonym_fields: FAIL #{failures.keys.inspect} #{got.slice(*failures.keys).inspect}" if failures.any?
  puts 'selftest_write_protonym_fields: ok (8 protonyms, 24 fields)'
end
