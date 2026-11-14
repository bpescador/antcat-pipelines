#!/usr/bin/env python3
"""
ocr_pages.py -- OCR the scanned pages of library PDFs, choosing the OCR language for each reference, and
write one text file per page for build_library.py --ocr-dir.

Run it where tesseract has the languages. The cloud workspace has eng deu fra ita spa por nld pol rus and
more; the Mac shell VM has English only. Pages with a text layer (build_library.MIN_TEXT_CHARS or more) are
skipped, so only the pages build_library records as missing are OCR'd.

Language, once per reference, from its first scanned pages:
  - tesseract's script detection (OSD). Cyrillic -> rus+eng: Russian and Ukrainian ant papers print the
    species names in Latin letters. (No Ukrainian model here; Ukrainian reads acceptably as Russian.)
  - Latin script -> OCR the page in five languages at once, count each language's common words, and use
    the one that wins. One language is about three times faster than five, and reads better.
  - Too little text to tell (tables, plates, a Latin diagnosis) -> eng.
Tested 13 Nov 2026 on Radchenko 1995h (127977) p. 3: Latin-alphabet OCR gave gibberish, rus read it cleanly.

Output in --out:
  <ref_id>_p<page>.txt   one file per page, PDF page numbers (what build_library.py --ocr-dir reads)
  languages.tsv          ref_id, page, lang, chars: one row per page written
  ref_languages.tsv      ref_id, script, lang, how: the choice per reference, so a rerun keeps it
Resumable: pages already written are skipped.

Usage:
  python3 ocr_pages.py --pdf-dir DIR --out DIR [--jobs 2] [--only ID,ID] [--max-seconds N]
PDF names start with the AntCat reference id: <ref_id>.pdf (library layout) or <ref_id>__<name>.pdf.
"""
import argparse, collections, csv, glob, os, re, subprocess, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_library import MIN_TEXT_CHARS, pdf_page_count, text_layer_pages  # noqa: E402

DETECT_LANGS = 'eng+deu+fra+ita+spa+por+nld'
# Words common in one language and rare in the others (short words shared across languages left out).
COMMON_WORDS = {
    'eng': 'the and of with is are from this which by to that as be have not or'.split(),
    'deu': 'der die das und ist mit von nicht ein eine auf den des sich dem bei wie auch sind'.split(),
    'fra': 'le les et est une du avec dans pas sur qui que au aux ce sont plus'.split(),
    'ita': 'il della che di con del una sono per gli non nel alla delle dei questa molto'.split(),
    'spa': 'el los las y que una por para es se del con su como más muy'.split(),
    'por': 'os do da com uma não dos das em ao pelo pela são muito'.split(),
    'nld': 'het een en van is met niet zijn op bij ook dan wordt'.split(),
}
MIN_WORDS_TO_DECIDE = 40
MIN_SHARE_TO_DECIDE = 0.03
# OSD script -> (tesseract languages, letters of that script). Species names stay in Latin letters, hence +eng.
NON_LATIN = {
    'Cyrillic': ('rus+eng', r'[Ѐ-ӿ]'),
    'Japanese': ('jpn+eng', r'[぀-ヿ一-鿿]'),
    'Han': ('chi_sim+chi_tra+eng', r'[一-鿿]'),
    'HanS': ('chi_sim+eng', r'[一-鿿]'),
    'HanT': ('chi_tra+eng', r'[一-鿿]'),
    'Hangul': ('kor+eng', r'[가-힯]'),
}
# Share of letters in the detected script. Measured 13 Nov 2026: Radchenko 1995h 0.81 (Cyrillic), Azuma 1951
# 0.10 to 0.14 (Japanese; one kanji is a word, the Latin names have many letters), false Cyrillic on Bingham
# 1903 and Borgmeier 1957a 0.00 and 0.02.
MIN_SCRIPT_SHARE = 0.05


def render(pdf, page, tmp, timeout):
    base = os.path.join(tmp, f'p{page}')
    subprocess.run(['pdftoppm', '-r', '300', '-gray', '-png', '-f', str(page), '-l', str(page), '-singlefile', pdf, base],
                   check=True, timeout=timeout, capture_output=True)
    return base + '.png'


def tesseract(png, lang, timeout, psm=None):
    cmd = ['tesseract', png, '-', '-l', lang] + (['--psm', str(psm)] if psm is not None else [])
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, env=dict(os.environ, OMP_THREAD_LIMIT='1'))
    except subprocess.TimeoutExpired:
        return ''
    return res.stdout.decode('utf-8', 'replace')


def script_of(png, timeout):
    try:
        res = subprocess.run(['tesseract', png, '-', '--psm', '0'], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ''
    m = re.search(r'^Script:\s*(\S+)', res.stdout.decode('utf-8', 'replace'), re.M)
    return m.group(1) if m else ''


def language_of(text):
    words = re.findall(r'[^\W\d_]+', text.lower())
    if len(words) < MIN_WORDS_TO_DECIDE:
        return None, 0.0
    counts = collections.Counter(words)
    share = {lang: sum(counts[w] for w in ws) / len(words) for lang, ws in COMMON_WORDS.items()}
    lang = max(share, key=share.get)
    return (lang, share[lang]) if share[lang] >= MIN_SHARE_TO_DECIDE else (None, share[lang])


def script_share(text, chars):
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if re.match(chars, c)) / len(letters) if len(letters) >= MIN_WORDS_TO_DECIDE else 0.0


def choose_language(ref_id, pdf, pages, timeout):
    """pages: the scanned page numbers of this reference. Returns (ref_id, script, lang, how)."""
    # Skip a title page or cover when there is more than one page; look at up to three pages.
    sample = (pages[1:] or pages)[:3]
    with tempfile.TemporaryDirectory() as tmp:
        scripts = []
        for p in sample:
            png = render(pdf, p, tmp, timeout)
            script = script_of(png, timeout)
            scripts.append(script)
            # OSD alone misreads some plates and poor scans (Bingham 1903 and Borgmeier 1957a came out as
            # Cyrillic, 13 Nov 2026): a non-Latin script counts only if OCR in it gives mostly its letters.
            if script in NON_LATIN:
                lang, chars = NON_LATIN[script]
                share = script_share(tesseract(png, lang, timeout), chars)
                if share >= MIN_SCRIPT_SHARE:
                    return ref_id, script, lang, f'OSD {script} on p{p}, {share:.2f} of letters in it'
            lang, share = language_of(tesseract(png, DETECT_LANGS, timeout))
            if lang:
                return ref_id, script or 'Latin', lang, f'common words {share:.2f} on p{p}'
    return ref_id, '/'.join(s for s in scripts if s) or '?', 'eng', 'too little text to tell; default'


def ocr_one(ref_id, pdf, page, lang, timeout):
    with tempfile.TemporaryDirectory() as tmp:
        return ref_id, page, lang, tesseract(render(pdf, page, tmp, timeout), lang, timeout)


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument('--pdf-dir', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--jobs', type=int, default=os.cpu_count() or 1)
    a.add_argument('--only', help='comma-separated reference ids')
    a.add_argument('--timeout', type=int, default=180)
    a.add_argument('--max-seconds', type=int, default=0, help='stop submitting new pages after this many seconds')
    o = a.parse_args()
    started = time.time()
    os.makedirs(o.out, exist_ok=True)
    only = {int(x) for x in o.only.split(',')} if o.only else None

    pdfs = {}
    for p in sorted(glob.glob(os.path.join(o.pdf_dir, '*.pdf'))):
        m = re.match(r'(\d+)(?:__.*)?\.pdf$', os.path.basename(p))
        if m and (only is None or int(m.group(1)) in only):
            pdfs[int(m.group(1))] = p

    # Scanned pages still to do, per reference.
    todo = {}
    for ref_id, pdf in pdfs.items():
        n = pdf_page_count(pdf)
        layer = text_layer_pages(pdf, n)
        pages = [i for i in range(1, n + 1) if len(layer[i - 1].strip()) < MIN_TEXT_CHARS]
        left = [i for i in pages if not os.path.exists(os.path.join(o.out, f'{ref_id}_p{i}.txt'))]
        if left:
            todo[ref_id] = (pages, left)
    print(f'{len(pdfs)} PDFs; {len(todo)} with pages to OCR; {sum(len(v[1]) for v in todo.values())} pages', flush=True)

    ref_lang_path = os.path.join(o.out, 'ref_languages.tsv')
    langs = {}
    if os.path.exists(ref_lang_path):
        for r in csv.reader(open(ref_lang_path, encoding='utf-8'), delimiter='\t'):
            langs[int(r[0])] = r[2]
    lang_rows = open(os.path.join(o.out, 'languages.tsv'), 'a', encoding='utf-8')
    with ProcessPoolExecutor(max_workers=o.jobs) as pool:
        need = [r for r in todo if r not in langs]
        with open(ref_lang_path, 'a', encoding='utf-8') as f:
            for fut in as_completed([pool.submit(choose_language, r, pdfs[r], todo[r][0], o.timeout) for r in need]):
                ref_id, script, lang, how = fut.result()
                langs[ref_id] = lang
                f.write(f'{ref_id}\t{script}\t{lang}\t{how}\n')
                f.flush()
                print(f'{ref_id}\t{script}\t{lang}\t{how}', flush=True)
        jobs = [(r, p) for r in sorted(todo) for p in todo[r][1]]
        futs, i, done = set(), 0, 0
        while i < len(jobs) or futs:
            while i < len(jobs) and len(futs) < o.jobs * 2 and not (o.max_seconds and time.time() - started > o.max_seconds):
                r, p = jobs[i]
                futs.add(pool.submit(ocr_one, r, pdfs[r], p, langs[r], o.timeout))
                i += 1
            if not futs:
                break
            fut = next(as_completed(futs))
            futs.remove(fut)
            ref_id, page, lang, text = fut.result()
            path = os.path.join(o.out, f'{ref_id}_p{page}.txt')
            with open(path + '.part', 'w', encoding='utf-8') as f:
                f.write(text)
            os.replace(path + '.part', path)  # a page file exists only when complete
            lang_rows.write(f'{ref_id}\t{page}\t{lang}\t{len(text.strip())}\n')
            lang_rows.flush()
            done += 1
            if done % 100 == 0:
                print(f'{done} pages, {time.time() - started:.0f} s', flush=True)
    stopped = i < len(jobs)
    print(f'done: {done} pages in {time.time() - started:.0f} s' + ('; stopped at --max-seconds, run again to continue' if stopped else ''))


if __name__ == '__main__':
    main()
