#!/usr/bin/env python3
"""
build_name_dictionary.py

Builds a dictionary of old species-group names and the valid name each one maps to today,
from a worldants dump (the nightly AntCat export, tab-separated). For matching names in
literature: requested by Steve Shattuck, September 2026.

Usage:
    python3 build_name_dictionary.py <worldants.txt> [out.csv]

Read-only: reads the dump, writes one CSV. Never touches the database.

Sources of "previous" names
  1. Every species-group row whose status is not valid and that has a "current valid name":
     obsolete combinations, synonyms, unavailable misspellings. The dump's "current valid
     name" is one hop only (a misspelling can point at a synonym), so the chain is followed
     here until it reaches a valid name or a dead end.
  2. The "was original combination" column: the protonym's original combination, where that
     name has no row of its own.
Rows whose chain ends at a non-valid name are kept and flagged in current_status.
Homonyms, unidentifiable, unavailable and excluded names have no "current valid name" in
the dump and are skipped (counted in the summary).

Output columns (Steve asked for the first two; the rest are there to filter on):
  previous_name, current_name, relationship, previous_status, current_status,
  rank, fossil, previous_antcat_id, current_antcat_id
"""
import csv
import sys
import collections
from datetime import date

csv.field_size_limit(10**9)

RELATIONSHIP = {
    'obsolete combination': 'obsolete combination',
    'synonym': 'synonym',
    'unavailable misspelling': 'misspelling',
}
MAX_HOPS = 12


def full_name(r):
    return ' '.join(x for x in (r['genus'], r['species'], r['subspecies']) if x)


def rank(r):
    return 'subspecies' if r['subspecies'] else 'species'


def main(src, out):
    with open(src, encoding='utf-8', errors='replace', newline='') as fh:
        rows = list(csv.DictReader(fh, delimiter='\t', quoting=csv.QUOTE_NONE))
    species_rows = [r for r in rows if r['species']]
    subfamilies = {r['subfamily'] for r in rows if r['subfamily']}

    def strip_subfamily(cvn):
        parts = cvn.split(' ')
        return ' '.join(parts[1:]) if parts and parts[0] in subfamilies else cvn

    by_name = collections.defaultdict(list)
    for r in species_rows:
        by_name[full_name(r)].append(r)

    def pick(name):
        """Row for a name: the valid one if there is one, else one that points onward."""
        cands = by_name.get(name, [])
        valid = [c for c in cands if c['status'] == 'valid']
        if valid:
            return valid[0]
        onward = [c for c in cands if c['current valid name']]
        return onward[0] if onward else (cands[0] if cands else None)

    def resolve(r):
        """Follow 'current valid name' hops to the end. Returns the final row, or None."""
        seen = set()
        cur = r
        for _ in range(MAX_HOPS):
            if cur['status'] == 'valid':
                return cur
            target = strip_subfamily(cur['current valid name'])
            if not target or target in seen:
                return cur if cur is not r else None
            seen.add(target)
            nxt = pick(target)
            if nxt is None:
                # name not in the dump as a row; return a stub so the name is still reported
                return {'antcat id': '', 'status': 'not in dump', '_name': target}
            cur = nxt
        return cur

    def name_of(row):
        return row.get('_name') or full_name(row)

    out_rows = []
    skipped = collections.Counter()
    hops_needed = 0

    # Source 1: non-valid rows with a current valid name
    for r in species_rows:
        if r['status'] == 'valid':
            continue
        if not r['current valid name']:
            skipped[r['status']] += 1
            continue
        final = resolve(r)
        if final is None:
            skipped['unresolvable chain'] += 1
            continue
        if strip_subfamily(r['current valid name']) != name_of(final):
            hops_needed += 1
        prev = full_name(r)
        if prev == name_of(final):
            continue
        out_rows.append([prev, name_of(final), RELATIONSHIP.get(r['status'], r['status']),
                         r['status'], final['status'], rank(r), 'yes' if r['fossil'] == 'TRUE' else 'no',
                         r['antcat id'], final['antcat id']])

    # Source 2: original combinations that have no row of their own
    covered = {(a, b) for a, b, *_ in out_rows}
    n_woc = 0
    for r in species_rows:
        woc = r['was original combination']
        if not woc or woc in by_name:
            continue
        final = r if r['status'] == 'valid' else (resolve(r) if r['current valid name'] else None)
        if final is None:
            skipped['original combination of a name with no current name'] += 1
            continue
        if woc == name_of(final) or (woc, name_of(final)) in covered:
            continue
        covered.add((woc, name_of(final)))
        out_rows.append([woc, name_of(final), 'original combination', 'protonym', final['status'],
                         'subspecies' if len(woc.split()) > 2 else 'species',
                         'yes' if r['fossil'] == 'TRUE' else 'no', f"P:{r['antcat id']}", final['antcat id']])
        n_woc += 1

    # de-duplicate and sort
    uniq = {tuple(x) for x in out_rows}
    out_rows = sorted(uniq)  # full-tuple sort: byte-identical output for the same dump

    with open(out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['previous_name', 'current_name', 'relationship', 'previous_status', 'current_status',
                    'rank', 'fossil', 'previous_antcat_id', 'current_antcat_id'])
        w.writerows(out_rows)

    ambiguous = {k for k, v in collections.Counter(x[0] for x in out_rows).items() if v > 1}
    ambiguous = {k for k in ambiguous if len({x[1] for x in out_rows if x[0] == k}) > 1}
    not_valid = sum(1 for x in out_rows if x[4] != 'valid')

    print(f"Dump: {src}")
    print(f"  rows in dump: {len(rows):,}; species-group rows: {len(species_rows):,}")
    print(f"Wrote {len(out_rows):,} rows to {out}")
    print(f"  by relationship: {dict(collections.Counter(x[2] for x in out_rows))}")
    print(f"  from 'was original combination': {n_woc:,}")
    print(f"  chains needing more than one hop: {hops_needed:,}")
    print(f"  rows whose current name is not valid: {not_valid:,} "
          f"{dict(collections.Counter(x[4] for x in out_rows if x[4] != 'valid'))}")
    print(f"  previous names mapping to more than one current name: {len(ambiguous):,}")
    print(f"  skipped (no current valid name in dump): {dict(skipped)}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else f"antcat__name_dictionary_{date.today():%Y%m%d}.csv"
    main(src, out)
