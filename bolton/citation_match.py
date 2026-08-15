"""
citation_match.py -- decide whether AntCat already cites the paper Bolton names.

Single coherent decision replacing the old stack of four fuzzy key-checks. Compares the
FIRST author + year with signature confirmation, so:
  - spelling variants match   (Bolton "Bathory 2024" == AntCat "Bathori 2024")
  - compound surnames match    (Bolton "Hita Garcia" == AntCat "Hita-Garcia")
  - a redescription does NOT match a same-author original description
    (Bolton "Xu, Liu, et al. 2024" != AntCat description "Qian & Xu, 2024")
"""
import re, unicodedata


def _fold(s):
    a = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in a if not unicodedata.combining(c))


def _edit1(a, b):
    """<= one single-character edit (substitution or insertion)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    return any(a[:i] + b[i] + a[i:] == b for i in range(la + 1))


_PARTICLES = tuple(sorted(('da', 'de', 'del', 'della', 'dela', 'di', 'do', 'dos', 'du',
                           'la', 'le', 'van', 'von', 'vander', 'ter', 'ten', 'des', 'st'),
                          key=len, reverse=True))


def _strip_particle(a):
    """Remove a leading surname particle (Da Silva -> silva, Von Ihering -> ihering) so the
    two catalogues match when one includes the particle in the surname and the other
    doesn't. Only strips if a substantial base remains."""
    for p in _PARTICLES:
        if a.startswith(p) and len(a) - len(p) >= 4:
            return a[len(p):]
    return a


def _same_author(a, b):
    """Two normalized surname forms are the same author: equal; one edit apart on names
    >=6 chars (bathori/bathory, galkowski/galkowsky, perezgonzales/perezgonzalez); one a
    prefix of the other where the longer is clearly compound (>=8 chars) and the prefix is
    >=4 (hita/hitagarcia, casadei/casadeiferreira); or equal after stripping a leading
    surname particle (silva/dasilva, ihering/vonihering). Length guards avoid short-name
    collisions (chen/chenzhang, smith/smithson are NOT merged)."""
    if a == b:
        return True
    if len(a) >= 6 and len(b) >= 6 and _edit1(a, b):
        return True
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    if len(lo) >= 4 and len(hi) >= 8 and hi.startswith(lo):
        return True
    pa, pb = _strip_particle(a), _strip_particle(b)
    if (pa != a or pb != b) and pa == pb:
        return True
    return False


def authors_of_segment(seg):
    """The surname forms an author-string names, before 'et al'/year. Each comma/&-separated
    group's words are joined so a compound or hyphenated surname collapses to one token
    ('Hita Garcia' -> hitagarcia, 'Casadei-Ferreira' -> casadeiferreira). Single-letter
    initials are dropped."""
    seg = unicodedata.normalize('NFC', seg)
    m = re.match(r"(.*?)(1[6789]\d\d|20\d\d)", seg)
    head = m.group(1) if m else seg
    out = []
    for g in re.split(r',|&', head):
        words = [w for w in re.findall(r"[A-Z][A-Za-z\u00C0-\u024F'\-]+", g) if len(w) > 1]
        if words and words[0].lower() != 'al':
            out.append(re.sub(r'[^a-z]', '', _fold(''.join(words)).lower()))
    return [a for a in out if a and a != 'etal']


def citation_present(bolton_seg, antcat_text):
    """Does antcat_text cite the same paper Bolton names in bolton_seg? Matches on first
    author + year with signature confirmation (see module docstring)."""
    # The dump stores some accents decomposed (e.g. "Guénard" as e + U+0301 combining
    # acute). Normalize to NFC so the precomposed letter falls in the author character
    # class below; otherwise the combining mark breaks the run and the citation is missed.
    bolton_seg = unicodedata.normalize('NFC', bolton_seg)
    antcat_text = unicodedata.normalize('NFC', antcat_text)
    ym = re.search(r'(1[6789]\d\d|20\d\d)', bolton_seg)
    if not ym:
        return False
    yr = ym.group(1)
    b_auths = authors_of_segment(bolton_seg)
    if not b_auths:
        return False
    b_first = b_auths[0]
    for m in re.finditer(r'([A-Z][A-Za-z\u00C0-\u024F\'\-.,&\s]{0,60}?),?\s*' + yr + r'[a-z]?(?![\d])',
                         antcat_text):
        a_auths = authors_of_segment(m.group(1) + ' ' + yr)
        if not a_auths:
            ws = re.findall(r"[A-Z][A-Za-z\u00C0-\u024F'\-]+", m.group(1))
            a_auths = [re.sub(r'[^a-z]', '', _fold(w).lower()) for w in ws[-2:]]
        if a_auths and _same_author(b_first, a_auths[0]):
            return True
    return False
