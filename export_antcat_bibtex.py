#!/usr/bin/env python3
"""
export_antcat_bibtex.py -- AntCat references -> BibTeX for TaxonWorks' Source
batch-loader, with nested containers resolved via crossref.

Input: the CSV from export_references_v2.rb (adds nesting_reference_id + container
fields to the original export).

CONTAINER MODEL (the "name author != publication author" case). A NestedReference is
a work published inside another (a chapter in an edited volume, a name in a faunistic
report). AntCat stores the container as its own Reference and links to it by
`nesting_reference_id`. Every one of the 663 distinct containers already exists as its
own row in this export, so we do NOT synthesise a container -- we emit the chapter as
@incollection with `crossref = {antcatNNNN}` pointing at the container's OWN entry.
That keeps one Source per publication (as TW wants) and keeps each entry's own
`antcat_id`, so the chapter keeps its nomenclatural author and the container keeps the
book/editor author -- no flattening.

Question 4 (shared id) holds on both: the chapter is @incollection{antcatCHAPTER},
its container is @book/@article{antcatCONTAINER}, and each carries note = {antcat_id: N}.
"""
import csv, sys, re, argparse
from collections import Counter

csv.field_size_limit(sys.maxsize)

# entry type by AntCat class. A NestedReference is a chapter -> @incollection.
TYPE_MAP = {'ArticleReference': 'article',
            'BookReference': 'book',
            'NestedReference': 'incollection'}

def bib_value(s):
    r"""Sanitise a string for a BRACE-DELIMITED BibTeX value: `field = {value}`.

    The value lives inside `{...}`, so its braces must be BALANCED -- BibTeX-Ruby
    (what TaxonWorks parses with) treats an unbalanced brace, or a backslash-escaped
    brace `\{`, as a syntax error and aborts the whole entry at the next `@`. So the
    old rule of escaping `{`->`\{`, `}`->`\}`, and `\`->`\textbackslash{}` was exactly
    backwards for this context.

    Rules, verified against BibTeX-Ruby's grammar:
      * A literal backslash starts a control sequence; AntCat titles that contain a
        stray `\` (e.g. "umbratus\*") have no TeX intent, so drop it.
      * Braces: keep balanced pairs (BibTeX allows nested balanced braces, and they
        usefully protect capitalisation), but remove UNMATCHED `{` or `}`. AntCat has
        titles with a single stray brace, sometimes paired with a `]` on the other end
        ("{New species ...]"), which is what broke the 4 known entries.
      * `[` and `]` are ordinary characters in a braced value -- leave them untouched
        (the `[...]` editorial brackets are meant to be kept).
      * `&`, `%`, `$`, `#`, `_`, `~`, `^` are special OUTSIDE braces but literal INSIDE
        a braced value in BibTeX-Ruby, so they need no escaping here. Leaving them
        as-is also preserves author strings like "Baroni Urbani" and titles verbatim.
    """
    if not s:
        return ''
    s = s.replace('\\', '')                     # strip stray backslashes (no TeX intent)
    # Drop UNMATCHED delimiters, keep balanced pairs. Braces must balance for
    # BibTeX-Ruby to parse the value at all; square brackets are ordinary characters,
    # but an unmatched one is a visible wart from AntCat's "[New species ...]" editorial
    # wrapper when the source bracket is lopsided (143410/143415). Balanced [...] --
    # "[In Japanese.]", "[sic]", "[Untitled. ...]" (1,501 titles) -- are preserved.
    s = _drop_unmatched(s, '{', '}')
    s = _drop_unmatched(s, '[', ']')
    return s.strip()


def _drop_unmatched(s, op, cl):
    out, depth = [], 0
    for ch in s:
        if ch == op:
            depth += 1
            out.append(ch)
        elif ch == cl:
            if depth > 0:
                depth -= 1
                out.append(ch)
            # unmatched closer -> drop
        else:
            out.append(ch)
    if depth:                                   # unmatched openers remain -> remove them
        res, keep = [], depth
        for ch in reversed(out):
            if ch == op and keep > 0:
                keep -= 1
                continue
            res.append(ch)
        out = list(reversed(res))
    return ''.join(out)

def clean_title(t):
    return bib_value(re.sub(r'\s*\[In [^\]]+\.\]', '', t or '').strip())

def authors_to_bibtex(a):
    return ' and '.join(p.strip() for p in (a or '').split(';') if p.strip())

def page_range(pg):
    m = re.search(r'(\d+)\s*[-\u2013]\s*(\d+)', pg or '')
    return f'{m.group(1)}--{m.group(2)}' if m else ''

def book_pages(pg):
    m = re.search(r'(\d+)\s*pp', pg or '')
    return m.group(1) if m else ''

def run(refs_csv, out_path):
    rows = list(csv.DictReader(open(refs_csv, encoding='utf-8')))
    by_id = {r['id'].strip(): r for r in rows}
    present = set(by_id)

    dangling = []          # crossref targets not in the file (should be none)
    n_crossref = 0
    with open(out_path, 'w', encoding='utf-8') as f:
        for r in rows:
            rid = r['id'].strip()
            btype = TYPE_MAP.get(r['type'], 'misc')
            fields = [('author', authors_to_bibtex(r['authors'])),
                      ('year', r['year'].strip() or r['citation_year'].strip()),
                      ('title', clean_title(r['title']))]

            if btype == 'article':
                fields.append(('journal', bib_value(r['journal'].strip())))
                pg = page_range(r['pagination'])
                if pg:
                    fields.append(('pages', pg))

            elif btype == 'incollection':
                container = r['nesting_reference_id'].strip()
                if container and container in present:
                    fields.append(('crossref', f'antcat{container}'))   # id-join to container entry
                    # crossref inheritance keys on the parent's `booktitle`, but the
                    # container is a full @book/@article with a `title`, so a strict
                    # processor won't inherit it. Carry the container title explicitly
                    # so the chapter is self-contained AND id-linked.
                    c = by_id[container]
                    fields.append(('booktitle', clean_title(c['title'])))
                    ceditor = authors_to_bibtex(c['authors'])
                    if ceditor:
                        fields.append(('editor', ceditor))
                    n_crossref += 1
                elif container:
                    dangling.append((rid, container))
                    fields.append(('booktitle', clean_title(r['nesting_title'])))
                    if r['nesting_authors'].strip():
                        fields.append(('editor', authors_to_bibtex(r['nesting_authors'])))
                else:
                    fields.append(('booktitle', ''))         # genuinely no container
                pg = page_range(r['pagination'])
                if pg:
                    fields.append(('pages', pg))

            elif btype == 'book':
                pp = book_pages(r['pagination'])
                if pp:
                    fields.append(('pages', pp))

            fields.append(('note', f'antcat_id: {rid}'))     # shared id, Source side
            fields.append(('keywords', f'antcat_id={rid}'))

            f.write(f'@{btype}{{antcat{rid},\n')
            f.write(',\n'.join(f'  {k} = {{{v}}}' for k, v in fields if v))
            f.write('\n}\n\n')

    # ---- report ----
    print(f'references read:   {len(rows)}')
    print(f'BibTeX entries:    {len(rows)}   -> {out_path}')
    for k, v in Counter(r['type'] for r in rows).most_common():
        print(f'   {v:6}  {k} -> @{TYPE_MAP.get(k, "misc")}')
    print()
    nested = [r for r in rows if r['type'] == 'NestedReference']
    print(f'nested chapters:                 {len(nested)}')
    print(f'  emitted with crossref:         {n_crossref}')
    print(f'  distinct containers referenced:{len({r["nesting_reference_id"].strip() for r in nested if r["nesting_reference_id"].strip()})}')
    no_container = sum(1 for r in nested if not r['nesting_reference_id'].strip())
    print(f'  genuinely no container:        {no_container}')
    # sanity: every crossref target present
    targets = {f'antcat{r["nesting_reference_id"].strip()}'
               for r in nested if r['nesting_reference_id'].strip()}
    keys = {f'antcat{r["id"].strip()}' for r in rows}
    print()
    print(f'SANITY crossref targets: {len(targets)} distinct')
    print(f'  all present as an entry in the file: {targets <= keys}  '
          f'(missing: {len(targets - keys)})')
    print(f'SANITY dangling containers (id given but not in file): {len(dangling)}')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--refs', required=True)
    ap.add_argument('--out', default='antcat_references.bib')
    a = ap.parse_args()
    run(a.refs, a.out)
