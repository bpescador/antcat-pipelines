#!/usr/bin/env python3
"""
propose_part_of_speech_by_form.py -- part of speech where the form of the epithet decides it (pattern-by-pattern
plan, Brian 14 Nov 2026 21:43; his two open questions of 21:53 answered from the Code and the literature, 21:59).

Rule ensis_form_pos -- every epithet ending in -ensis or -ense:
  The Latin suffix -ensis forms adjectives "belonging to, coming from" (Allen & Greenough, New Latin Grammar,
  sect. 249: forensis, Siciliensis); geographical epithets in -ensis, -anus, -inus, -icus are adjectives (Stearn
  1973: 214, Botanical Latin, cited by Manara 1992, Taxon 41: 524; ICBN Rec. 73D.1); -ensis/-ense is a
  two-termination adjective "indicating provenience" (Pellizzari & Williams 2013, Zootaxa 3710: 403, Table 2).
  Latin has no noun in -ensis but ensis 'sword' itself (none of AntCat's 1,600 is a compound of it). So the form
  demonstrates a Latin adjective (ICZN Art. 31.2; AntCat policy on name grammar and spelling, Rule 1.1), and the
  ambiguity default of Art. 31.2.2 (Rule 1.5) does not arise. Place matched or not: the place decides only the
  derivation, which is a separate field.
  -> adjective; basis author_stated where the published etymology calls it an adjective, else grammatical_form;
     demonstrated.
  Held: a part of speech other than adjective already recorded (never overwritten; listed for Brian); a published
  etymology that calls it a noun while no part of speech is recorded (the policy adopts the adjective but the
  disagreement needs a public note first, Rule 1, last paragraph); interpretation disputed or unresolved.

Rule toponym_anus_pos -- the toponym derivations in -anus/-ana/-anum (verified place stem, written 14 Nov):
  -anus forms adjectives "especially from proper nouns to denote belonging to or coming from" (Allen & Greenough
  sect. 249.2: Romanus); modern place adjectives in -anus (Stearn 1973; Manara 1992: mexicanus, texanus).
  With the place stem verified the suffix cannot be part of a personal name or a Latin noun.
  -> adjective; grammatical_form; demonstrated. Other -anus names wait for their own stem test.

Inputs: --protonyms (gender/protonym_pages_export.rb TSV), --derivations (the toponym derivation write input).
Outputs: --out (every candidate with its rule, result and reason), --write-input (rows for
gender/write_protonym_fields.rb), --held (held rows for Brian). Standard library only; read only.
"""
import argparse, collections, csv, hashlib, re, sys

csv.field_size_limit(sys.maxsize)
NOUN_STATEMENT = re.compile(r'\bnoun\b|apposition|substantiv', re.I)
ADJ_STATEMENT = re.compile(r'adjectiv', re.I)


def read_tsv(path, quoting=csv.QUOTE_MINIMAL):
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t', quoting=quoting))


def locality_md5(p):
    return hashlib.md5(re.sub(r'[\t\r\n]+', ' ', p['locality']).encode('utf-8')).hexdigest()


def ensis(p):
    """-> (result, reason, basis)"""
    ety = p['etymology_taxt']
    says_noun = bool(NOUN_STATEMENT.search(ety)) and not ADJ_STATEMENT.search(ety)
    says_adj = bool(ADJ_STATEMENT.search(ety))
    if p['part_of_speech'] not in ('', 'adjective'):
        return 'held', f"part of speech recorded as {p['part_of_speech']} (never overwritten)", ''
    if p['interpretation_status'] in ('disputed', 'unresolved'):
        return 'held', f"interpretation is {p['interpretation_status']}", ''
    if says_noun and not p['part_of_speech']:
        return 'held', 'the published etymology calls it a noun: needs a public note before the adjective', ''
    return 'proposed', '', 'author_stated' if says_adj else 'grammatical_form'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--derivations', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--write-input')
    ap.add_argument('--held')
    a = ap.parse_args()

    prot = read_tsv(a.protonyms)
    by_id = {p['protonym_id']: p for p in prot}
    anus_ids = set()
    for d in read_tsv(a.derivations, quoting=csv.QUOTE_NONE):
        if '<i>-anus</i>' in d['derivation']:
            p = by_id.get(d['protonym_id'])
            if p and p['protonym_name'] == d['protonym_name'] and re.search(r'(anus|ana|anum)$', p['epithet']):
                anus_ids.add(d['protonym_id'])

    out, counts = [], collections.Counter()
    for p in prot:
        if re.search(r'(ensis|ense)$', p['epithet'].lower()):
            rule = 'ensis_form_pos'
            result, reason, basis = ensis(p)
        elif p['protonym_id'] in anus_ids:
            rule = 'toponym_anus_pos'
            if p['part_of_speech'] not in ('', 'adjective'):
                result, reason, basis = 'held', f"part of speech recorded as {p['part_of_speech']}", ''
            elif p['etymology_taxt'].strip():
                result, reason, basis = 'held', 'has a sourced etymology', ''
            else:
                result, reason, basis = 'proposed', '', 'grammatical_form'
        else:
            continue
        counts[f'{rule}: {result}' + (f' ({reason.split(" (")[0].split(":")[0]})' if reason else '')] += 1
        out.append((p, rule, result, reason, basis))

    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'epithet', 'year', 'part_of_speech', 'interpretation_status',
                    'rule', 'result', 'reason', 'basis', 'etymology'])
        for p, rule, result, reason, basis in out:
            w.writerow([p['protonym_id'], p['protonym_name'], p['epithet'], p['year'], p['part_of_speech'],
                        p['interpretation_status'], rule, result, reason, basis,
                        re.sub(r'\s+', ' ', p['etymology_taxt'])[:300]])
    if a.write_input:
        with open(a.write_input, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar='\\')
            w.writerow(['protonym_id', 'protonym_name', 'rule', 'field', 'value', 'locality_md5'])
            for p, rule, result, reason, basis in out:
                if result != 'proposed':
                    continue
                md5 = locality_md5(p) if rule == 'toponym_anus_pos' else ''
                for field, value in [('gender_agreement_type', 'adjective'), ('part_of_speech_basis', basis),
                                     ('interpretation_status', 'demonstrated')]:
                    w.writerow([p['protonym_id'], p['protonym_name'], rule, field, value, md5])
    if a.held:
        with open(a.held, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n')
            w.writerow(['protonym_id', 'protonym_name', 'author_citation', 'epithet', 'part_of_speech', 'rule',
                        'reason', 'etymology'])
            for p, rule, result, reason, basis in out:
                if result == 'held':
                    w.writerow([p['protonym_id'], p['protonym_name'], p['author_citation'], p['epithet'],
                                p['part_of_speech'], rule, reason, re.sub(r'\s+', ' ', p['etymology_taxt'])])
    for k in sorted(counts):
        print(f'{counts[k]:5d}  {k}')
    print('candidates', len(out))


if __name__ == '__main__':
    main()
