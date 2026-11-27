#!/usr/bin/env python3
"""propose_agreement_set2.py -- READ ONLY. Current combinations (valid, synonym, homonym, unidentifiable) whose
adjectival epithet does not agree with the genus gender, with forms verified in Lewis & Short or by a Latin
adjectival suffix, and the exclusions (stem differs, noun endings, unverified forms, interpretation).
  LS_INDEX=ls_index.tsv python3 gender/propose_agreement_set2.py COMPLETENESS.jsonl OUT.json"""
import json, csv, sys, re, collections
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexicon import load, lookup
import importlib.util
spec = importlib.util.spec_from_file_location('f', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'propose_adjective_forms.py'))
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'propose_adjective_forms.py')).read().split('def last(n)')[0]   # rules only
ns = {'__file__': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'propose_adjective_forms.py')}; exec(src.replace("src, outdir = sys.argv[1], sys.argv[2]\nR = [json.loads(l) for l in open(src)]\nS = [r for r in R if r['group'] == 'species_group']", ''), ns)
forms = ns['forms']; LS = ns['LS']
R = [json.loads(l) for l in open('' + sys.argv[1] + '')]
G = {'masculine': 0, 'feminine': 1, 'neuter': 2}
PREFIXES = {'sub','bi','tri','semi','ob','per','prae','pro','re','in','dis','ex','con','ante','post','super','supra','infra','inter','para','pseudo','neo','quadri','multi','pauci'}
NOUNISH = re.compile(r'(cola|colus|colum|perda|perdus|gyne|chaeta|chaetus|membrum|membra|noda|nodum|phila|philus|philum|phyta|phytus|donta|dontus|ops|phemus|strata)$')
KEPT = {'unjustified_emendation_in_prevailing_usage', 'incorrect_subsequent_spelling_in_prevailing_usage', 'commission_ruling'}
out, exc = [], []
def last(n): return n.split()[-1]
for r in R:
    if r['group'] != 'species_group' or r['gender_agreement_type'] not in ('adjective', 'participle'): continue
    if r['masculine_epithet'] and r['feminine_epithet'] and r['neuter_epithet']: continue
    e = r['epithet']; f = forms(e)
    if not f or f == 'NOUN' or e not in f[:3]: continue
    bad = [t for t in r['taxa'] if t['status'] in ('valid','synonym','homonym','unidentifiable') and t['genus_gender'] in G and t['name'] and last(t['name']) != f[G[t['genus_gender']]]]
    if not bad: continue
    rd = lookup(LS, e)
    m0 = f[0]
    adj = [x for x in rd if x['kind'] in ('adjective', 'participle') and x.get('itype','').strip() not in ('ae', 'ae, m.', 'ae, f.')
           and not ('y' in e and x.get('matched','').startswith('variant'))]
    heads = sorted({f"{x['headword']}" if 'headword' in x else x.get('key','') for x in adj})
    ver, level = '', ''
    if adj:
        ver = 'Lewis & Short: ' + '; '.join(sorted({(x.get('headword') or x.get('key')) + (' ' + x['itype'] if x.get('itype') else '') for x in adj}))[:120]; level = 'A'
    SUF = re.search(r'(ensis|ense|ianus|iana|ianum|anus|ana|anum|icus|ica|icum|inus|ina|inum)$', e)
    if not ver and SUF and len(e) - len(SUF.group(1)) >= 3:
        ver, level = ('Latin adjectival suffix -ensis, -ense (two terminations)' if SUF.group(1) in ('ensis','ense') else
                      'Latin adjectival suffix (-anus, -icus, -inus: three terminations) on a place or personal name'), 'B'
    if not ver:
        for i in range(1, len(m0) - 5):
            pre, suf = m0[:i], m0[i:]
            if not (re.search(r'[io]$', pre) or pre in PREFIXES): continue
            a2 = [x for x in lookup(LS, suf) if x['kind'] in ('adjective', 'participle')]
            if a2:
                ver = f'final component {suf}: Lewis & Short ' + '; '.join(sorted({(x.get('headword') or x.get('key')) + (' ' + x['itype'] if x.get('itype') else '') for x in a2}))[:100]; level = 'A'
                break

    for t in bad:
        want = f[G[t['genus_gender']]]
        row = dict(protonym_id=r['protonym_id'], original=r['name'], taxon_id=t['id'], status=t['status'], present=t['name'],
                   proposed=t['name'][: -len(last(t['name']))] + want, genus=t['genus'], genus_gender=t['genus_gender'],
                   pos=r['gender_agreement_type'], pos_basis=r['part_of_speech_basis'] or '', interp=r['interpretation_status'] or '',
                   spelling_basis=r['spelling_basis'] or '', forms='/'.join(f[:3]), rule=f[3], verified=ver,
                   nomen_nudum=r['nomen_nudum'], year=r['year'], author=(r['authorship_key'] or '').replace('<i>','').replace('</i>',''))
        why = []
        if r['nomen_nudum']: why.append('nomen nudum')
        if r['interpretation_status'] not in ('demonstrated', 'reasonably_inferred'): why.append(f"interpretation {r['interpretation_status']}")
        if r['spelling_basis'] in KEPT: why.append(f"spelling kept: {r['spelling_basis']}")
        if not ver: why.append('forms not verified: neither the word nor its final component is an adjective or participle in Lewis & Short')
        if last(t['name']) not in f[:3]: why.append(f"stem differs: present {last(t['name'])} is not a gender form of the original {e} (an emendation or misspelling, not agreement)")
        if NOUNISH.search(e): why.append('ends in a noun or noun-forming element (-cola, -perda, -gyne, -chaeta, -membrum, -noda, -phila...)')
        if r['interpretation_status'] == 'reasonably_inferred': row['note'] = 'reasonably inferred: needs a name-by-name approval'
        else: row['note'] = ''
        row['level'] = level
        row['basis'] = ('ICZN Arts. 31.2, 34.2: ' + r['gender_agreement_type'] + ', ending agrees with the ' + t['genus_gender'] + ' gender of ' + t['genus'])
        (exc if why else out).append(dict(row, exception='; '.join(why)))
c = collections.Counter(x['status'] for x in out); print('proposed', len(out), c)
print('exceptions', len(exc), collections.Counter(x['status'] for x in exc), collections.Counter(x['exception'].split(':')[0] for x in exc))
print('protonyms', len({x['protonym_id'] for x in out}))
print(collections.Counter(bool(x['verified']) for x in out), collections.Counter(x['interp'] for x in out))
json.dump(dict(out=out, exc=exc), open(sys.argv[2], 'w'), ensure_ascii=False)
