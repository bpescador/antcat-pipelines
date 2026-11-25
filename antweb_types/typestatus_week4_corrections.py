#!/usr/bin/env python3
"""
typestatus_week4_corrections.py -- correction lists from Bradley's returned week 4 workbook
(AntWeb vs AntCat type status). READ ONLY. Same output columns as typestatus_corrections.py
(week 3), split the same way by where AntWeb takes each record from.

  python3 antweb_types/typestatus_week4_corrections.py --merged typestatus_merged.csv \
      --returned WEEK4_RETURNED.xlsx --protonyms PROTONYMS.jsonl --names antcat_names.tsv \
      --antweb ANTWEB.tsv --out OUTDIR --stamp 20261125 [--sent EARLIER.csv ...]

Week 4 has three kinds of tab:
  Day 1  misplacements ("Group", "Codes (AntWeb)"): answer "AntCat" -> the name is AntCat's
         protonym holding the code; the kind of type stays as AntWeb has it.
  Day 2  lectotype rows ("Code", "AntCat protonym"): answer "Paralectotype" -> paralectotype of
         that protonym.
  Day 3, Day 4  rank conflicts ("First code", "Codes (AntWeb status)"): answer "AntCat" -> the
         kind AntCat records for that code: the kind of its primary type material when the code
         is in the primary specimen line, of its secondary material when it is in the secondary
         line. A code AntCat does not list, or material AntCat does not name a kind for, is left
         out with the reason, for a look by hand.
Answers "AntWeb" (AntCat is wrong, to fix in AntCat) and "Unsure" go to the not-listed file.
Codes already in a file given with --sent are left out (already corrected).
"""
import argparse, csv, json, os, re
from collections import Counter, defaultdict
import openpyxl
from typestatus_corrections import nc, lines, kind_of

csv.field_size_limit(10**9)
CODE = re.compile(r'[A-Z]{2,}[A-Z0-9\-]*\d{3,}[A-Z0-9\-]*')
PRIMARY = ('holotype', 'lectotype', 'neotype', 'syntype')
SECONDARY = ('paralectotype', 'paratype')


def codes_in(text):
    """Codes in an AntCat type text, with 'X to Y' ranges expanded (up to 50)."""
    t = (text or '').upper(); out = set(nc(c) for c in CODE.findall(t))
    for m in re.finditer(r'([A-Z]+)(\d+)\s+TO\s+(?:[A-Z]+)?(\d+)', t):
        lo, hi, w = int(m.group(2)), int(m.group(3)), len(m.group(2))
        if 0 < hi - lo <= 50:
            out.update(nc(f"{m.group(1)}{n:0{w}d}") for n in range(lo, hi + 1))
    return out


def stated_kind(text, kinds):
    """The one kind named in the 'type material:' statement (its first sentence only: later
    sentences say things like 'no lectotype designated'). '' when none or more than one."""
    m = re.search(r'type material:\s*([^.]*)', text or '', re.I)
    t = (m.group(1) if m else '').lower()
    found = [k for k in kinds if re.search(r'\b' + k + r's?\b', t)]
    return found[0] if len(found) == 1 else ''


def main():
    ap = argparse.ArgumentParser()
    for k in ('merged', 'returned', 'protonyms', 'names', 'antweb', 'out', 'stamp'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--sent', nargs='*', default=[])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    P = {}
    for line in open(a.protonyms, encoding='utf-8'):
        if line.strip():
            p = json.loads(line); P[str(p['protonym_id'])] = p
    NAMES = {d['protonym_key']: d for d in csv.DictReader(open(a.names, encoding='utf-8'), delimiter='\t')}
    AW = {}
    r = csv.reader(lines(a.antweb), delimiter='\t'); H = {h: i for i, h in enumerate(next(r))}
    G = lambda row, k: row[H[k]] if (k in H and len(row) > H[k]) else ''
    for row in r:
        if G(row, 'type_status'):
            f = G(row, 'backup_file_name')
            AW.setdefault(nc(G(row, 'code')), dict(raw=G(row, 'code').upper(), ts=G(row, 'type_status'), owner=G(row, 'ownedby'), group=G(row, 'access_group'),
                          source='TaxonWorks' if 'TW' in f else f"AntWeb upload group {G(row, 'access_group')}"))
    MERGED = defaultdict(list)
    for d in csv.DictReader(open(a.merged, encoding='utf-8')):
        MERGED[nc(d['code'])].append(d)
    SENT = set()
    for fn in a.sent:
        SENT.update(nc(d['catalog_number']) for d in csv.DictReader(open(fn, encoding='utf-8')))

    todo, skip = [], []   # todo: (code, protonym id, kind or None, mismatch, basis, note)
    wb = openpyxl.load_workbook(a.returned, data_only=True)
    for ws in wb.worksheets:
        rows = [[('' if c is None else str(c).strip()) for c in row] for row in ws.iter_rows(values_only=True)]
        hi = next((i for i, row in enumerate(rows) if 'Correct?' in row), None)
        if hi is None:
            continue
        h = rows[hi]; ia = h.index('Correct?'); note_i = len(h) - 1
        for row in rows[hi + 1:]:
            if not row or not row[0]:
                continue
            ans, note, where = row[ia], row[note_i], f"week 4 {ws.title}"
            if 'Codes (AntWeb)' in h:                       # Day 1, misplacements
                for c in row[h.index('Codes (AntWeb)')].split(','):
                    code = nc(c)
                    if not code:
                        continue
                    hold = [x for d in MERGED.get(code, []) for x in d['holding_id'].split(';') if x]
                    if ans != 'AntCat' or len(set(hold)) != 1:
                        skip.append((code, where, f"answer {ans or 'none'}" if ans != 'AntCat' else f"AntCat lists it under {len(set(hold))} protonyms", note)); continue
                    todo.append((code, hold[0], None, 'misplacement', f"reviewed ({where} {row[0]})", note))
            elif 'Code' in h and 'AntCat protonym' in h:    # Day 2, lectotypes
                code = nc(row[h.index('Code')]); pid = re.search(r'\((\d+)\)\s*$', row[h.index('AntCat protonym')])
                if ans != 'Paralectotype' or not pid:
                    skip.append((code, where, f"answer {ans or 'none'}", note)); continue
                todo.append((code, pid.group(1), 'paralectotype', 'rank', f"reviewed ({where}; lectotype designated by {row[h.index('Designated by')]})", note))
            elif 'Codes (AntWeb status)' in h:              # Days 3 and 4, rank conflicts
                pid = re.search(r'\((\d+)\)\s*$', row[h.index('AntCat protonym')])
                for c in re.findall(r'([A-Za-z0-9\-]+)\s*\(', row[h.index('Codes (AntWeb status)')]):
                    code = nc(c)
                    if ans != 'AntCat' or not pid:
                        skip.append((code, where, f"answer {ans or 'none'}", note)); continue
                    p = P.get(pid.group(1), {})
                    pt, st = p.get('primary_type_taxt') or '', p.get('secondary_type_taxt') or ''
                    if code in codes_in(pt): kind = stated_kind(pt, PRIMARY)
                    elif code in codes_in(st): kind = stated_kind(st, SECONDARY)
                    else: kind = ''
                    if not kind:
                        skip.append((code, where, 'answer AntCat, but AntCat does not list the code under one stated kind: by hand', note)); continue
                    todo.append((code, pid.group(1), kind, 'rank', f"reviewed ({where})", note))

    out, seen = defaultdict(list), set()
    for code, pid, kind, mism, basis, note in todo:
        aw = AW.get(code)
        if code in SENT:
            skip.append((code, basis, 'already in an earlier corrections file', note)); continue
        if not aw:
            skip.append((code, basis, 'not a type specimen in this AntWeb dump', note)); continue
        if code in seen:
            continue
        seen.add(code)
        p = P[pid]; name = p['name']; words = name.replace('(', ' ( ').split()
        key = f"{words[0].lower()}|{re.sub(r'[^a-z-]', '', words[-1].lower())}|{p['year']}"
        tw = NAMES.get(key, {}); kind = kind or kind_of(aw['ts'])
        auth = re.sub(r'<[^>]+>|[()]', '', tw.get('authorship', '')) or f"{p['author'].split(',')[0]}, {p['year']}"
        should = f"{kind} of {name} {auth}"
        if should.strip().lower() == aw['ts'].strip().lower():
            skip.append((code, basis, 'AntWeb already shows this type status', note)); continue
        rec = dict(catalog_number=aw['raw'], antweb_type_status_now=aw['ts'], correct_type_kind=kind, correct_protonym=name,
                   correct_authorship=auth, antweb_type_status_should=should, antcat_protonym_id=pid,
                   antcat_protonym_url=f"https://antcat.org/protonyms/{pid}", tw_protonym_key=key if tw else '',
                   tw_antcat_id=tw.get('antcat_id', ''), tw_scientific_name=tw.get('scientific_name', ''), mismatch=mism,
                   basis=basis, owner=aw['owner'], antweb_source=aw['source'],
                   antweb_url=f"https://www.antweb.org/specimen.do?name={code.lower()}",
                   antcat_text=re.sub(r'\s+', ' ', ((p.get('primary_type_taxt') or '') + ' ' + (p.get('secondary_type_taxt') or '')))[:400],
                   reviewer_note=note)
        out['tw' if aw['source'] == 'TaxonWorks' else ('group76' if aw['group'] == '76' else 'other')].append(rec)

    cols = ['catalog_number', 'antweb_type_status_now', 'correct_type_kind', 'correct_protonym', 'correct_authorship',
            'antweb_type_status_should', 'antcat_protonym_id', 'antcat_protonym_url', 'tw_protonym_key', 'tw_antcat_id',
            'tw_scientific_name', 'mismatch', 'basis', 'owner', 'antweb_source', 'antweb_url', 'antcat_text', 'reviewer_note']
    for grp in ('tw', 'group76', 'other'):
        rs = sorted(out[grp], key=lambda x: (x['mismatch'], x['correct_protonym'], x['catalog_number']))
        with open(f"{a.out}/antcat__{grp}_typestatus_corrections_{a.stamp}.csv", 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rs)
        print(f"{grp}: {len(rs)} rows", dict(Counter((x['mismatch'], x['correct_type_kind']) for x in rs)),
              f"| no TW name key: {sum(1 for x in rs if not x['tw_antcat_id'])}")
    with open(f"{a.out}/antcat__typestatus_not_listed_{a.stamp}.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['code', 'where', 'reason', 'note']); w.writerows(skip)
    print(f"not listed: {len(skip)}", dict(Counter(x[2] for x in skip)))


if __name__ == '__main__':
    main()
