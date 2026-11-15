#!/usr/bin/env python3
"""
page_locator.py -- the PDF page of each species-group name's original description, from the literature library.

Every later step that reads verbatim text (the etymology as printed, the type locality as printed, the name as
first presented) starts from this page (Brian, 14 Nov 2026).

How
  1. For each reference, the offset between printed and PDF page numbers: integers standing alone in the first
     and last three lines of each page are read as printed page numbers; each votes for printed - PDF page. A
     number that matches only the last digits of the expected page (OCR drops digits: "— 42 —" for 142) counts
     half. The offset with most votes wins; a second offset with strong support is kept for reprints that carry
     two paginations (Karavaiev 1926: 65-69 and 47-51).
  2. For each protonym: the first arabic page of its authorship citation, minus the offset, is the PDF page.
     The epithet must be on that page; OCR errors are allowed (edit distance 1, or 2 for long epithets).

Confidence (column `confidence`)
  A   offset found; the epithet is on the cited page
  B   offset found; the epithet, spelled exactly, is on the page before or after (a heading or offset slip)
  C   no usable offset; the epithet is on exactly one page, or on one page beside "n. sp." or similar
  D   the epithet is in the reference, but not near the cited page (or on several pages with no offset)
  E   the epithet is not found in the reference (OCR, or the wrong reference)
  F   the reference is not in the library (no PDF in AntCat), or no arabic page is cited

Inputs
  --library  the library folder (pages/<ref_id>/p0001.txt ...)
  --protonyms  protonym_pages TSV from gender/protonym_pages_export.rb
  --out  output TSV (one row per protonym), plus <out>.offsets.tsv (one row per reference)
Read only. Standard library only.
"""
import argparse, collections, csv, os, re, sys, unicodedata

csv.field_size_limit(sys.maxsize)

NUM_RE = re.compile(r'(?<![\w/.,:-])(\d{1,4})(?![\w/,:-]|\.\d)')
OF_TOTAL_RE = re.compile(r'(?<![\w/.,:-])(\d{1,4})\s?/\s?(\d{1,4})(?![\w/,:.-])')
PAGE_RE = re.compile(r'\d+')
NEW_SPECIES_RE = re.compile(r'\b(n\.?\s?sp|sp\.?\s?n(ov)?|nov\.?\s?sp|n\.?\s?(subsp|var|st|stirps|r)\b|'
                            r'nov\.|new species|new subspecies|spec\.?\s?nov|sp\.\s?nova|var\.\s?nov)', re.I)


def page_files(library, ref_id):
    folder = os.path.join(library, 'pages', ref_id)
    if not os.path.isdir(folder):
        return None
    files = sorted(f for f in os.listdir(folder) if re.match(r'p\d+\.txt$', f))
    texts = {}
    for f in files:
        with open(os.path.join(folder, f), encoding='utf-8', errors='replace') as fh:
            texts[int(f[1:-4])] = fh.read()
    return texts


def edge_numbers(text, total=None):
    """integers standing alone in the first and last three lines; with `total` (the PDF's page count), also N in
    "N/total", the page numbering of PeerJ and some other journals (Prebus 2021b: "184/462"), which NUM_RE skips"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    edge = lines[:3] + lines[-3:] if len(lines) > 6 else lines
    out = set()
    for line in edge:
        for m in NUM_RE.finditer(line):
            n = int(m.group(1))
            if 0 < n < 5000:
                out.add(n)
        if total:
            for m in OF_TOTAL_RE.finditer(line):
                if int(m.group(2)) == total and 0 < int(m.group(1)) <= total:
                    out.add(int(m.group(1)))
    return out


def offsets_for(texts):
    """-> list of (offset, exact votes, score), best first."""
    votes = collections.Counter()
    seen = {i: edge_numbers(t, len(texts)) for i, t in texts.items()}
    for i, nums in seen.items():
        for n in nums:
            votes[n - i] += 1
    scored = []
    for off, exact in votes.items():
        if exact < 1:
            continue
        score = 0.0
        for i, nums in seen.items():
            expect = i + off
            if expect in nums:
                score += 1
            elif expect > 0 and any(len(str(n)) < len(str(expect)) and str(expect).endswith(str(n)) for n in nums):
                score += 0.5
        scored.append((off, exact, score))
    scored.sort(key=lambda x: (-x[2], -x[1], abs(x[0])))
    return scored


def usable_offsets(offsets):
    """The best offset when it has two exact votes, or one and a clear lead; a second only with two votes."""
    out = []
    if offsets:
        off, exact, score = offsets[0]
        runner_up = offsets[1][2] if len(offsets) > 1 else 0
        if exact >= 2 or (exact >= 1 and score >= 1.5 and score > runner_up):
            out.append(offsets[0])
    out += [o for o in offsets[1:3] if o[1] >= 2]
    return out[:2]


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def page_words(text):
    t = fold(text).replace('­', '')
    t = re.sub(r'-\s*\n\s*', '', t)                    # words broken at a line end
    return re.findall(r'[a-z]+', t)


def edit_distance_le(a, b, k):
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > k:
            return False
        prev = cur
    return prev[-1] <= k


class RefText:
    """One reference's pages, read once: the words of each page and the pages of each word."""

    def __init__(self, texts):
        self.texts = texts
        self.pages_of = collections.defaultdict(set)
        for i, t in texts.items():
            for w in set(page_words(t)):
                self.pages_of[w].add(i)
        self.by_length = collections.defaultdict(list)
        for w in self.pages_of:
            self.by_length[len(w)].append(w)

    def epithet_pages(self, epithet):
        """-> {pdf page: 'exact' | 'fuzzy'}; fuzzy allows OCR errors (edit distance 1, or 2 from 10 letters)"""
        e = fold(epithet)
        hits = {i: 'exact' for i in self.pages_of.get(e, ())}
        if hits:
            return hits
        k = 2 if len(e) >= 10 else 1 if len(e) >= 6 else 0
        for n in range(len(e) - k, len(e) + k + 1) if k else ():
            for w in self.by_length.get(n, ()):
                if edit_distance_le(w, e, k):
                    for i in self.pages_of[w]:
                        hits.setdefault(i, 'fuzzy')
        return hits


def near_new_species(text, epithet):
    t = fold(text)
    e = fold(epithet)
    for m in re.finditer(re.escape(e[:max(4, len(e) - 2)]), t):
        if NEW_SPECIES_RE.search(t[max(0, m.start() - 80):m.end() + 120]):
            return True
    return False


def cited_page(pages):
    m = PAGE_RE.search(pages or '')
    return int(m.group(0)) if m else None


def locate(row, ref, offsets):
    """-> dict with pdf_page, offset, confidence, match, epithet_pages"""
    epithet = row['epithet']
    cited = cited_page(row['authorship_pages'])
    res = dict(cited_page=cited if cited is not None else '', pdf_page='', offset='', offset_votes='',
               confidence='F', match='', epithet_pages='')
    if ref is None or cited is None:
        return res
    texts = ref.texts
    hits = ref.epithet_pages(epithet)
    res['epithet_pages'] = ' '.join(str(i) for i in sorted(hits))
    usable = usable_offsets(offsets)
    for off, exact, _ in usable[:2]:
        page = cited - off
        if page not in texts:
            continue
        res.update(offset=off, offset_votes=exact)
        if page in hits:
            res.update(pdf_page=page, confidence='A', match=hits[page])
            return res
        for near in (page + 1, page - 1):
            if hits.get(near) == 'exact':                 # a fuzzy hit next door is too weak (Wheeler 1902:
                res.update(pdf_page=near, confidence='B', match='exact')     # "Augusta" for augustae)
                return res
    if not hits:
        res['confidence'] = 'E'
        return res
    if len(hits) == 1:
        page = next(iter(hits))
        res.update(pdf_page=page, confidence='C', match=hits[page])
        return res
    flagged = [i for i in sorted(hits) if near_new_species(texts[i], epithet)]
    if len(flagged) == 1:
        res.update(pdf_page=flagged[0], confidence='C', match=hits[flagged[0]])
        return res
    res['confidence'] = 'D'
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--library', required=True)
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    with open(a.protonyms, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh, delimiter='\t'))
    by_ref = collections.defaultdict(list)
    for r in rows:
        by_ref[r['authorship_reference_id']].append(r)

    out_rows, offset_rows, counts = [], [], collections.Counter()
    for ref_id, refrows in sorted(by_ref.items()):
        texts = page_files(a.library, ref_id) if ref_id else None
        offsets = offsets_for(texts) if texts else []
        ref = RefText(texts) if texts else None
        if texts is not None:
            best = offsets[0] if offsets else ('', 0, 0)
            second = offsets[1] if len(offsets) > 1 else ('', 0, 0)
            offset_rows.append([ref_id, len(texts), best[0], best[1], best[2], second[0], second[1]])
        for r in refrows:
            res = locate(r, ref, offsets)
            counts[res['confidence']] += 1
            out_rows.append([r['protonym_id'], r['protonym_name'], r['epithet'], ref_id, r['authorship_pages'],
                             r['author_citation'], res['cited_page'], res['pdf_page'], res['offset'],
                             res['offset_votes'], res['confidence'], res['match'], res['epithet_pages']])

    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'epithet', 'ref_id', 'authorship_pages', 'author_citation',
                    'cited_page', 'pdf_page', 'offset', 'offset_votes', 'confidence', 'match', 'epithet_pages'])
        w.writerows(out_rows)
    with open(a.out + '.offsets.tsv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['ref_id', 'pdf_pages', 'offset', 'votes', 'score', 'second_offset', 'second_votes'])
        w.writerows(offset_rows)
    total = sum(counts.values())
    for c in 'ABCDEF':
        print(f'{c} {counts[c]:6d}  {100 * counts[c] / max(total, 1):5.1f}%')
    print(f'protonyms {total}; references in the library {len(offset_rows)}')


if __name__ == '__main__':
    main()
