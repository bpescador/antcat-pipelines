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


def kind_of(itype, gen, pos, body, orth='', key=''):
    head = re.sub(r'<[^>]+>', '', body[:600])
    # L&S prints some proper-noun headwords in lower case (orth "īcărus", key "Icarus"): the key decides too
    if orth[:1].isupper() or key[:1].isupper():
        # a capitalized adjective (Gallicus, Romanus) is an adjective; a capitalized noun is a proper noun
        # an adjective's own inflection (Afer, fra, frum; Aeolius, a, um) decides even where a substantive use
        # inside the headword's grammar (Afer, a native of Africa) supplies a gender (audit 16 Nov 2026)
        if re.fullmatch(r'(\w*a, \w*um|is, e|\w*is, \w*e)', itype):
            return 'adjective'
        if not gen and 'adj' in pos:
            return 'adjective'
        return 'proper noun'
    if re.search(r'\bP\. a\.', head):
        return 'adjective'  # a participial adjective (minutus 'small') is used as an adjective
    if re.search(r'\bpart\.|\bParticip', head):
        if 'adj' not in pos:
            return 'participle'
    if 'adj' in pos or re.fullmatch(r'(\w*a, \w*um|e|is, e|\w*is, \w*e)', itype):
        return 'adjective'
    # a verb's principal parts end in its conjugation number ("āvi, ātum, 1"); L&S marks v. a. / v. n. as gen
    if re.search(r'(^|[ ,])[1-4]\.?$', itype.strip()) or pos.startswith('v'):
        return 'verb'
    if gen:
        return 'noun'
    if pos.startswith('v') or re.search(r'\b(āre|ēre|ĕre|īre|are|ere|ire)\b', itype):
        return 'verb'
    return 'other'


def headword_segment(body):
    """The entry up to the first headword printed after its first sense closes. Derived words (Icarus ...
    Derivv. Icarius, a, um, adj.) are printed in later senses; spellings of the headword itself (avus, also
    avos; vomer ... collat. form vomis) stand in the grammar run or inside the first sense."""
    end = body.find('</sense>')
    if end < 0:
        return body
    nxt = re.search(r'<orth\b', body[end:])
    return body[:end + nxt.start()] if nxt else body


def build(ls_path, out_path):
    text = open(ls_path, encoding='utf-8').read()
    n = 0
    with open(out_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['key', 'headword', 'kind', 'itype', 'gen', 'pos', 'entry', 'gloss'])
        for attrs, body in ENTRY_RE.findall(text):
            a = dict(ATTR_RE.findall(attrs))
            key = fold(re.sub(r'\d+$', '', a.get('key', '')))
            if not key or a.get('type') == 'spur':
                continue  # type="spur": a false reading L&S records only to reject it (Obsidianus)
            orth = html.unescape(tag(body, 'orth'))
            # the headword's own itype, gen and pos stand before the next headword printed inside the entry; a
            # derived word (Icarus ... Derivv. Icarius, a, um, adj.) must not lend the headword its part of
            # speech. <sense> is no boundary: Perseus opens the first sense mid-grammar.
            head = headword_segment(body)
            itype, gen, pos = tag(head, 'itype'), tag(head, 'gen'), tag(head, 'pos')
            gloss = ''
            m = re.search(r'<sense\b[^>]*>(.*?)</sense>', body, re.S)
            if m:
                gloss = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip()[:120]
            w.writerow([key, orth, kind_of(itype, gen, pos, body, orth, a.get('key', '')), itype, gen, pos,
                        a.get('id', ''), gloss])
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
    # classical spellings in Lewis & Short: clypeus -> clipeus, setosus -> saetosus, laevigatus -> levigatus
    for v in {e.replace('y', 'i'), e.replace('ae', 'e'), re.sub(r'^se', 'sae', e), e.replace('k', 'c'),
              e.replace('oe', 'e'), e.replace('y', 'i').replace('ae', 'e')} - {e}:
        if v in idx:
            add(v, 'variant spelling', kinds=('adjective', 'participle', 'noun', 'proper noun'))
        for end, head in ADJ_FORMS:
            if v.endswith(end) and len(v) > len(end) + 2:
                add(v[: -len(end)] + head, f'variant spelling, -{end} as a form of -{head}', kinds=('adjective', 'participle'))
    # comparative, superlative and diminutive of an adjective are adjectives (A&G 124-128, 243)
    for pat, heads, how in [(r'(ior|ius)$', ('us', 'is', 'er'), 'comparative'),
                            (r'(issim|illim|errim)(us|a|um)$', ('us', 'is', 'er'), 'superlative'),
                            (r'(ul|ell|ol)(us|a|um)$', ('us', 'is'), 'diminutive')]:
        m = re.search(pat, e)
        if m and len(e) - len(m.group(0)) >= 3:
            st = e[: m.start()]
            for h in heads:
                add(st + h, how + ' of the adjective', kinds=('adjective',))
                if how == 'superlative' and m.group(1) == 'illim':
                    add(st + 'il' + h, how + ' of the adjective', kinds=('adjective',))
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
    g = sub.add_parser('build-greek')
    g.add_argument('--lsj-dir', required=True)
    g.add_argument('--out', required=True)
    l = sub.add_parser('lookup')
    l.add_argument('--index', required=True)
    l.add_argument('words', nargs='+')
    a = ap.parse_args()
    if a.cmd == 'build':
        build(a.ls, a.out)
    elif a.cmd == 'build-greek':
        build_greek(a.lsj_dir, a.out)
    else:
        idx = load(a.index)
        for wd in a.words:
            rs = lookup(idx, wd)
            print(f'{wd}: {summarize(rs)}')
            for r in rs:
                print(f"   {r['headword']:<18} {r['kind']:<11} {r['itype']:<8} {r['gen']:<4} {r['pos']:<6} "
                      f"[{r['matched']}] {r['gloss'][:60]}")



# ---- Greek: Liddell-Scott-Jones (Perseus edition, betacode) -------------------------------------------------
# Latinized the way zoological names Latinize Greek: k -> c, u -> y (ou -> u), f -> ph, x -> ch, q -> th, y -> ps,
# h (eta) -> e, w (omega) -> o, c (xi) -> x, rough breathing -> h, ai -> ae, oi -> oe; endings -os -> -us, -on -> -um.
BETA = {'a': 'a', 'b': 'b', 'g': 'g', 'd': 'd', 'e': 'e', 'z': 'z', 'h': 'e', 'q': 'th', 'i': 'i', 'k': 'c',
        'l': 'l', 'm': 'm', 'n': 'n', 'c': 'x', 'o': 'o', 'p': 'p', 'r': 'r', 's': 's', 't': 't', 'u': 'y',
        'f': 'ph', 'x': 'ch', 'y': 'ps', 'w': 'o', 'v': 'u'}


def latinize_beta(beta):
    b = re.sub(r'\d+$', '', beta.lower())
    rough = '(' in b[:3]
    b = re.sub(r'[/\\=()+|*\'^_-]', '', b)
    out = ''.join(BETA.get(ch, '') for ch in b)
    out = out.replace('gg', 'ng').replace('gk', 'nc').replace('gx', 'nch').replace('oy', 'u')
    out = out.replace('ai', 'ae').replace('oi', 'oe').replace('ei', 'i')
    if out.startswith('r'):
        out = 'rh' + out[1:]
    if rough and out and out[0] in 'aeiouy':
        out = 'h' + out
    return out


def greek_kind(itypes, gen):
    it = [re.sub(r'[/\\=()+|]', '', x).strip(' ,') for x in itypes]
    # adjectives: -os, -a/-e, -on; -os, -on (two endings); -ys, -eia, -y; -es, -es
    if 'on' in it and (len(it) >= 2) or it[:2] in (['eia', 'y'], ['es', 'es']) or ('eia' in it and 'y' in it):
        return 'adjective'
    if gen:
        return 'noun'
    if it and re.fullmatch(r'(ou|hs|as|os|atos|ews|idos|ontos|ews|eos|ous|w)', it[0]):
        return 'noun'
    return 'other'


def build_greek(lsj_dir, out_path):
    import glob
    n = 0
    with open(out_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['key', 'stem', 'headword', 'kind', 'gen', 'entry', 'gloss'])
        for path in sorted(glob.glob(f'{lsj_dir}/grc.lsj.perseus-eng*.xml')):
            text = open(path, encoding='utf-8').read()
            for attrs, body in ENTRY_RE.findall(text):
                a = dict(ATTR_RE.findall(attrs))
                if a.get('type') != 'main':
                    continue
                beta = a.get('key', '')
                lat = latinize_beta(beta)
                if len(lat) < 3:
                    continue
                itypes = re.findall(r'<itype\b[^>]*>(.*?)</itype>', body)
                gen = tag(body, 'gen')
                m = re.search(r'<tr\b[^>]*>(.*?)</tr>', body, re.S)
                gloss = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip()[:80] if m else ''
                head = re.sub(r'[/\\=()+|^]', '', re.sub(r'<[^>]+>', ' ', body[:500]))
                head = re.sub(r'\[[^\]]*\]', ' ', head)
                if re.search(r'^\s*\S+\s*,\s*(a|h)\s*,?\s*on\b|^\s*\S+os\s*,\s*on\b|\beia\s*,\s*y\b|^\s*\S+hs\s*,\s*es\b', head):
                    kind = 'adjective'
                else:
                    kind = greek_kind(itypes, gen)
                key = re.sub(r'os$', 'us', re.sub(r'on$', 'um', lat))
                stem = re.sub(r'(us|os|um|on|e|a|es|is|ys|er|ex|ix|ax|ox|yx|ops|ps)$', '', lat)
                w.writerow([key, stem, beta, kind, gen, a.get('id', ''), gloss])
                n += 1
    print(f'{n} entries -> {out_path}')


if __name__ == '__main__':
    main()
