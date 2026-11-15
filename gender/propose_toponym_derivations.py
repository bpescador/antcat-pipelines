#!/usr/bin/env python3
"""
propose_toponym_derivations.py -- the toponym pilot of the AntCat policy on derived etymologies.

Brian's approval of 14 Nov 2026 (20:16): about 640 species-group names whose recognizable geographic stem (-ensis,
-anus) matches the type locality recorded in AntCat get an AntCat derivation of the form

  Toponym: Formed from Sulawesi with the Latin adjectival suffix -ensis, 'of Sulawesi'. Sulawesi is the type
  locality recorded in AntCat.

stating the linguistic formation and the locality evidence, never the author's intention. Only names without a
sourced etymology and without a derivation. The derivation field is plain text on antcat.org (no italics yet).

Held, with the reason, instead of proposed:
  - the epithet is a Latin word in its own right (montanus 'of mountains', pratensis 'of meadows'): the place match
    may be a coincidence (Montana)
  - the stem matches more than one place in the locality, or the matched words are an adjective ("Dominican")
  - the matched place is only part of a longer place name ("Guinea" in "Papua New Guinea", "Colorado" in "Barro
    Colorado"), or the locality lists several places, so "X is the type locality" would not be exact
  - the stem matches only loosely: anything beyond one final vowel or a connecting -i- (brunensis for Brunei, which
    may be Brno; koreanensis; peruvianus)
  - an island group ("Andaman Is"), where "Andaman is the type locality" is not exact: wording to agree
  - the recorded part of speech is not adjective (the grammar policy decides; the derivation must agree)
  - with --locator and --library: described in 1990 or later, or the original description has an Etymology section
    (a published etymology takes precedence; it is extracted first)

Inputs: --protonyms (gender/protonym_pages_export.rb TSV). Output: --out TSV, one row per candidate, with the
proposal or the reason it is held. Standard library only; read only.
"""
import argparse, collections, csv, hashlib, os, re, sys, unicodedata

csv.field_size_limit(sys.maxsize)

SUFFIXES = [('ensis', '-ensis'), ('ense', '-ensis'), ('anus', '-anus'), ('ana', '-anus'), ('anum', '-anus')]
# Latin words with these endings formed from common nouns, not places (Lewis & Short): a type locality that happens
# to contain them proves nothing
LATIN_WORDS = {
    'pratensis', 'pratense', 'hortensis', 'hortense', 'nemorensis', 'nemorense', 'castrensis', 'forensis',
    'montanus', 'montana', 'montanum', 'fontanus', 'fontana', 'silvanus', 'silvana', 'urbanus', 'urbana',
    'humanus', 'humana', 'arcanus', 'arcana', 'mundanus', 'mundana', 'paganus', 'pagana', 'meridianus',
    'meridiana', 'insulanus', 'insulana', 'veteranus', 'decumanus', 'oppidanus', 'oppidana', 'campanus',
    'campana', 'vulcanus', 'vulcana', 'romanus', 'romana', 'germanus', 'germana', 'ruralis'}
# adjectives that stand in localities in place of the place name ("Dominican Amber")
ADJECTIVE_WORDS = {'dominican', 'american', 'african', 'mexican', 'chinese', 'japanese', 'indian', 'australian',
                   'brazilian', 'baltic', 'arabian', 'philippine', 'malagasy', 'burmese', 'peruvian', 'bolivian',
                   'colombian', 'venezuelan', 'argentinian', 'chilean', 'canadian', 'european', 'asian'}
# words around a place name in a locality segment that do not change the place ("Andaman Is", "Mt Kinabalu")
EDGE_WORDS = {'is', 'i', 'island', 'islands', 'isl', 'mts', 'mt', 'mount', 'mountains', 'province', 'prov', 'state',
              'region', 'district', 'lake', 'isla', 'ilha', 'ile', 'pulau', 'dept', 'department'}
# place names read with the article in English: "Formed from the Philippines"
WITH_ARTICLE = {'Philippines', 'Bahamas', 'Comoros', 'Seychelles', 'Netherlands', 'Maldives', 'Moluccas', 'Andes'}
NOT_A_PLACE = re.compile(r'(cene|aceous|amber|\blate\b|\bearly\b|\bmiddle\b|\bformation\b|\d)', re.I)


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def segments(locality):
    """'U.S.A. (Colorado, Florissant, late Eocene)' -> [['U.S.A.'], ['Colorado', 'Florissant', 'late Eocene']]"""
    groups = [g for g in re.split(r'[()]', unicodedata.normalize('NFC', locality)) if g.strip()]
    # 'East Malaysia: Sabah' is one place within another, not two places: the part after the last colon counts
    return [[x.split(':')[-1].strip() for x in re.split(r'[,;]', g) if x.split(':')[-1].strip()] for g in groups]


def place_check(words, locality):
    """'' when the matched words are a whole place in the locality, else the reason to hold"""
    for group in segments(locality):
        for seg in group:
            seg_words = [w for w in re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", seg)]
            core = [w for w in seg_words if fold(w).strip('.') not in EDGE_WORDS]
            if ' '.join(core) == words:
                others = [x for x in group if x != seg and not NOT_A_PLACE.search(x)]
                if others:
                    return 'the type locality lists several places: ' + ', '.join(group)
                return ''
    return 'part of a longer place name in the locality: ' + locality


def places(locality):
    """-> list of (folded joined words, original words) for runs of one to three words of the locality"""
    locality = unicodedata.normalize('NFC', locality)      # 'Tucumán' in NFD split at the accent ('Tucuma')
    words = re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", locality)
    out = []
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            run = words[i:i + n]
            out.append((fold(''.join(run)).replace("'", '').replace('’', '').replace('-', ''), ' '.join(run)))
    return out


def match(stem, place):
    """-> 'exact', 'close' or ''. Close: the place is the stem plus one final vowel (arizon-a, chil-e, mindana-o), or
    the stem is the place plus a connecting -i- (madagascar-i-ensis, taiwan-i-ensis), or the place is the stem plus a
    final -s, -es, -os, -as, -us that the Latin stem drops (philippin-ensis, hondur-ensis). Anything looser (brun-ensis
    for Brunei, which may be Brno; korean-ensis; peruv-ianus) is not proposed."""
    if len(stem) < 3 or len(place) < 4:
        return ''
    if stem == place:
        return 'exact'
    if len(place) == len(stem) + 1 and place.startswith(stem) and place[-1] in 'aeiou':
        return 'close'
    if stem == place + 'i':
        return 'close'
    if len(stem) >= 4 and place.startswith(stem) and place[len(stem):] in ('s', 'es', 'os', 'as', 'us'):
        return 'close'                                 # the Latin stem drops a final -s: Philippines, Honduras
    return ''


ETYMOLOGY_HEADING = re.compile(r'\b(etymology|etymologie|etimolog[ií]a|derivatio nominis|derivation of (the )?name)\b',
                               re.I)


def published_etymology_likely(r, loc, library):
    """policy: a published etymology takes precedence. '' when none is expected, else the reason to hold."""
    year = int(r['year']) if r['year'].isdigit() else 0
    if year >= 1990:     # nearly every description since then prints one, not always within 5 pages of the heading
        return 'described 1990 or later: a published etymology is likely; extract it first'
    if loc and loc['confidence'] in ('A', 'B', 'C') and loc['pdf_page']:
        p = int(loc['pdf_page'])
        for q in range(p, p + 5):
            f = os.path.join(library, 'pages', loc['ref_id'], f'p{q:04d}.txt')
            if os.path.exists(f):
                with open(f, encoding='utf-8', errors='replace') as fh:
                    if ETYMOLOGY_HEADING.search(fh.read()):
                        return 'the original description has an Etymology section: the published etymology first'
        return ''
    return ''


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--write-input', help='also write the input of gender/write_etymology_derivations.rb')
    ap.add_argument('--locator', help='page_locator TSV; with --library, holds names whose original description has '
                                      'an Etymology section (the published etymology goes first)')
    ap.add_argument('--library', help='literature library folder (pages/<ref_id>/pNNNN.txt)')
    a = ap.parse_args()
    located = {}
    if a.locator:
        with open(a.locator, newline='', encoding='utf-8') as fh:
            located = {x['protonym_id']: x for x in csv.DictReader(fh, delimiter='\t')}
    with open(a.protonyms, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh, delimiter='\t'))
    out, counts = [], collections.Counter()
    for r in rows:
        if r['etymology_taxt'].strip() or r.get('etymology_derivation', '').strip():
            continue
        ep = fold(r['epithet'])
        hit = next(((ep[:-len(s)], label) for s, label in SUFFIXES if ep.endswith(s)), None)
        if not hit:
            continue
        stem, suffix = hit
        cands = [(p, words) for p, words in places(r['locality']) if match(stem, p)]
        loose = not cands and any(len(stem) >= 4 and (p.startswith(stem) or stem.startswith(p)) and
                                  abs(len(p) - len(stem)) <= 2 for p, _ in places(r['locality']))
        if not cands and not loose:
            continue                                   # no match: not a pilot candidate at all
        reason = ''
        if loose:
            cands = [(p, words) for p, words in places(r['locality'])
                     if len(stem) >= 4 and (p.startswith(stem) or stem.startswith(p)) and abs(len(p) - len(stem)) <= 2]
        names = sorted({w for _, w in cands}, key=len)
        multi = re.search(r'\)\s*[,;]', r['locality']) or re.search(r'\b[A-Z]{4,}\b', r['locality'])
        if loose:
            reason = 'the stem matches the place only loosely (' + stem + ' / ' + names[0] + ')'
        elif multi:
            reason = 'the type locality lists several places: ' + r['locality']
        elif re.search(r'\b' + re.escape(names[0]) + r'\s+(Is|Islands)\b', r['locality']):
            reason = f'island group ("{names[0]} Is"): the wording "{names[0]} is the type locality" to agree'
        elif ep in LATIN_WORDS:
            reason = 'a Latin word in its own right; the place match may be a coincidence'
        elif len({fold(w) for w in names}) > 1 and not all(fold(names[0]) in fold(w) for w in names):
            reason = 'the stem matches more than one place: ' + '; '.join(names)
        elif fold(names[0]) in ADJECTIVE_WORDS:
            reason = f'the matched word is an adjective ("{names[0]}"), not the place name'
        elif place_check(names[0], r['locality']):
            reason = place_check(names[0], r['locality'])
        elif r['part_of_speech'] and r['part_of_speech'] != 'adjective':
            reason = f"recorded part of speech is {r['part_of_speech']}"
        elif a.library and published_etymology_likely(r, located.get(r['protonym_id']), a.library):
            reason = published_etymology_likely(r, located.get(r['protonym_id']), a.library)
        place = names[0]
        the = 'the ' if place in WITH_ARTICLE else ''
        text = (f"Toponym: Formed from {the}{place} with the Latin adjectival suffix {suffix}, 'of {the}{place}'. "
                f"{(the + place)[:1].upper() + (the + place)[1:]} is the type locality recorded in AntCat.")
        out.append([r['protonym_id'], r['protonym_name'], r['author_citation'], r['year'], r['locality'], stem,
                    place, suffix, 'held' if reason else 'proposed', reason, '' if reason else text])
        counts['held' if reason else 'proposed'] += 1
        if reason:
            counts['held: ' + reason.split(':')[0].split(' (')[0]] += 1
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'author_citation', 'year', 'locality', 'stem', 'place', 'suffix',
                    'result', 'reason', 'derivation'])
        w.writerows(out)
    if a.write_input:
        by_id = {r['protonym_id']: r for r in rows}
        with open(a.write_input, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar='\\')
            w.writerow(['protonym_id', 'protonym_name', 'derivation', 'locality_md5'])
            for x in out:
                if x[8] == 'proposed':
                    loc = re.sub(r'[\t\r\n]+', ' ', by_id[x[0]]['locality'])
                    w.writerow([x[0], x[1], x[10], hashlib.md5(loc.encode('utf-8')).hexdigest()])
    for k in sorted(counts):
        print(f'{counts[k]:5d}  {k}')
    print('candidates', len(out))


if __name__ == '__main__':
    main()
