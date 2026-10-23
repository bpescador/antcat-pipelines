#!/usr/bin/env python3
"""
depository_triage.py -- give every A/B residual row from diff_depositories.py a bucket,
a suggested decision and the evidence for it, so the reviewer only decides.

Buckets, first match wins:
  pair     the row's NGC-only and AntCat-only codes form a pair listed in --pairs
           (possible same collection). One answer per pair settles all its rows.
  notes    AntCat's own type text or notes already mention every NGC-only code
           outside the depository statement (e.g. "Bolton cites the holotype
           depository as IEUB"). Suggest: AntCat correct.
  author   (B rows) Bolton's index "PRINCIPAL DEPOSITORIES OF SINGLE AUTHORS" (in the
           SUB. 8 depositories file) contains the codes of one side only.
  paper    evidence quoted from the original description, from --evidence
           (protonym_id,suggestion,evidence,source).
  none     nothing automatic: needs the original description or the type specimen.

  PYTHONPATH=.:bolton python3 bolton/depository_triage.py --run <diff_depositories out> \\
      --protonyms protonyms_species_typeinfo.jsonl --bolton-list "SUB. 8 ....docx" \\
      [--pairs pairs.csv] [--evidence evidence.csv] --out triage.csv
pairs.csv: ngc_code,antcat_code,question,suggestion
"""
import argparse, csv, json, re, unicodedata


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s or '') if not unicodedata.combining(c)).lower()


def author_index(path):
    import docx
    ps = [p.text for p in docx.Document(path).paragraphs]
    i0 = next(i for i, t in enumerate(ps) if 'PRINCIPAL DEPOSITORIES OF SINGLE AUTHORS' in t)
    idx = {}
    for t in ps[i0 + 1:]:
        if '\t' not in t:
            continue
        name, rest = t.split('\t', 1)
        codes = re.findall(r'\b[A-Z]{3,6}\b', re.sub(r'\[.*', '', rest))
        if codes:
            idx[fold(name.strip())] = (codes, re.sub(r'\s+', ' ', t.replace('\t', ' ')).strip())
    return idx


def sentence_with(text, code):
    """the sentence of AntCat type text that mentions code (tags stripped)"""
    t = re.sub(r'<[^>]+>', '', text)
    ss = [s.strip() for s in re.split(r'(?<=[.;])\s+(?=[A-Z0-9{(])', t) if s.strip()]
    for i, s in enumerate(ss):
        if re.search(r'(?<![A-Z])' + re.escape(code) + r'(?![A-Z])', s):
            return (ss[i - 1] + ' ' + s) if (len(s) < 60 and i > 0) else s   # short hit: add context
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--bolton-list', required=True)
    ap.add_argument('--pairs')
    ap.add_argument('--evidence')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    ac = {}
    for l in open(a.protonyms, encoding='utf-8'):
        if l.strip():
            r = json.loads(l); ac[str(r['protonym_id'])] = r
    aidx = author_index(a.bolton_list)
    pairs = {}
    if a.pairs:
        for p in csv.DictReader(open(a.pairs, encoding='utf-8')):
            pairs[(p['ngc_code'], p['antcat_code'])] = p
    ev = {}
    if a.evidence:
        for e in csv.DictReader(open(a.evidence, encoding='utf-8')):
            ev[e['protonym_id']] = e

    rows = [r for r in csv.DictReader(open(f"{a.run}/type_depository_residual.csv", encoding='utf-8'))
            if r['priority'] in ('A_ngc_has_extra', 'B_both_differ')]
    out = []
    for r in rows:
        A = ac[r['protonym_id']]
        no = [x for x in r['ngc_only'].split('; ') if x]
        ao = [x for x in r['antcat_only'].split('; ') if x]
        full = ' | '.join(x for x in (A.get('primary_type_taxt'), A.get('secondary_type_taxt'), A.get('type_notes_taxt')) if x)
        rest = full
        for seg in filter(None, r['antcat_depository_text'].split(' | ')):
            rest = rest.replace(seg, ' ')
        rest_plain = re.sub(r'<[^>]+>', '', rest)
        bucket, sugg, evid, pair = 'none', '', '', ''
        hit = [(n, c) for n in no for c in ao if (n, c) in pairs]
        if hit:
            n, c = hit[0]
            bucket, pair = 'pair', f'{n} / {c}'
            sugg = f"Settled by the answer to pair {n} / {c}"
            evid = pairs[(n, c)]['question']
        elif no and all(re.search(r'(?<![A-Z])' + re.escape(c) + r'(?![A-Z])', rest_plain) for c in no):
            bucket = 'notes'
            sugg = 'Probably no change: AntCat already mentions the NGC code (see evidence)'
            evid = ' // '.join(dict.fromkeys(sentence_with(rest, c) for c in no))
        else:
            au = fold((r['author'] or '').split(';')[0].split(',')[0].strip())
            ent = aidx.get(au)
            if r['priority'].startswith('B') and ent:
                codes, line = ent
                n_ok = any(c in codes for c in no); a_ok = any(c in codes for c in ao)
                if n_ok != a_ok:
                    bucket = 'author'
                    sugg = 'Probably fix AntCat' if n_ok else 'Probably AntCat correct'
                    evid = f"Bolton's author index: {line}"
            if bucket == 'none' and r['protonym_id'] in ev:
                e = ev[r['protonym_id']]
                bucket, sugg, evid = 'paper', e['suggestion'], f"{e['evidence']} [{e['source']}]"
        out.append(dict(protonym_id=r['protonym_id'], name=A.get('name') or '', author=r['author'], year=r['year'],
                        priority=r['priority'][:1], ngc_only=r['ngc_only'], antcat_only=r['antcat_only'],
                        ngc_line=r['ngc_depository_line'], antcat_text=r['antcat_depository_text'],
                        bucket=bucket, pair=pair, suggestion=sugg, evidence=evid,
                        url=f"https://www.antcat.org/protonyms/{r['protonym_id']}"))
    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    from collections import Counter
    print(f"wrote {a.out}: {len(out)} rows", dict(Counter(o['bucket'] for o in out)))


if __name__ == '__main__':
    main()
