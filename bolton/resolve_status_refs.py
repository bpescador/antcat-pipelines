#!/usr/bin/env python3
"""
resolve_status_refs.py -- EXPERIMENTAL. Resolve each missing Status-as-species
citation to an AntCat REFERENCE ID, producing upload-ready "{ref NNNNN}: page" tokens.

The resolution chain (Brian's method):
  1. Bolton's citation shorthand gives first-author + year ("Hamer et al., 2025").
  2. Bolton's REFERENCES section (bolton_references.csv) has the full author list AND
     title for that entry -- so "Hamer et al. 2025" expands to the specific paper.
  3. Match the full author list (accent-folded) to AntCat's reference table -> the id.
  4. When one author has several papers that year, disambiguate by title: the species'
     genus usually appears in the describing paper's title. What's left (a faunistic
     checklist covering many genera) is flagged for a one-glance human pick.

AntCat stores the line as editable "{ref N}: page" markup, so the output token drops
straight in. NOTHING here writes to AntCat.
"""
import csv, sys, re, unicodedata, os, argparse
from collections import defaultdict

csv.field_size_limit(sys.maxsize)



def _fold(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c))


def full_author_key(s):
    a = re.sub(r'\([^)]*\)', ' ', _fold(s))
    a = re.sub(r'\b[A-Z]\.', '', a)
    return re.sub(r'[^a-z]', '', a.lower())


def first_author_key(s):
    m = re.match(r"([A-Za-z'\-]+)", _fold(s).strip())
    return re.sub(r'[^a-z]', '', m.group(1).lower()) if m else ''


def y4(s):
    m = re.search(r'(1[6789]\d\d|20\d\d)', s or '')
    return m.group(1) if m else ''


def run(status_csv, refs_csv, bolton_refs_csv, out_dir='.'):
    os.makedirs(out_dir, exist_ok=True)

    # AntCat: full-author+year -> [ref rows]
    ac_by = defaultdict(list)
    for r in csv.DictReader(open(refs_csv, encoding='utf-8')):
        yr = y4(r['year'] or r['citation_year'])
        if yr:
            ac_by[(full_author_key(r['authors']), yr)].append(r)

    # Bolton refs: first-author+year -> [full entries]
    bo_by_fa = defaultdict(list)
    for r in csv.DictReader(open(bolton_refs_csv, encoding='utf-8')):
        bo_by_fa[(first_author_key(r['author']), r['year'])].append(r)

    rows = list(csv.DictReader(open(status_csv, encoding='utf-8')))
    resolved, needs_pick_rows = [], []
    pick_papers = {}

    for x in rows:
        m = re.match(r"([A-Za-z\u00C0-\u024F'\-]+).*?(\d{4})", x['added_citation'])
        if not m:
            continue
        fa, yr = first_author_key(m.group(1)), m.group(2)
        page = x.get('page', '').strip()
        qual = x.get('qualifier', '').strip()
        if not page:                          # fallback for older status files without the column
            pm = re.search(re.escape(yr) + r'[a-z]?\s*:?\s*(\d+)', x.get('bolton_line', ''))
            if pm:
                page = pm.group(1)

        # candidate AntCat ids via Bolton's full-author entries
        bo_entries = bo_by_fa.get((fa, yr), [])
        cand_ids = []
        for b in bo_entries:
            for h in ac_by.get((full_author_key(b['author']), yr), []):
                cand_ids.append((h['id'], b.get('reference_text', ''), h['title']))
        # also try direct antcat first-author match if Bolton has no entry
        if not cand_ids:
            for (ak, ay), hs in ac_by.items():
                if ay == yr and ak.startswith(fa):
                    for h in hs:
                        cand_ids.append((h['id'], '', h['title']))

        uniq = list({c[0]: c for c in cand_ids}.values())

        def emit(rid):
            cite = f'{{ref {rid}}}: {page}' + (f' {qual}' if qual else '') if page else f'{{ref {rid}}}'
            has_line = x.get('antcat_has_line', 'yes')
            if has_line == 'no':
                # no existing line of this type -> the token is a WHOLE new history item.
                # If Bolton's line has other (usually pre-2015) citations too, creating the
                # line from just this one would be incomplete -- flag it for manual entry
                # with the full Bolton line, rather than emit a partial history item.
                other_cites = len(re.findall(r'\d{4}[a-z]?\s*:', x.get('bolton_line', ''))) > 1
                if other_cites:
                    action = 'create_line_manual'
                    token = f"{x['line_type']}: {cite}.  [INCOMPLETE -- Bolton line also has "
                    token += f"earlier citations; build full line from: {x.get('bolton_line','')}]"
                else:
                    action = 'create_line'
                    token = f"{x['line_type']}: {cite}."
            else:
                action = 'append'
                token = cite
            resolved.append(dict(antcat_id=x['antcat_id'], genus=x['genus'],
                                 epithet=x['epithet'], line_type=x['line_type'],
                                 action=action, paper=x['added_citation'], reference_id=rid,
                                 token=token, page=page, qualifier=qual))

        if len(uniq) == 1:
            emit(uniq[0][0])
        elif len(uniq) > 1:
            picked = None
            # (a) partial author signature: Bolton often names the first 1-2 co-authors
            # before "et al." ("Hamer, Lee, Wang, et al."). Match those against each
            # candidate's author list -- if exactly one candidate contains all named
            # co-authors, that's the paper. This is matching, not guessing.
            sig = re.search(re.escape(m.group(1)) + r'((?:,\s*[A-Z][A-Za-z\u00C0-\u024F\'\-]+)*)'
                            r'\s*,?\s*et\s+al', x['bolton_line'])
            named = []
            if sig and sig.group(1):
                named = [full_author_key(s) for s in re.split(r',\s*', sig.group(1)) if s.strip()]
            if named:
                matches = [c for c in uniq
                           if all(nm in full_author_key(c[1] or c[2]) for nm in named)]
                if len({c[0] for c in matches}) == 1:
                    picked = matches[0][0]
            # (b) genus-in-title fallback
            if picked is None:
                g = x['genus'].lower()
                gh = [c for c in uniq if g in (c[1] + ' ' + c[2]).lower()]
                if len({c[0] for c in gh}) == 1:
                    picked = gh[0][0]
            if picked is not None:
                emit(picked)
            else:
                needs_pick_rows.append(x)
                key = (fa, yr)
                if key not in pick_papers:
                    pick_papers[key] = dict(paper=x['added_citation'], rows=0,
                                            candidates='; '.join(
                                                f"{c[0]}={c[2][:45]}" for c in uniq[:6]))
                pick_papers[key]['rows'] += 1
        else:
            needs_pick_rows.append(x)
            key = (fa, yr)
            if key not in pick_papers:
                pick_papers[key] = dict(paper=x['added_citation'], rows=0,
                                        candidates='(no author-string match in AntCat -- '
                                        'Bolton may cite this by a different first author, '
                                        'or spell the author differently; pick the id by hand)')
            pick_papers[key]['rows'] += 1

    resolved.sort(key=lambda r: (r['paper'], r['genus'], r['epithet']))
    o1 = os.path.join(out_dir, 'status_refs_upload_ready.csv')
    with open(o1, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['antcat_id', 'genus', 'epithet', 'line_type',
                                          'action', 'paper', 'reference_id', 'token', 'page', 'qualifier'],
                           lineterminator='\n')
        w.writeheader(); w.writerows(resolved)

    picks = sorted(pick_papers.values(), key=lambda p: -p['rows'])
    o2 = os.path.join(out_dir, 'status_refs_needs_pick.csv')
    with open(o2, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['paper', 'rows', 'candidates'],
                           lineterminator='\n')
        w.writeheader(); w.writerows(picks)

    print(f'missing citations:              {len(rows)}')
    print(f'  auto-resolved to a ref id:    {len(resolved)} ({100*len(resolved)//len(rows)}%)   -> {o1}')
    print(f'  need a one-glance human pick: {len(needs_pick_rows)} rows / {len(picks)} papers   -> {o2}')
    print()
    for p in picks:
        print(f'   {p["rows"]:4} rows  {p["paper"]:30}  {p["candidates"][:70]}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', required=True)
    ap.add_argument('--refs', required=True, help='antcat references CSV')
    ap.add_argument('--bolton-refs', required=True, help='bolton_out/bolton_references.csv')
    ap.add_argument('--out-dir', default='.')
    a = ap.parse_args()
    run(a.status, a.refs, a.bolton_refs, a.out_dir)
