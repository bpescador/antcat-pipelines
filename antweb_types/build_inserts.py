#!/usr/bin/env python3
"""
build_inserts.py — generate the AntCat primary-type ADD worklist from the matcher output.

Usage:
    python3 build_inserts.py PROTONYMS.jsonl ANTWEB.tsv type_link_queue.csv [OUTDIR]

Produces:
    primary_adds.csv — one row per protonym in the auto-primary backlog, with the exact ADD
                       text, the case type, and reviewer flags. ALL rows get the specimen
                       link added; material conflicts are flagged, not withheld.

Rules (see README "Type-info formatting spec"):
  - Enter the bare specimen code, uppercased. Multiple codes comma-separated.
  - Never insert an AntWeb-derived locality — locality comes from the publication.
  - Three cases:
      specimen_only   : AntCat already has material+locality+depository -> add/append specimen line
      add_depository  : AntCat has text but no depository -> add depository + specimen lines
      full_block      : AntCat has no primary text -> build material + depository + specimen
                        (NO locality), plus a secondary block if AntWeb has paratypes
  - Material-consistency flag: AntWeb kind vs AntCat material kind (syntype<->lectotype suppressed).
"""
import csv, json, re, sys
from collections import defaultdict
csv.field_size_limit(10**9)

PROT = sys.argv[1] if len(sys.argv) > 1 else 'protonyms_species_typeinfo.jsonl'
AW   = sys.argv[2] if len(sys.argv) > 2 else 'aw.tsv'
QUEUE= sys.argv[3] if len(sys.argv) > 3 else 'type_link_queue.csv'
OUT  = (sys.argv[4].rstrip('/') + '/') if len(sys.argv) > 4 else ''

PRIMARY={'holotype','lectotype','neotype','syntype','cotype','type'}
SING={'holotype','lectotype','neotype'}
BENIGN={frozenset(['syntype','lectotype'])}
def ncode(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())
def kind_of(ts): return ts.split(' of ')[0].strip().lower().rstrip('s')

prot={}
for line in open(PROT):
    p=json.loads(line); prot[str(p['protonym_id'])]=p

awf={}
with open(AW, newline='', encoding='utf-8', errors='replace') as f:
    r=csv.reader(f, delimiter='\t'); hdr=next(r); H={h:i for i,h in enumerate(hdr)}
    G=lambda row,k: row[H[k]] if (k in H and len(row)>H[k]) else ''
    for row in r:
        if not G(row,'type_status'): continue
        awf[ncode(G(row,'code'))]=dict(code=G(row,'code'),ts=G(row,'type_status'),
            caste=G(row,'caste'),life=G(row,'life_stage'),dep=G(row,'ownedby'))

autoP=defaultdict(list); autoS=defaultdict(list)
with open(QUEUE) as f:
    for d in csv.DictReader(f):
        if d['tier']=='auto' and d['antcat_protonym_ids']:
            (autoP if d['primary']=='True' else autoS)[d['antcat_protonym_ids']].append(d)

def caste_of(d):
    c=(d.get('caste') or '').lower()
    if c: return c
    l=(d.get('life') or '').lower()
    for w in ['worker','queen','male','gyne','soldier']:
        if w in l: return w
    return 'specimen'
def material_line(specs):
    kinds=defaultdict(int)
    for s in specs: kinds[(kind_of(s['ts']),caste_of(s))]+=1
    out=[]
    for (k,c),n in kinds.items():
        if k in SING: out.append(f"{k} {c}")
        else: out.append(f"{n} {k} {c}s" if n>1 else f"{k} {c}s (number not stated)")
    return ', '.join(out)
def ac_material_kind(t):
    m=re.search(r'type[- ]material:\s*(?:[\d\s]+)?([a-z]+)', t, re.I)
    return m.group(1).lower() if m else ''

rows=[]
for pid in autoP:
    cur=prot.get(pid,{}).get('primary_type_taxt') or ''
    name=autoP[pid][0]['antcat_protonyms']
    pspecs=[awf[ncode(r['code'])] for r in autoP[pid] if ncode(r['code']) in awf]
    if not pspecs: continue
    pcodes=', '.join(s['code'].upper() for s in pspecs)
    pdeps=', '.join(sorted({s['dep'] for s in pspecs if s['dep']}))
    awurls=' '.join(f"https://www.antweb.org/specimen.do?name={s['code']}" for s in pspecs)
    has_block=bool(cur.strip()); has_dep=bool(re.search(r'type deposit',cur,re.I))
    has_spec=bool(re.search(r'type specimen',cur,re.I))

    # material flag
    ack=ac_material_kind(cur); awk=kind_of(pspecs[0]['ts']); mat_flag=''
    if ack and awk and ack!=awk and ack in PRIMARY and awk in PRIMARY and frozenset([ack,awk]) not in BENIGN:
        mat_flag=f"AntWeb {awk} vs AntCat material {ack}"

    needs_locality=''
    if has_block and has_dep:
        case='specimen_append' if has_spec else 'specimen_addline'
        add=(f"append to existing Primary type specimen line: , {pcodes}" if has_spec
             else f"add line: Primary type specimen: {pcodes}.")
    elif has_block and not has_dep:
        case='add_depository'
        add=f"add lines: Primary type depository: {pdeps}. Primary type specimen: {pcodes}."
    else:
        case='full_block'; needs_locality='yes (from publication)'
        add=f"Primary type material: {material_line(pspecs)}. Primary type depository: {pdeps}. Primary type specimen: {pcodes}."
        if pid in autoS:
            sspecs=[awf[ncode(r['code'])] for r in autoS[pid] if ncode(r['code']) in awf]
            if sspecs:
                sdeps=', '.join(sorted({s['dep'] for s in sspecs if s['dep']}))
                scodes=', '.join(s['code'].upper() for s in sspecs)
                add+=(f" Secondary type material: {material_line(sspecs)}. "
                      f"Secondary type depositor{'ies' if len(sdeps.split(', '))>1 else 'y'}: {sdeps}. "
                      f"Secondary type specimens: {scodes}.")
    rows.append(dict(protonym_id=pid, protonym=name,
        antcat_url=f"https://antcat.org/protonyms/{pid}", case=case,
        specimen_codes=pcodes, add_text=add, material_flag=mat_flag,
        needs_locality=needs_locality, antweb_urls=awurls))

rows.sort(key=lambda d:(d['case']!='specimen_append', d['case']!='specimen_addline',
                        bool(d['material_flag']), d['protonym']))
with open(OUT+'primary_adds.csv','w',newline='') as f:
    w=csv.DictWriter(f, fieldnames=['protonym_id','protonym','antcat_url','case',
        'specimen_codes','add_text','material_flag','needs_locality','antweb_urls'])
    w.writeheader(); [w.writerow(d) for d in rows]

from collections import Counter
cc=Counter(d['case'] for d in rows); mf=sum(1 for d in rows if d['material_flag'])
print(f"primary_adds.csv: {len(rows)} protonyms")
for k,v in cc.items(): print(f"  {k:16} {v}")
print(f"  material_flag set on {mf} (specimen still added; flagged for review)")
