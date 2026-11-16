# frozen_string_literal: true
#
# selftest_correct_protonym_fields.rb -- runs gender/correct_protonym_fields.rb against stand-ins for Rails, the
# Protonym model and PaperTrail (no database) and checks each field's result. Run by smoke.sh:
#   ruby gender/selftest_correct_protonym_fields.rb
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

  class Version
    Row = Struct.new(:item_id, :request_uuid, :changeset)
    ROWS = []
    def self.where(item_type:, item_id:, request_uuid:)
      Rel.new(ROWS.select { |r| r.item_id == item_id && request_uuid.include?(r.request_uuid) })
    end
    Rel = Struct.new(:rows) do
      def order(*) = self
      def to_a = rows
    end
  end
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

  def self.find_by(id:) = DB[id]

  def initialize(id, name, attrs)
    @id = id
    @name = name
    @attrs = attrs.dup
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

W = 'write-uuid'
ADJ = { 'gender_agreement_type' => 'adjective', 'part_of_speech_basis' => 'grammatical_form',
        'interpretation_status' => 'demonstrated' }.freeze
SET = ADJ.transform_values { |v| [nil, v] }.freeze
Protonym::DB.merge!(
  1 => Protonym.new(1, 'A icarus', ADJ),                                        # revert, all three set by the write
  2 => Protonym.new(2, 'B bus', ADJ),                                           # revert, part of speech was there before
  3 => Protonym.new(3, 'C isis', ADJ),                                          # update part of speech
  4 => Protonym.new(4, 'D dus', ADJ.merge('gender_agreement_type' => 'participle')), # edited since the write
  5 => Protonym.new(5, 'E eus', ADJ),                                           # no version from the write
  6 => Protonym.new(6, 'F fus', ADJ),                                           # update, part of speech set before
  7 => Protonym.new(7, 'G other', ADJ),                                         # name differs
  8 => Protonym.new(8, 'H hus', ADJ),                                           # update the status only
  9 => Protonym.new(9, 'I ius', ADJ.merge('interpretation_status' => 'disputed')) # Brian judged it open
)
PaperTrail::Version::ROWS.push(
  PaperTrail::Version::Row.new(1, W, SET), PaperTrail::Version::Row.new(2, W, SET.except('gender_agreement_type')),
  PaperTrail::Version::Row.new(3, W, SET), PaperTrail::Version::Row.new(4, W, SET),
  PaperTrail::Version::Row.new(5, 'another-uuid', SET), PaperTrail::Version::Row.new(6, W, SET.except('gender_agreement_type')),
  PaperTrail::Version::Row.new(7, W, SET), PaperTrail::Version::Row.new(8, W, SET), PaperTrail::Version::Row.new(9, W, SET)
)
REVERT = ADJ.keys.map { |f| ['revert', f, ADJ[f], ''] }.freeze
INPUT_ROWS = {
  1 => ['A icarus', REVERT], 2 => ['B bus', REVERT],
  3 => ['C isis', [['update', 'gender_agreement_type', 'adjective', 'noun_in_apposition']]],
  4 => ['D dus', REVERT], 5 => ['E eus', REVERT],
  6 => ['F fus', [['update', 'gender_agreement_type', 'adjective', 'noun_in_apposition']]],
  7 => ['G gus', REVERT],
  8 => ['H hus', [['update', 'interpretation_status', 'demonstrated', 'reasonably_inferred']]],
  9 => ['I ius', [['update', 'interpretation_status', 'demonstrated', 'reasonably_inferred']]]
}.freeze
EXPECTED = {
  1 => %w[reverted reverted reverted], 2 => %w[kept reverted reverted], 3 => %w[updated],
  4 => %w[held held held], 5 => %w[held held held], 6 => %w[held], 7 => %w[held held held], 8 => %w[updated],
  9 => %w[held]
}.freeze
AFTER = {
  1 => {}, 2 => { 'gender_agreement_type' => 'adjective' }, 3 => ADJ.merge('gender_agreement_type' => 'noun_in_apposition'),
  8 => ADJ.merge('interpretation_status' => 'reasonably_inferred')
}.freeze

Dir.mktmpdir do |dir|
  ENV['SELFTEST_ROOT'] = dir
  Dir.mkdir(File.join(dir, 'tmp'))
  input = File.join(dir, 'tmp', 'in.tsv')
  File.write(input, "protonym_id\tprotonym_name\taction\tfield\twritten_value\tnew_value\treason\n" +
    INPUT_ROWS.flat_map { |id, (n, rs)| rs.map { |a, f, w, v| [id, n, a, f, w, v, 'test'].join("\t") } }.join("\n") + "\n")
  ENV['INPUT'] = input
  ENV['MODE'] = 'write'
  ENV['WRITE_REQUESTS'] = W
  $stdout = File.open(File::NULL, 'w')
  load File.expand_path('correct_protonym_fields.rb', __dir__)
  $stdout = STDOUT
  log = Dir[File.join(dir, 'tmp', 'correct_protonym_fields_write_*.tsv')].first
  got = File.readlines(log, chomp: true).drop(1).map { |l| l.split("\t", -1) }.group_by { |c| c[1].to_i }
  failures = EXPECTED.reject { |id, want| got.fetch(id, []).map(&:first) == want }
  abort "selftest_correct_protonym_fields: FAIL #{failures.keys.inspect} #{got.slice(*failures.keys).inspect}" if failures.any?
  AFTER.each do |id, want|
    have = ADJ.keys.to_h { |f| [f, Protonym::DB[id][f]] }.compact
    abort "selftest_correct_protonym_fields: FAIL stored values of #{id}: #{have.inspect}" unless have == want
  end
  puts 'selftest_correct_protonym_fields: ok (9 protonyms, 20 fields)'
end
