# coverage_protonyms.py -- share of species-group protonyms with at least one type specimen code, now and after the AntWeb merge.
# Recovered verbatim on 2026-11-03 from the chat "Automating type specimen linking between
# Antcat and Antweb" (claude.ai chat 7b114e80, 8 Jun 2026, turn 48), where it ran as an inline step.
# One-off: paths and file names are the June chat's (/tmp/work, /mnt/user-data/outputs, prot.jsonl).
# Kept for the record; not maintained. See antweb_types/README.md.

import json, re, csv
def deacc(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c))
CODE_RE = re.compile(r'(?<![A-Z0-9])[A-Z]{2,}[ \-]?[A-Z]{0,3}-?\d{3,}[A-Z0-9\-]*')
def codes_in(t): return {re.sub(r'[^A-Z0-9]','',c) for c in CODE_RE.findall(deacc(t or '').upper())}

# denominator: all species-group protonyms
all_ids=set(); has_code_now=set()
for line in open('prot.jsonl'):
    p=json.loads(line); pid=p['protonym_id']; all_ids.add(pid)
    prim=p.get('primary_type_taxt') or ''; seco=p.get('secondary_type_taxt') or ''
    if codes_in(prim) or codes_in(seco): has_code_now.add(pid)

# protonyms that would GAIN a specimen from the AntWeb merge (auto-routed targets)
gain=set()
with open('type_link_queue.csv') as f:
    for r in csv.DictReader(f):
        if r['tier']=='auto':
            for x in r['antcat_protonym_ids'].split(';'):
                if x.strip().isdigit(): gain.add(int(x))

after = has_code_now | gain
N=len(all_ids)
print(f"Species-group protonyms (denominator):      {N:,}")
print(f"Have >=1 type specimen NOW:                  {len(has_code_now):,}  ({100*len(has_code_now)/N:.1f}%)")
print(f"Would gain >=1 from AntWeb auto-merge:        {len(gain):,}")
print(f"  of which had none before:                  {len(gain - has_code_now):,}")
print(f"Have >=1 type specimen AFTER full merge:      {len(after):,}  ({100*len(after)/N:.1f}%)")
print(f"Still WITHOUT any type specimen after merge:  {N-len(after):,}  ({100*(N-len(after))/N:.1f}%)")
