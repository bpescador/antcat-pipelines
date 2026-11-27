# build_agreement_set2_20261127.py -- READ ONLY, record of how set 2 (27 Nov 2026) was built from the review:
# Brian's six held rows, nomina nuda held, the evidence for formation-verified rows stated per name, then the
# grouped-write input (taxon_name row + three protonym form rows per combination). Paths are those of that session.
import json, csv, re, collections, hashlib
d = json.load(open('set2/set2.json'))
R = {}
for l in open('/mnt/user-data/uploads/snapshots/completeness-20261127/completeness_20261127_20261127000426.jsonl'):
    r = json.loads(l); R[r['protonym_id']] = r
EXCL = {437260: 'held by Brian: the original derivation refers to the wing stigma; stigmata can be a plural noun; the match to stigmo does not establish a participle',
        445497: 'held by Brian: bubalus is a Latin noun (buffalo); recorded part of speech to be corrected separately',
        433492: 'held by Brian: pending confirmation that proletaria is adjectival, not a noun in apposition',
        450740: 'held by Brian: pending confirmation of the original grammatical treatment of spuria',
        449626: 'held by Brian: the adjectival derivation of chloana is insufficiently established',
        449958: 'held by Brian: noun and adjective readings of salina both need consideration'}
PERSONAL = {'arnoldianus': 'Arnold', 'muellerianus': 'Müller', 'silvestrianum': 'Silvestri', 'santschianum': 'Santschi',
            'wroughtonianum': 'Wroughton', 'mayrianum': 'Mayr'}
NONPLACE = {'parabiotica': 'adjective in -icus formed from parabiosis (Greek para- + biōsis), three terminations',
            'symbiotica': 'adjective in -icus formed from symbiosis (Greek symbiōsis), three terminations',
            'thoracica': 'adjective in -icus formed from the noun thorax, thoracis (Latin thoracicus), three terminations',
            'concentrica': 'adjective in -icus, Neo-Latin concentricus (con- + centrum), three terminations',
            'icterica': 'Latin ictericus, -a, -um "jaundiced" (Greek ikterikos), an adjective of three terminations',
            'eocenica': 'adjective in -icus formed from Eocene, three terminations'}
def evidence(x):
    if x['level'] != 'B': return x['verified']
    e = x['present'].split()[-1]; p = R[x['protonym_id']]; loc = (p['locality'] or '').strip()
    if e in NONPLACE: return NONPLACE[e]
    if e in PERSONAL: return f'adjective with the suffix -ianus on the personal name {PERSONAL[e]}, three terminations'
    where = f' (type locality: {loc})' if loc else ''
    if re.search(r'ens(is|e)$', e): return f'adjective with the suffix -ensis on a place name{where}, two terminations'
    suf = re.search(r'(an|in|ic)(us|a|um)$', e).group(1)
    return f'adjective with the suffix -{suf}us on a place name{where}, three terminations'
keep, held = [], []
for x in d['out']:
    if x['taxon_id'] in EXCL: held.append(dict(x, exception=EXCL[x['taxon_id']])); continue
    p = R[x['protonym_id']]
    if p['nomen_nudum']: held.append(dict(x, exception='unavailable: nomen nudum')); continue
    keep.append(dict(x, verified=evidence(x)))
c = collections.Counter(x['status'] for x in keep); print('keep', len(keep), c, 'held', len(held))
assert len({x['taxon_id'] for x in keep}) == len(keep) and len({x['protonym_id'] for x in keep}) == len(keep)
rows, labels = [], collections.Counter(x['present'] for x in keep)
for x in sorted(keep, key=lambda x: ({'valid': 0, 'synonym': 1}.get(x['status'], 2), x['present'])):
    p = R[x['protonym_id']]
    g = x['present'] if labels[x['present']] == 1 else f"{x['present']} ({x['taxon_id']})"
    rows.append([g, 'taxon_name', str(x['taxon_id']), x['present'], 'name', x['present'], x['proposed']])
    m, f, n = x['forms'].split('/')
    for fld, v in (('masculine_epithet', m), ('feminine_epithet', f), ('neuter_epithet', n)):
        assert not p[fld]
        rows.append([g, 'protonym', str(x['protonym_id']), p['name'], fld, '', v])
with open('set2/agreement_set2_20261127.tsv', 'w', newline='') as fh:
    w = csv.writer(fh, delimiter='\t', lineterminator='\n'); w.writerow(['group', 'kind', 'record_id', 'label', 'field', 'old', 'new']); w.writerows(rows)
print(len(rows), 'rows')
json.dump(dict(keep=keep, held=held), open('set2/set2_final.json', 'w'), ensure_ascii=False)
# canary candidates: valid, demonstrated, dictionary, not original combination
for x in keep:
    t = [t for t in R[x['protonym_id']]['taxa'] if t['id'] == x['taxon_id']][0]
    if x['status'] == 'valid' and x['interp'] == 'demonstrated' and x['level'] == 'A' and not t['original_combination']:
        print('canary candidate', x['present'], x['taxon_id'])
