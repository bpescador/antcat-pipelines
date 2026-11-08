#!/usr/bin/env python3
"""
selftest.py -- checks that reconcile_types.py and build_inserts.py still make the decisions
settled with Brian in June 2026, on a small made-up fixture (no real data, nothing written
outside a temporary folder).

  python3 antweb_types/selftest.py        # prints SELFTEST PASS or the failed checks

Each case below is one decision from the June chat (7b114e80, 8 Jun 2026):
  - spaced AntCat code "AMNH Bu-014" is the same specimen as AntWeb amnh-bu014 (already linked)
  - holotype/paratype swapped between the two sides is a rank disagreement (Pheidole mivory)
  - subgenus, connecting words (r., var.) and gender endings are not AntWeb fixes (israele/israelis)
  - a one-letter epithet difference is a "spelling" fix to check against the publication (sylvaini)
  - AntWeb naming a later combination is a "current_combination" fix (Syscia tolteca)
  - a code held under a different protonym is a misplacement (alapa holotype under dolabra)
  - a bare "holotype" routes by the determination; AntWeb paratypes give a secondary block
  - no AntWeb locality is ever written; material conflicts are flagged, not withheld
Added 2026-11-03 (build_inserts.py --flags / --institutions, Bradley's conventions of 2026-10-30):
  - replacement names and nomina nuda are held back, with a reason, not offered for entry
  - AntWeb depositories that are not AntCat codes are flagged; an [Also] alias names the AntCat code
  - primary and secondary text come in separate columns, one per AntCat field
Added 2026-11-08:
  - an NGC-style "Type-depository:" counts as a depository (no second depository line)
"""
import csv, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

PROTONYMS = [
    dict(protonym_id=1, name='Myanmyrma gracilis', author='Engel, M.S.; Grimaldi, D.A.', year=2005,
         primary_type_taxt='Primary type material: holotype worker. Primary type depository: AMNH. Primary type specimen: AMNH Bu-014.'),
    dict(protonym_id=2, name='Pheidole mivory', author='Salata, S.; Fisher, B.L.', year=2020,
         primary_type_taxt='Primary type material: holotype major worker. Primary type depository: CASC. Primary type specimen: CASENT0825256.',
         secondary_type_taxt='Secondary type depository: CASC. Secondary type specimens: CASENT0825255, CASENT0923288.'),
    dict(protonym_id=3, name='Tapinoma erraticum r. israelis', author='Forel, A.', year=1904,
         primary_type_taxt='Primary type depository: MHNG. Primary type specimen: ANTWEB1008471.'),
    dict(protonym_id=4, name='Strumigenys silvaini', author='Fisher, B.L.', year=2000,
         primary_type_taxt='Primary type depository: CASC. Primary type specimen: CASENT0005639.'),
    dict(protonym_id=5, name='Strumigenys alapa', author='Fisher, B.L.', year=2000, primary_type_taxt=''),
    dict(protonym_id=6, name='Strumigenys dolabra', author='Fisher, B.L.', year=2000,
         primary_type_taxt='Primary type depository: CASC. Primary type specimen: CASENT0005482, CASENT0005483.'),
    dict(protonym_id=7, name='Cerapachys (Parasyscia) toltecus', author='Forel, A.', year=1900,
         primary_type_taxt='Primary type depository: MHNG. Primary type specimen: CASENT0900007.'),
    dict(protonym_id=8, name='Haidomyrmex scimitarus', author='Barden, P.; Grimaldi, D.A.', year=2012,
         primary_type_taxt=''),
    dict(protonym_id=9, name='Pheidole pennsylvanica', author='Wheeler, W.M.', year=1928,
         primary_type_taxt='Primary type material: holotype major worker. Primary type locality: U.S.A. Primary type depository: MCZC.'),
    dict(protonym_id=10, name='Pyramica moloch', author='Bolton, B.', year=2000,
         primary_type_taxt='Primary type material: lectotype worker. Primary type depository: BMNH. Primary type specimen: CASENT0900001.'),
    dict(protonym_id=11, name='Kartidris nyos', author='Xu, Z.; Zhang, J.', year=2002,
         primary_type_taxt='Primary type material: holotype worker. Primary type locality: China.'),
    dict(protonym_id=12, name='Camponotus novum', author='Smith, A.', year=1950, primary_type_taxt=''),
    dict(protonym_id=13, name='Pheidole nuda', author='Smith, A.', year=1951, primary_type_taxt=''),
    dict(protonym_id=14, name='Pheidole costaricensis', author='Longino, J.T.', year=2009,
         primary_type_taxt='Primary type material: holotype major worker. Primary type depository: INBio.'),
    dict(protonym_id=15, name='Lasius stutt', author='Smith, A.', year=1952,
         primary_type_taxt='Primary type material: holotype worker. Primary type depository: SMNK.'),
    dict(protonym_id=16, name='Acanthomyrmex careo', author='Moffett, M.W.', year=1986,
         primary_type_taxt='Type-material: holotype minor worker. Type-locality: Malaysia. Type-depository: BMNH.'),
]
FLAGS = [dict(protonym_id=12, name_type='SpeciesName', nomen_nudum=False, replacement_name=True,
              replacement_name_taxt=False, taxon_statuses=['valid']),
         dict(protonym_id=13, name_type='SpeciesName', nomen_nudum=True, replacement_name=False,
              replacement_name_taxt=False, taxon_statuses=['unavailable'])]
INSTITUTIONS = [dict(abbreviation=a, name=n) for a, n in [
    ('AMNH', 'American Museum of Natural History'), ('MCZC', 'Museum of Comparative Zoology'),
    ('BMNH', 'Natural History Museum, London'), ('IZAS', 'Institute of Zoology, Beijing'),
    ('INBio', '[Also INBC] Instituto Nacional de Biodiversidad, Costa Rica'),
    ('SMNK', 'Staatliches Museum fuer Naturkunde, Karlsruhe')]]
AW_COLS = ['code', 'type_status', 'genus', 'species', 'subspecies', 'ownedby', 'country',
           'localityname', 'caste', 'life_stage']
AW_ROWS = [
    ['amnh-bu014', 'holotype of Myanmyrma gracilis Engel & Grimaldi, 2005', 'Myanmyrma', 'gracilis', '', 'AMNH', 'Myanmar', 'Kachin', 'worker', ''],
    ['casent0825255', 'holotype of Pheidole mivory Salata & Fisher, 2020', 'Pheidole', 'mivory', '', 'CASC', 'Madagascar', 'X', 'worker', ''],
    ['casent0825256', 'paratypes of Pheidole mivory Salata & Fisher, 2020', 'Pheidole', 'mivory', '', 'CASC', 'Madagascar', 'X', 'worker', ''],
    ['antweb1008471', 'syntype of Tapinoma erraticum israele Forel, 1904', 'Tapinoma', 'israelis', '', 'MHNG', 'Israel', 'X', 'worker', ''],
    ['casent0005639', 'holotype of Strumigenys sylvaini Fisher, 2000', 'Strumigenys', 'sylvaini', '', 'CASC', 'Madagascar', 'X', 'worker', ''],
    ['casent0005482', 'holotype of Strumigenys dolabra Fisher, 2000', 'Strumigenys', 'dolabra', '', 'CASC', 'Madagascar', 'X', 'worker', ''],
    ['casent0005483', 'holotype of Strumigenys alapa Fisher, 2000', 'Strumigenys', 'alapa', '', 'CASC', 'Madagascar', 'X', 'worker', ''],
    ['casent0900007', 'syntype of Syscia tolteca Forel, 1900', 'Syscia', 'tolteca', '', 'MHNG', 'Mexico', 'X', 'worker', ''],
    ['amnh-bufb80', 'holotype', 'Haidomyrmex', 'scimitarus', '', 'AMNH', 'Myanmar', 'Kachin amber', 'queen', ''],
    ['amnh-bufb81', 'paratype of Haidomyrmex scimitarus Barden & Grimaldi, 2012', 'Haidomyrmex', 'scimitarus', '', 'AMNH', 'Myanmar', 'Kachin amber', 'queen', ''],
    ['casent0911221', 'syntype of Pheidole pennsylvanica Wheeler, 1928', 'Pheidole', 'pennsylvanica', '', 'MCZC', 'USA', 'Massachusetts', 'major worker', ''],
    ['casent0900193', 'lectotype of Pyramica moloch Bolton, 2000', 'Pyramica', 'moloch', '', 'BMNH', 'Malaysia', 'X', 'worker', ''],
    ['casent0900011', 'holotype of Kartidris nyos Xu & Zhang, 2002', 'Kartidris', 'nyos', '', 'IZAS', 'China', 'Yunnan, somewhere', 'worker', ''],
    ['casent0999999', 'holotype of Nonexistus fakeus Smith, 1999', 'Nonexistus', 'fakeus', '', 'CASC', 'Peru', 'X', 'worker', ''],
    ['casent0900012', 'holotype of Camponotus novum Smith, 1950', 'Camponotus', 'novum', '', 'AMNH', 'USA', 'X', 'worker', ''],
    ['casent0900013', 'syntype of Pheidole nuda Smith, 1951', 'Pheidole', 'nuda', '', 'AMNH', 'USA', 'X', 'worker', ''],
    ['inb0003000002', 'paratype of Pheidole costaricensis Longino, 2009', 'Pheidole', 'costaricensis', '', 'INBC', 'Costa Rica', 'X', 'major worker', ''],
    ['inb0003000001', 'holotype of Pheidole costaricensis Longino, 2009', 'Pheidole', 'costaricensis', '', 'INBC', 'Costa Rica', 'X', 'major worker', ''],
    ['casent0900015', 'holotype of Lasius stutt Smith, 1952', 'Lasius', 'stutt', '', 'SMNS Stuttgart', 'Germany', 'X', 'worker', ''],
    ['casent0900016', 'holotype of Acanthomyrmex careo Moffett, 1986', 'Acanthomyrmex', 'careo', '', 'NHMUK', 'Malaysia', 'X', 'minor worker', ''],
]

fails = []
def check(ok, what):
    if not ok: fails.append(what)

def main():
    with tempfile.TemporaryDirectory() as d:
        pj, aw = os.path.join(d, 'prot.jsonl'), os.path.join(d, 'aw.tsv')
        with open(pj, 'w') as f:
            for p in PROTONYMS: f.write(json.dumps(p) + '\n')
        with open(aw, 'w', newline='') as f:
            w = csv.writer(f, delimiter='\t'); w.writerow(AW_COLS); w.writerows(AW_ROWS)
        run = lambda *a: subprocess.run([sys.executable, *a], capture_output=True, text=True)
        r1 = run(os.path.join(HERE, 'reconcile_types.py'), pj, aw, d)
        check(r1.returncode == 0, f'reconcile_types.py failed: {r1.stderr[-400:]}')
        r2 = run(os.path.join(HERE, 'build_inserts.py'), pj, aw, os.path.join(d, 'type_link_queue.csv'), d)
        check(r2.returncode == 0, f'build_inserts.py failed: {r2.stderr[-400:]}')
        if fails: return
        rd = lambda n, dd=d: list(csv.DictReader(open(os.path.join(dd, n))))
        tier = {r['code']: r['tier'] for r in rd('type_link_queue.csv')}
        mm = {(r['code'], r['type']) for r in rd('review_mismatches.csv')}
        fx = {r['code']: r['fix_type'] for r in rd('antweb_typestatus_fixes.csv')}
        adds = {r['protonym_id']: r for r in rd('primary_adds.csv')}
        june_held_file = os.path.exists(os.path.join(d, 'primary_adds_held.csv'))
        # second run with the 2026-11-03 options
        fj, ij, d2 = os.path.join(d, 'flags.jsonl'), os.path.join(d, 'inst.jsonl'), os.path.join(d, 'opt')
        os.makedirs(d2)
        with open(fj, 'w') as f:
            for x in FLAGS: f.write(json.dumps(x) + '\n')
        with open(ij, 'w') as f:
            for x in INSTITUTIONS: f.write(json.dumps(x) + '\n')
        r3 = run(os.path.join(HERE, 'build_inserts.py'), pj, aw, os.path.join(d, 'type_link_queue.csv'), d2,
                 f'--flags={fj}', f'--institutions={ij}')
        check(r3.returncode == 0, f'build_inserts.py with options failed: {r3.stderr[-400:]}')
        if fails: return
        adds2 = {r['protonym_id']: r for r in rd('primary_adds.csv', d2)}
        held2 = {r['protonym_id']: r for r in rd('primary_adds_held.csv', d2)}

    check(tier.get('amnh-bu014') == 'already_linked', 'spaced code AMNH Bu-014 not matched to amnh-bu014')
    check(('casent0825255', 'rank') in mm and ('casent0825256', 'rank') in mm, 'mivory holotype/paratype swap not flagged as rank')
    check('antweb1008471' not in fx, 'israele/israelis (connecting word + gender ending) flagged as an AntWeb fix')
    check(fx.get('casent0005639') == 'spelling', 'sylvaini/silvaini not flagged as spelling')
    check(fx.get('casent0900007') == 'current_combination', 'Syscia tolteca not flagged as current_combination')
    check(('casent0005483', 'misplacement') in mm, 'alapa holotype under dolabra not flagged as misplacement')
    check(tier.get('casent0999999') == 'nomatch', 'unknown protonym not nomatch')
    check(set(adds) == {'8', '9', '10', '11', '12', '13', '14', '15', '16'}, f'primary_adds protonyms {sorted(adds)} != 8 to 16 (June mode holds nothing)')
    check(not june_held_file, 'June mode wrote a held file')
    a = adds.get('8', {})
    check(a.get('case') == 'full_block' and a.get('needs_locality', '').startswith('yes'), 'bare holotype not a full_block needing locality')
    check('Primary type specimen: AMNH-BUFB80.' in a.get('add_text', ''), 'full block lacks the bare uppercase code AMNH-BUFB80')
    check('Secondary type specimens: AMNH-BUFB81.' in a.get('add_text', ''), 'full block lacks the secondary block from the AntWeb paratype')
    check('locality' not in a.get('add_text', '').lower() and 'kachin' not in a.get('add_text', '').lower(),
          'an AntWeb-derived locality was written into add_text')
    check(adds.get('9', {}).get('material_flag') == 'AntWeb syntype vs AntCat material holotype', 'syntype-vs-holotype material conflict not flagged')
    check(adds.get('9', {}).get('case') == 'specimen_addline', 'pennsylvanica not specimen_addline (link must still be added)')
    check(adds.get('10', {}).get('add_text') == 'append to existing Primary type specimen line: , CASENT0900193', 'moloch append text wrong')
    check(adds.get('11', {}).get('add_text') == 'add lines: Primary type depository: IZAS. Primary type specimen: CASENT0900011.', 'nyos add_depository text wrong')
    check(adds.get('16', {}).get('case') == 'specimen_addline', 'NGC-style "Type-depository:" not seen: a second depository line would be added')
    # 2026-11-03 options
    check(set(adds2) == {'8', '9', '10', '11', '14', '15', '16'}, f'with --flags, primary_adds protonyms {sorted(adds2)} != 8 to 11, 14 to 16')
    check(held2.get('12', {}).get('hold_reason') == 'replacement name', 'replacement name not held')
    check(held2.get('13', {}).get('hold_reason') == 'nomen nudum; unavailable name', f"nomen nudum hold reason: {held2.get('13', {}).get('hold_reason')}")
    check(adds2.get('14', {}).get('depository_check') == 'AntWeb INBC = AntCat INBio ([Also] note)', 'INBC alias not resolved to INBio')
    check(adds2.get('15', {}).get('depository_check') == 'not an AntCat code: SMNS Stuttgart', 'non-code ownedby not flagged')
    check(all(adds2[k]['depository_check'] == '' for k in ('8', '9', '10', '11')), 'a valid AntCat code was flagged')
    a2 = adds2.get('8', {})
    check(a2.get('primary_add', '').endswith('Primary type specimen: AMNH-BUFB80.') and 'Secondary' not in a2.get('primary_add', ''),
          'primary_add holds more than the primary block')
    check(a2.get('secondary_add') == 'Secondary type material: paratype queens (number not stated). Secondary type depository: AMNH. Secondary type specimens: AMNH-BUFB81.',
          'secondary_add wrong')
    check(a2.get('add_text') == adds.get('8', {}).get('add_text'), 'add_text changed by the options')


if __name__ == '__main__':
    main()
    if fails:
        print('SELFTEST FAIL'); [print('  -', f) for f in fails]; sys.exit(1)
    print('SELFTEST PASS')
