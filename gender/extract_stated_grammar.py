#!/usr/bin/env python3
"""
extract_stated_grammar.py -- what the original description itself says about a species-group name: the printed
etymology paragraph and any explicit grammatical statement (noun in apposition, adjective, participle, genitive or
dedication, arbitrary combination). Queue Q1 of gender/ETYMOLOGY_GRAMMAR_RUNBOOK.md. Read only.

For each protonym the page locator found (confidence A, B or C), the species account is the text from the name's
heading on its description page to the heading of the next name described in the same reference (at most
--max-pages pages). The first etymology heading inside that account opens the passage; it ends at the next
section heading or after --max-chars characters.

Output columns: protonym_id, protonym_name, epithet, year, ref_id, pdf_page, confidence, passage_page, heading,
epithet_in_passage, stated (semicolon list: noun_in_apposition, adjective, participle, genitive, dedication,
arbitrary, place, latin_or_greek), passage.

The statement is evidence, never the decision: a Latin adjective form agrees whatever the author said (policy
Rule 1.1), and "named after X" is a dedication, not a part of speech.
"""
import argparse, bisect, collections, csv, os, re, sys, unicodedata

csv.field_size_limit(sys.maxsize)

HEADING = re.compile(
    r'(?im)^[ \t]*(?:[0-9IVX.]+[ \t]+)?(etymology|etymologie|etimolog[ií]a|etymologia|derivatio nominis|'
    r'derivation of (?:the )?(?:specific )?name|name derivation|origin of (?:the )?name|namensgebung|'
    r'[ée]tymologie|étymologie)\b[ \t]*[.:—–-]?')
INLINE = re.compile(
    r'(?i)\b(etymology|etimolog[ií]a|derivatio nominis|[ée]tymologie|etymologie)[ \t]*[.:—–-]')
SECTION = re.compile(
    r'(?im)^[ \t]*(?:[0-9IVX.]+[ \t]+)?(diagnosis|description|distribution|discussion|comments?|remarks?|'
    r'material examined|type material|additional material|other material|holotype|paratypes?|worker|queen|male|'
    r'gyne|biology|natural history|ecology|habitat|measurements|notes?|identification|taxonomic notes?|'
    r'geographic range|range|variation|comparative notes?|differential diagnosis|non-type material|'
    r'diagn[oó]stico|descripci[oó]n|distribuci[oó]n|comentarios?|material examinado|obrera|reina|macho)\b[ \t]*[.:—–-]?')
NEW_SP = re.compile(r'(?i)\b(n\.?\s?sp|sp\.?\s?n(ov)?|nov\.?\s?sp|new species|new subspecies|spec\.?\s?nov|'
                    r'sp\.\s?nova|ssp\.?\s?n|subsp\.?\s?n|n\.?\s?subsp|var\.?\s?n|n\.?\s?var)\b')

STATED = [
    ('noun_in_apposition', re.compile(
        r'(?i)\bin\s+apposition|\bapposition\b|sustantivo en aposici[oó]n|substantivo em aposi[cç][aã]o|'
        r'\binvariable\b|\bindeclinable\b|\bnon[- ]latin\b|treated as (?:a |an )?(?:indeclinable |invariable )?noun')),
    ('adjective', re.compile(r'(?i)\badjectiv|\badjetiv|\badjektiv|\badjectif')),
    ('participle', re.compile(r'(?i)\bparticip')),
    ('genitive', re.compile(r'(?i)\bgenitiv|\bpatronym|\bmatronym|\beponym')),
    ('dedication', re.compile(
        r'(?i)named (?:after|for|in hono[u]?r)|dedicated to|in hono[u]?r of|hono[u]?rs?\b|in memory of|'
        r'dedicad[oa] a|en honor (?:a|de)|em homenagem|zu ehren|benannt nach|d[ée]di[ée]e? [àa]|in recognition of')),
    ('arbitrary', re.compile(
        r'(?i)arbitrary (?:combination|arrangement|name)|random combination|combination of letters|'
        r'nonsense|no (?:particular )?meaning|euphon|anagram')),
    ('place', re.compile(r'(?i)type localit|locality where|where the (?:type|holotype|species)|named (?:after|for) the '
                         r'(?:island|country|province|region|river|mountain|park|forest|locality|state|city|town|village)')),
    ('latin_or_greek', re.compile(r'(?i)\blatin\b|\bgreek\b|\bgr\.|\bl\.\s|\blat\.|\blat[ií]n\b|\bgriego\b|\bgrego\b')),
]


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def read_page(library, ref, p):
    try:
        with open(os.path.join(library, 'pages', ref, f'p{p:04d}.txt'), encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def heading_pos(text, epithet):
    """position of the name's own heading on its page: the epithet beside 'n. sp.' and the like, else its first use"""
    f = fold(text)
    ep = fold(epithet)
    first = None
    for m in re.finditer(re.escape(ep), f):
        if first is None:
            first = m.start()
        if NEW_SP.search(text[max(0, m.start() - 60): m.end() + 80]):
            return m.start()
    return first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--library', required=True)
    ap.add_argument('--locator', required=True, help='page_locator output')
    ap.add_argument('--protonyms', required=True, help='protonym_pages TSV (year)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-pages', type=int, default=6)
    ap.add_argument('--max-chars', type=int, default=900)
    a = ap.parse_args()

    year = {}
    with open(a.protonyms, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh, delimiter='\t', quoting=csv.QUOTE_NONE):
            year[r['protonym_id']] = r['year']
    with open(a.locator, encoding='utf-8', newline='') as fh:
        rows = [r for r in csv.DictReader(fh, delimiter='\t') if r['confidence'] in ('A', 'B', 'C') and r['pdf_page']]
    by_ref = collections.defaultdict(list)
    for r in rows:
        by_ref[r['ref_id']].append(r)

    n = found = 0
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'epithet', 'year', 'ref_id', 'pdf_page', 'confidence',
                    'passage_page', 'heading', 'epithet_in_passage', 'stated', 'passage'])
        for ref, rs in by_ref.items():
            cache = {}
            page = lambda p: cache.setdefault(p, read_page(a.library, ref, p))
            # each name's heading as (page, position); the next heading in the reference bounds the account
            heads = []
            for r in rs:
                p = int(r['pdf_page'])
                pos = heading_pos(page(p), r['epithet'])
                heads.append((p, pos if pos is not None else 0, r))
            heads.sort(key=lambda t: (t[0], t[1]))
            keys = [(p, pos) for p, pos, _ in heads]
            for i, (p, pos, r) in enumerate(heads):
                n += 1
                end = keys[i + 1] if i + 1 < len(heads) else (p + a.max_pages, 0)
                # two names with the same heading position cannot be told apart: skip both
                if (i + 1 < len(heads) and keys[i + 1] == (p, pos)) or (i and keys[i - 1] == (p, pos)):
                    continue
                last = min(end[0], p + a.max_pages)
                hit = None
                for q in range(p, last + 1):
                    t = page(q)
                    lo = pos if q == p else 0
                    hi = end[1] if q == end[0] else len(t)
                    if q == end[0] and q != p and end[1] == 0:
                        break
                    seg = t[lo:hi]
                    m = HEADING.search(seg) or INLINE.search(seg)
                    if m:
                        hit = (q, lo + m.end(), m.group(1), t, hi)
                        break
                if not hit:
                    continue
                q, s, head, t, hi = hit
                body = t[s: min(hi, s + a.max_chars)]
                if len(body) < 40 and q < last:        # the heading closes the page: the passage runs on
                    body += ' ' + page(q + 1)[: a.max_chars]
                m = SECTION.search(body, 20)
                if m:
                    body = body[: m.start()]
                body = re.sub(r'\s+', ' ', body).strip(' .:—–-')
                if len(body) < 12:
                    continue
                stated = [name for name, rx in STATED if rx.search(body)]
                found += 1
                w.writerow([r['protonym_id'], r['protonym_name'], r['epithet'], year.get(r['protonym_id'], ''), ref,
                            r['pdf_page'], r['confidence'], q, head, 'yes' if fold(r['epithet']) in fold(body) else '',
                            ';'.join(stated), body])
    print(f'{n} located protonyms; {found} with an etymology passage -> {a.out}')


if __name__ == '__main__':
    main()
