#!/usr/bin/env python3
"""
typestatus_week.py -- build a reviewer's week from the refreshed type-status sheet, the linker
additions and the NGC-label drafts: one CSV per day plus week.json for bolton/review_week.py.
READ ONLY.

  python3 antweb_types/typestatus_week.py --merged typestatus_merged.csv --adds primary_adds.csv \
      --held primary_adds_held.csv --labels ngc_labels_draft.csv --protonyms PROTONYMS.jsonl \
      --out WEEKDIR [--groups-per-day 16] [--seed 20261108] [--title "..."]
  python3 bolton/review_week.py --spec WEEKDIR/week.json --xlsx WEEK.xlsx

Days (first used for Bradley's week 3, from Mon 9 Nov 2026):
  Day 1 labels   the drafting rule for NGC-style labels, and 12 drafted records to check
  Day 1 linker   28 linker additions sampled across cases (not on his sheet, no NGC labels, no present_check),
                 plus 2 held by convention; each is checked against AntWeb and the AntCat page
  Day 2          replacement-name misplacements (one row per group), and 10 + 10 samples of the
                 two rank patterns (lectotype designated; syntypes in AntCat). If a sample agrees,
                 the rest of that pattern can be handled as a batch instead of row by row.
  Days 3 to 5    misplacement groups that fit no pattern, largest first, --groups-per-day each
  All rows       the whole refreshed sheet, his answers carried over (reference; not timed)
Minutes per item follow his week 2 actual times (about 5 min per check, 8 per research item).
"""
import argparse, csv, json, os, random, re
from collections import Counter, defaultdict

csv.field_size_limit(10**9)
MIN_LABEL_RULE, MIN_LABEL_EX, MIN_LINK, MIN_SIMPLE, MIN_GROUP = 1, 3, 5, 4, 8
ANSWERS = ['AntCat', 'AntWeb', 'AntWeb (partially)', 'Unsure']


def rd(p): return list(csv.DictReader(open(p, encoding='utf-8')))


def wr(p, rows, cols):
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def short(t, n=500): t = (t or '').strip(); return t if len(t) <= n else t[:n - 1] + '…'


def main():
    ap = argparse.ArgumentParser()
    for k in ('merged', 'adds', 'held', 'labels', 'protonyms', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--groups-per-day', type=int, default=16)
    ap.add_argument('--seed', type=int, default=20261108)
    ap.add_argument('--title', default='AntWeb vs AntCat type status, week 3')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rnd = random.Random(a.seed)
    P = {}
    for line in open(a.protonyms, encoding='utf-8'):
        if line.strip():
            p = json.loads(line); P[str(p['protonym_id'])] = p
    M, adds, held, labels = rd(a.merged), rd(a.adds), rd(a.held), rd(a.labels)
    live = [d for d in M if d['status'] != 'resolved']

    # ---- Day 1 labels: the rule, then examples covering each variant ----
    cnt = Counter((d['field'], l) for d in labels for l in d['labels'].split('; ') if d['field'] != 'type notes')
    target = defaultdict(int)
    for (fld, l), k in cnt.items():
        x = re.sub(r'^(?:Paratype-|Type[- ])', '', l)
        target[(fld, ('Primary type ' if fld == 'primary' else 'Secondary type ') + x)] += k
    d1 = [dict(ref=f'rule {i}', kind='rule', name=f'{fld} field', current=', '.join(sorted(l for (f2, l) in cnt if f2 == fld and
               re.sub(r'^(?:Paratype-|Type[- ])', '', l) == t.split(' type ', 1)[1])), draft=t, count=k, min=MIN_LABEL_RULE)
          for i, ((fld, t), k) in enumerate(sorted(target.items(), key=lambda x: (x[0][0] != 'primary', -x[1])), 1)]
    picks, seen = [], set()
    def pick(pred, why):
        for d in labels:
            if d['protonym_id'] not in seen and pred(d):
                seen.add(d['protonym_id']); picks.append((d, why)); return
    pick(lambda d: d['field'] == 'primary' and 'Type-material' in d['labels'] and 'Type-depository' in d['labels'] and not d['flag'], 'the common case')
    pick(lambda d: d['field'] == 'primary' and 'Type-specimen' in d['labels'], 'with a specimen line')
    pick(lambda d: d['field'] == 'primary' and 'Type-depositories' in d['labels'], 'plural depositories')
    pick(lambda d: d['field'] == 'primary' and 'Type depositories' in d['labels'], 'one NGC label in an AntCat-labelled field')
    pick(lambda d: d['field'] == 'primary' and 'Type-localities' in d['labels'], 'plural localities')
    pick(lambda d: d['field'] == 'secondary' and 'Paratype-material' in d['labels'] and 'Paratype-depositories' in d['labels'], 'secondary field, the common case')
    pick(lambda d: d['field'] == 'secondary' and 'Paratype-specimens' in d['labels'], 'secondary with specimens')
    pick(lambda d: d['field'] == 'secondary' and 'Type depositories' in d['labels'], '"Type depositories" in the secondary field')
    pick(lambda d: d['field'] == 'secondary' and 'Type-material' in d['labels'], '"Type-material" in the secondary field')
    pick(lambda d: d['flag'] == 'paratypes in the primary field', 'flagged: paratypes in the primary field')
    pick(lambda d: d['field'] == 'type notes', 'left alone: a quotation in type notes')
    pick(lambda d: d['field'] == 'secondary' and 'Paratype-localities' in d['labels'], 'plural paratype localities')
    d1 += [dict(ref=d['protonym_id'], kind=f"example: {why}", name=f"{d['name']} ({d['field']} field)", current=d['current'],
                draft=d['draft'] if d['draft'] != d['current'] else '(unchanged)', count='', url=d['url'], min=MIN_LABEL_EX)
           for d, why in picks]

    # ---- Day 1 linker sample ----
    on_sheet = {x for d in live for x in (d['holding_id'].split(';') + d['named_id'].split(';')) if x}
    ngc = {d['protonym_id'] for d in labels if d['field'] != 'type notes'}
    pool = [d for d in adds if d['protonym_id'] not in on_sheet and d['protonym_id'] not in ngc and not d.get('present_check')]
    strata = [('specimen line, no flag', lambda d: d['case'] == 'specimen_addline' and not d['material_flag'], 10),
              ('append to a specimen line', lambda d: d['case'] == 'specimen_append', 5),
              ('material differs', lambda d: bool(d['material_flag']), 5),
              ('full block (no AntCat type text)', lambda d: d['case'] == 'full_block', 5),
              ('adds a depository line', lambda d: d['case'] == 'add_depository', 3)]
    link, used = [], set()
    for why, pred, k in strata:
        c = [d for d in pool if pred(d) and d['protonym_id'] not in used]
        for d in rnd.sample(c, min(k, len(c))):
            used.add(d['protonym_id']); link.append((d, why))
    n_held = min(2, len(held))
    for d in rnd.sample(held, n_held):
        link.append((d, f"held: {d['hold_reason']}"))
    d1b = []
    for d, why in link:
        p = P.get(d['protonym_id'], {})
        d1b.append(dict(protonym_id=d['protonym_id'], protonym=d['protonym'], why=why,
                        now=short(p.get('primary_type_taxt'), 400) or '(empty)', now_sec=short(p.get('secondary_type_taxt'), 250),
                        primary_add=d.get('primary_add') or d['add_text'], secondary_add=d.get('secondary_add', ''),
                        flags='; '.join(x for x in (d['material_flag'], d['depository_check'], d.get('present_check', ''), d.get('hold_reason', '')) if x),
                        antweb=d['antweb_urls'], url=d['antcat_url'], min=MIN_LINK))

    # ---- Day 2: replacement names (by group) + rank pattern samples ----
    by_group = defaultdict(list)
    for d in live:
        if d['group']:
            by_group[d['group']].append(d)
    def grow(g, rows, m):
        d = rows[0]
        return dict(ref=g, codes=', '.join(x['code'].upper() for x in rows), n=len(rows), antweb_says=d['antweb_typestatus'],
                    antweb_det=d['antweb_det'], owner_country=f"{d['antweb_owner']} / {d['antweb_country']}",
                    country_in=d['country_in'], antcat_has=f"{d['antcat_holding']} ({d['holding_id']})",
                    antcat_sentence=short(d['antcat_sentence'], 400),
                    antweb_named=f"{d['antweb_names']} ({d['named_id']})", named_text=short(d['named_primary'], 300),
                    suggestion=d['suggestion'], earlier='; '.join(sorted({f"{x['answer']} {x['notes']}".strip() for x in rows if x['answer'] or x['notes']})),
                    url=d['antcat_url'], named_url=d['named_url'], antweb_url=d['antweb_url'], min=m)
    rn = sorted((g for g, rows in by_group.items() if rows[0]['pattern'] == 'replacement name'), key=lambda g: -len(by_group[g]))
    d2 = [dict(grow(g, by_group[g], MIN_SIMPLE), kind='replacement name') for g in rn]
    for pat in ('lectotype designated', 'syntypes in AntCat'):
        c = [d for d in live if d['type'] == 'rank' and d['pattern'] == pat]
        for d in rnd.sample(c, min(10, len(c))):
            d2.append(dict(ref=d['code'].upper(), kind=f"sample of {sum(1 for x in live if x['pattern'] == pat)}: {pat}",
                           codes=d['code'].upper(), n=1, antweb_says=d['antweb_typestatus'], antweb_det=d['antweb_det'],
                           owner_country=f"{d['antweb_owner']} / {d['antweb_country']}",
                           antcat_has=f"{d['antcat_holding']} ({d['holding_id']})", antcat_sentence=short(d['antcat_sentence'], 400),
                           suggestion=d['suggestion'], url=d['antweb_url'], antweb_url=d['antweb_url'], min=MIN_SIMPLE))

    # ---- Days 3 to 5: misplacement groups that fit no pattern, largest first ----
    conf = sorted((g for g, rows in by_group.items() if rows[0]['pattern'] == 'conflict'),
                  key=lambda g: (-len(by_group[g]), by_group[g][0]['antweb_names']))
    days_m = [conf[i:i + a.groups_per_day] for i in range(0, min(len(conf), 3 * a.groups_per_day), a.groups_per_day)]
    left = conf[3 * a.groups_per_day:]

    # ---- write CSVs ----
    C1 = ['ref', 'kind', 'name', 'current', 'draft', 'count', 'url', 'min']
    wr(f'{a.out}/day1_labels.csv', d1, C1)
    C1b = ['protonym_id', 'protonym', 'why', 'now', 'now_sec', 'primary_add', 'secondary_add', 'flags', 'antweb', 'url', 'min']
    wr(f'{a.out}/day1_linker.csv', d1b, C1b)
    CG = ['ref', 'kind', 'codes', 'n', 'antweb_says', 'antweb_det', 'owner_country', 'country_in', 'antcat_has',
          'antcat_sentence', 'antweb_named', 'named_text', 'suggestion', 'earlier', 'url', 'named_url', 'antweb_url', 'min']
    wr(f'{a.out}/day2.csv', d2, CG)
    for i, gs in enumerate(days_m, 3):
        wr(f'{a.out}/day{i}.csv', [dict(grow(g, by_group[g], MIN_GROUP), kind='misplacement') for g in gs], CG)
    allcols = ['status', 'type', 'group', 'code', 'antweb_typestatus', 'antcat_holding', 'answer', 'notes', 'resolved_how',
               'pattern', 'suggestion', 'antweb_url', 'antcat_url']
    wr(f'{a.out}/all_rows.csv', sorted(M, key=lambda d: ({'open': 0, 'new': 1, 'resolved': 2}[d['status']], d['type'], d['group'], d['code'])), allcols)

    # ---- week.json for review_week.py ----
    n_lect = sum(1 for d in live if d['pattern'] == 'lectotype designated')
    n_syn = sum(1 for d in live if d['pattern'] == 'syntypes in AntCat')
    n_rank_conf = sum(1 for d in live if d['type'] == 'rank' and d['pattern'] == 'conflict')
    st = Counter(d['status'] for d in M)
    waiting = [d for d in M if d['status'] == 'open' and d['answer']]
    G = [['ref', 'Group', 8], ['codes', 'Codes (AntWeb)', 16], ['n', 'n', 4], ['antweb_says', 'AntWeb says', 30],
         ['antweb_det', 'AntWeb determination', 18], ['owner_country', 'AntWeb owner / country', 16],
         ['country_in', 'Country found in AntCat locality of', 12], ['antcat_has', 'AntCat lists it under', 26],
         ['antcat_sentence', 'AntCat text holding the code', 40], ['antweb_named', 'AntWeb names (AntCat protonym)', 26],
         ['named_text', 'That protonym in AntCat', 40], ['earlier', 'Your earlier note', 24]]
    ans = [['Correct?', 14, ANSWERS], ['Note (what to change, and where: AntWeb/TW or AntCat)', 40, None]]
    spec = {
        'title': a.title,
        'link_note': 'The first column links to the record: the AntCat protonym on Day 1, the AntWeb specimen on the other days.',
        'intro': [
            f"Your sheet of 430 rows, rerun on 8 Nov exports (AntCat protonyms and AntWeb specimens, same day). "
            f"{st['resolved']} rows are resolved since June, most by your TaxonWorks fixes reaching AntWeb; "
            f"{st['open']} are still open and {st['new']} are new. All your answers are carried over (tab All rows).",
            "Patterns found in AntCat's own data are shown as evidence, not as answers. Please check them the same way as before.",
            f"Rows still open that you have already answered (the AntWeb change has not happened yet): "
            + '; '.join(f"{d['code'].upper()} ({d['answer']}" + (f": {short(d['notes'], 90)})" if d['notes'] else ')') for d in waiting) + '.',
            "Camponotus hova cemeryi (5 codes, Day 2): cemeryi Özdikmen 2010 is a replacement name for C. hova var. luteolus Emery 1925, "
            "so the lectotype series stays on luteolus in AntCat, and AntWeb should name luteolus. This answers the question in your notes.",
            f"Left for week 4: {len(left)} misplacement groups, {n_rank_conf} rank conflicts, and the rest of the two rank patterns "
            f"({n_lect} lectotype designated, {n_syn} syntypes in AntCat) once Day 2's samples are in."],
        'assumptions': [
            "Times come from your week 2 actual times (13 h 15 min for a 7 h 45 min estimate): about 5 minutes per check, "
            "8 per item that needs the original description.",
            "A misplacement group is every code with the same AntWeb name and the same AntCat protonym: one answer covers them all.",
            "\"Country found in AntCat locality of\" says whether AntWeb's country appears in each protonym's AntCat type locality. It is a hint only."],
        'days': [
            dict(tab='Day 1 labels', title='AntCat labels for NGC-style type fields', csv=f'{a.out}/day1_labels.csv',
                 what=[f"{len({d['protonym_id'] for d in labels})} protonyms still use NGC labels (Type-material:, Type-depository:, Paratype-depositories:).",
                       "Proposed rule: in the primary field Type-X becomes Primary type X; in the secondary field Paratype-X (and Type-X) becomes "
                       "Secondary type X. Nothing else in the text changes. Type notes are left alone (they quote original data).",
                       "Rule rows: is the target wording right? Example rows: is the draft right? Once agreed, AntCatBot makes the changes "
                       "through the usual staged write (dry run, canary, 10 rows, the rest), before the linker adds any specimen codes."],
                 columns=[['ref', 'Rule / protonym', 11], ['kind', 'What', 22], ['name', 'Field / protonym', 24], ['current', 'Now', 55],
                          ['draft', 'Draft', 55], ['count', 'Records', 8]],
                 inputs=[['Right?', 10, ['Yes', 'Change']], ['Note', 30, None]], link='url'),
            dict(tab='Day 1 linker', title=f'A sample of {len(d1b)} linker additions', csv=f'{a.out}/day1_linker.csv',
                 what=["The linker found AntWeb type specimens for 8,611 protonyms whose AntCat type fields lack the code (June: 8,675).",
                       f"{len(d1b) - n_held} rows sampled across the kinds of addition, plus {n_held} held back by convention. Open the AntCat page and the AntWeb "
                       "specimen; say whether the drafted text is right. Locality is never taken from AntWeb.",
                       "If the sample is clean, the clean rows go in through AntCatBot (staged write); rows on your type-status sheet and "
                       "flagged rows are held back."],
                 columns=[['protonym_id', 'Protonym', 9], ['protonym', 'Name', 22], ['why', 'Kind', 16], ['now', 'AntCat primary now', 40],
                          ['now_sec', 'AntCat secondary now', 26], ['primary_add', 'Drafted primary text', 40],
                          ['secondary_add', 'Drafted secondary text', 30], ['flags', 'Flags', 22], ['antweb', 'AntWeb', 30]],
                 inputs=[['Verdict', 14, ['Add as drafted', 'Add with change', 'Do not add', 'Unsure']], ['Note', 30, None]], link='url'),
            dict(tab='Day 2', title='Replacement names, and samples of the two rank patterns', csv=f'{a.out}/day2.csv',
                 what=["Replacement names (one row per group): AntWeb names the replacement name; AntCat keeps the type on the original "
                       "name's protonym, by convention. The fix is on AntWeb.",
                       f"Lectotype designated (sample of 10 of {n_lect}): AntWeb says syntype; AntCat records a lectotype and lists this code "
                       f"as a paralectotype. Syntypes in AntCat (10 of {n_syn}): AntWeb says paratype; AntCat records syntypes, no holotype.",
                       "If a sample agrees throughout, the rest of that pattern can be fixed as a batch on AntWeb. Please do not fix the "
                       "sampled rows in TW one by one yet."],
                 columns=[['ref', 'Group / code', 12], ['kind', 'Pattern', 18]] + G[1:2] + G[3:4] + G[7:9] + G[9:10] +
                         [['suggestion', 'What AntCat shows', 36]] + G[11:12],
                 inputs=ans, link='antweb_url'),
        ] + [dict(tab=f'Day {i}', title=f'Misplacements, {len(gs)} groups ({sum(len(by_group[g]) for g in gs)} codes)', csv=f'{a.out}/day{i}.csv',
                  what=["AntWeb names one protonym; AntCat lists the code under another. Which name is the specimen a type of? "
                        "Use the original description and the AntWeb specimen label.",
                        "One answer per group covers every code in it. The first column links to the AntWeb specimen."],
                  columns=G[:8] + G[8:11] + G[11:12], inputs=ans, link='antweb_url')
             for i, gs in enumerate(days_m, 3)] + [
            dict(tab='All rows', title='Your whole sheet, refreshed 8 Nov (reference, not timed)', csv=f'{a.out}/all_rows.csv',
                 reference=True,
                 what=["Your answers and notes are carried over unchanged. status: open = still a mismatch; resolved = no longer a "
                       "mismatch on 8 Nov (resolved how says what changed); new = not in June's list."],
                 columns=[['status', 'Status', 9], ['type', 'Type', 12], ['group', 'Group', 7], ['code', 'Code', 15],
                          ['antweb_typestatus', 'AntWeb says', 36], ['antcat_holding', 'AntCat lists it under', 28],
                          ['answer', 'Your answer', 12], ['notes', 'Your notes', 36], ['resolved_how', 'Resolved how', 30],
                          ['pattern', 'Pattern', 16]],
                 link='antweb_url')]}
    json.dump(spec, open(f'{a.out}/week.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"Day 1 labels {len(d1)}; Day 1 linker {len(d1b)}; Day 2 {len(d2)}; "
          + '; '.join(f"Day {i} {len(gs)} groups ({sum(len(by_group[g]) for g in gs)} codes)" for i, gs in enumerate(days_m, 3))
          + f"; left for week 4: {len(left)} groups, {n_rank_conf} rank conflicts -> {a.out}/week.json")


if __name__ == '__main__':
    main()
