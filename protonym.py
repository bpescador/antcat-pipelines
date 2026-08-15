#!/usr/bin/env python3
"""
protonym.py -- name identity for the Bolton(NGC) <-> AntCat diff.

WHY THIS EXISTS
Bolton records a name under the spelling it was PUBLISHED with, inside its
ORIGINAL COMBINATION:

    propinqua. Melophorus fieldi var. propinqua Viehmeyer, 1925a: 36 ...

AntCat stores the name gender-agreed to its CURRENT genus:

    name fields:   Melophorus fieldi propinquus
    history line:  Melophorus fieldi var. propinqua Viehmeyer, 1925a : 36 ...

So the two catalogues disagree on spelling for exactly the names Bolton treats
as non-valid (junior synonyms, varieties, subspecies). Matching those epithets
as strings -- even gender-stemmed, even with an edit-distance tolerance -- is a
guess. The first line of AntCat's `taxonomic history html` is the protonym as
published (it IS the Bolton view), so both sides can be keyed on the same thing:

    PROTONYM KEY = (original terminal epithet, 4-digit year, first-author surname)

Disambiguation letters (1914b vs 1914c) are dropped: the two catalogues assign
them independently.

A name then has many SPELLINGS in AntCat (the original, the gender-corrected
current one, misspellings, and one row per obsolete combination). The resolver
maps every one of them back to the protonym key, so an act's target can be
compared by identity instead of by string.
"""
import re, html, unicodedata

YEAR = r'(1[6789]\d\d|20\d\d)'
_RANKS = {'var', 'subsp', 'st', 'r', 'n', 'nr', 'f', 'm', 'ab', 'race', 'v',
          'sp', 'ssp', 'form', 'natio'}
# author-name particles: lowercase, but part of the AUTHOR, not an epithet
_PARTICLES = {'von', 'van', 'de', 'da', 'del', 'della', 'di', 'du', 'le', 'la',
              'den', 'der', 'dos', 'das', 'ten', 'ter', 'af', 'zu', 'y', 'e',
              'in', 'auct', 'nec', 'et', 'al'}

def strip_html(h):
    h = re.sub(r'<a\b[^>]*class="pdf-link"[^>]*>.*?</a>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    h = html.unescape(h)
    h = re.sub(r'\bPDF\b', ' ', h)
    return re.sub(r'\s+', ' ', h).strip()

def fold(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c))

def authorkey(s):
    return re.sub(r'[^a-z]', '', fold(s or '').lower())

def year4(s):
    m = re.search(YEAR, s or '')
    return m.group(1) if m else ''

def parse_protonym(text):
    """AntCat history opening -> (genus, terminal_epithet, author_surname, year).

    Handles: subgenus in parens, rank markers (var./subsp./st./r./n.), fossil
    daggers, bracketed notes before the name, authors with particles ('Dalla
    Torre', 'von Ihering') and initials ('Smith, F. 1858b'), and DOIs standing
    in for a page number."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r'^\[[^\]]*\]\s*', '', t)              # leading "[Note: ...]"
    # AntCat prefixes a header to the history: "Extant: 3 valid subspecies <protonym>"
    t = re.sub(r'^(?:Extant|Fossil)\b[^A-Z]*', '', t)
    t = t.lstrip('†*‡ ')
    m = re.search(YEAR, t[:400])
    if not m:
        return None
    yr = m.group(1)
    prefix = t[:m.start()]
    # include Latin Extended-A/B: Csősz, Radchenko, Đurić ...
    LET = r"A-Za-z\u00C0-\u024F"
    toks = re.findall(r"[" + LET + r"][" + LET + r"'\-]*\.?", prefix)
    if not toks:
        return None

    genus = None
    eps, author = [], ''
    in_author = False
    for raw in toks:
        w = raw.rstrip('.')
        wl = fold(w).lower()
        if not w:
            continue
        if genus is None:
            if w[:1].isupper():
                genus = wl
            continue
        if in_author:                                  # after a particle: take the surname
            if w[:1].isupper():
                author = w
                break
            continue
        if wl in _RANKS:                               # rank marker: skip
            continue
        if w[:1].isupper():                            # capitalised
            if eps:                                    # ... after an epithet -> author
                author = w
                break
            continue                                   # subgenus / second capital: skip
        if wl in _PARTICLES:
            if eps:                                    # particle introduces the author
                in_author = True                       # 'de Andrade', 'von Ihering'
            continue
        eps.append(wl)                                 # lowercase -> epithet
    if not genus or not eps:
        return None
    return (genus, eps[-1], authorkey(author), yr)

def protokey(terminal_epithet, author, year):
    """the shared key; letters dropped from the year"""
    ep = fold(terminal_epithet or '').lower()
    return (ep, authorkey(author), year4(year)) if ep and year4(year) else None
