"""Split order violations into script-fixable and manual (for Bradley).

Canonical sort key per line: rank of its kind (accepted order, 2026-11-07), with the
status block (Subspecies of, Status as species, Junior synonym of) sharing one rank so
its lines keep their relative editor order (chronology not yet verified). Lines of the
same rank keep editor order. A page is script-fixable when it breaks a strong rule,
contains no Note or OTHER line, and the canonical sort only moves classified lines.
"""
import json, collections, itertools, csv
order = json.load(open('/tmp/ho/order_species-group.json'))
ORDER = order['order']
b = order['before']
STATUS = {'Subspecies of', 'Status as species', 'Junior synonym of'}
rank = {}
r = 0
for k in ORDER:
    if k in STATUS:
        rank[k] = min(ORDER.index(s) for s in STATUS if s in ORDER)
    else:
        rank[k] = ORDER.index(k)
strong = {}
for key, v in b.items():
    a, c = key.split('|'); rv = b.get(f'{c}|{a}', 0)
    if a in rank and c in rank and v + rv >= 20 and v / (v + rv) >= 0.95 and not (a in STATUS and c in STATUS):
        strong[(a, c)] = (v, rv)

rows = [x for x in json.load(open('/tmp/ho/rows.json')) if x['group'] == 'species-group']
by = collections.defaultdict(list)
for x in rows: by[x['protonym_id']].append(x)
auto, manual = [], []
for pid, it in by.items():
    it.sort(key=lambda x: (x['pos'], x['iid']))
    bad = sorted({(it[j]['kind'], it[i]['kind']) for i, j in itertools.combinations(range(len(it)), 2)
                  if (it[j]['kind'], it[i]['kind']) in strong})
    if not bad: continue
    kinds = [x['kind'] for x in it]
    unranked = [k for k in kinds if k not in rank]
    rec = {'protonym_id': pid, 'violations': '; '.join(f'{a} before {c}' for a, c in bad),
           'current': ' | '.join(kinds)}
    if 'Note' in kinds or 'OTHER' in kinds or unranked:
        rec['reason'] = 'page has a Note or unclassified line'
        manual.append((rec, it)); continue
    new = sorted(it, key=lambda x: (rank[x['kind']], x['pos'], x['iid']))
    rec['proposed'] = ' | '.join(x['kind'] for x in new)
    rec['new_positions'] = ' '.join(f"{x['iid']}:{n + 1}" for n, x in enumerate(new))
    auto.append((rec, it))
print(f'strong rules: {len(strong)}; pages breaking one: {len(auto) + len(manual)}')
print(f'  script-fixable (re-sort by kind): {len(auto)}')
print(f'  manual (has Note or unclassified line): {len(manual)}')
c = collections.Counter(v for rec, _ in auto + manual for v in rec['violations'].split('; '))
for k, v in c.most_common(12): print(f'  {v:4d}  {k}')
json.dump({'auto': [a for a, _ in auto], 'manual': [m for m, _ in manual]}, open('/tmp/ho/fixes.json', 'w'))
