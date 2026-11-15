#!/usr/bin/env python3
"""
lexicon.py -- Lewis & Short readings for an epithet (pattern-by-pattern plan, queue Q4; Brian 14 Nov 2026 21:43:
"The dictionary lookup must detect multiple possible readings rather than automatically accepting the first
match").

Source: Lewis & Short, A Latin Dictionary (1879), Perseus Digital Library edition, from the Perseus lexical-data
repository (https://github.com/PerseusDL/lexica, CTS_XML_TEI/perseus/pdllex/lat/ls/lat.ls.perseus-eng1.xml),
CC BY-SA 4.0. Attribution: Perseus Digital Library, Tufts University. Only headwords, grammatical labels and a
short gloss are indexed; the dictionary text itself is not copied into this repository.

  python3 gender/lexicon.py build --ls .../lat.ls.perseus-eng1.xml --out ls_index.tsv
  python3 gender/lexicon.py lookup --index ls_index.tsv laevigatus spina crassispina

Each reading: headword, kind (adjective | participle | noun | verb | other), the dictionary's labels (itype,
gender, pos), entry id, first gloss. lookup() returns every reading of every headword the epithet can be a form
of (masculine, feminine or neuter nominative of an adjective; nominative of a noun), never just the first.
"""
import argparse, csv, html, re, sys, unicodedata

ENTRY_RE = re.compile(r'<entryFree\b([^>]*)>(.*?)</entryFree>', re.S)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return s.replace('j', 'i').replace('v', 'u')


def tag(body, name):
    m = re.search(rf'<{name}\b[^>]*>(.*?)</{name}>', body, re.S)
    return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''


def kind_of(itype, gen, pos, body, orth=''):
    head = re.sub(r'<[^>]+>', '', body[:600])
    if orth[:1].isupper():
        return 'proper noun'
    if re.search(r'\bP\. a\.|\bpart\.|\bParticip', head):
        if 'adj' not in pos:
            return 'participle'
    if 'adj' in pos or re.fullmatch(r'(\w*a, \w*um|e|is, e|\w*is, \w*e)', itype):
        return 'adjective'
    if gen:
        return 'noun'
    if pos.startswith('v') or re.search(r'\b(āre|ēre|ĕre|īre|are|ere|ire)\b', itype):
        return 'verb'
    return 'other'


def build(ls_path, out_path):
    text = open(ls_path, encoding='utf-8').read()
    n = 0
    with open(out_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['key', 'headword', 'kind', 'itype', 'gen', 'pos', 'entry', 'gloss'])
        for attrs, body in ENTRY_RE.findall(text):
            a = dict(ATTR_RE.findall(attrs))
            key = fold(re.sub(r'\d+$', '', a.get('key', '')))
            if not key:
                continue
            orth = html.unescape(tag(body, 'orth'))
            itype, gen, pos = tag(body, 'itype'), tag(body, 'gen'), tag(body, 'pos')
            gloss = ''
            m = re.search(r'<sense\b[^>]*>(.*?)</sense>', body, re.S)
            if m:
                gloss = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip()[:120]
            w.writerow([key, orth, kind_of(itype, gen, pos, body, orth), itype, gen, pos, a.get('id', ''), gloss])
            n += 1
    print(f'{n} entries -> {out_path}')


def load(index_path):
    idx = {}
    with open(index_path, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            idx.setdefault(r['key'], []).append(r)
    return idx


# nominative endings an epithet can show for a dictionary headword: (epithet ending, headword ending)
ADJ_FORMS = [('a', 'us'), ('um', 'us'), ('us', 'us'), ('e', 'is'), ('is', 'is'), ('ra', 'er'), ('rum', 'er'),
             ('er', 'er'), ('era', 'er'), ('erum', 'er')]


# participles: (epithet ending, verb headword ending, what it is)
PARTICIPLE_FORMS = [('atus', 'o', 'perfect participle'), ('ata', 'o', 'perfect participle'),
                    ('atum', 'o', 'perfect participle'), ('ans', 'o', 'present participle'),
                    ('ens', 'eo', 'present participle'), ('ens', 'o', 'present participle'),
                    ('itus', 'io', 'perfect participle'), ('ita', 'io', 'perfect participle'),
                    ('itum', 'io', 'perfect participle')]
# a noun's own nominative may hide behind a gender ending a later author gave it (globus -> globa, the trap of
# nouns declined as adjectives): these candidates are reported as 'altered ending', never as the noun itself
NOUN_ALTERED = [('a', 'us'), ('a', 'um'), ('us', 'a'), ('um', 'us'), ('um', 'a'), ('a', 'es'), ('us', 'es')]


def lookup(idx, epithet):
    """Every reading of every headword that `epithet` can be a form of, each labelled with how it matched."""
    e = fold(epithet)
    seen, out = set(), []

    def add(key, how, kinds=None, kind_as=None):
        for r in idx.get(key, []):
            if (r['entry'], how) in seen or (kinds and r['kind'] not in kinds):
                continue
            seen.add((r['entry'], how))
            out.append(dict(r, matched=how, kind=kind_as or r['kind']))

    add(e, 'as spelled')
    for end, head in ADJ_FORMS:
        if e.endswith(end) and len(e) > len(end) + 2:
            add(e[: -len(end)] + head, f'-{end} as a form of -{head}', kinds=('adjective', 'participle'))
    for end, head, what in PARTICIPLE_FORMS:
        if e.endswith(end) and len(e) > len(end) + 2:
            add(e[: -len(end)] + head, f'{what} of the verb', kinds=('verb',), kind_as='participle')
    if any(r['kind'] != 'proper noun' for r in out):
        return out
    for end, head in NOUN_ALTERED:
        if e.endswith(end) and len(e) > len(end) + 2:
            add(e[: -len(end)] + head, f'noun -{head} with the ending -{end}', kinds=('noun',), kind_as='noun (altered ending)')
    return out


def summarize(readings):
    kinds = sorted({r['kind'] for r in readings})
    return '+'.join(kinds) if kinds else 'not found'


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--ls', required=True)
    b.add_argument('--out', required=True)
    l = sub.add_parser('lookup')
    l.add_argument('--index', required=True)
    l.add_argument('words', nargs='+')
    a = ap.parse_args()
    if a.cmd == 'build':
        build(a.ls, a.out)
    else:
        idx = load(a.index)
        for wd in a.words:
            rs = lookup(idx, wd)
            print(f'{wd}: {summarize(rs)}')
            for r in rs:
                print(f"   {r['headword']:<18} {r['kind']:<11} {r['itype']:<8} {r['gen']:<4} {r['pos']:<6} "
                      f"[{r['matched']}] {r['gloss'][:60]}")


if __name__ == '__main__':
    main()
