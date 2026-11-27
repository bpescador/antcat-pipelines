#!/usr/bin/env python3
"""Propose masculine/feminine/neuter forms for species-group adjectives and participles from the epithet's ending.
Reads the completeness export; writes proposals and holds. Read only."""
import json, sys, re, csv
from collections import Counter
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from lexicon import load, lookup
LS = load(__import__('os').environ.get('LS_INDEX', 'ls_index.tsv'))
src, outdir = sys.argv[1], sys.argv[2]
R = [json.loads(l) for l in open(src)]
S = [r for r in R if r['group'] == 'species_group']
G = {'masculine': 0, 'feminine': 1, 'neuter': 2}
KEEP_E = {'asper','liber','miser','tener','lacer','prosper','gibber','alter','exter','dexter','ceter','posterus','lacerus'}
DROP_E = {'ruber','glaber','scaber','sacer','macer','ater','creber','integer','pulcher','aeger','piger','taeter','teter','vafer','faber'}
VALID = {'valid', 'synonym', 'homonym', 'unidentifiable', 'excluded from Formicidae', 'unavailable uncategorized'}

NIGER = re.compile(r'^(|.*o|semi|sub|ob|post|extremi)nig(er|ra|rum)$')
NOUN_END = re.compile(r'(cephal|scap|clype|corp|carp|gnath|not|nod|spin|gastr|thorac|som|derm|pter|ophthalm|ocul|stip|pod|op)(us|a|um|os|on)$')
def forms(e):
    """(m, f, n, rule) or None."""
    if NOUN_END.search(e) or re.search(r'(pus|pa|pum)$', e) and re.search(r'[aeiouy]p(us|a|um)$', e): return 'NOUN'
    if re.search(r'nig(er|ra|rum)$', e):
        if not NIGER.match(e): return None
        st = e[: e.rindex('nig')] + 'nig'; return (st+'er', st+'ra', st+'rum', '-er (drops e)')
    if re.search(r'ens(is|e)$', e):
        st = re.sub(r'(is|e)$', '', e); return (st+'is', st+'is', st+'e', 'ensis')
    if re.search(r'(ens|ans)$', e): return (e, e, e, 'participle -ens/-ans')
    if re.search(r'(ceps|cipes)$', e): return (e, e, e, '-ceps') if e.endswith('ceps') else None
    if re.search(r'(color)$', e): return (e, e, e, '-color')
    if re.search(r'(trix|senex|harpax|exlex)$', e): return None
    if re.search(r'(ax|ex|ix|ox|ux|yx)$', e) and len(e) > 3: return (e, e, e, 'one form -x')
    if re.search(r'(ors|ers|ons|urs)$', e): return (e, e, e, 'one form -rs/-ns')
    if e.endswith('ior'): return (e, e, e[:-2]+'us', 'comparative -ior')
    # -er family
    if re.search(r'(gaster|gastra|gastrum|electra|alacer|alacris)$', e) or e in ('fera', 'ferum', 'ferus'): return None
    if e.endswith('er') and any(e.endswith(k) for k in DROP_E): return (e, e[:-2]+'ra', e[:-2]+'rum', '-er (drops e)')
    if re.search(r'afer$', e): return (e, e[:-2]+'ra', e[:-2]+'rum', '-er (drops e)')
    if e.endswith('er'):
        base = e
        stem = e if (any(e.endswith(k) for k in KEEP_E) or re.search(r'(fer|ger)$', e)) else None
        if stem is None and any(e.endswith(k) for k in DROP_E): stem = e[:-2]+'r'
        if stem is None: return None
        return (e, stem+'a', stem+'um', '-er')
    m = re.match(r'(.*)(us|a|um)$', e)
    if m and not e.endswith('ius') and not re.search(r'[^aeiou]r(a|um)$', e) and not re.search(r'er(a|um)$', e):
        st = m.group(1)
        if st.endswith('i') and m.group(2) == 'us' and False: pass
        return (st+'us', st+'a', st+'um', '-us -a -um')
    if re.search(r'i(us|a|um)$', e):
        st = re.sub(r'(us|a|um)$', '', e); return (st+'us', st+'a', st+'um', '-ius -ia -ium')
    # -ra/-rum after consonant: niger type, or after e: asper type
    m = re.match(r'(.*)(a|um)$', e)
    if m:
        st = m.group(1)
        if st.endswith('er') and (any((st).endswith(k) for k in DROP_E) or st.endswith('afer')): return None
        if st.endswith('er'):
            if any((st).endswith(k) for k in KEEP_E) or re.search(r'(fer|ger)$', st): return (st, st+'a', st+'um', '-er (keeps e)')
            return None
        if re.search(r'[^aeiou]r$', st):
            masc = st[:-1]+'er'
            if any(masc.endswith(k) for k in DROP_E) or re.search(r'(br|cr|tr|gr|dr)$', st): return (masc, st+'a', st+'um', '-er (drops e)')
            return None
    m = re.match(r'(.*)(is|e)$', e)
    if m and len(e) > 3:
        st = m.group(1); return (st+'is', st+'is', st+'e', '-is -e')
    return None

def last(n): return (n or '').split()[-1] if n else ''
rows, holds, rule_c, hold_c = [], [], Counter(), Counter()
for r in S:
    if r['gender_agreement_type'] not in ('adjective', 'participle'): continue
    if r['masculine_epithet'] and r['feminine_epithet'] and r['neuter_epithet']: continue
    pid, e = r['protonym_id'], r['epithet']
    def hold(why): holds.append((pid, r['name'], r['gender_agreement_type'], why)); hold_c[why.split(':')[0]] += 1
    if r['nomen_nudum']: hold('nomen nudum'); continue
    if r['interpretation_status'] not in ('demonstrated', 'reasonably_inferred'): hold(f"interpretation {r['interpretation_status']}"); continue
    if any([r['masculine_epithet'], r['feminine_epithet'], r['neuter_epithet']]): hold('some forms already set'); continue
    f = forms(e)
    if f == 'NOUN': hold(f'ends in a noun (policy of 23 Nov: a noun phrase): {e}'); continue
    if not f: hold(f'ending not handled: {e}'); continue
    if f[3] == '-us -a -um':
        rd = lookup(LS, e); ks = {x['kind'] for x in rd}
        if ks and not ks & {'adjective', 'participle'}: hold(f'Lewis & Short has it only as {"+".join(sorted(ks))}: {e}'); continue
    m_, f_, n_, rule = f
    if e not in (m_, f_, n_): hold(f'original spelling not among the forms: {e} -> {m_}/{f_}/{n_}'); continue
    bad, checked = [], 0
    for t in r['taxa']:
        if t['status'] not in VALID or not t['genus_gender'] or not t['name']: continue
        checked += 1
        want = (m_, f_, n_)[G[t['genus_gender']]] if t['genus_gender'] in G else None
        if want and last(t['name']) != want: bad.append(f"{t['name']} ({t['status']}, genus {t['genus_gender']}) expects {want}")
    if bad: hold('current spelling disagrees with genus gender: ' + '; '.join(bad)); continue
    rule_c[rule] += 1
    rows.append((pid, r['name'], m_, f_, n_, rule, checked))
print('proposed', len(rows), dict(rule_c)); print('held', len(holds)); print(hold_c.most_common(12))
with open(f'{outdir}/forms_proposed.tsv', 'w', newline='') as fh:
    w = csv.writer(fh, delimiter='\t'); w.writerow(['protonym_id','name','masculine','feminine','neuter','rule','taxa_checked']); w.writerows(rows)
with open(f'{outdir}/forms_held.tsv', 'w', newline='') as fh:
    w = csv.writer(fh, delimiter='\t'); w.writerow(['protonym_id','name','part_of_speech','reason']); w.writerows(holds)
