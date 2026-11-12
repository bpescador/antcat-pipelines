#!/usr/bin/env python3
"""
propose_part_of_speech.py -- Phase 1 of the gender-agreement plan: scripted part-of-speech proposals
for AntCat species-group protonyms whose current spelling differs from the original. Read only:
writes a proposals TSV and a summary; nothing goes to AntCat until the proposals are reviewed.

Why: TaxonWorks computes current spellings from the protonym's part of speech and the genus gender.
Without part of speech in AntCat, TW's spellings drift from AntCat's (trochis/troche, Nov 2026).
Plan: claude/GENDER_AGREEMENT_PLAN.md, Phase 1 (rules below, in order).

  1 original ends -i, -ae, -orum, -arum      noun_in_genitive_case   high    changed spelling: probable error
  2 -ensis/-ense, current -ensis or -ense     adjective               high
  3 other -is or -e                           manual                  none    the trochis trap: noun or adjective
    -cola/-colus/-colum (dweller)             manual                  none    sphagnicolus -> sphagnicola (Nov 2026):
                                                                              a noun keeps its original spelling
    compound ending in a noun (-cephalus,     manual                  none    noun phrase under Yanega's reading
    -spinus, -nodus, -scapus, -notus...)                                      (Littauer 2025), adjective under Bolton's:
                                                                              AntCat policy decision (Nov 2026)
  4 -us -a -um -er -ra -rum -ior -ius, and the current spelling is one of the three predicted forms
                                              adjective               medium  sample-check against originals
  5 current spelling matches no predicted form: not a pure gender change (emendation, misspelling,
    irregular adjective); listed, no proposal

predict_three_forms is ported from TaxonWorks (lib/utilities/nomenclature.rb, SpeciesFileGroup/taxonworks,
development branch checked 2026-09-24), with its table of irregular adjectives (gender/latin_adjectives.py,
copied 2026-11-12 from 5dea15e). TW computes the three spellings itself from part of speech and genus gender;
this copy only keeps AntCat's proposals identical to what TW will show.

Input:  --names antcat_names.tsv (export_antcat_names.py: original_epithet, spelling_differs)
        --genus-gender genus_gender.tsv (optional; gender/gender_baseline.rb): rule 4 rows whose current
          ending disagrees with the current genus's gender are noted (Strumigenys calvus, Nov 2026)
        --set part_of_speech_set.tsv (optional; gender/gender_baseline.rb): the part of speech editors
          already set. It wins over the proposal; where they differ the row is flagged, because either the
          typed value or the current spelling is wrong (Leptanilloides prometea, Nov 2026)
Output: --out folder: part_of_speech_proposals.tsv, summary.txt
"""
import argparse, collections, csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from latin_adjectives import LATIN_ADJECTIVES  # noqa: E402  (TaxonWorks' table)

csv.field_size_limit(sys.maxsize)


def predict_three_forms(name):
    """-> (masculine, feminine, neuter), as TaxonWorks' Utilities::Nomenclature.predict_three_forms,
    including its table of irregular adjectives (acer/acris/acre...), checked first as TW does"""
    if name in LATIN_ADJECTIVES:
        return LATIN_ADJECTIVES[name]
    n = name
    if re.search(r'color(is)?$', n):
        return (n, n, n)
    if n.endswith('is'):
        return (n, n, n[:-2] + 'e')
    if n.endswith('e'):
        return (n[:-1] + 'is', n[:-1] + 'is', n)
    if n.endswith('us'):
        return (n, n[:-2] + 'a', n[:-2] + 'um')
    if n in ('niger', 'integer'):
        return (n, n[:-2] + 'ra', n[:-2] + 'rum')
    if re.search(r'(fer|ger)$', n):
        return (n, n + 'a', n + 'um')
    if n.endswith('er'):
        return (n, n[:-2] + 'ra', n[:-2] + 'rum')
    m = re.search(r'(fer|ger)(um|a)$', n)
    if m:
        b = n[:m.end(1)]
        return (b, b + 'a', b + 'um')
    m = re.search(r'([bfg])r(um|a)$', n)
    if m:
        b = n[:m.start(1) + 1]
        return (b + 'er', b + 'ra', b + 'rum')
    if n.endswith('um') or n.endswith('a'):
        b = n[:-2] if n.endswith('um') else n[:-1]
        return (b + 'us', b + 'a', b + 'um')
    if re.search(r'(nor|ior|jor)$', n):
        return (n, n, n[:-2] + 'us')
    return (n, n, n)


# Compounds whose last element is a Greek or Latin noun (head, spine, node, back, scape, jaw, tail...).
# Commissioner Yanega's letter of 26 Sep 2025 (Chelaner longinode; followed in Littauer 2025): such
# compounds are noun phrases and keep their original ending, whatever it is; Bolton declined them.
NOUN_COMPOUND = re.compile(r'^[a-z]{3,}?(nod|not|dors|scap|gnath|cephal|ophthalm|pter|mer|som|acanth|spin|lob|'
                           r'carin|cost|crist|squam|pyg|cer|cnem|derm|gastr|rhach|stern|ommat|ur)(us|a|um)$')


def classify(orig, cur, gender=''):
    forms = predict_three_forms(orig)
    if re.search(r'(i|ae|orum|arum)$', orig):
        note = ('genitive noun: the change is not a gender change (emendation, misspelling or error): check'
                if cur != orig else '')
        return 1, 'noun_in_genitive_case', 'high', note
    if re.search(r'i?ens(is|e)$', orig) and re.search(r'i?ens(is|e)$', cur):
        return 2, 'adjective', 'high', ''          # -ense too: Monomorium howense -> Chelaner howensis
    if re.search(r'(is|e)$', orig):
        return 3, 'manual', 'none', 'noun or adjective: check the etymology'
    if re.search(r'col(a|us|um)$', orig):
        return 3, 'manual', 'none', '-cola (dweller) is a noun, which keeps its original spelling: check'
    if NOUN_COMPOUND.match(orig) and not re.search(r'(obscur|impur|matur|^pur|ignot|sincer)', orig):
        return 3, 'manual', 'none', ('compound ending in a noun (-cephalus, -spinus, -nodus...): a noun phrase, '
                                     'invariable, under the Glossary as read by Yanega (Littauer 2025); '
                                     'declined as an adjective by Bolton: AntCat policy decision')
    if re.search(r'(us|a|um|er|ra|rum|ior|ius)$', orig) and cur in forms:
        want = dict(zip(('masculine', 'feminine', 'neuter'), forms)).get(gender)
        if want and cur != want:
            return 4, 'adjective', 'medium', f'ending disagrees with the {gender} genus: expected {want}'
        return 4, 'adjective', 'medium', '' if gender else 'genus gender not given'
    if cur not in forms:
        return 5, '', 'n/a', 'current spelling is none of the predicted forms ' + '/'.join(forms)
    return 0, '', 'n/a', 'no rule'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--names', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--genus-gender')
    ap.add_argument('--set')
    a = ap.parse_args()
    typed = {}
    if a.set:
        typed = {t['taxon_id']: t['gender_agreement_type']
                 for t in csv.DictReader(open(a.set, encoding='utf-8'), delimiter='\t')}
    gender = {}
    if a.genus_gender:
        for g in csv.DictReader(open(a.genus_gender, encoding='utf-8'), delimiter='\t'):
            if g['rank'] == 'Genus' and g['gender']:
                gender.setdefault(g['name'], set()).add(g['gender'])
        gender = {k: v.pop() for k, v in gender.items() if len(v) == 1}   # homonymous genera: skip
    os.makedirs(a.out, exist_ok=True)
    rows = [r for r in csv.DictReader(open(a.names, encoding='utf-8'), delimiter='\t')
            if r['spelling_differs'] == 'TRUE']
    out, stats = [], collections.Counter()
    for r in rows:
        orig = r['original_epithet'].strip().lower()
        cur = (r['subspecies'] or r['species']).strip().lower()
        rule, pos, conf, note = classify(orig, cur, gender.get(r['genus'], ''))
        have = typed.get(r['antcat_id'], '')
        if have and have != pos and not (have == 'participle' and pos == 'adjective'):
            # a changed spelling is only right for an adjective or participle
            note = (f'typed {have}, but the spelling was changed: the typed value or the spelling is wrong'
                    if have.startswith('noun') else f'typed {have}: settles the manual check' if pos == 'manual'
                    else f'typed {have}; proposal {pos or "none"}') + (f'; {note}' if note else '')
        stats[(rule, pos or '-', r['status'])] += 1
        out.append(dict(antcat_id=r['antcat_id'], current_name=r['scientific_name'], status=r['status'],
                        original_combination=r['original_combination'], original_epithet=orig,
                        current_epithet=cur, forms='/'.join(predict_three_forms(orig)), rule=rule,
                        proposed_part_of_speech=pos, confidence=conf, typed_part_of_speech=have, note=note))
    out.sort(key=lambda d: (d['rule'], d['current_name']))
    with open(os.path.join(a.out, 'part_of_speech_proposals.tsv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()), delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(out)
    by_rule = collections.Counter(d['rule'] for d in out)
    valid = collections.Counter(d['rule'] for d in out if d['status'] == 'valid')
    names = {1: 'genitive noun', 2: '-ensis adjective', 3: 'manual (-is/-e)', 4: 'adjective (-us/-a/-um...)',
             5: 'not a pure gender change', 0: 'no rule'}
    lines = [f'protonyms with a changed spelling: {len(out)} (valid {sum(valid.values())})'] + \
            [f'  rule {k} {names[k]}: {by_rule[k]} (valid {valid[k]})' for k in sorted(by_rule)] + \
            [f'  rule 4 endings that disagree with the genus gender: '
             f'{sum(1 for d in out if "ending disagrees" in d["note"])}',
             f'  part of speech already typed: {sum(1 for d in out if d["typed_part_of_speech"])}; '
             f'typed noun but spelling changed: {sum(1 for d in out if "the typed value or the spelling" in d["note"])}']
    open(os.path.join(a.out, 'summary.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
