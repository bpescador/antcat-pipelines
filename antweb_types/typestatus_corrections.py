#!/usr/bin/env python3
"""
typestatus_corrections.py -- turn the reviewed AntWeb vs AntCat type-status rows into
correction lists for whoever holds each AntWeb record's source data. READ ONLY.

  python3 antweb_types/typestatus_corrections.py --merged typestatus_merged.csv \
      --returned WEEK_RETURNED.xlsx --protonyms PROTONYMS.jsonl --names antcat_names.tsv \
      --antweb ANTWEB.tsv --out OUTDIR [--stamp 20261111]

AntWeb takes each specimen record from one source: TaxonWorks (file specimenTW1.txt, access
group 1, reloaded nightly) or a curator's own upload (e.g. group 76, MZSP). A fix sticks only
at the source, so the rows are split by it:
  OUTDIR/antcat__tw_typestatus_corrections_STAMP.csv      records that come from TaxonWorks
  OUTDIR/antcat__group76_typestatus_corrections_STAMP.csv records from AntWeb upload group 76
  OUTDIR/antcat__other_typestatus_corrections_STAMP.csv   records from any other upload group
  OUTDIR/antcat__typestatus_not_listed_STAMP.csv          open rows left out, with the reason

A row is listed when (in this order):
  reviewed   the reviewer answered "AntCat" (week workbook, or his earlier sheet): the type
             belongs to the protonym AntCat lists it under.
  rule       not reviewed, but one of the two patterns whose sample he confirmed (week 3,
             2026-11-10):
               syntypes in AntCat (sample 10 of 10): AntWeb says paratype; AntCat records
                 syntypes and no holotype, with this code in the primary field -> syntype;
               lectotype designated (sample 7 of 10, 3 unsure whether the specimen was the
                 lectotype): only rows where AntCat's primary specimen line names the
                 lectotype by ANOTHER code -> paralectotype.
Left out: answers "AntWeb" (AntCat is wrong; fixed in AntCat), "Unsure", blank, and every row
not yet reviewed that fits neither rule.

The correct name is always the AntCat protonym holding the code (original combination), with
the key the TaxonWorks name load used (protonym_key, antcat_id in antcat_names.tsv). The
correct type kind: from the rule for rank rows; AntWeb's own kind for misplacements (only the
name is wrong there).
"""
import argparse, csv, json, os, re, unicodedata
from collections import Counter, defaultdict
import openpyxl

csv.field_size_limit(10**9)
SING = {'holotypes': 'holotype', 'paratypes': 'paratype', 'syntypes': 'syntype', 'lectotypes': 'lectotype',
        'paralectotypes': 'paralectotype', 'neotypes': 'neotype', 'cotype': 'syntype', 'cotypes': 'syntype'}


def nc(s): return re.sub(r'[^A-Z0-9]', '', unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper())


def lines(path):
    with open(path, 'rb') as f:
        for b in f:
            try: yield b.decode('utf-8')
            except UnicodeDecodeError: yield b.decode('latin-1')


def kind_of(ts):
    k = (ts or '').strip().split(' ')[0].lower()
    return SING.get(k, k)


def main():
    ap = argparse.ArgumentParser()
    for k in ('merged', 'returned', 'protonyms', 'names', 'antweb', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--stamp', default='20261111')
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
            AW.setdefault(nc(G(row, 'code')), dict(
                ts=G(row, 'type_status'), owner=G(row, 'ownedby'), group=G(row, 'access_group'),
                source='TaxonWorks' if 'TW' in f else f"AntWeb upload group {G(row, 'access_group')}"))

    # reviewer's answers in the returned week workbook (tabs with a "Correct?" column)
    REV = {}
    wb = openpyxl.load_workbook(a.returned, data_only=True)
    for ws in wb.worksheets:
        hr = next((i for i in range(1, 16) if ws.cell(row=i, column=1).value in ('Group / code', 'Group')), None)
        if not hr:
            continue
        hdr = [ws.cell(row=hr, column=c).value for c in range(1, ws.max_column + 1)]
        if 'Correct?' not in hdr or 'Codes (AntWeb)' not in hdr:
            continue
        ia, inote, icodes = hdr.index('Correct?'), len(hdr) - 1, hdr.index('Codes (AntWeb)')
        for i in range(hr + 1, ws.max_row + 1):
            vals = [ws.cell(row=i, column=c).value for c in range(1, ws.max_column + 1)]
            if not vals[0]:
                continue
            for code in str(vals[icodes] or '').split(','):
                if code.strip():
                    REV[nc(code)] = dict(answer=(vals[ia] or '').strip(), note=(vals[inote] or '').strip(), where=f"{ws.title} {vals[0]}")

    rows = [d for d in csv.DictReader(open(a.merged, encoding='utf-8')) if d['status'] != 'resolved']
    out, skip = defaultdict(list), []
    seen = {}
    for d in rows:
        code = nc(d['code']); aw = AW.get(code, {}); rev = REV.get(code)
        holders = [h for h in d['holding_id'].split(';') if h]
        basis = why_not = ''
        if rev:
            if rev['answer'] == 'AntCat': basis = f"reviewed ({rev['where']})"
            else: why_not = f"reviewed: {rev['answer'] or 'no answer'} ({rev['where']})"
        elif d['answer']:
            if d['answer'] == 'AntCat': basis = 'reviewed (earlier sheet)'
            else: why_not = f"reviewed on the earlier sheet: {d['answer']}"
        elif d['pattern'] == 'syntypes in AntCat':
            basis = 'rule: syntypes in AntCat'
        elif d['pattern'] == 'lectotype designated':
            pt = P.get(holders[0], {}).get('primary_type_taxt') or '' if holders else ''
            m = re.search(r'Primary type specimens?:\s*([^.]*)', pt)
            codes = [nc(x) for x in re.findall(r'[A-Z]{2,}[A-Z0-9\-]*\d{3,}[A-Z0-9\-]*', (m.group(1) if m else '').upper())]
            if codes and code not in codes: basis = 'rule: paralectotype (lectotype coded in AntCat)'
            else: why_not = 'not reviewed: lectotype not coded in AntCat (week 4, by paper)'
        else:
            why_not = 'not reviewed yet (week 4)'
        if not why_not and len(holders) != 1:
            why_not = f"AntCat lists the code under {len(holders)} protonyms"
        if not why_not and not aw:
            why_not = 'not a type specimen in this AntWeb dump'
        if why_not:
            skip.append(dict(code=d['code'].upper(), type=d['type'], antweb_type_status_now=aw.get('ts', d['antweb_typestatus']),
                             antcat_holding=d['antcat_holding'], source=aw.get('source', ''), reason=why_not,
                             note=(rev or {}).get('note', '') or d['notes']))
            continue
        p = P[holders[0]]
        name = p['name']; words = name.replace('(', ' ( ').split()
        genus = words[0]; epithet = re.sub(r'[^a-z\-]', '', words[-1].lower())
        key = f"{genus.lower()}|{epithet}|{p['year']}"
        tw = NAMES.get(key, {})
        kind = ('paralectotype' if basis.startswith('rule: paralectotype') else
                'syntype' if basis == 'rule: syntypes in AntCat' else
                'paralectotype' if d['type'] == 'rank' and d['pattern'] == 'lectotype designated' else
                'syntype' if d['type'] == 'rank' and d['pattern'] == 'syntypes in AntCat' else kind_of(aw['ts']))
        auth = re.sub(r'[()]', '', tw.get('authorship', '')) or f"{p['author'].split(',')[0]}, {p['year']}"
        rec = dict(catalog_number=d['code'].upper(), antweb_type_status_now=aw['ts'],
                   correct_type_kind=kind, correct_protonym=name, correct_authorship=auth,
                   antweb_type_status_should=f"{kind} of {name} {auth}",
                   antcat_protonym_id=holders[0], antcat_protonym_url=f"https://antcat.org/protonyms/{holders[0]}",
                   tw_protonym_key=key if tw else '', tw_antcat_id=tw.get('antcat_id', ''), tw_scientific_name=tw.get('scientific_name', ''),
                   mismatch=d['type'], basis=basis, owner=aw['owner'], antweb_source=aw['source'],
                   antweb_url=f"https://www.antweb.org/specimen.do?name={d['code'].lower()}",
                   antcat_text=d['antcat_sentence'], reviewer_note=(rev or {}).get('note', '') or d['notes'])
        if code in seen:   # the same specimen in a rank and a misplacement row: must agree
            prev = seen[code]
            if (prev['correct_type_kind'], prev['antcat_protonym_id']) != (kind, holders[0]):
                prev['basis'] += f"; CONFLICT with the {d['type']} row ({kind}, {holders[0]}): check by hand"
            continue
        seen[code] = rec
        grp = 'tw' if aw['source'] == 'TaxonWorks' else ('group76' if aw['group'] == '76' else 'other')
        out[grp].append(rec)

    # AntCat writes some series as a range ("MZSP0082254 to MZSP0082260"). Only the end codes
    # are in its text, so the matcher sees only those; the codes between, when AntWeb gives
    # them the same (wrong) type status, take the same correction (Bradley, week 3: M023,
    # M024, M043).
    for grp in list(out):
        for rec in list(out[grp]):
            for m in re.finditer(r'([A-Z]+)(\d+)\s+to\s+(?:[A-Z]+)?(\d+)', rec['antcat_text']):
                pre, lo, hi, width = m.group(1), int(m.group(2)), int(m.group(3)), len(m.group(2))
                if not 0 < hi - lo <= 50:
                    continue
                for n in range(lo + 1, hi):
                    c = nc(f"{pre}{n:0{width}d}"); aw = AW.get(c)
                    if c in seen or not aw or aw['ts'].strip().lower() != rec['antweb_type_status_now'].strip().lower():
                        continue
                    new = dict(rec, catalog_number=c, antweb_url=f"https://www.antweb.org/specimen.do?name={c.lower()}",
                               basis=f"{rec['basis']}; inside the AntCat range {m.group(0)}", owner=aw['owner'],
                               antweb_source=aw['source'])
                    seen[c] = new; out[grp].append(new)

    cols = ['catalog_number', 'antweb_type_status_now', 'correct_type_kind', 'correct_protonym', 'correct_authorship',
            'antweb_type_status_should', 'antcat_protonym_id', 'antcat_protonym_url', 'tw_protonym_key', 'tw_antcat_id',
            'tw_scientific_name', 'mismatch', 'basis', 'owner', 'antweb_source', 'antweb_url', 'antcat_text', 'reviewer_note']
    for grp, fn in (('tw', 'tw'), ('group76', 'group76'), ('other', 'other')):
        rs = sorted(out[grp], key=lambda x: (not x['basis'].startswith('reviewed'), x['correct_protonym'], x['catalog_number']))
        with open(f"{a.out}/antcat__{fn}_typestatus_corrections_{a.stamp}.csv", 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rs)
        print(f"{fn}: {len(rs)} rows", dict(Counter(x['basis'].split(' (')[0] for x in rs)),
              f"| no TW name key: {sum(1 for x in rs if not x['tw_antcat_id'])}")
    sc = ['code', 'type', 'antweb_type_status_now', 'antcat_holding', 'source', 'reason', 'note']
    with open(f"{a.out}/antcat__typestatus_not_listed_{a.stamp}.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=sc); w.writeheader(); w.writerows(skip)
    print(f"not listed: {len(skip)}", dict(Counter(re.sub(r' \(.*', '', x['reason']) for x in skip)))


if __name__ == '__main__':
    main()
