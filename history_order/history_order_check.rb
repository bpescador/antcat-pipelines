# frozen_string_literal: true
#
# history_order_check.rb  (READ-ONLY)
#
# For each protonym that already has a relational (structured) history item, prints
# the history exactly as the catalog page orders it (HistoryPresenter, the class the
# catalog view uses), with each line's type, group_order, editor position and id.
# Shows whether structured items keep the editors' position order or move by type.
#
# Run:
#   docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/history_order_check.rb

protonym_ids = HistoryItem.where.not(type: History::Definitions::TAXT).distinct.pluck(:protonym_id)
moved = 0

protonym_ids.each do |pid|
  protonym = Protonym.find(pid)
  items = protonym.history_items
  rendered = HistoryPresenter.new(items).grouped_items.flat_map(&:items)
  by_position = items.sort_by { |i| [i.position || 0, i.id] }
  differs = rendered.map(&:id) != by_position.map(&:id)
  moved += 1 if differs

  puts "\n== protonym #{pid} #{protonym.name.name} | page order differs from editor position order: #{differs}"
  rendered.each do |i|
    text = i.type == History::Definitions::TAXT ? i.taxt.to_s : i.to_taxt
    puts format('  pos %-3s %-24s slot %-4s id %-7s %s', i.position.to_s, i.type, i.definition.group_order, i.id,
      text.gsub(/\s+/, ' ').truncate(90))
  end
end

puts "\nProtonyms with structured items: #{protonym_ids.size}; page order differs from editor order: #{moved}"
