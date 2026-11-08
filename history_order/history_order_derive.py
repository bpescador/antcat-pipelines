"""Derive canonical order of history kinds from editor positions; report strength, ambiguity, violations."""
import json, collections, itertools, random, sys
GROUP = sys.argv[1] if len(sys.argv) > 1 else 'species-group'
MIN_N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
rows = [r for r in json.load(open('/tmp/ho/rows.json')) if r['group'] == GROUP]
by_p = collections.defaultdict(list)
for r in rows: by_p[r['protonym_id']].append(r)
for v in by_p.values(): v.sort(key=lambda r: (r['pos'], r['iid']))

before = collections.Counter()   # (a,b) -> number of protonyms where a precedes b (majority of item pairs)
for items in by_p.values():
    pc = collections.Counter()
    for i, j in itertools.combinations(range(len(items)), 2):
        a, b = items[i]['kind'], items[j]['kind']
        if a != b: pc[(a, b)] += 1
    for (a, b), n in pc.items():
        m = pc.get((b, a), 0)
        if n > m or (n == m and a < b): before[(a, b)] += 1 if n > m else 0
kinds_count = collections.Counter(r['kind'] for r in rows)
kinds = [k for k, v in kinds_count.items() if v >= MIN_N and k not in ('OTHER',)]

def score(order):
    s = 0
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            s += before[(a, b)]
    return s
total = sum(before[(a, b)] for a in kinds for b in kinds if a != b)
# Start: sort by win share, then local search with insertion moves.
win = {a: sum(before[(a, b)] for b in kinds if b != a) / max(1, sum(before[(a, b)] + before[(b, a)] for b in kinds if b != a)) for a in kinds}
order = sorted(kinds, key=lambda k: -win[k])
best = score(order); improved = True
while improved:
    improved = False
    for i in range(len(order)):
        for j in range(len(order)):
            if i == j: continue
            o = order[:]; k = o.pop(i); o.insert(j, k)
            s = score(o)
            if s > best: order, best, improved = o, s, True
print(f'== {GROUP}: {len(by_p)} protonyms; kinds with >= {MIN_N} lines: {len(kinds)}')
print(f'Pairwise protonym observations consistent with the order: {best}/{total} = {best/total:.1%}\n')
print('Order (n lines; agreement with each later kind, weakest pair):')
for i, a in enumerate(order):
    weak = []
    for b in order[i + 1:]:
        f, r = before[(a, b)], before[(b, a)]
        if f + r >= 5: weak.append((f / (f + r), b, f, r))
    weak.sort()
    w = weak[0] if weak else None
    ws = f'weakest vs "{w[1]}" {w[2]}:{w[3]} ({w[0]:.0%})' if w else ''
    print(f'  {i+1:2d}. {a:42s} n={kinds_count[a]:5d}  {ws}')
print('\nAmbiguous pairs (both directions, 60/40 or closer, >=10 protonyms):')
for a, b in itertools.combinations(order, 2):
    f, r = before[(a, b)], before[(b, a)]
    if f + r >= 10 and min(f, r) / (f + r) >= 0.4:
        print(f'  {a} vs {b}: {f}:{r}')
json.dump({'group': GROUP, 'order': order, 'before': {f'{a}|{b}': v for (a, b), v in before.items()}},
          open(f'/tmp/ho/order_{GROUP}.json', 'w'))
