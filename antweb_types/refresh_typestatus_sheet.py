#!/usr/bin/env python3
"""
refresh_typestatus_sheet.py -- bring a reviewer's type-status sheet up to date with a new
reconcile_types.py run, keeping every answer he has given. READ ONLY.

  python3 antweb_types/refresh_typestatus_sheet.py SHEET.xlsx RUN_DIR PROTONYMS.jsonl FLAGS.jsonl ANTWEB.tsv OUT.csv

SHEET.xlsx  the reviewer's copy of review_mismatches.csv with his two columns added
            ("antweb or antcat correct?", "notes"), e.g. Bradley's AntWeb_AntCat_mismatches.xlsx
            of 2026-11-08 (430 rows from the June run).
RUN_DIR     the new reconcile_types.py output (review_mismatches.csv, type_link_queue.csv).
PROTONYMS   bolton/export_protonyms.rb output, same day as ANTWEB.
FLAGS       antweb_types/export_protonym_flags.rb output.
ANTWEB.tsv  the AntWeb specimen dump the run used.

Each row of OUT.csv is one code and mismatch type (misplacement or rank), with:
  status       resolved (in the sheet, no longer a mismatch), open (still a mismatch),
               new (a mismatch the sheet does not have)
  answer, notes        the reviewer's, carried over unchanged
  resolved_how         for resolved rows: what changed between the two runs
  pattern, suggestion  what the AntCat data already shows. Evidence, not a decision:
    replacement name       AntWeb names a replacement name; the type belongs to the original
                           homonym's protonym, where AntCat has it (Bradley 2026-11-08: 21 of his
                           notes). AntCat convention: no type information under replacement names.
    lectotype designated   AntWeb "syntype"; AntCat records a lectotype and lists this code as
                           a paralectotype.
    syntypes in AntCat     AntWeb "paratype"; AntCat records syntypes (no holotype) and lists this
                           code in the primary field.
    conflict               none of these: check the original description.
  group        misplacements with the same AntWeb-named and AntCat-holding protonyms share a
               group, so one decision covers every code in it.
  evidence     AntWeb determination, owner, country, and whether that country appears in each
               protonym's AntCat type locality; the AntCat sentence that holds the code.
"""
import csv, json, re, sys, unicodedata
from collections import Counter, defaultdict
import openpyxl
csv.field_size_limit(10**9)

SHEET, RUN, PROT, FLAGS, AW, OUT = sys.argv[1:7]
ANS, NOTES = 'antweb or antcat correct?', 'notes'


def deacc(s): return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
def nc(s): return re.sub(r'[^A-Z0-9]', '', deacc(s).upper())
def pid(url): return url.rstrip('/').rsplit('/', 1)[-1] if url else ''


P = {}
for line in open(PROT, encoding='utf-8'):
    if line.strip():
        p = json.loads(line); P[str(p['protonym_id'])] = p
F = {}
for line in open(FLAGS, encoding='utf-8'):
    if line.strip():
        f_ = json.loads(line); F[str(f_['protonym_id'])] = f_
Q = {nc(d['code']): d for d in csv.DictReader(open(f'{RUN}/type_link_queue.csv', encoding='utf-8'))}
NEW = {(nc(d['code']), d['type']): d for d in csv.DictReader(open(f'{RUN}/review_mismatches.csv', encoding='utf-8'))}
def lines(path):
    # the AntWeb dump is mostly UTF-8 with some Latin-1 rows ("S\xe3o Paulo"); decode each line on its own
    with open(path, 'rb') as f:
        for b in f:
            try: yield b.decode('utf-8')
            except UnicodeDecodeError: yield b.decode('latin-1')


A = {}
_r = csv.reader(lines(AW), delimiter='\t'); H = {h: i for i, h in enumerate(next(_r))}
G = lambda row, k: row[H[k]] if (k in H and len(row) > H[k]) else ''
for row in _r:
    if G(row, 'type_status'):
        A.setdefault(nc(G(row, 'code')), dict(
            det=' '.join(x for x in (G(row, 'genus'), G(row, 'species'), G(row, 'subspecies')) if x),
            owner=G(row, 'ownedby'), country=G(row, 'country'), ts=G(row, 'type_status')))

wb = openpyxl.load_workbook(SHEET, data_only=True); ws = wb.active
hdr = [c.value for c in ws[1]]
OLD = {}
for vals in ws.iter_rows(min_row=2, values_only=True):
    d = dict(zip(hdr, vals))
    if d.get('code'):
        OLD[(nc(d['code']), d['type'])] = d


def is_repl(i): return bool(F.get(i, {}).get('replacement_name') or F.get(i, {}).get('replacement_name_taxt'))


def sentence_with(code, text):
    c = nc(code)
    for s in re.split(r'(?<=\.)\s+(?=[A-Z])', text or ''):
        if c in nc(s):
            return s.strip()
    return ''


def country_in(country, p):
    if not country or not p: return False
    t = deacc(' '.join([p.get('locality') or '', p.get('primary_type_taxt') or ''])).lower()
    return deacc(country).lower() in t


def kinds(t):
    t = (t or '').lower()
    return {k for k in ('holotype', 'lectotype', 'neotype', 'syntype', 'paralectotype', 'paratype') if re.search(r'\b' + k, t)}


def classify(typ, code, kind, named, holder):
    hp = P.get(holder[0], {}) if holder else {}
    pt, st, c = hp.get('primary_type_taxt') or '', hp.get('secondary_type_taxt') or '', nc(code)
    if typ == 'misplacement':
        rn = [i for i in named if is_repl(i)]
        if rn:
            return ('replacement name',
                    f"AntCat correct by convention: AntWeb names the replacement name {P[rn[0]]['name']} "
                    f"({rn[0]}); the type belongs to {hp.get('name')} ({holder[0]}), the original name. Fix on AntWeb.")
        return ('conflict', 'Check the original description: which name is this specimen a type of?')
    if kind == 'syntype' and c in nc(st) and 'paralectotype' in kinds(st) and 'lectotype' in kinds(pt):
        return ('lectotype designated',
                'AntCat records a lectotype and lists this code as a paralectotype; AntWeb still says syntype. Probably fix AntWeb.')
    if kind == 'paratype' and c in nc(pt) and 'syntype' in kinds(pt) and not ({'holotype', 'lectotype', 'neotype'} & kinds(pt)):
        return ('syntypes in AntCat',
                'AntCat records syntypes (no holotype) with this code in the primary field; AntWeb says paratype. Check whether the original named a holotype.')
    return ('conflict', 'Check the original description: primary or secondary type?')


rows = []
for key in list(OLD) + [k for k in NEW if k not in OLD]:
    code_n, typ = key
    old, new, q = OLD.get(key), NEW.get(key), Q.get(code_n, {})
    code = (old or new)['code']
    status = 'new' if not old else ('open' if new else 'resolved')
    holder = [pid(u) for u in (new or old)['antcat_url'].split(' | ') if u]
    named = [x for x in (q.get('antcat_protonym_ids') or '').split(';') if x]
    aw = A.get(code_n, {})
    how = ''
    if status == 'resolved':
        ts_old, ts_new = (old.get('antweb_typestatus') or '').strip(), (q.get('type_status') or '').strip()
        if not q: how = 'no longer a type specimen on AntWeb'
        elif ts_new != ts_old: how = f"AntWeb now reads \"{ts_new}\" ({q.get('tier')})"
        elif q.get('tier') == 'auto': how = 'AntCat no longer lists the code; AntWeb unchanged (now a linker addition)'
        else: how = f"AntCat changed; AntWeb unchanged ({q.get('tier')})"
    pattern, sugg = ('', '')
    if status != 'resolved':
        pattern, sugg = classify(typ, code, q.get('kind', ''), named, holder)
    hp, npr = P.get(holder[0], {}) if holder else {}, P.get(named[0], {}) if named else {}
    hold_txt = sentence_with(code, (hp.get('primary_type_taxt') or '') + ' ' + (hp.get('secondary_type_taxt') or ''))
    rows.append(dict(
        status=status, type=typ, code=code,
        antweb_typestatus=aw.get('ts') or q.get('type_status') or (old or {}).get('antweb_typestatus', ''),
        antweb_typestatus_june=(old or {}).get('antweb_typestatus', '') if old and (old.get('antweb_typestatus') or '').strip() != (q.get('type_status') or '').strip() else '',
        antcat_holding=' | '.join(P.get(h, {}).get('name', '') for h in holder), holding_id=';'.join(holder),
        antweb_names=';'.join(P.get(i, {}).get('name', '') for i in named), named_id=';'.join(named),
        answer=(old or {}).get(ANS) or '', notes=(old or {}).get(NOTES) or '', resolved_how=how,
        pattern=pattern, suggestion=sugg,
        antweb_det=aw.get('det', ''), antweb_owner=aw.get('owner', ''), antweb_country=aw.get('country', ''),
        country_in=('both' if country_in(aw.get('country'), hp) and country_in(aw.get('country'), npr) else
                    'AntCat holder' if country_in(aw.get('country'), hp) else
                    'AntWeb-named' if country_in(aw.get('country'), npr) else 'neither') if typ == 'misplacement' else '',
        antcat_sentence=hold_txt,
        named_primary=(npr.get('primary_type_taxt') or '')[:400] if typ == 'misplacement' else '',
        antweb_url=f"https://www.antweb.org/specimen.do?name={code}",
        antcat_url=f"https://antcat.org/protonyms/{holder[0]}" if holder else '',
        named_url=f"https://antcat.org/protonyms/{named[0]}" if named else ''))

# one group per (AntWeb-named, AntCat-holding) pair of protonyms; numbered in sheet order
grp, n = {}, 0
for d in rows:
    if d['type'] == 'misplacement' and d['status'] != 'resolved':
        k = (d['named_id'], d['holding_id'])
        if k not in grp:
            n += 1; grp[k] = f"M{n:03d}"
        d['group'] = grp[k]
    else:
        d['group'] = ''
size = Counter(d['group'] for d in rows if d['group'])
for d in rows:
    d['group_size'] = size[d['group']] if d['group'] else ''

cols = ['status', 'type', 'group', 'group_size', 'code', 'antweb_typestatus', 'antweb_typestatus_june',
        'antcat_holding', 'holding_id', 'antweb_names', 'named_id', 'answer', 'notes', 'resolved_how',
        'pattern', 'suggestion', 'antweb_det', 'antweb_owner', 'antweb_country', 'country_in',
        'antcat_sentence', 'named_primary', 'antweb_url', 'antcat_url', 'named_url']
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

print(f"sheet {len(OLD)} rows; new run {len(NEW)} mismatches -> {OUT}")
print('  status:', dict(Counter(d['status'] for d in rows)))
print('  answered and still open:', sum(1 for d in rows if d['status'] == 'open' and d['answer']))
print('  answered and resolved:', sum(1 for d in rows if d['status'] == 'resolved' and d['answer']))
print('  resolved how:', Counter(re.sub(r'".*"', '"..."', d['resolved_how']) for d in rows if d['resolved_how']).most_common())
print('  open+new by pattern:', Counter((d['type'], d['pattern']) for d in rows if d['status'] != 'resolved').most_common())
print('  misplacement groups:', len(size), '| codes in groups:', sum(size.values()))
