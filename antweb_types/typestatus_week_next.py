#!/usr/bin/env python3
"""
typestatus_week_next.py -- build the reviewer's next type-status week from what is still open
after a returned week and the correction files. READ ONLY. One CSV per day plus week.json for
bolton/review_week.py. First used for Bradley's week 4 (from 2026-11-16).

  python3 antweb_types/typestatus_week_next.py --merged typestatus_merged.csv \
      --notlisted antcat__typestatus_not_listed_STAMP.csv --corrections CORR_DIR \
      --returned WEEK_RETURNED.xlsx --protonyms PROTONYMS.jsonl --references antcat_references.csv \
      --out WEEKDIR [--rank-codes 30] [--title "..."]
  python3 bolton/review_week.py --spec WEEKDIR/week.json --xlsx WEEK.xlsx

Days:
  Day 1 misplacements  open misplacement groups (one answer per group), plus any question
                       carried over; earlier "Unsure" misplacements come back here
  Day 2 lectotypes     rank rows where AntCat records a lectotype designation but does not
                       name the lectotype by its code, plus earlier "Unsure" lectotype rows;
                       sorted by the designating paper, so one paper answers several rows
  Day 3, Day 4         rank conflicts (AntWeb primary vs AntCat secondary or the reverse), one
                       row per protonym, whole protonyms up to --rank-codes codes; the rest wait
  All rows             the whole list with every answer so far and what was done with it
Minutes follow his week 3 times: 8 per misplacement group, 10 per paper plus 2 per further row,
8.5 per rank-conflict code.
"""
import argparse, csv, glob, json, os, re, unicodedata
from collections import defaultdict, OrderedDict
import openpyxl

csv.field_size_limit(10**9)
ANS = ['AntCat', 'AntWeb', 'AntWeb (partially)', 'Unsure']


def nc(s): return re.sub(r'[^A-Z0-9]', '', unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper())
def rd(p): return list(csv.DictReader(open(p, encoding='utf-8')))
def short(t, n=500): t = (t or '').strip(); return t if len(t) <= n else t[:n - 1] + '…'


def wr(p, rows, cols):
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    for k in ('merged', 'notlisted', 'corrections', 'returned', 'protonyms', 'references', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--rank-codes', type=int, default=30)
    ap.add_argument('--title', default='AntWeb vs AntCat type status, week 4')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    P = {}
    for line in open(a.protonyms, encoding='utf-8'):
        if line.strip():
            p = json.loads(line); P[str(p['protonym_id'])] = p
    REF = {d['id']: d for d in csv.DictReader(open(a.references, encoding='utf-8'))}
    M = rd(a.merged); MB = {nc(d['code']): d for d in M}
    NL = rd(a.notlisted)
    done = {}
    for f in glob.glob(os.path.join(a.corrections, 'antcat__*_typestatus_corrections_*.csv')):
        for d in rd(f):
            done[nc(d['catalog_number'])] = d

    def ref_short(rid):
        r = REF.get(rid)
        if not r: return f'ref {rid}'
        au = re.split(r';|&', r['authors'] or '')[0].split(',')[0].strip()
        more = ' et al.' if (r['authors'] or '').count(';') >= 2 else (' & ' + r['authors'].split(';')[1].split(',')[0].strip() if ';' in (r['authors'] or '') else '')
        return f"{au}{more}, {r['citation_year'] or r['year']}"

    def resolve(t):   # {ref N} -> short citation, for reading
        return re.sub(r'\{ref (\d+)\}', lambda m: ref_short(m.group(1)), t or '')

    # ---- Day 1: misplacement groups not yet reviewed, and earlier Unsure misplacements ----
    mis = [d for d in NL if d['type'] == 'misplacement' and (d['reason'].startswith('not reviewed yet') or 'Unsure' in d['reason'])]
    groups = OrderedDict()
    for d in sorted(mis, key=lambda x: (MB[nc(x['code'])]['antweb_names'], x['code'])):
        m = MB[nc(d['code'])]
        groups.setdefault(m['group'] or d['code'], []).append((d, m))
    d1 = [dict(ref='M016', kind='question from week 3', codes='FOCOL2754, FOCOL2755', n=2,
               antweb_says='syntype of Myrmecocystus cursor tancrei Forel, 1901', antcat_has='Formica aenescens (AntCat)',
               antcat_sentence='', antweb_named='Myrmecocystus cursor tancrei',
               question='Your answer was "AntWeb", but your note says "They are correctly syntypes of Formica aenescens". Which is right?',
               earlier='week 3, Day 4', url='https://www.antweb.org/specimen.do?name=focol2754', min=3)]
    for g, rows in groups.items():
        d, m = rows[0]
        d1.append(dict(ref=g, kind='misplacement' + (' (unsure before)' if 'Unsure' in d['reason'] else ''),
                       codes=', '.join(x['code'] for x, _ in rows), n=len(rows), antweb_says=m['antweb_typestatus'],
                       antweb_det=m['antweb_det'], owner_country=f"{m['antweb_owner']} / {m['antweb_country']}",
                       source=d['source'], country_in=m['country_in'],
                       antcat_has=f"{m['antcat_holding']} ({m['holding_id']})", antcat_sentence=short(resolve(m['antcat_sentence']), 400),
                       antweb_named=f"{m['antweb_names']} ({m['named_id']})", named_text=short(resolve(m['named_primary']), 300),
                       earlier=short(d['note'], 200), url=m['antweb_url'], min=8))

    # ---- Day 2: lectotype rows by designating paper ----
    lec = [d for d in NL if d['type'] == 'rank' and ('lectotype not coded' in d['reason'] or 'Unsure' in d['reason'])]
    def paper(d):
        m = MB[nc(d['code'])]; pt = P.get(m['holding_id'].split(';')[0], {}).get('primary_type_taxt') or ''
        x = re.search(r'designation of \{ref (\d+)\}(?::\s*([^)]*))?', pt)
        return (ref_short(x.group(1)), x.group(1), (x.group(2) or '').strip()) if x else ('(no designation cited)', '', '')
    lec.sort(key=lambda d: (paper(d)[0], MB[nc(d['code'])]['antcat_holding'], d['code']))
    d2, seen_paper = [], set()
    for d in lec:
        m = MB[nc(d['code'])]; p = P.get(m['holding_id'].split(';')[0], {})
        ps, rid, pg = paper(d)
        first = rid not in seen_paper; seen_paper.add(rid)
        d2.append(dict(ref=d['code'], paper=f"{ps}: {pg}" if pg else ps, protonym=f"{m['antcat_holding']} ({m['holding_id']})",
                       antweb_says=m['antweb_typestatus'], owner=m['antweb_owner'], source=d['source'],
                       primary=short(resolve(p.get('primary_type_taxt')), 450), secondary=short(resolve(p.get('secondary_type_taxt')), 300),
                       earlier=short(d['note'], 200) if 'Unsure' in d['reason'] else '',
                       url=m['antweb_url'], min=10 if first else 2))

    # ---- Days 3 and 4: rank conflicts by protonym ----
    rk = [d for d in NL if d['type'] == 'rank' and d['reason'].startswith('not reviewed yet')]
    byp = OrderedDict()
    for d in sorted(rk, key=lambda x: (x['source'] != 'TaxonWorks', MB[nc(x['code'])]['antcat_holding'], x['code'])):
        byp.setdefault(MB[nc(d['code'])]['holding_id'], []).append(d)
    pick, left, n = [], [], 0
    for pid, rows in byp.items():
        (pick if n + len(rows) <= a.rank_codes or not pick else left).append((pid, rows))
        if pick and pick[-1][0] == pid: n += len(rows)
    def rrow(pid, rows):
        p = P.get(pid.split(';')[0], {})
        return dict(ref=rows[0]['code'], codes=', '.join(f"{x['code']} ({MB[nc(x['code'])]['antweb_typestatus'].split(' of ')[0]})" for x in rows),
                    n=len(rows), protonym=f"{MB[nc(rows[0]['code'])]['antcat_holding']} ({pid})",
                    antweb_says=MB[nc(rows[0]['code'])]['antweb_typestatus'], source=rows[0]['source'],
                    primary=short(resolve(p.get('primary_type_taxt')), 450), secondary=short(resolve(p.get('secondary_type_taxt')), 350),
                    url=MB[nc(rows[0]['code'])]['antweb_url'], min=round(8.5 * len(rows)))
    rr = [rrow(pid, rows) for pid, rows in pick]
    half, acc, d3, d4 = sum(r['min'] for r in rr) / 2, 0, [], []
    for r in rr:
        (d3 if acc < half else d4).append(r); acc += r['min']

    # ---- All rows: every answer so far ----
    REV = {}
    wb = openpyxl.load_workbook(a.returned, data_only=True)
    for ws in wb.worksheets:
        hr = next((i for i in range(1, 16) if ws.cell(row=i, column=1).value in ('Group / code', 'Group')), None)
        if not hr: continue
        hdr = [ws.cell(row=hr, column=c).value for c in range(1, ws.max_column + 1)]
        if 'Correct?' not in hdr: continue
        for i in range(hr + 1, ws.max_row + 1):
            vals = [ws.cell(row=i, column=c).value for c in range(1, ws.max_column + 1)]
            for code in str(vals[hdr.index('Codes (AntWeb)')] or '').split(','):
                if code.strip(): REV[nc(code)] = (vals[hdr.index('Correct?')] or '', vals[-1] or '')
    allr = []
    for d in M:
        c = nc(d['code']); ans, note = REV.get(c, (d['answer'], d['notes']))
        fix = done.get(c)
        here = {nc(x) for r in d1 + d2 + d3 + d4 for x in (r.get('codes', '') + ',' + r['ref']).replace('(', ',').split(',')}
        state = (d['resolved_how'] and f"resolved by 8 Nov: {d['resolved_how']}") or \
                (fix and (f"corrected in TaxonWorks 11 Nov" if fix['antweb_source'] == 'TaxonWorks' else f"correction sent to {fix['antweb_source']}")) or \
                ('in this week' if c in here else
                 'AntCat to be fixed (your answer: AntWeb)' if ans == 'AntWeb' else 'later')
        allr.append(dict(state=state, type=d['type'], code=d['code'].upper(), antweb_typestatus=d['antweb_typestatus'],
                         antcat_holding=d['antcat_holding'], answer=ans, notes=note, antweb_url=d['antweb_url']))
    allr.sort(key=lambda r: (r['state'].startswith('resolved'), r['state'], r['type'], r['code']))

    C1 = ['ref', 'kind', 'codes', 'n', 'antweb_says', 'antweb_det', 'owner_country', 'source', 'country_in', 'antcat_has',
          'antcat_sentence', 'antweb_named', 'named_text', 'question', 'earlier', 'url', 'min']
    C2 = ['ref', 'paper', 'protonym', 'antweb_says', 'owner', 'source', 'primary', 'secondary', 'earlier', 'url', 'min']
    C3 = ['ref', 'codes', 'n', 'protonym', 'antweb_says', 'source', 'primary', 'secondary', 'url', 'min']
    wr(f'{a.out}/day1.csv', d1, C1); wr(f'{a.out}/day2.csv', d2, C2)
    wr(f'{a.out}/day3.csv', d3, C3); wr(f'{a.out}/day4.csv', d4, C3)
    wr(f'{a.out}/all_rows.csv', allr, ['state', 'type', 'code', 'antweb_typestatus', 'antcat_holding', 'answer', 'notes', 'antweb_url'])

    n_left = sum(len(rows) for _, rows in left)
    ans = [['Correct?', 14, ANS], ['Note (what is right, with the source)', 40, None]]
    spec = {
        'title': a.title,
        'link_note': 'The first column links to the AntWeb specimen. AntCat protonym ids are in brackets: antcat.org/protonyms/ID.',
        'intro': [
            "Week 3 is done. 131 corrections are now in TaxonWorks (AntWeb shows them after its nightly reload), and 129 MZSP records "
            "go to MZSP, whose own upload feeds AntWeb. Tab All rows shows every answer so far and what was done with it.",
            "From this week: answers only, please. You do not need to edit TaxonWorks or AntCat. We apply TaxonWorks changes from your "
            "answers, and routine AntCat ones by script. We will ask you to edit AntCat yourself only where the text needs your judgement.",
            "If the 8 Nov workbooks from the history work (replacement-name pages, nested references) are still open, do those first.",
            f"Next week: the other {n_left} rank-conflict codes, and a new sample of the specimen linker once its drafting is fixed."],
        'assumptions': [
            "Times come from your week 3 actual times: 8 minutes per misplacement group, about 10 minutes per paper for the lectotype "
            "rows (2 for each further row from the same paper), 8.5 minutes per code for rank conflicts."],
        'days': [
            dict(tab='Day 1', title=f'Misplacements, {len(d1) - 1} groups, and one question', csv=f'{a.out}/day1.csv',
                 what=["AntWeb names one protonym; AntCat lists the code under another. Which name is the specimen a type of? "
                       "Most are MZSP specimens: Ulysséa et al. 2025 (Table S1) covers them, as in week 3.",
                       "The first row is a question about your week 3 answer for M016."],
                 columns=[['ref', 'Group', 8], ['codes', 'Codes (AntWeb)', 16], ['antweb_says', 'AntWeb says', 30],
                          ['antweb_det', 'AntWeb determination', 18], ['owner_country', 'AntWeb owner / country', 16],
                          ['country_in', 'Country found in AntCat locality of', 12], ['antcat_has', 'AntCat lists it under', 26],
                          ['antcat_sentence', 'AntCat text holding the code', 40], ['antweb_named', 'AntWeb names (AntCat protonym)', 26],
                          ['named_text', 'That protonym in AntCat', 36], ['question', 'Question', 30], ['earlier', 'Earlier note', 20]],
                 inputs=ans, link='url'),
            dict(tab='Day 2', title=f'Lectotypes: {len(d2)} specimens from {len(seen_paper)} designating papers', csv=f'{a.out}/day2.csv',
                 what=["AntCat records a lectotype designation for these protonyms but does not name the lectotype by its specimen code, "
                       "so we cannot tell whether this specimen is the lectotype or a paralectotype. AntWeb calls it a syntype.",
                       "Rows are sorted by the designating paper: open it once for all its rows. For each specimen pick Lectotype, "
                       "Paralectotype, Still a syntype (no valid designation) or Unsure.",
                       "If the paper gives the lectotype's code, please put it in the note: AntCat can then record it."],
                 columns=[['ref', 'Code', 15], ['paper', 'Designated by', 22], ['protonym', 'AntCat protonym', 26],
                          ['antweb_says', 'AntWeb says', 30], ['owner', 'Owner', 8], ['primary', 'AntCat primary type', 50],
                          ['secondary', 'AntCat secondary type', 36], ['earlier', 'Your week 3 note', 22]],
                 inputs=[['Correct?', 14, ['Lectotype', 'Paralectotype', 'Still a syntype', 'Unsure']], ['Note (lectotype code, page)', 36, None]],
                 link='url'),
        ] + [dict(tab=f'Day {i}', title=f'Rank conflicts, {sum(r["n"] for r in rows)} codes on {len(rows)} protonyms', csv=f'{a.out}/day{i}.csv',
                  what=["AntWeb and AntCat disagree on whether the specimen is a primary type (holotype, lectotype, syntype) or a "
                        "secondary one (paratype, paralectotype). AntCat lists the code in the field shown.",
                        "One row per protonym; codes with AntWeb's status in brackets. If the codes need different answers, say so in the note."],
                  columns=[['ref', 'First code', 15], ['codes', 'Codes (AntWeb status)', 30], ['protonym', 'AntCat protonym', 26],
                           ['antweb_says', 'AntWeb says (first code)', 30], ['primary', 'AntCat primary type', 50],
                           ['secondary', 'AntCat secondary type', 40]],
                  inputs=ans, link='url') for i, rows in ((3, d3), (4, d4))] + [
            dict(tab='All rows', title='Every row so far, with your answers and what was done', csv=f'{a.out}/all_rows.csv', reference=True,
                 what=["state: corrected in TaxonWorks, sent to MZSP, resolved by 8 Nov (AntWeb or AntCat changed), in this week, or later."],
                 columns=[['state', 'State', 26], ['type', 'Type', 12], ['code', 'Code', 15], ['antweb_typestatus', 'AntWeb says', 34],
                          ['antcat_holding', 'AntCat lists it under', 28], ['answer', 'Your answer', 12], ['notes', 'Your notes', 40]],
                 link='antweb_url')]}
    json.dump(spec, open(f'{a.out}/week.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"Day 1 {len(d1)} rows ({len(d1) - 1} groups + 1 question); Day 2 {len(d2)} rows, {len(seen_paper)} papers; "
          f"Day 3 {len(d3)} protonyms ({sum(r['n'] for r in d3)} codes); Day 4 {len(d4)} ({sum(r['n'] for r in d4)}); "
          f"rank codes left for next week {n_left}; all rows {len(allr)}")


if __name__ == '__main__':
    main()
