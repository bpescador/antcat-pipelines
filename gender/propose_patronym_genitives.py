#!/usr/bin/env python3
"""
propose_patronym_genitives.py -- queue Q3 of the pattern-by-pattern plan: personal-name genitives
(-i, -ii, -ae, -orum, -arum). Read only; proposals for Brian's rule review, nothing written.

Brian, 14 Nov 2026 21:43: do not classify every -i/-ae ending as a personal-name genitive merely because the stem
is not a Latin word. Three levels:
  demonstrated         direct evidence: the published etymology states the dedication or the genitive
  reasonably inferred  the stem matches a documented personal name, the genitive formation fits (Art. 31.1.2),
                       and no substantial competing reading exists
  unresolved           ambiguous form, or the stem is not documented as a person
A documented name (AntCat author; collector in AntCat's type records; person in the original description)
supports the stem, never the honoree. Spellings are never emended (Art. 31.1.3; Dubois 2007).

Competing readings checked: the epithet is a Latin word or form (Lewis & Short, gender/lexicon.py), e.g. a
common-noun genitive (formicae); the stem is a place in the AntCat locality.

Inputs: --protonyms (protonym_pages_export.rb TSV), --types (protonyms_species_typeinfo.jsonl.gz),
--references (export_references.rb CSV), --lexicon (lexicon.py index). Outputs: --out (every candidate),
--sample (30 for Brian's review, stratified). Standard library only.
"""
import argparse, collections, csv, gzip, json, random, re, sys, unicodedata, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexicon import load as load_lexicon, lookup  # noqa: E402

csv.field_size_limit(sys.maxsize)
GENITIVE = re.compile(r'(orum|arum|ii|i|ae)$')


def fold(s):
    s = s.replace('ß', 'ss').replace('æ', 'ae').replace('ø', 'o')
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def surname_keys(name):
    """'Müller' -> {'muller', 'mueller'}; 'de Andrade' -> {'deandrade', 'andrade'}"""
    raw = name.strip()
    keys = set()
    plain = re.sub(r'[^a-z]', '', fold(raw))
    if plain:
        keys.add(plain)
    umlaut = re.sub(r'[^a-z]', '', fold(raw.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')))
    if umlaut:
        keys.add(umlaut)
    parts = re.split(r'[\s\'-]+', raw)
    if len(parts) > 1:
        last = re.sub(r'[^a-z]', '', fold(parts[-1]))
        if len(last) > 2:
            keys.add(last)
    return {k for k in keys if len(k) > 2}


def stems(epithet):
    """Possible name stems for a genitive epithet, with the formation."""
    e = fold(epithet)
    out = []
    for end, how in [('orum', '-orum (several, with a man)'), ('arum', '-arum (several women)'),
                     ('ii', '-ii'), ('ae', '-ae'), ('i', '-i')]:
        if e.endswith(end) and len(e) > len(end) + 2:
            st = e[: -len(end)]
            out.append((st, how))
            if end == 'ii':
                out.append((st + 'i', '-i on a name ending in -i'))
            if end == 'ae':
                out.append((st + 'a', '-ae on a name ending in -a'))
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--types', required=True)
    ap.add_argument('--references', required=True)
    ap.add_argument('--lexicon', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sample')
    a = ap.parse_args()

    authors = collections.defaultdict(set)  # key -> surnames as written
    with open(a.references, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            for person in (r.get('authors') or '').split(';'):
                sur = person.split(',')[0].strip()
                if sur:
                    for k in surname_keys(sur):
                        authors[k].add(sur)
    collectors = collections.defaultdict(set)
    type_text = {}
    with gzip.open(a.types, 'rt', encoding='utf-8') as fh:
        for line in fh:
            t = json.loads(line)
            txt = ' '.join(x or '' for x in (t.get('primary_type_taxt'), t.get('secondary_type_taxt'), t.get('type_notes_taxt')))
            type_text[str(t['protonym_id'])] = txt
            for who in re.findall(r'<i>([^<]+)</i>', txt):
                for person in re.split(r'\s*(?:,|&|\band\b)\s*', who):
                    toks = [x for x in re.split(r'\s+', person.strip()) if x and not re.fullmatch(r'[A-Z]\.?|[A-Z]\.[A-Z]\.?|et|al\.?', x)]
                    if toks:
                        for k in surname_keys(toks[-1]):
                            collectors[k].add(toks[-1])
    lex = load_lexicon(a.lexicon)
    with open(a.protonyms, encoding='utf-8', newline='') as fh:
        prot = list(csv.DictReader(fh, delimiter='\t'))

    out, counts = [], collections.Counter()
    for p in prot:
        ep = p['epithet']
        if not GENITIVE.search(fold(ep)) or re.search(r'(ensis|ense)$', ep):
            continue
        readings = [r for r in lookup(lex, ep) if r['kind'] != 'proper noun' and r['matched'] == 'as spelled']
        level, reason, person, how, source = 'unresolved', '', '', '', ''
        loc = fold(p['locality'] + ' ' + type_text.get(p['protonym_id'], ''))
        ety = p['etymology_taxt']
        if readings:
            level, reason = 'not this queue', f"a Latin word as spelled ({readings[0]['headword']}, {readings[0]['kind']})"
        else:
            words = re.sub(r'[^a-z ]', ' ', fold(p['locality'])).split()
            place = next((w for st, _ in stems(ep) for w in words if len(st) > 3 and w.startswith(st)), '')
            if place:
                level, reason = 'unresolved', f'the stem is also a place in the type locality ({place})'
        if not readings and not reason:
            for st, h in stems(ep):
                own = [c for c in collectors.get(st, ()) if fold(c) in loc or st in loc]
                if ety.strip() and re.search(st, fold(ety)):
                    level, person, how, source = 'demonstrated', st, h, 'named in the published etymology'
                    break
                if own:
                    level, person, how, source = 'reasonably inferred', sorted(own)[0], h, "collector of this name's type material"
                    break
                if st in authors:
                    level, person, how, source = 'reasonably inferred', sorted(authors[st])[0], h, 'author in AntCat'
                    break
                if st in collectors:
                    level, person, how, source = 'reasonably inferred', sorted(collectors[st])[0], h, "collector in AntCat's type records"
                    break
            if level == 'unresolved' and not reason:
                st0 = stems(ep)[0][0] if stems(ep) else ''
                if st0 and len(st0) > 3 and st0 in re.sub(r'[^a-z ]', ' ', loc).split():
                    reason = f'the stem {st0} is a word of the type locality: possibly a place'
                else:
                    reason = 'stem not documented as a person in AntCat'
        counts[level + (f' ({source})' if source else '')] += 1
        out.append([p['protonym_id'], p['protonym_name'], p['author_citation'], ep, p['part_of_speech'], level,
                    person, how, source, reason, re.sub(r'\s+', ' ', ety)[:200]])

    cols = ['protonym_id', 'protonym_name', 'author_citation', 'epithet', 'part_of_speech', 'level', 'person',
            'formation', 'evidence', 'reason', 'etymology']
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(cols)
        w.writerows(out)
    if a.sample:
        random.seed(15)
        by = collections.defaultdict(list)
        for r in out:
            by[(r[5], r[8])].append(r)
        quota = {('reasonably inferred', 'author in AntCat'): 8,
                 ('reasonably inferred', "collector of this name's type material"): 6,
                 ('reasonably inferred', "collector in AntCat's type records"): 5,
                 ('demonstrated', 'named in the published etymology'): 3}
        pick = []
        for k, n in quota.items():
            pick += random.sample(by.get(k, []), min(n, len(by.get(k, []))))
        rest = [r for r in out if r[5] in ('unresolved', 'not this queue')]
        pick += random.sample(rest, min(30 - len(pick), len(rest)))
        with open(a.sample, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n')
            w.writerow(cols + ['proposed_part_of_speech', 'proposed_derivation', 'brian_decision'])
            for r in pick:
                pos = 'noun_in_genitive_case' if r[5] in ('demonstrated', 'reasonably inferred') else ''
                ending = re.search(r'(orum|arum|ii|ae|i)$', fold(r[3])).group(1)
                der = (f"Personal name: formed as the genitive (Latin <i>-{ending}</i>) of the surname {r[6]}."
                       if r[5] == 'reasonably inferred' else '')
                w.writerow(r + [pos, der, ''])
    for k in sorted(counts):
        print(f'{counts[k]:6d}  {k}')
    print('candidates', len(out))


if __name__ == '__main__':
    main()
