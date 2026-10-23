#!/usr/bin/env python3
"""
diff_depositories.py -- NGC (Bolton) vs AntCat type-depository comparison.

Layer 2 (depository resolution) + Layer 3 (content diff) of BOLTON_SYNC_RUNBOOK.md.
Extracted 2026-10-23 from the July 2026 inline analysis (claude.ai chat "Mapping NGC
type material to AntCat fields", 2026-07-23; the final run is turn 21). That work was
never saved as a file. The logic below is the July logic; departures are marked
"V2:" and are switched off by --july.

Steps
  1. Match NGC headwords to AntCat species-group protonyms on
     (terminal epithet, first author surname, year).                 [July turn 13]
  2. Split matched pairs: fill candidates (NGC has type info, AntCat primary
     empty) and the compare set (both populated).                    [July turn 13]
  3. Depository codes per record: NGC "Type-depository/-ies:" lines; AntCat
     "Primary/Secondary type depository/-ies:" segments. Parentheticals dropped.
  4. Equivalence classes by union-find over AntCat's institutions table, where
     aliases are an "[Also X; Y]" or "[Formerly X]" prefix of the name.  [turn 19]
  5. Bolton's own list (SUB. 8 DEPOSITORIES OF TYPE-MATERIAL): codes absent from
     AntCat are matched to an AntCat code by institution name (Jaccard >= 0.55
     on words longer than 3 letters).                                 [turn 21]
  6. NGC codes still unknown are read as Bolton typos when exactly one known code
     is a one-letter substitution or adjacent transposition AND sits in the same
     record on the AntCat side.                                       [turn 21]
  7. What still differs is the residual, split by direction:
       A_ngc_has_extra    NGC cites a depository AntCat lacks (actionable)
       B_both_differ      both sides have something the other lacks
       C_antcat_has_extra AntCat cites more (almost always AntCat being right)

V2 changes (default; --july turns them off):
  * --crosswalk CSV (code_a,code_b,relation): extra alias source. Rows with relation
    "same" or "same-for-comparison" are joined; anything else ("probable") is not.
  * Codes with a hyphen suffix (NMNH-S, NMNH-NM) are read whole. July read NMNH-S
    as NMNH.
  * Known codes containing a space ("NMNH NASU", "NZC ZSI") are read whole.
  * Iteration is sorted, so reruns give identical files. July iterated a set; the
    one effect was which reading won for a typo code that resolves two ways.
  * The residual sheet gains antcat_url and the AntCat depository segments.

Run from the repo root (imports protonym.py):
  PYTHONPATH=.:bolton python3 bolton/diff_depositories.py \\
      --ngc-blocks   <parse_bolton out>/bolton_species_blocks.jsonl \\
      --protonyms    protonyms_species_typeinfo.jsonl   (bolton/export_protonyms.rb) \\
      --institutions institutions.jsonl                 (bolton/institutions_export.rb) \\
      --bolton-list  "SUB. 8 DEPOSITORIES OF TYPE-MATERIAL.docx" \\
      [--crosswalk   antcat__depository_crosswalk_YYYYMMDD.csv] \\
      --out <dir>

July 2026 baseline (runbook section 5): 22,298 matched, 11 fill candidates,
17,937 comparable, 94.0% raw, 95.7% after aliases, 95.9% after Bolton list and
typos, residual 740 (A 187, B 139, C 414), 21 errata, 6 Bolton-only codes.
"""
import argparse, csv, hashlib, html, json, os, re, sys, unicodedata
from collections import Counter

from protonym import fold, year4

# --------------------------------------------------------------- 1. matching
def surname_first(a):
    """Symmetric author key: first author, surname portion, first word.
       AntCat 'Baroni Urbani, C.' -> baroni ; NGC 'Baroni' -> baroni"""
    a = (a or '').split(';')[0]          # first author only
    a = a.split(',')[0]                  # drop initials
    a = fold(a).strip()
    toks = [t for t in re.split(r'\s+', a) if t]
    return re.sub(r'[^a-z]', '', toks[0].lower()) if toks else ''


def key(ep, author, year):
    ep = re.sub(r'[^a-z]', '', fold(ep or '').lower())
    y = year4(str(year or ''))
    a = surname_first(author)
    return (ep, a, y) if ep and y else None


def load_antcat(path):
    ac, dup = {}, 0
    for l in open(path, encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        toks = (r.get('name') or '').split()
        k = key(toks[-1] if toks else '', r.get('author'), r.get('year'))
        if not k:
            continue
        if k in ac:
            dup += 1
        else:
            ac[k] = r
    return ac, dup


def load_ngc(path):
    nk, dup = {}, 0
    for l in open(path, encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        toks = (r.get('original_combination') or '').split()
        k = key(toks[-1] if toks else r.get('epithet', ''), r.get('author'), r.get('year'))
        if not k:
            continue
        if k in nk:
            dup += 1
        else:
            nk[k] = r
    return nk, dup


TYPE = re.compile(r'^(Type-material|Type-locality|Type-localities|Type-depository|'
                  r'Type-depositories|Type-specimen|Type-specimens)\s*:', re.I)


def ngc_has_type(r):
    return any(TYPE.match(l.strip()) for l in (r.get('block_text') or '').split('\n'))


# ------------------------------------------------------- 3. code extraction
DEP_NGC = re.compile(r'^Type-depositor(?:y|ies)\s*:\s*(.*)$', re.I)
DEP_AC = re.compile(r'(?:Primary|Secondary) type depositor(?:y|ies)\s*:\s*([^.]*)', re.I)
CODE_JULY = re.compile(r'\b([A-Z]{3,6}(?:[A-Z0-9]{0,3})?)\b')
CODE_V2 = re.compile(r'\b([A-Z]{3,6}(?:[A-Z0-9]{0,3})?(?:-[A-Z]{1,3})?)(?![A-Za-z0-9-])')


class Extractor:
    def __init__(self, july, spaced_codes=()):
        self.code = CODE_JULY if july else CODE_V2
        # longest first, so a longer spaced code wins over a shorter one inside it
        self.spaced = [] if july else sorted(set(spaced_codes), key=len, reverse=True)

    def codes(self, seg):
        seg = re.sub(r'\([^)]*\)', '', seg)        # drop (holotype)/(paratypes) tags
        out = set()
        for sc in self.spaced:
            pat = r'(?<![A-Za-z0-9-])' + re.escape(sc) + r'(?![A-Za-z0-9-])'
            if re.search(pat, seg):
                out.add(sc)
                seg = re.sub(pat, ' ', seg)
        return out | set(self.code.findall(seg))

    def ngc(self, r):
        out = set()
        for l in (r.get('block_text') or '').split('\n'):
            m = DEP_NGC.match(l.strip())
            if m:
                out |= self.codes(m.group(1))
        return out

    @staticmethod
    def ac_text(a):
        txt = ' '.join([a.get('primary_type_taxt') or '', a.get('secondary_type_taxt') or ''])
        return re.sub(r'<[^>]+>', ' ', html.unescape(txt))

    def ac(self, a):
        out = set()
        for m in DEP_AC.finditer(self.ac_text(a)):
            out |= self.codes(m.group(1))
        return out

    def ac_segments(self, a):
        return ' | '.join(m.group(0).strip() for m in DEP_AC.finditer(self.ac_text(a)))


# --------------------------------------------------- 4. equivalence classes
ALSO = re.compile(r'^[\[\{]\s*(?:Also|Formerly)\s+([^\]\}]+)[\]\}]', re.I)


def build_classes(inst_rows, crosswalk_pairs=()):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    codes = set(); n_alias = 0
    for r in inst_rows:
        ab = (r.get('abbreviation') or '').strip()
        if not ab:
            continue
        codes.add(ab); find(ab)
        m = ALSO.match((r.get('name') or '').strip())
        if m:
            n_alias += 1
            for alt in re.split(r'[;,]| or ', m.group(1)):
                alt = alt.strip()
                if alt:
                    union(ab, alt); codes.add(alt)
    for a, b in crosswalk_pairs:
        codes.add(a); codes.add(b); union(a, b)
    cls = {c: find(c) for c in codes}
    return cls, n_alias


def load_crosswalk(path):
    pairs, skipped = [], Counter()
    for r in csv.DictReader(open(path, encoding='utf-8')):
        rel = (r.get('relation') or '').strip()
        a, b = (r.get('code_a') or '').strip(), (r.get('code_b') or '').strip()
        if not a or not b:
            continue
        if rel in ('same', 'same-for-comparison'):
            pairs.append((a, b))
        else:
            skipped[rel] += 1
    return pairs, skipped


# ------------------------------------------------- 5. Bolton's own code list
def wordset(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r'\[[^\]]*\]', '', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return set(w for w in s.split() if len(w) > 3)


def parse_bolton_list(path):
    import docx
    bolton = {}
    for p in docx.Document(path).paragraphs:
        t = p.text
        if '\t' not in t:
            continue
        parts = t.split('\t')
        code = parts[0].strip()
        name = ' '.join(x.strip() for x in parts[1:]).strip()
        if re.fullmatch(r'[A-Z][A-Z0-9.\- ]{2,9}', code) and name and not re.fullmatch(r'[A-Z, ]+', name):
            bolton[code] = re.sub(r'\s+', ' ', name)
    return bolton


def name_hits(bolton, ac_names, cls):
    hits = []
    for m in sorted(c for c in bolton if c not in cls):
        bn = wordset(bolton[m])
        if not bn:
            continue
        best, bestscore = None, 0
        for c, n in ac_names.items():
            an = wordset(n)
            if not an:
                continue
            j = len(bn & an) / len(bn | an)
            if j > bestscore:
                bestscore, best = j, c
        if bestscore >= 0.55:
            hits.append((m, best, round(bestscore, 2)))
    return hits


# ---------------------------------------------------------------- 6. typos
def is_typo_of(bad, good):
    """single substitution or adjacent transposition, same length"""
    if len(bad) != len(good) or bad == good:
        return False
    d = [i for i, (x, y) in enumerate(zip(bad, good)) if x != y]
    if len(d) == 1:
        return True
    return len(d) == 2 and d[1] == d[0] + 1 and bad[d[0]] == good[d[1]] and bad[d[1]] == good[d[0]]


def dep_line(r):
    return next((l.strip() for l in (r.get('block_text') or '').split('\n')
                 if re.match(r'^Type-depositor', l.strip(), re.I)), '')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--ngc-blocks', required=True)
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--institutions', required=True)
    ap.add_argument('--bolton-list', required=True)
    ap.add_argument('--crosswalk')
    ap.add_argument('--july', action='store_true', help='July 2026 logic exactly (no V2 changes)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    if a.july and a.crosswalk:
        sys.exit('--july reproduces July: leave out --crosswalk')
    os.makedirs(a.out, exist_ok=True)
    M = {'mode': 'july' if a.july else 'v2', 'inputs': {}}
    for k in ('ngc_blocks', 'protonyms', 'institutions', 'bolton_list', 'crosswalk'):
        p = getattr(a, k)
        if p:
            M['inputs'][k] = {'path': os.path.basename(p),
                              'md5': hashlib.md5(open(p, 'rb').read()).hexdigest()}

    # 1-2. match and split
    ac, ac_dup = load_antcat(a.protonyms)
    nk, nk_dup = load_ngc(a.ngc_blocks)
    both = sorted(set(nk) & set(ac))
    fill, compare = [], []
    split = Counter()
    for k in both:
        hn = ngc_has_type(nk[k]); ha = bool((ac[k].get('primary_type_taxt') or '').strip())
        if hn and ha: split['both'] += 1; compare.append(k)
        elif hn: split['ngc_only'] += 1; fill.append(k)
        elif ha: split['antcat_only'] += 1
        else: split['neither'] += 1
    M.update(antcat_keyed=len(ac), antcat_dup=ac_dup, ngc_keyed=len(nk), ngc_dup=nk_dup,
             matched=len(both), split=dict(split), fill_candidates=len(fill))

    # 4. classes
    inst = [json.loads(l) for l in open(a.institutions, encoding='utf-8') if l.strip()]
    xw_pairs, xw_skipped = load_crosswalk(a.crosswalk) if a.crosswalk else ([], Counter())
    cls_ac, n_alias = build_classes(inst)
    cls, _ = build_classes(inst, xw_pairs)
    M.update(institutions=len(inst), institutions_with_alias_prefix=n_alias,
             crosswalk_pairs_used=len(xw_pairs), crosswalk_skipped=dict(xw_skipped),
             classes=len(set(cls.values())),
             multi_code_classes=sum(1 for v in Counter(cls.values()).values() if v > 1))

    # 5. Bolton list
    bolton = parse_bolton_list(a.bolton_list)
    ac_names = {(r.get('abbreviation') or '').strip():
                re.sub(r'^\[[^\]]*\]\s*', '', (r.get('name') or '').strip())
                for r in inst if (r.get('abbreviation') or '').strip()}
    hits = name_hits(bolton, ac_names, cls)
    extra = {m: c for m, c, _ in hits}
    M.update(bolton_codes=len(bolton), bolton_codes_absent=sum(1 for c in bolton if c not in cls),
             bolton_name_matched=len(hits))

    def klass_with(c, classes):
        return classes.get(extra.get(c, c), extra.get(c, c))

    def klass(c):
        return klass_with(c, cls)
    known = set(cls) | set(extra)

    # 3. codes
    spaced = [c for c in cls if ' ' in c]
    X = Extractor(a.july, spaced)
    rows = []
    for k in compare:
        n, d = X.ngc(nk[k]), X.ac(ac[k])
        if n and d:
            rows.append((k, n, d))
    M['comparable'] = len(rows)

    # 6. typos (one map for the whole run; a code with two readings keeps the last)
    typo, tpairs = {}, Counter()
    for k, n, d in rows:
        if {klass(x) for x in n} == {klass(x) for x in d}:
            continue
        dclass = {klass(x) for x in d}
        for c in sorted(n):
            if c in known:
                continue
            cand = [g for g in sorted(known) if is_typo_of(c, g)]
            hit = [g for g in cand if klass(g) in dclass]
            if len(hit) == 1:
                typo[c] = hit[0]; tpairs[(c, hit[0])] += 1

    def canon(s):
        return {klass(typo.get(c, c)) for c in s}

    raw = alias_ac = alias = fin = 0; still = []
    for k, n, d in rows:
        if n == d: raw += 1
        if {klass_with(x, cls_ac) for x in n} == {klass_with(x, cls_ac) for x in d}: alias_ac += 1
        if {klass(x) for x in n} == {klass(x) for x in d}: alias += 1
        if canon(n) == canon(d): fin += 1
        else: still.append((k, n, d))
    t = len(rows) or 1
    M.update(equal_raw=raw, equal_after_antcat_aliases=alias_ac,
             equal_after_all_aliases=alias, equal_final=fin,
             pct_raw=round(100 * raw / t, 1), pct_final=round(100 * fin / t, 1),
             residual=len(still))

    # outputs ------------------------------------------------------------
    with open(os.path.join(a.out, 'type_fill_candidates.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['protonym_id', 'genus', 'epithet', 'author', 'year', 'antcat_name', 'ngc_type_block'])
        for k in fill:
            n, d = nk[k], ac[k]
            blk = [l.strip() for l in (n.get('block_text') or '').split('\n')
                   if TYPE.match(l.strip()) or l.strip().startswith('[Note')]
            w.writerow([d['protonym_id'], n['genus'], n['epithet'], n['author'], n['year'], d['name'], ' | '.join(blk)])

    seen = {}
    for k, n, d in rows:
        for c in sorted(n):
            if c in typo:
                seen.setdefault((c, typo[c]), []).append(k)
    with open(os.path.join(a.out, 'ngc_depository_errata.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ngc_code', 'correct_code', 'n_records', 'in_bolton_own_list', 'example_taxon', 'ngc_depository_line'])
        for (b, g), ks in sorted(seen.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            r = nk[ks[0]]
            w.writerow([b, g, len(ks), 'yes' if b in bolton else 'no',
                        f"{r['genus']} {r['epithet']} {r['author']} {r['year']}", dep_line(r)])
    M['errata'] = len(seen)

    pri = Counter()
    with open(os.path.join(a.out, 'type_depository_residual.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        head = ['priority', 'protonym_id', 'genus', 'epithet', 'author', 'year',
                'ngc_only', 'antcat_only', 'ngc_codes', 'antcat_codes',
                'ngc_depository_line', 'antcat_primary_type_taxt']
        if not a.july:
            head += ['antcat_url', 'antcat_depository_text']
        w.writerow(head)
        for k, n, d in still:
            r, A = nk[k], ac[k]
            cn, ca = canon(n), canon(d)
            no = sorted(x for x in n if klass(typo.get(x, x)) not in ca)
            ao = sorted(x for x in d if klass(x) not in cn)
            p = 'A_ngc_has_extra' if (no and not ao) else ('C_antcat_has_extra' if (ao and not no) else 'B_both_differ')
            pri[p] += 1
            row = [p, A['protonym_id'], r['genus'], r['epithet'], r['author'], r['year'],
                   '; '.join(no), '; '.join(ao), '; '.join(sorted(n)), '; '.join(sorted(d)),
                   dep_line(r), (A.get('primary_type_taxt') or '')[:400]]
            if not a.july:
                row += [f"https://www.antcat.org/protonyms/{A['protonym_id']}", X.ac_segments(A)]
            w.writerow(row)
    M['residual_by_priority'] = dict(sorted(pri.items()))

    with open(os.path.join(a.out, 'antcat_institution_gaps.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['bolton_code', 'bolton_institution_name', 'suggested_action'])
        gaps = sorted(c for c in bolton if c not in cls)
        for m in gaps:
            alias_of = extra.get(m, '')
            act = ('NOT a depository (it is the Code) - ignore' if m == 'ICZN' else
                   f'variant of existing AntCat code {alias_of} - no action' if alias_of else
                   'ADD to AntCat institutions table')
            w.writerow([m, bolton[m], act])
    M['bolton_only_codes'] = len(gaps)

    with open(os.path.join(a.out, 'metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(M, f, indent=2)

    print(f"mode {M['mode']}")
    print(f"matched {len(both)}  (AntCat keyed {len(ac)}, NGC keyed {len(nk)})  split {dict(split)}")
    print(f"fill candidates {len(fill)}")
    print(f"institutions {len(inst)}  classes {M['classes']} (multi-code {M['multi_code_classes']})"
          f"  crosswalk pairs {len(xw_pairs)}")
    print(f"Bolton list codes {len(bolton)}  absent from AntCat {M['bolton_codes_absent']}  name-matched {len(hits)}")
    print(f"comparable {len(rows)}")
    print(f"  raw                       {raw} ({M['pct_raw']}%)")
    print(f"  + AntCat alias classes    {alias_ac} ({100 * alias_ac / t:.1f}%)")
    if xw_pairs:
        print(f"  + crosswalk               {alias} ({100 * alias / t:.1f}%)")
    print(f"  + Bolton list + typos     {fin} ({M['pct_final']}%)   residual {len(still)}")
    print(f"residual by priority {M['residual_by_priority']}")
    print(f"errata {len(seen)}   Bolton-only codes {len(gaps)}")
    print(f"wrote 4 CSVs + metrics.json to {a.out}")


if __name__ == '__main__':
    main()
