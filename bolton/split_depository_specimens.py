#!/usr/bin/env python3
"""
split_depository_specimens.py -- draft the split of AntCat's combined
"... type depositories and specimens:" segments into a depositories list and a
specimens field (the reviewer's request, 2026-10-30), so comparisons can read the
depositories. DRAFT for a reviewer to check and paste; nothing is written to AntCat.

  "Secondary type depositories and specimens: CASC: CASENT0247017; MCZC: MCZ-ENT00593559."
  -> "Secondary type depositories: CASC, MCZC. Secondary type specimens: CASC: CASENT0247017; MCZC: MCZ-ENT00593559."

"Paratype-depositories and specimens" becomes "Secondary type ...". The rest of the
field, including markup, is kept as stored.

  python3 bolton/split_depository_specimens.py protonyms_species_typeinfo.jsonl out.csv [institutions.jsonl]

With institutions.jsonl, mixed-case codes (INBio, CeNak, PMSPbU, Raffles) are read too; without it they
are missed, as INBio was in the 2026-11-02 week.
"""
import csv, json, re, sys

SEG = re.compile(r'(?P<label>(?P<tier>Primary|Secondary) type depositor(?:y|ies)|Paratype-depositor(?:y|ies)|Type-depositor(?:y|ies))'
                 r' and specimens?\s*:\s*(?P<body>.*?)(?P<end>\.\s*(?=(?:Primary|Secondary) type [a-z]+:|Paratype-|Type-)|\.?\s*$)', re.S)
C = r'[A-Z]{2,7}(?:-[A-Z]{1,4})?'
CODE = re.compile(C)


def use_codes(extra):
    """also accept these literal codes (mixed case, from AntCat's institutions)"""
    global C, CODE
    alts = sorted({re.escape(x) for x in extra}, key=len, reverse=True)
    C = r'(?:' + '|'.join(alts + [r'[A-Z]{2,7}(?:-[A-Z]{1,4})?']) + r')'
    CODE = re.compile(C)


def codes_in(body):
    """depository codes: in each ';' part, the code(s) before the first ':' (after any caste
    label such as 'major workers:'), or a bare code with no specimens listed."""
    out = []
    flat = re.sub(r'\([^()]*\)', '', body)
    # a code group after ';' or ',' and before ':' (a ',' here is a slip for ';')
    for grp in re.findall(r'(?:^|[;,])\s*(?:[a-z][a-z ]*:\s*)*((?:' + C + r'\s*,\s*)*' + C + r')\s*:', flat):
        for c in grp.split(','):
            c = c.strip()
            if CODE.fullmatch(c) and c not in out:
                out.append(c)
    for part in flat.split(';'):
        part = re.sub(r'^\s*(?:[a-z][a-z ]*:\s*)+', '', part.strip())
        head = part.split(':', 1)[0] if ':' in part else part
        for c in head.split(','):
            c = c.strip().rstrip('.')
            if CODE.fullmatch(c) and c not in out:
                out.append(c)
    return out


def split(text):
    m = SEG.search(text or '')
    if not m:
        return None, 'no combined segment'
    tier = 'Primary' if m.group('tier') == 'Primary' else 'Secondary'
    body = m.group('body').strip()
    if body.endswith('.') and not body.endswith('.)'):
        body = body[:-1]
    codes = codes_in(body)
    if not codes:
        return None, 'no codes found'
    codes = sorted(codes)
    n_spec = len(re.findall(r'[A-Z]{2,}[A-Za-z-]*\d{3,}', body))
    dep = f"{tier} type {'depositories' if len(codes) > 1 else 'depository'}: {', '.join(codes)}."
    spec = f"{tier} type {'specimens' if n_spec != 1 else 'specimen'}: {body}" + ('' if body.endswith('.)') else '.')
    note = ''
    if re.search(r'\d,\s*' + C + r'\s*:', body):
        note = 'comma where a semicolon should separate depositories'
    new = text[:m.start()] + dep + ' ' + spec + (' ' if m.end() < len(text) else '') + text[m.end():].lstrip()
    return new.strip(), note


def main():
    src, out = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 3:
        inst = [json.loads(l) for l in open(sys.argv[3], encoding='utf-8') if l.strip()]
        use_codes([i['abbreviation'] for i in inst if re.search(r'[a-z]', i.get('abbreviation') or '')])
    rows = []
    for l in open(src, encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        for field in ('primary_type_taxt', 'secondary_type_taxt'):
            t = r.get(field) or ''
            if ' and specimen' not in t or 'depositor' not in t:
                continue
            new, problem = split(t)
            rows.append(dict(protonym_id=r['protonym_id'], name=r['name'], author=r['author'], year=r['year'],
                             field=field, current=t, draft=new or '', problem=problem if not new else '', note=problem if new else '',
                             url=f"https://www.antcat.org/protonyms/{r['protonym_id']}"))
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    bad = [r for r in rows if r['problem']]
    print(f"  notes: {sum(1 for r in rows if r['note'])}")
    print(f"wrote {out}: {len(rows)} fields, {len(bad)} without a draft")
    for r in bad:
        print('  ', r['protonym_id'], r['name'], r['problem'], '|', r['current'][:160])


if __name__ == '__main__':
    main()
