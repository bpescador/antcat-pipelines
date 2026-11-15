#!/usr/bin/env python3
"""
verify_etymology_sources.py -- checks on the write candidates of etymology_sources.py, before any write.

Brian's conditions of 14 Nov 2026 (17:43): write only the word-for-word matches with a confidently established
printed page (621 original descriptions, 100 later works); confirm the reference, the printed page and that the
passage belongs to the named species; for later works, that the passage is an etymology of this species and not of
another one. The normalized score alone is not proof. This script makes the checks that the text allows, so that
the page images are looked at where they matter (all flagged rows, plus a sample of the rest).

Checks (columns)
  page_check     'printed'    the proposed printed page number stands in the first or last lines of the PDF page
                 'neighbours' it does not, but the pages before or after carry the numbers the offset predicts
                 'offset'     neither: the page rests on the paper's offset alone
  species_check  'in passage' the epithet is inside the matched passage
                 'account'    the last new-species heading ("<epithet> ... sp. n.") before the passage is this name's
                 'other species (x)'  it is another name's (or a caption or diagnosis that looks like one)
                 'near' / 'far' / 'absent'  no such heading: the last mention of the epithet within 600 words, further,
                              or none in the 15 PDF pages before
  page_bracket   originals only: the passage's printed page against the name's description page and the next name's
                 in the same paper ('inside', 'last name in paper', "on next name's page", 'after next name', ...)
  year_check     later works only: 'later' (published after the original), 'same year', 'earlier'
  original_check later works only, original description not located: does the whole original reference carry the
                 etymology (score >= 0.9)? 'in original' means the source would be the original description
  verdict        'ok' or 'check' with the reasons. A species is accepted on 'in passage', 'account' or a page
                 'inside' its own account; any 'other species' or a page outside the account holds the row

Inputs: --sources (etymology_sources TSV), --library, --protonyms (protonym_pages export).
Read only. Standard library only. Run with PYTHONPATH=gender:literature (sandboxes set PYTHONSAFEPATH).
"""
import argparse, csv, os, re, sys, unicodedata

from etymology_sources import (Library, tokens_of_taxt, score, best_window, REF_LEAD_RE, SOURCE_TAIL_RE, fold)
from page_locator import edge_numbers, edit_distance_le

csv.field_size_limit(sys.maxsize)

HEADING = {'etymology', 'etymologie', 'etimologia', 'etymologia', 'derivatio', 'derivation'}
NEW_SP = re.compile(r'\b(sp|n|nov|new|spec)\s+(n|nov|sp|species|nova)\b')
LOOKBACK = 15                    # PDF pages before the passage page searched for the species heading


def raw_page(library, ref_id, p):
    f = os.path.join(library, 'pages', ref_id, f'p{int(p):04d}.txt')
    if not os.path.exists(f):
        return ''
    with open(f, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def first_number(pages):
    m = re.search(r'\d+', pages or '')
    return int(m.group(0)) if m else None


def description_page(pages):
    """the cited page of the description itself: "34 (in key), 200, fig. 120" -> 200 (Prebus 2021b); a first page
    "in key", "in list" or "in table" is passed over when a plain page follows. "Diagnosis in key" is the
    description and stays."""
    parts = [x.strip() for x in (pages or '').split(',')]
    if parts and re.search(r'\((in key|in list|in table)', parts[0]):
        for x in parts[1:]:
            if re.fullmatch(r'\d+(-\d+)?', x):
                return int(re.match(r'\d+', x).group(0))
    return first_number(pages)


def page_check(library, ref_id, pdf, printed, total):
    if printed is None:
        return 'none'
    if printed in edge_numbers(raw_page(library, ref_id, pdf), total):
        return 'printed'
    before = printed - 1 in edge_numbers(raw_page(library, ref_id, pdf - 1), total)
    after = printed + 1 in edge_numbers(raw_page(library, ref_id, pdf + 1), total)
    return 'neighbours' if before or after else 'offset'


QUOTES = '“"«„‘\''


def quoted(raw, passage):
    """True when the matched passage opens with a quotation mark on the page: the later work quotes an earlier text
    (MacKay 2025: 428 quotes Baroni Urbani 1972 for Camponotus kutterianus), so it is not where the etymology was
    published (Brian, 14 Nov: provenance is where it was published)"""
    words = passage.split()[:4]
    if len(words) < 2:
        return False
    t = unicodedata.normalize('NFKD', raw)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    pat = r'\W+'.join(re.escape(w) for w in words)
    for m in re.finditer(pat, t, re.I):
        lead = t[max(0, m.start() - 200):m.start()]
        h = max(lead.lower().rfind('etymolog'), lead.lower().rfind('derivatio'))
        lead = lead[h:] if h >= 0 else lead[-4:]      # from the heading, or the few characters before the passage
        opened = sum(lead.count(q) for q in '“«„') + lead.count('"') % 2
        closed = sum(lead.count(q) for q in '”»')
        if opened > closed or (lead.rstrip().endswith(("'", '‘'))):
            return True
    return False


def is_epithet(word, ep):
    if word == ep:
        return True
    k = 2 if len(ep) >= 10 else 1 if len(ep) >= 6 else 0
    return bool(k) and abs(len(word) - len(ep)) <= k and word[:3] == ep[:3] and edit_distance_le(word, ep, k)


def species_check(pages, pdf, ety, ep, sisters):
    """-> (result, words between the deciding mention and the passage). `sisters`: the epithets of the other names
    described in the same reference (from the protonym export). In a paper of new species, the passage belongs to the
    account whose heading ("<epithet> ... sp. n.") stands last before it; without such headings, to the name last
    mentioned before it."""
    seq, starts = [], {}
    for p in range(pdf - LOOKBACK, pdf + 2):
        starts[p] = len(seq)
        seq += pages.get(p, [])
    here = pages.get(pdf, []) + pages.get(pdf + 1, [])
    s, span = score(ety, here)
    s3, span3 = score(ety, here, spread=3)
    if s3 >= 0.97 and s3 > s:
        span = span3
    if not span:
        return 'absent', ''
    a, b = starts[pdf] + span[0], starts[pdf] + span[1]
    if any(is_epithet(w, ep) for w in seq[a:b]):
        return 'in passage', 0
    for i in range(a - 1, -1, -1):                     # the last new-species heading before the passage
        w = seq[i]
        mine = is_epithet(w, ep)
        if (mine or w in sisters) and NEW_SP.search(' '.join(seq[i + 1:i + 8])):
            return ('account' if mine else f'other species ({w})'), a - i
    mentions = [i for i in range(a) if is_epithet(seq[i], ep)]
    if not mentions:
        return 'absent', ''
    gap = a - mentions[-1]
    return ('near' if gap <= 600 else 'far'), gap


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--sources', required=True)
    ap.add_argument('--library', required=True)
    ap.add_argument('--protonyms', required=True, help='protonym_pages export, for the names of each reference')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    sisters, cited_pages = {}, {}
    with open(a.protonyms, newline='', encoding='utf-8') as fh:
        for x in csv.DictReader(fh, delimiter='\t'):
            sisters.setdefault(x['authorship_reference_id'], set()).add(fold(x['epithet']))
            c = description_page(x['authorship_pages'])
            if c is not None:
                cited_pages.setdefault(x['authorship_reference_id'], set()).add(c)

    years = {}
    with open(os.path.join(a.library, 'refs.tsv'), newline='', encoding='utf-8') as fh:
        for x in csv.DictReader(fh, delimiter='\t'):
            m = re.search(r'\d{4}', x.get('year') or '')
            years[x['ref_id']] = int(m.group(0)) if m else None
    with open(a.sources, newline='', encoding='utf-8') as fh:
        rows = [r for r in csv.DictReader(fh, delimiter='\t')
                if r['category'] in ('verbatim', 'later_work') and r['proposed_pages'].strip()]
    lib = Library(a.library)
    out, tally = [], {}
    for r in rows:
        ref, pdf = r['found_ref'], int(r['found_pdf_page'])
        printed = first_number(r['proposed_pages'])
        taxt = r['etymology_taxt']
        lead = REF_LEAD_RE.match(taxt) or SOURCE_TAIL_RE.search(taxt)
        body = (taxt[lead.end():] if lead.start() == 0 else taxt[:lead.start()]) if lead else taxt
        ety = tokens_of_taxt(body)
        ep = fold(r['protonym_name'].split()[-1])
        pages = lib.pages(ref)
        pc = page_check(a.library, ref, pdf, printed, len(pages))
        sc, gap = species_check(pages, pdf, ety, ep, sisters.get(ref, set()) - {ep})
        reasons = []
        if pc == 'offset':
            reasons.append('printed page not confirmed on the page')
        bracket = ''
        if r['category'] == 'verbatim':
            # the passage's printed page between the name's cited page and the next name's cited page in the same
            # paper (AntCat cites the page of each heading): the account the passage stands in
            cited = description_page(r['authorship_pages'])
            later = sorted(c for c in cited_pages.get(ref, ()) if cited is not None and c > cited)
            nxt = later[0] if later else None
            if printed is None or cited is None:
                bracket = 'unknown'
            elif printed < cited:
                bracket = 'before cited page'
            elif nxt is None:
                bracket = 'last name in paper' if printed - cited <= 15 else 'far after cited page'
            elif printed < nxt:
                bracket = 'inside'
            elif printed == nxt:
                bracket = 'on next name\'s page'
            else:
                bracket = 'after next name'
        species_ok = sc in ('in passage', 'account') or bracket in ('inside', 'last name in paper') or \
            (sc == 'near' and bracket != 'after next name')
        if bracket in ('before cited page', 'after next name', 'far after cited page') or sc.startswith('other'):
            species_ok = False                         # a conflict between the two checks is held, not resolved
        if not species_ok:
            reasons.append(f'species: {sc}' + (f', page {bracket}' if bracket else ''))
        yc = oc = ''
        if r['category'] == 'later_work':
            yo, yf = int(r['year'] or 0), years.get(ref)
            yc = 'unknown' if not (yo and yf) else 'later' if yf > yo else 'same year' if yf == yo else 'earlier'
            if yc != 'later':
                reasons.append(f'later work is {yc}')
            if quoted(raw_page(a.library, ref, pdf) + raw_page(a.library, ref, pdf + 1), r['printed_passage']):
                reasons.append('the later work quotes an earlier text')
            if r['locator_confidence'] not in ('A', 'B', 'C'):
                orig = r['authorship_reference_id']
                op = lib.pages(orig)
                if op:
                    s, on, _ = best_window(ety, sorted(op), op)
                    oc = f'in original (p{on}, {s:.2f})' if s >= 0.9 else f'not in original ({s:.2f})'
                    if s >= 0.9:
                        reasons.append('etymology is in the original description')
                else:
                    oc = 'original not in library'
                    reasons.append(oc)
        lib.cache.clear()
        verdict = 'ok' if not reasons else 'check'
        tally[(r['category'], verdict)] = tally.get((r['category'], verdict), 0) + 1
        out.append([r['protonym_id'], r['protonym_name'], r['author_citation'], r['category'], r['proposed_source'],
                    r['proposed_reference_id'] or r['authorship_reference_id'], r['proposed_pages'], pdf,
                    r['text_kind'], r['locator_confidence'], r['score'], pc, sc, gap, bracket, yc, oc, verdict,
                    '; '.join(reasons)])
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'author_citation', 'category', 'source', 'reference_id', 'pages',
                    'pdf_page', 'text_kind', 'locator_confidence', 'score', 'page_check', 'species_check',
                    'words_since_mention', 'page_bracket', 'year_check', 'original_check', 'verdict', 'reasons'])
        w.writerows(out)
    for k in sorted(tally):
        print(*k, tally[k])
    print('rows', len(out))


if __name__ == '__main__':
    main()
