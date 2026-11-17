#!/usr/bin/env python3
"""propose_genus_gender.py -- proposes a grammatical gender for every genus-group name AntCat records without one.

Input:  genus_gender.tsv from gender/gender_baseline.rb (taxon_id, rank, name, status, gender), every genus-group
        taxon record. A subgenus record is named "Genus (Subgenus)".
Output: one row per record without a gender: the name the gender belongs to, the proposal, a tier and the basis.
        Also the records whose recorded gender disagrees with the same name's genus-rank record.

The gender is that of the genus-group name itself (ICZN Art. 30), so a subgenus record takes the gender of the
subgenus name, not of the genus it is combined with (species-group names agree with the genus, Art. 31.2, which is
why a subgenus's gender changes no spelling).

Tiers, in order:
  A  the same name has a genus-rank record with a gender in AntCat
  B  the ending: every AntCat genus-rank name with this ending (3 or more) has the same gender
  B2 the ending: 90% or more of 8 or more such names
  K  the final component is a Greek or Latin word of known gender, or the Code gives the gender
     (Art. 30.1: the word's gender; 30.1.4.2 -ops masculine; 30.2.4: no indication, masculine unless the name ends
     in -a (feminine) or -um, -on, -u (neuter)); table FINALS below, each with its reason
  M  a misspelling of a name whose gender AntCat records: the gender of that name
  C  open: nothing above applies, or AntCat's own records disagree

Nothing is written to AntCat by this script.
"""
import argparse
import csv
import re
from collections import Counter, defaultdict

# Final components: (ending, gender, reason). Longest match wins. Greek and Latin words by their own gender
# (Art. 30.1.1, 30.1.2); arbitrary names by Art. 30.2.4.
FINALS = [
    ('rhachis', 'feminine', 'Greek rhachis (f.), as Polyrhachis'),
    ('thrix', 'feminine', 'Greek thrix (f.), hair'),
    ('thrinax', 'feminine', 'Greek thrinax (f.), trident'),
    ('acantha', 'feminine', 'Greek akantha (f.), thorn'),
    ('rhaphe', 'feminine', 'Greek rhaphe (f.), seam'),
    ('turba', 'feminine', 'Latin turba (f.)'),
    ('sphincta', 'feminine', 'ends in -a; Greek sphinktos in the feminine'),
    ('saga', 'feminine', 'ends in -a (Art. 30.2.4)'),
    ('opsis', 'feminine', 'Greek opsis (f.), as Colobopsis'),
    ('pelta', 'feminine', 'Latin pelta (f.), shield'),
    ('basis', 'feminine', 'Greek basis (f.)'),
    ('tarsus', 'masculine', 'Latinized Greek tarsos (m.)'),
    ('platypus', 'masculine', 'Greek pous (m.), foot'),
    ('platys', 'masculine', 'Greek adjective platys in the masculine'),
    ('amblys', 'masculine', 'Greek adjective amblys in the masculine'),
    ('brachys', 'masculine', 'Greek adjective brachys in the masculine'),
    ('pachys', 'masculine', 'Greek adjective pachys in the masculine, as Cerapachys'),
    ('gigas', 'masculine', 'Greek gigas (m.), giant'),
    ('sirex', 'masculine', 'as Sirex (m.)'),
    ('phyma', 'neuter', 'Greek phyma (n.), swelling'),
    ('teras', 'neuter', 'Greek teras (n.), as Myrmoteras'),
]
# Whole names: (gender, reason).
NAMES = {
    'Lelejus': ('masculine', 'ends in -us; combined with venustus by its author (Art. 30.2.2)'),
    'Karavaievia': ('feminine', 'a personal name with -ia'),
    'Santschia': ('feminine', 'a personal name with -ia'),
    'Evelyna': ('feminine', 'a personal name with -a'),
    'Florencea': ('feminine', 'a personal name with -a'),
    'Myrmatopa': ('feminine', 'ends in -a (Art. 30.2.4)'),
    'Myrmepomis': ('masculine', 'an arbitrary name with no indication of gender (Art. 30.2.4)'),
    'Myrmopiromis': ('masculine', 'an arbitrary name with no indication of gender (Art. 30.2.4)'),
    'Myrmomalis': ('masculine', 'an arbitrary name with no indication of gender (Art. 30.2.4)'),
    'Myrafant': ('masculine', 'an arbitrary name with no indication of gender (Art. 30.2.4)'),
    # The word's own gender outranks the ending as other AntCat names use it (tier B would give the opposite):
    # -rema names in AntCat are the feminine -crema names; -amma names are Greek neuters in -ma (gramma, stemma).
    'Myrmotrema': ('neuter', 'Greek trema (n.), hole (Art. 30.1.2)'),
    'Myrmopsamma': ('feminine', 'Greek psammos (f.), sand, latinized with -a (Art. 30.1.3)'),
}
# Misspellings and the name they misspell.
MISSPELLINGS = {
    'Ectatona': 'Ectatomma', 'Myopopona': 'Myopopone', 'Ophthalmopona': 'Ophthalmopone', 'Simopona': 'Simopone',
    'Lepalaea': 'Leptalea', 'Leptalaea': 'Leptalea', 'Ocodoma': 'Oecodoma', 'Tetramorum': 'Tetramorium',
    'Ceratopachys': 'Cerapachys', 'Myrtoteras': 'Myrmoteras',
}
# Left open on purpose, with the reason.
OPEN = {
    'Myrmentoma': 'entoma is a Greek neuter plural; AntCat names in -oma are neuter (4) and feminine (3)',
    'Myrmhopla': 'hopla is a Greek neuter plural; ends in -a',
    'Cephaloxys': 'oxys is a masculine adjective, but F. Smith combined it with capitata; read the original',
    'Forelifidis': 'not identified',
    'Myrmegis': 'not identified',
    'Savignyi': 'not a genus-group name in form',
}


def subject(name):
    m = re.search(r'\(([^)]+)\)\s*$', name.strip())
    return (m.group(1) if m else name.strip().split()[-1]).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--genus-gender', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--disagreements', required=True)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.genus_gender, encoding='utf-8'), delimiter='\t'))
    genus = defaultdict(set)
    for r in rows:
        if r['rank'] == 'Genus' and r['gender']:
            genus[r['name'].strip()].add(r['gender'])
    known = {k: next(iter(v)) for k, v in genus.items() if len(v) == 1}

    out = []
    for r in rows:
        if r['gender']:
            continue
        n = subject(r['name'])
        low = n.lower()
        prop = tier = basis = ''
        if n in known:
            prop, tier, basis = known[n], 'A', f'AntCat records {known[n]} for the genus-rank name {n}'
        elif n in OPEN:
            tier, basis = 'C', OPEN[n]
        elif n in NAMES:
            prop, basis = NAMES[n]
            tier = 'K'
        elif n in MISSPELLINGS and MISSPELLINGS[n] in known:
            prop, tier = known[MISSPELLINGS[n]], 'M'
            basis = f'a misspelling of {MISSPELLINGS[n]} ({prop} in AntCat)'
        else:
            for L in range(len(low) - 1, 2, -1):
                suf = low[-L:]
                pool = [(k, v) for k, v in known.items() if k.lower().endswith(suf) and k.lower() != low]
                if len(pool) < 3:
                    continue
                c = Counter(v for _, v in pool)
                top, cnt = c.most_common(1)[0]
                if cnt == len(pool):
                    ex = ', '.join(sorted(k for k, _ in pool)[:3])
                    prop, tier = top, 'B'
                    basis = f'-{suf}: {len(pool)} AntCat genus names with this ending, all {top} (e.g. {ex})'
                elif len(pool) >= 8 and cnt / len(pool) >= 0.9:
                    odd = ', '.join(f'{k} {v}' for k, v in pool if v != top)
                    prop, tier = top, 'B2'
                    basis = f'-{suf}: {cnt} of {len(pool)} AntCat genus names with this ending are {top} (not: {odd})'
                break
            if not tier:
                for end, gender, why in sorted(FINALS, key=lambda f: -len(f[0])):
                    if low.endswith(end):
                        prop, tier, basis = gender, 'K', f'-{end}: {why}'
                        break
            if not tier:
                tier, basis = 'C', 'no rule applies'
        out.append(dict(r, subject=n, proposed=prop, tier=tier, basis=basis))

    fields = ['taxon_id', 'rank', 'name', 'status', 'subject', 'proposed', 'tier', 'basis']
    with open(a.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t', extrasaction='ignore')
        w.writeheader()
        w.writerows(sorted(out, key=lambda o: (o['tier'], o['subject'], o['name'])))

    # Records whose gender differs from the genus-rank record of the same name (a subgenus record that follows the
    # genus it is combined with), and names with two genders among genus-rank records.
    dis = []
    for r in rows:
        if not r['gender']:
            continue
        n = subject(r['name'])
        if r['rank'] == 'Subgenus' and n in known and known[n] != r['gender']:
            dis.append(dict(r, subject=n, expected=known[n], note='subgenus record carries another gender than the name'))
    for k, v in genus.items():
        if len(v) > 1:
            dis.append(dict(taxon_id='', rank='Genus', name=k, status='', gender='/'.join(sorted(v)), subject=k,
                            expected='', note='two genders among genus-rank records'))
    with open(a.disagreements, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['taxon_id', 'rank', 'name', 'status', 'gender', 'subject', 'expected', 'note'],
                           delimiter='\t', extrasaction='ignore')
        w.writeheader()
        w.writerows(dis)

    tiers = Counter(o['tier'] for o in out)
    print(f'records without gender: {len(out)}')
    for t in sorted(tiers):
        g = Counter(o['proposed'] or 'open' for o in out if o['tier'] == t)
        print(f'  tier {t}: {tiers[t]}  {dict(g)}')
    print(f'distinct names: {len({o["subject"] for o in out})}; with a proposal: '
          f'{len({o["subject"] for o in out if o["proposed"]})}')
    print(f'disagreements among recorded genders: {len(dis)}')


if __name__ == '__main__':
    main()
