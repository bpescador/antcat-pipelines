#!/usr/bin/env python3
"""
reconcile_types.py  —  AntCat <-> AntWeb type reconciliation matcher.

Usage:
    python3 reconcile_types.py PROTONYMS.jsonl ANTWEB.tsv [OUTDIR]

Inputs:
  PROTONYMS.jsonl : AntCat species-group protonym export (from export_protonyms.rb)
  ANTWEB.tsv      : full AntWeb specimen export (tab-separated, may be latin-1)

Outputs (in OUTDIR, default current dir):
  type_link_queue.csv        one row per AntWeb type specimen, with tier + routing
  antweb_typestatus_fixes.csv AntWeb name typos to fix in AntWeb (specimen correctly linked)
  review_mismatches.csv       misplacement + rank discrepancies for AntCat-side review

See README for methodology and parsing rules.
"""
import csv, re, sys, json, unicodedata
from collections import defaultdict, Counter
from difflib import SequenceMatcher
csv.field_size_limit(10**9)

PROT = sys.argv[1] if len(sys.argv) > 1 else 'protonyms_species_typeinfo.jsonl'
AW   = sys.argv[2] if len(sys.argv) > 2 else 'aw.tsv'
OUT  = (sys.argv[3].rstrip('/') + '/') if len(sys.argv) > 3 else ''

CONN = set("ab f finterm form m morph n nat r ssp st subp subsp v var".split())
PRIMARY   = {'holotype','lectotype','neotype','syntype','cotype','type'}
SECONDARY = {'paratype','paralectotype','cotypes'}

def deacc(s): return unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode()
def antweb_url(code): return f"https://www.antweb.org/specimen.do?name={code}"
def norm_name(s):
    s = deacc(s).lower(); s = re.sub(r'\([^)]*\)',' ',s).replace('.',' ')
    return ' '.join(t for t in s.split() if t and t not in CONN)
def norm_code(s): return re.sub(r'[^A-Z0-9]','', deacc(s).upper())
CODE_RE = re.compile(r'(?<![A-Z0-9])[A-Z]{2,}[ \-]?[A-Z]{0,3}-?\d{3,}[A-Z0-9\-]*')
def codes_in(t): return {re.sub(r'[^A-Z0-9]','',c) for c in CODE_RE.findall(deacc(t or '').upper())}
def surname_ac(a):
    a = deacc(a or ''); a = re.split(r'[&;]| and ', a)[0].split(',')[0]
    toks = [t for t in re.split(r'[ .]+', a) if len(t) > 1]
    return toks[0].lower() if toks else ''
def last_ep(nm): t = nm.split(); return t[-1] if t else ''
def gstem(e): return re.sub(r'(us|um|is|ii|os|ae|a|e|i|o)$','', e)
def same_taxon(a, b):
    x, y = last_ep(a), last_ep(b)
    if not x or not y: return False
    return (gstem(x) == gstem(y) and gstem(x) != '') or SequenceMatcher(None, x, y).ratio() >= 0.80
def name_relation(a, b):
    # Compare genus + terminal epithet only. Subgenera and connecting words are already
    # stripped by norm_name; middle (species-of-subspecies) parts are ignored. Gender
    # endings tolerated via gstem so israele/israelis, sewellii/sewelli, Megaponera/
    # Megaloponera count as the SAME name (no fix). Returns: same | current_combination |
    # spelling | different.
    at, bt = a.split(), b.split()
    if not at or not bt: return 'different'
    ag, bg, ae, be = at[0], bt[0], at[-1], bt[-1]
    genus_same = ag == bg or SequenceMatcher(None, ag, bg).ratio() >= 0.85
    term_same  = gstem(ae) == gstem(be) and gstem(ae) != ''
    if genus_same and term_same: return 'same'
    if term_same: return 'current_combination'   # terminal epithet matches; genus differs -> AntWeb used another combination
    if genus_same and SequenceMatcher(None, ae, be).ratio() >= 0.80: return 'spelling'
    return 'different'

# ---------------- AntCat protonym indexes ----------------
prot = {}; name_index = defaultdict(list); name_only = defaultdict(list); code_index = defaultdict(list)
for line in open(PROT):
    p = json.loads(line); nm = norm_name(p['name']); yr = str(p['year']) if p['year'] else ''
    prim = p.get('primary_type_taxt') or ''; seco = p.get('secondary_type_taxt') or ''
    rec = dict(id=p['protonym_id'], name=p['name'], author=p.get('author') or '', year=yr,
               surname=surname_ac(p.get('author')), nm=nm,
               url=f"https://antcat.org/protonyms/{p['protonym_id']}")
    prot[p['protonym_id']] = rec
    if nm and yr: name_index[(nm, yr)].append(rec)
    if nm: name_only[nm].append(rec)
    for c in codes_in(prim): code_index[c].append((p['protonym_id'], 'primary'))
    for c in codes_in(seco): code_index[c].append((p['protonym_id'], 'secondary'))

def parse_ts(ts):
    m = re.match(r'\s*([A-Za-z]+)\s*(?:of\s+(.*?))?(?:\s*\(search on AntCat\))?\s*$', ts)
    if not m: return ('', '', '', '', '')
    kind = m.group(1).lower().rstrip('s'); proto = (m.group(2) or '').strip()
    if not proto: return (kind, '', '', '', '')
    ym = re.search(r'(\d{4})', proto); yr = ym.group(1) if ym else ''
    pre = re.sub(r'\([^)]*\)',' ', proto[:ym.start()] if ym else proto)
    toks = [t for t in re.split(r'[ ,]+', pre) if t]
    nt = []; au = []; started = False
    for i, t in enumerate(toks):
        if i == 0: nt.append(t)
        elif (not started) and t[:1].islower(): nt.append(t)
        else: started = True; au.append(t)
    sn = next((t.lower() for t in au if len(t) > 1 and t.lower() not in ('et','al')), '')
    return (kind, proto, norm_name(' '.join(nt)), yr, sn)

# ---------------- walk AntWeb ----------------
rows = []; mismatches = []; fixes = []; counts = Counter(); seen = set()
with open(AW, newline='', encoding='utf-8', errors='replace') as f:
    r = csv.reader(f, delimiter='\t'); hdr = next(r); H = {h: i for i, h in enumerate(hdr)}
    G = lambda row, k: row[H[k]] if (k in H and len(row) > H[k]) else ''
    for row in r:
        ts = G(row, 'type_status')
        if not ts: continue
        code = G(row, 'code'); nc = norm_code(code)
        if nc in seen: continue
        seen.add(nc)
        kind, proto, nm, yr, sn = parse_ts(ts)
        aw_primary = (kind in PRIMARY) or (kind and kind not in SECONDARY)
        det = norm_name(' '.join(x for x in [G(row,'genus'), G(row,'species'), G(row,'subspecies')] if x))
        dep = G(row,'ownedby'); cty = G(row,'country'); loc = G(row,'localityname'); caste = G(row,'caste')

        # route candidates
        cands = name_index.get((nm, yr), []) if (nm and yr) else []
        if not cands and nm and not yr:
            c2 = name_only.get(nm, []); cands = c2 if len(c2) == 1 else []
        if not cands and (not proto) and kind in PRIMARY and det:     # bare primary -> determination
            c3 = name_only.get(det, []); cands = c3 if len(c3) == 1 else []
        if len(cands) > 1 and sn:
            ba = [c for c in cands if c['surname'] == sn]
            if ba: cands = ba

        owners = code_index.get(nc, []); owner_ids = {i for i, _ in owners}; cand_ids = {c['id'] for c in cands}

        if owners:
            owner_nm   = prot[next(iter(owner_ids))]['nm']
            owner_name = prot[next(iter(owner_ids))]['name']
            owner_url  = prot[next(iter(owner_ids))]['url']
            rel = name_relation(nm, owner_nm) if (nm and proto) else 'same'
            if cand_ids and (owner_ids & cand_ids):
                tier = 'already_linked'
                pl = {p_ for i, p_ in owners if i in cand_ids}
                if aw_primary and pl == {'secondary'}:
                    mismatches.append((code, 'rank', ts, [prot[i]['name'] for i in owner_ids], [prot[i]['url'] for i in owner_ids]))
                elif (not aw_primary) and pl == {'primary'}:
                    mismatches.append((code, 'rank', ts, [prot[i]['name'] for i in owner_ids], [prot[i]['url'] for i in owner_ids]))
            elif cand_ids and not (owner_ids & cand_ids) and not same_taxon(nm, owner_nm):
                tier = 'misplacement'
                mismatches.append((code, 'misplacement', ts, [prot[i]['name'] for i in owner_ids], [prot[i]['url'] for i in owner_ids]))
            else:
                tier = 'already_linked'
            # AntWeb name-fix detection: code correctly linked, but type_status name needs fixing.
            # name_relation ignores subgenera (stripped), connecting words (stripped), and gender
            # endings; 'same' is not a fix. Only flag a real spelling typo or a current-combination.
            if rel in ('current_combination', 'spelling'):
                fixes.append((code, ts, owner_name, rel, antweb_url(code), owner_url))
        else:
            if len(cands) == 1: tier = 'auto'
            elif len(cands) > 1: tier = 'ambiguous'
            else: tier = 'nomatch'

        counts[tier] += 1; counts[('P_' if aw_primary else 'S_') + tier] += 1
        ac_url = (cands[0]['url'] if cands else (prot[next(iter(owner_ids))]['url'] if owners else ''))
        rows.append(dict(code=code, tier=tier, primary=aw_primary, kind=kind, protonym=proto, year=yr,
                         antcat_protonym_ids=';'.join(str(c['id']) for c in cands),
                         antcat_protonyms=';'.join(c['name'] for c in cands),
                         antweb_url=antweb_url(code), antcat_url=ac_url,
                         depository=dep, country=cty, locality=loc, type_status=ts))

# ---------------- write ----------------
with open(OUT+'type_link_queue.csv','w',newline='') as f:
    w = csv.DictWriter(f, fieldnames=['code','tier','primary','kind','protonym','year',
        'antcat_protonym_ids','antcat_protonyms','antweb_url','antcat_url','depository','country','locality','type_status'])
    w.writeheader(); [w.writerow(d) for d in rows]
with open(OUT+'antweb_typestatus_fixes.csv','w',newline='') as f:
    w = csv.writer(f); w.writerow(['code','fix_type','antweb_typestatus','antcat_protonym_name','antweb_url','antcat_protonym_url'])
    for c, ts, nm_, rel, awu, u in fixes: w.writerow([c, rel, ts, nm_, awu, u])
with open(OUT+'review_mismatches.csv','w',newline='') as f:
    w = csv.writer(f); w.writerow(['code','type','antweb_typestatus','antcat_protonym_holding','antweb_url','antcat_url'])
    for m in sorted(mismatches, key=lambda x:(x[1],x[0])): w.writerow([m[0], m[1], m[2], ' | '.join(m[3]), antweb_url(m[0]), ' | '.join(m[4])])

# ---------------- summary ----------------
not_on = counts['auto'] + counts['ambiguous'] + counts['nomatch']
print(f"AntWeb type specimens: {sum(counts[t] for t in ['already_linked','auto','ambiguous','nomatch','misplacement'])}")
for t in ['already_linked','auto','ambiguous','nomatch']:
    print(f"  {t:14} {counts[t]:6}  (primary {counts['P_'+t]:5} / secondary {counts['S_'+t]:5})")
print(f"NOT on AntCat: {not_on}  (auto {counts['auto']} / ambiguous {counts['ambiguous']} / nomatch {counts['nomatch']})")
print(f"AntWeb name fixes: {len(fixes)}   misplacements: {sum(1 for m in mismatches if m[1]=='misplacement')}   rank: {sum(1 for m in mismatches if m[1]=='rank')}")
