#!/usr/bin/env python3
"""
etymology_sources.py -- where each existing AntCat etymology was printed, and what goes in the etymology fields.

AntCat #1607 (14 Nov 2026) split the etymology into: the author's words exactly as printed (etymology_taxt), whose
words they are (etymology_source: original description, or a later work in etymology_reference_id), the pages,
an AntCat translation and an AntCat derivation. The 1,203 etymologies entered before then have none of this. This
script finds each one in the literature library and proposes the fields; nothing is written to AntCat here.

How
  1. The original description's page comes from literature/page_locator.py. The etymology is compared, word by
     word, with that page and the pages around it (it may follow the description by a page or two), then with
     the whole reference.
  2. Not found there: the rarest words of the etymology pick candidate pages anywhere in the library, which are
     compared the same way (a later revision may be the source).
  3. A leading "{ref N}: pages:", or a closing "(Source: {ref N}: pages.)", marks a later work; that reference
     is checked first.
  Words compared: letters and digits, accents and case folded, words broken at line ends joined; AntCat's name
  tags ({tax N} and the like) match any one or two words. Score: the share of the etymology's words found in
  order (difflib matching blocks).

Category (column `category`)
  verbatim      score >= 0.95 in the authorship reference: source original description, pages from the page found
  near          0.75 to 0.95 there: the same passage with differences (OCR, or AntCat's edits); review the text
  partial       0.45 to 0.75 there: AntCat's paraphrase or a shortened quote; the printed passage is shown
  mismatch      the wording matches but a name or place in AntCat's text is not in the passage (a template
                sentence used for several species): never taken as found
  later_work    found in another reference (score >= 0.9), or marked "{ref N}:" and found there
  not_found     no printed passage found: stays as it is, not verified (often no PDF in AntCat)
Printed pages: PDF page plus the reference's offset (page_locator's offsets file), only where that offset is trusted
(the description was located through it, or another reference's offset has three votes); otherwise blank, to check.

Inputs: --protonyms (gender/protonym_pages_export.rb), --locator (page_locator.py output), --library.
Output: --out TSV, one row per protonym with an etymology. Read only. Standard library only.
"""
import argparse, collections, csv, difflib, os, re, sys, unicodedata

csv.field_size_limit(sys.maxsize)

TAG_RE = re.compile(r'\{(tax|taxac|prott|prottac|unmissing|misspelling|missing)\b[^}]*\}')
REF_LEAD_RE = re.compile(r'^\s*\{ref (\d+)\}\s*:\s*([^:]{0,40}?):\s*')
SOURCE_TAIL_RE = re.compile(r'\s*\(Source:\s*\{ref (\d+)\}\s*:?\s*([^)]{0,40})\)\.?\s*$')
ANY_REF_RE = re.compile(r'\{ref (\d+)\}')
WILD = '∗'


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def tokens_of_taxt(taxt):
    t = TAG_RE.sub(f' {WILD} ', taxt)
    t = re.sub(r'\{[^}]*\}', ' ', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    return [w if w != WILD else WILD for w in re.findall(rf'[a-z0-9]+|{WILD}', fold(t))]


def tokens_of_page(text):
    t = fold(text).replace('­', '')
    t = re.sub(r'-\s*\n\s*', '', t)
    return re.findall(r'[a-z0-9]+', t)


def score(ety, page, spread=1.5):
    """share of the etymology's words found in order in `page` within one passage (at most `spread` times the
    etymology's length: scattered common words are not a match), and that passage's span"""
    real = [w for w in ety if w != WILD]
    if not real or not page:
        return 0.0, None
    sm = difflib.SequenceMatcher(None, ety, page, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return 0.0, None
    window = int(spread * len(ety)) + 8
    best, best_span, j, total = 0, None, 0, 0
    for i, b in enumerate(blocks):
        total += b.size
        while b.b + b.size - blocks[j].b > window:
            total -= blocks[j].size
            j += 1
        if total > best:
            best, best_span = total, (blocks[j].b, b.b + b.size)
    wild = sum(1 for w in ety if w == WILD)
    return min(1.0, (best + wild) / len(ety)), best_span


def best_window(ety, pages, page_tokens):
    """compare with each page joined to the next (a passage may run over); -> (score, pdf page, passage). A text
    layer of two columns interleaves lines: a passage found whole only when spread over three times its length
    counts when nothing is missing from it."""
    best = (0.0, None, '')
    for p in pages:
        toks = page_tokens.get(p)
        if toks is None:
            continue
        joined = toks + page_tokens.get(p + 1, [])
        s, span = score(ety, joined)
        s3, span3 = score(ety, joined, spread=3)
        if s3 >= 0.97 and s3 > s:
            s, span = s3, span3
        if s > best[0]:
            passage = ' '.join(joined[span[0]:span[1]]) if span else ''
            on = p if not span or span[0] < len(toks) else p + 1
            best = (s, on, passage[:900])
    return best


def missing_words(ety, passage, taxt):
    """the etymology's words absent from the passage; capitalised ones (names, places) flagged"""
    have = set(passage.split())
    capital = {fold(w) for w in re.findall(r'\b[A-Z][a-z\u00e0-\u017f]+', re.sub(r'\{[^}]*\}|<[^>]+>', ' ', taxt))}
    def split_present(w):                              # a word cut by interleaved columns: "shambh" ... "ala"
        return any(w[:k] in have and w[k:] in have for k in range(3, len(w) - 1))
    gone = [w for w in dict.fromkeys(ety) if w != WILD and w not in have and not split_present(w)]
    return gone, [w for w in gone if w in capital]


class Library:
    def __init__(self, folder):
        self.folder = folder
        self.cache = {}
        self._index = None

    def pages(self, ref_id):
        if ref_id not in self.cache:
            d = os.path.join(self.folder, 'pages', ref_id)
            out = {}
            if ref_id and os.path.isdir(d):
                for f in os.listdir(d):
                    m = re.match(r'p(\d+)\.txt$', f)
                    if m:
                        with open(os.path.join(d, f), encoding='utf-8', errors='replace') as fh:
                            out[int(m.group(1))] = tokens_of_page(fh.read())
            self.cache[ref_id] = out
        return self.cache[ref_id]

    def index(self):
        """word -> set of (ref_id, page), built once over the whole library"""
        if self._index is None:
            idx = collections.defaultdict(set)
            for ref_id in os.listdir(os.path.join(self.folder, 'pages')):
                for p, toks in self.pages(ref_id).items():
                    for w in set(toks):
                        if len(w) >= 5:
                            idx[w].add((ref_id, p))
                self.cache.pop(ref_id, None)
            self._index = idx
        return self._index


def offsets_by_ref(path):
    out = {}
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as fh:
            for r in csv.DictReader(fh, delimiter='\t'):
                # trusted only when most pages carry it: França et al. 2024 (18 pages, no printed numbers) got +1 from
                # four stray numbers ("(11 at CELC:"), and its etymology page came out one too high (sample, 14 Nov)
                votes, pdf_pages = int(r['votes'] or 0), int(r['pdf_pages'] or 0)
                if r['offset'] != '' and votes >= 2 and votes >= 0.5 * pdf_pages:
                    out[r['ref_id']] = (int(r['offset']), votes)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--locator', required=True)
    ap.add_argument('--library', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    with open(a.protonyms, newline='', encoding='utf-8') as fh:
        rows = [r for r in csv.DictReader(fh, delimiter='\t') if r['etymology_taxt'].strip()]
    with open(a.locator, newline='', encoding='utf-8') as fh:
        loc = {r['protonym_id']: r for r in csv.DictReader(fh, delimiter='\t')}
    offsets = offsets_by_ref(a.locator + '.offsets.tsv')
    text_kind, ref_year = {}, {}
    refs_tsv = os.path.join(a.library, 'refs.tsv')
    if os.path.exists(refs_tsv):
        with open(refs_tsv, newline='', encoding='utf-8') as fh:
            for x in csv.DictReader(fh, delimiter='\t'):
                y = re.search(r'\d{4}', x.get('year') or '')
                ref_year[x['ref_id']] = int(y.group(0)) if y else None
                ocr, layer = int(x['ocr_pages'] or 0), int(x['text_layer_pages'] or 0)
                text_kind[x['ref_id']] = 'text layer' if not ocr else 'OCR' if not layer else 'mixed'

    lib = Library(a.library)

    results, unresolved = {}, []
    for r in rows:
        taxt = r['etymology_taxt']
        lead = REF_LEAD_RE.match(taxt) or SOURCE_TAIL_RE.search(taxt)
        body = (taxt[lead.end():] if lead.start() == 0 else taxt[:lead.start()]) if lead else taxt
        ety = tokens_of_taxt(body)
        ref_id = r['authorship_reference_id']
        l = loc.get(r['protonym_id'], {})
        res = dict(category='not_found', score=0.0, found_ref=ref_id if lead is None else '', found_pdf_page='',
                   printed_page='', passage='', later_ref='', note='', missing='')
        if lead:                                       # "{ref N}: pages:" -- a later work by AntCat's own record
            later = lead.group(1)
            res.update(later_ref=later, note=f'marked as from {{ref {later}}}: {lead.group(2).strip()}')
            pages = lib.pages(later)
            if pages:
                s, p, passage = best_window(ety, sorted(pages), pages)
                gone, gone_names = missing_words(ety, passage, body)
                res.update(score=round(s, 3), found_ref=later, found_pdf_page=p or '', passage=passage,
                           missing=' '.join(gone))
                if s >= 0.9 and not gone_names:
                    res['category'] = 'later_work'
            results[r['protonym_id']] = res
            continue
        pages = lib.pages(ref_id)
        if pages:
            located = int(l['pdf_page']) if l.get('pdf_page') else None
            near = [p for p in range(located - 1, located + 4)] if located else []
            s, p, passage = best_window(ety, near, pages) if near else (0.0, None, '')
            if s < 0.95:
                s2, p2, passage2 = best_window(ety, sorted(pages), pages)
                if s2 > s:
                    s, p, passage = s2, p2, passage2
            res.update(score=round(s, 3), found_pdf_page=p or '', passage=passage)
            gone, gone_names = missing_words(ety, passage, body)
            res['missing'] = ' '.join(gone)
            if s >= 0.95 and not gone_names:
                res['category'] = 'verbatim'
            elif gone_names and s >= 0.45:
                res['category'] = 'mismatch'                # same wording, another name (a template sentence)
            elif s >= 0.75:
                res['category'] = 'near'
            elif s >= 0.45:
                res['category'] = 'partial'
        if res['category'] in ('not_found', 'partial', 'mismatch'):
            unresolved.append((r, ety, res, body))
        results[r['protonym_id']] = res

    if unresolved:                                     # step 2: anywhere in the library
        idx = lib.index()
        for r, ety, res, body in unresolved:
            words = sorted({w for w in ety if w != WILD and len(w) >= 5 and w in idx}, key=lambda w: len(idx[w]))
            if len(words) < 3:
                continue
            cands = collections.Counter()
            for w in words[:6]:
                for rp in idx[w]:
                    cands[rp] += 1
            # A later work is published after the original description: an earlier paper with the same words is
            # another species' etymology (Aphaenogaster bressleri 2021 matched Yoshimura & Fisher 2012). Sorted,
            # so that ties do not depend on set order (review of 14 Nov: two runs chose different papers).
            year = int(r['year']) if (r.get('year') or '').isdigit() else None
            ranked = sorted(((n, ref, p) for (ref, p), n in cands.items()
                             if n >= 3 and ref != r['authorship_reference_id']
                             and not (year and ref_year.get(ref) and ref_year[ref] < year)),
                            key=lambda x: (-x[0], x[1], x[2]))
            best = (0.0, None, None, '')
            for n, ref, p in ranked[:8]:
                pages = lib.pages(ref)
                s, pp, passage = best_window(ety, [p - 1, p], pages)
                if s > best[0]:
                    best = (s, ref, pp, passage)
            gone, gone_names = missing_words(ety, best[3], body)
            if best[0] >= 0.9 and not gone_names and (best[0] > res['score'] or res['category'] == 'mismatch'):
                res.update(category='later_work', score=round(best[0], 3), found_ref=best[1], later_ref=best[1],
                           found_pdf_page=best[2] or '', passage=best[3], missing=' '.join(gone),
                           note='found in another reference, not the authorship reference')

    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'year', 'author_citation', 'authorship_reference_id',
                    'authorship_pages', 'locator_confidence', 'category', 'score', 'proposed_source',
                    'proposed_reference_id', 'proposed_pages', 'found_ref', 'found_pdf_page', 'etymology_taxt',
                    'printed_passage', 'missing_words', 'text_kind', 'note'])
        counts = collections.Counter()
        for r in rows:
            res = results[r['protonym_id']]
            cat = res['category']
            counts[cat] += 1
            source, ref_out, printed = '', '', ''
            # A printed page only where the offset is trusted: for the authorship reference, when the description
            # itself was located through that offset (A, B); for another reference, with three or more votes.
            # (Terayama 1996, Silva et al. 2013: an offset that disagrees with the cited page.)
            l_conf = loc.get(r['protonym_id'], {}).get('confidence', '')
            if res['found_pdf_page'] != '' and res['found_ref'] in offsets:
                off, votes = offsets[res['found_ref']]
                own = res['found_ref'] == r['authorship_reference_id']
                if (own and l_conf in ('A', 'B')) or (not own and votes >= 3):
                    printed = str(int(res['found_pdf_page']) + off)
                cited = re.search(r'\d+', r['authorship_pages'])
                if own and printed and cited and int(printed) < int(cited.group(0)):
                    printed = ''                       # an etymology before its name's heading: offset off by one?
                    res['note'] = (res['note'] + '; ' if res['note'] else '') + 'page before the cited page: check'

            if cat in ('verbatim', 'near', 'partial'):          # never 'mismatch'
                source = 'original_description'
            elif cat == 'later_work':
                source, ref_out = 'later_work', res['later_ref']
            w.writerow([r['protonym_id'], r['protonym_name'], r['year'], r['author_citation'],
                        r['authorship_reference_id'], r['authorship_pages'],
                        loc.get(r['protonym_id'], {}).get('confidence', ''), cat, res['score'], source, ref_out,
                        printed if source else '', res['found_ref'], res['found_pdf_page'], r['etymology_taxt'],
                        res['passage'], res['missing'], text_kind.get(res['found_ref'], ''), res['note']])
    total = sum(counts.values())
    for c in ('verbatim', 'near', 'partial', 'mismatch', 'later_work', 'not_found'):
        print(f'{c:11s} {counts[c]:5d}  {100 * counts[c] / max(total, 1):5.1f}%')
    print(f'etymologies {total}')


if __name__ == '__main__':
    main()
