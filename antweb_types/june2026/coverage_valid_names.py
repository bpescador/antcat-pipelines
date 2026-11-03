# coverage_valid_names.py -- the same for current valid species-group names, via each name's basionym (needs worldants.txt).
# Recovered verbatim on 2026-11-03 from the chat "Automating type specimen linking between
# Antcat and Antweb" (claude.ai chat 7b114e80, 8 Jun 2026, turn 50), where it ran as an inline step.
# One-off: paths and file names are the June chat's (/tmp/work, /mnt/user-data/outputs, prot.jsonl).
# Kept for the record; not maintained. See antweb_types/README.md.

import csv, sys, json, re, unicodedata
csv.field_size_limit(sys.maxsize)
def deacc(s): return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c))
CONN=r'\b(var|st|subsp|ssp|r|nat|ab|m|f|race|form|forma|stirps)\b\.?'
def norm(s):
    s=deacc(s).lower(); s=re.sub(r'\([^)]*\)',' ',s); s=re.sub(CONN,' ',s)
    s=re.sub(r'[^a-z ]',' ',s); return re.sub(r'\s+',' ',s).strip()
CODE_RE=re.compile(r'(?<![A-Z0-9])[A-Z]{2,}[ \-]?[A-Z]{0,3}-?\d{3,}[A-Z0-9\-]*')
def codes_in(t): return {re.sub(r'[^A-Z0-9]','',c) for c in CODE_RE.findall(deacc(t or '').upper())}

# --- protonym type data: name+year -> id, and code-status sets ---
prot_by_ny={}; has_code_now=set(); 
for line in open('prot.jsonl'):
    p=json.loads(line); pid=p['protonym_id']; nm=norm(p['name']); y=str(p['year']) if p['year'] else ''
    prot_by_ny.setdefault((nm,y),[]).append(pid)
    if codes_in(p.get('primary_type_taxt')) or codes_in(p.get('secondary_type_taxt')): has_code_now.add(pid)
# gain = auto-routed protonym targets
gain=set()
for r in csv.DictReader(open('type_link_queue.csv')):
    if r['tier']=='auto':
        for x in r['antcat_protonym_ids'].split(';'):
            if x.strip().isdigit(): gain.add(int(x))
after_ids = has_code_now | gain

# --- worldants taxa ---
rows=[]
with open('20260608-05_05_43-worldants.txt', encoding='utf-8', errors='replace') as f:
    for row in csv.DictReader(f, delimiter='\t'): rows.append(row)
def full(x): return norm(' '.join(t for t in [x['genus'],x['species'],x['subspecies']] if (t or '').strip()))
def cvn(x):
    t=norm(x['current valid name']).split()
    return ' '.join(t[1:]) if len(t)>1 else ''   # drop subfamily
def isoc(x): return (x['original combination'] or '').strip().upper()=='TRUE'
def yr(x): return (x['year'] or '').strip()

valid=[x for x in rows if (x['status'] or '').strip().lower()=='valid' and (x['species'] or '').strip()]
# basionym index for recombined valids: obsolete-combination + origcomb=TRUE, keyed by the valid name it resolves to
basio_by_validname={}
for x in rows:
    if (x['status'] or '').strip().lower()=='obsolete combination' and isoc(x):
        basio_by_validname.setdefault(cvn(x), x)

def resolve_protids(nm,y):
    ids=prot_by_ny.get((nm,y))
    if ids: return ids
    # year fallback: unique name match
    cand=[k for k in prot_by_ny if k[0]==nm]
    if len(cand)==1: return prot_by_ny[cand[0]]
    return []

n=len(valid); matched=0; now=0; after=0; unmatched=0
for v in valid:
    if isoc(v): bn, by = full(v), yr(v)
    else:
        b=basio_by_validname.get(full(v))
        if b: bn, by = full(b), yr(b)
        else: bn, by = full(v), yr(v)   # fallback: try the valid name itself
    ids=resolve_protids(bn,by)
    if not ids: unmatched+=1; continue
    matched+=1
    if any(i in has_code_now for i in ids): now+=1
    if any(i in after_ids   for i in ids): after+=1

print(f"Current valid species-group names:            {n:,}")
print(f"  basionym matched to a protonym:             {matched:,}  ({100*matched/n:.0f}%)")
print(f"  basionym not matched (name/year gap):       {unmatched:,}")
print()
print(f"Valid names with a type specimen NOW:         {now:,}  ({100*now/n:.1f}% of all valid)")
print(f"Valid names with a type specimen AFTER merge: {after:,}  ({100*after/n:.1f}% of all valid)")
print(f"  (as % of matched basionyms after merge:     {100*after/matched:.1f}%)")
