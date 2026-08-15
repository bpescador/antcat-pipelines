#!/usr/bin/env python3
"""
diff_status_refs.py -- STANDALONE, EXPERIMENTAL. Not part of diff_history.py yet.

Bolton's "Status as species:" lines carry the faunistic citation trail -- every
redescription, regional checklist, and revision that treated the taxon as a valid
species. AntCat is known to under-populate exactly these, so this is the largest
pool of potentially-missing references, and diff_history.py deliberately skips it.

This script compares Bolton's Status-as-species citations (and, optionally, the
"As unavailable (infrasubspecific) name" lines) against AntCat's full citation set
for the paired name, and reports the ones AntCat lacks.

It REUSES the proven pieces from the main pipeline:
  - protonym identity pairing (protonym.py, via diff_history.AntCat)
  - the citations() parser WITH its _canon_in / et-al / first-author-or-nearest keying
    (so "X, in Y", "Boudinot, Bock, et al.", online-early years are handled the same)

The one NEW thing it must do: STRIP THE LABEL before parsing citations, or the words
"Status"/"species" are captured as author surnames. That is the bug that made an
earlier quick count untrustworthy.

Output: status_refs_to_check.csv -- one row per (name, missing citation), with the
same review disposition as the added-refs sheet: a disagreement to verify, not a
confirmed gap.
"""
import csv, sys, json, os, re, argparse
from collections import defaultdict
import diff_history as D            # reuse AntCat, citations(), loose(), bolton_protokey()
from citation_match import citation_present, authors_of_segment, _same_author

csv.field_size_limit(sys.maxsize)

# Citation-bearing history line types that diff_history.py does NOT compare. Each is
# harvested identically: strip the label, parse the citations, diff against AntCat.
# The label pattern captures everything up to the ':' that introduces the citations;
# for the "... in <taxon>:" forms the taxon is part of the label (a placement, not a
# synonymy target we need to resolve -- we only care about the citation trail here).
#
# NOT included, deliberately:
#   Current subspecies:     a list of subspecies NAMES, no citations -> nothing to diff
#   Replacement name:       handled by diff_history.py's replacement logic
#   Type-*/Distribution:    pure metadata
LINE_LABELS = {
    'Status as species':          r'Status as species',
    'As unavailable (infrasub.)':  r'As unavailable \(infrasubspecific\) name',
    'Incertae sedis':              r'[Ii]ncertae sedis in [A-Z][a-z]+',
    'Unidentifiable taxon':        r'Unidentifiable taxon(?:[;,] incertae sedis in [A-Z][a-z]+)?',
    'Nomen dubium':                r'Nomen dubium',
    'Nomen oblitum':               r'Nomen oblitum(?:, synonym of [a-z]+)?',
    'Unplaced to subgenus':        r'[Uu]nplaced to subgenus',
    'Combination (provisional)':   r'Combination \(provisional\) in [A-Z][a-z]+',
}
# one compiled matcher per label: "^ <label> : <citations>"
LINE_MATCHERS = [(name, re.compile(r'^\s*(?:' + pat + r')\s*:\s*(.*)$'))
                 for name, pat in LINE_LABELS.items()]




def run(bolton_dir, worldants, out_dir, recent_from=2015, only_status=False):
    os.makedirs(out_dir, exist_ok=True)
    ac = D.AntCat(worldants)

    rows = []
    n_lines = n_cite = n_present = n_missing = 0
    names_with_gaps = set()
    by_linetype = defaultdict(int)
    matchers = ([m for m in LINE_MATCHERS if m[0] == 'Status as species']
                if only_status else LINE_MATCHERS)

    with open(os.path.join(bolton_dir, 'bolton_species_blocks.jsonl')) as fh:
        for line in fh:
            b = json.loads(line)
            bk = D.bolton_protokey(b)
            if not bk:
                continue
            key = ac.pair(*bk, cur_genus=b['genus'])
            if not key:
                continue
            me = ac.names[key]
            ac_cites = set(D.citations(me['text']))
            ac_loose = {D.loose(k) for k in ac_cites}

            for raw in (b.get('block_text') or '').split('\n'):
                stripped = raw.strip()
                hit = next(((nm, m) for nm, rx in matchers for m in [rx.match(stripped)] if m),
                           None)
                if not hit:
                    continue
                label, mm = hit
                n_lines += 1
                payload = mm.group(1)                       # citations only; label stripped
                # judge each citation once, grouped by year -- a citation is "present" if
                # ANY of its author keys (first author or nearest surname) matches AntCat.
                by_yl = defaultdict(list)
                for k, (sur, yl) in D.citations(payload).items():
                    by_yl[yl].append((k, sur))
                for yl, grp in by_yl.items():
                    yr = int(yl[:4])
                    if yr < recent_from:
                        continue
                    n_cite += 1
                    # single coherent decision: does AntCat cite THIS paper? Matches on
                    # first author + year with signature confirmation, so spelling variants
                    # and compound surnames count as present, while a redescription is not
                    # matched to a same-author original description. Isolate Bolton's own
                    # citation segment so its author signature is compared, not the line.
                    bseg = next((s for s in re.split(r';', payload)
                                 if yl[:4] in s and any(sur in s for _, sur in grp)),
                                payload)
                    if citation_present(bseg, me['text']):
                        n_present += 1
                        continue
                    # online-early vs formal year: AntCat cites the SAME first author within
                    # one year on this name (Bolton "Mera-Rodriguez 2024" == AntCat 2025).
                    b_first = (authors_of_segment(bseg) or [''])[0]
                    if b_first and any(
                            _same_author(b_first, (authors_of_segment(m.group(1) + ' ' + m.group(2))
                                                   or [''])[0])
                            for m in re.finditer(
                                r'([A-Z][A-Za-z\u00C0-\u024F\'\-.,&\s]{0,60}?),?\s*'
                                r'(1[6789]\d\d|20\d\d)[a-z]?', me['text'])
                            if abs(yr - int(m.group(2))) == 1):
                        n_present += 1
                        continue
                    n_missing += 1
                    by_linetype[label] += 1
                    names_with_gaps.add((b['genus'], b['epithet']))
                    # page for THIS citation: find the surname of the citation (any key in
                    # the group), then the "year: page" that follows it in the full payload.
                    # Search the untruncated payload -- the citation is often at the end of
                    # a long line, past any display cutoff.
                    page = ''
                    qualifier = ''
                    for _, sur in grp:
                        pm = re.search(re.escape(sur) + r'[^;:]*?' + re.escape(yl[:4])
                                       + r'[a-z]?\s*:?\s+(\d+)\s*(\([^)]+\))?', payload)
                        if pm:
                            page = pm.group(1)
                            qualifier = pm.group(2) or ''
                            break
                    if not page:               # fallback: any "<this year>[:] page" in payload
                        pm = re.search(re.escape(yl[:4]) + r'[a-z]?\s*:?\s+(\d+)\s*(\([^)]+\))?',
                                       payload)
                        if pm:
                            page = pm.group(1)
                            qualifier = pm.group(2) or ''
                    # does AntCat already have a line of THIS type for this name? If not, a
                    # script must CREATE the whole history item ("Status as species: {ref
                    # N}: p.") rather than append the token to an existing line.
                    ac_has_line = 'yes' if label.split(' (')[0].lower() in me['text'].lower() \
                                  else 'no'
                    rows.append(dict(newest=yr, genus=b['genus'], epithet=b['epithet'],
                                     antcat_id=me['antcat_id'], line_type=label,
                                     antcat_has_line=ac_has_line,
                                     added_citation=D.first_author_cite(payload, yl),
                                     page=page, qualifier=qualifier,
                                     bolton_line=raw.strip()))

    rows.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))
    out = os.path.join(out_dir, 'status_refs_to_check.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['newest', 'genus', 'epithet', 'antcat_id',
                                          'line_type', 'antcat_has_line', 'added_citation',
                                          'page', 'qualifier', 'bolton_line'],
                           lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

    # PAPER-LEVEL SUMMARY: the missing citations cluster hard onto a few big faunistic
    # papers (a regional catalogue cited on hundreds of species). Reviewing 168 papers
    # -- "should AntCat ingest this one, and on how many species" -- is the real task,
    # not eyeballing 2,000 rows. This is the primary deliverable.
    by_paper = defaultdict(list)
    for r in rows:
        m = re.match(r'([A-Za-z\u00C0-\u024F&.\- ]+?)(?: et al\.|,)?\s*(\d{4})',
                     r['added_citation'])
        pk = f"{m.group(1).strip()} {m.group(2)}" if m else r['added_citation']
        by_paper[pk].append(r)
    summary = sorted(([pk, len(rs), min(x['newest'] for x in rs),
                       ', '.join(sorted({f"{x['genus']} {x['epithet']}" for x in rs})[:5])]
                      for pk, rs in by_paper.items()),
                     key=lambda s: -s[1])
    sout = os.path.join(out_dir, 'status_refs_by_paper.csv')
    with open(sout, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['paper', 'species_count', 'year', 'example_species'])
        w.writerows(summary)

    print(f'lines scanned:                 {n_lines}')
    print(f'recent (>= {recent_from}) citations on them: {n_cite}')
    print(f'  already in AntCat:           {n_present}')
    print(f'  MISSING from AntCat:         {n_missing}   -> {out}')
    print(f'  names affected:              {len(names_with_gaps)}')
    print(f'  distinct papers:             {len(by_paper)}   -> {sout}')
    print()
    print(f'  missing by line type:')
    for lt, c in sorted(by_linetype.items(), key=lambda x: -x[1]):
        print(f'     {c:5}  {lt}')
    print()
    print(f'  top papers driving the gap:')
    for pk, cnt, yr, ex in summary[:8]:
        print(f'     {cnt:4}  {pk}')
    return


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--bolton-dir', required=True)
    ap.add_argument('--worldants', required=True)
    ap.add_argument('--out-dir', default='status_out')
    ap.add_argument('--recent-from', type=int, default=2015)
    ap.add_argument('--only-status', action='store_true',
                    help='scan only "Status as species" lines (default: all citation-bearing types)')
    a = ap.parse_args()
    run(a.bolton_dir, a.worldants, a.out_dir, a.recent_from, a.only_status)
