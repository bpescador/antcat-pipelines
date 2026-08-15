#!/usr/bin/env python3
"""
diff_catalogue.py  -- compare Bolton 2026 vs AntCat and write the update lists.

Inputs (produced by parse_antcat.py and parse_bolton.py):
  antcat_out/antcat_species_keys.json, antcat_genera_keys.json
  antcat_out/antcat_species.csv,        antcat_genera.csv
  bolton_out/bolton_species.csv, bolton_genera.csv, bolton_references.csv
  [optional] antcat_references.csv  (from export_references.rb) with columns
             including author_names_string / authors and citation_year / year

Outputs (in diff_out/):
  species_in_bolton_not_antcat.csv   <- ADD/CHECK list (new or differently-placed names)
  species_in_antcat_not_bolton.csv   <- REVIEW list (AntCat-valid names Bolton doesn't list)
  genera_in_bolton_not_antcat.csv
  genera_in_antcat_not_bolton.csv
  references_in_bolton_not_antcat.csv (only if antcat_references.csv supplied)
  SUMMARY.txt
"""
import csv, sys, json, os, re, unicodedata
from parse_antcat import gstem, norm_genus

csv.field_size_limit(sys.maxsize)

def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def load_csv(path):
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fields):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)

def run(antcat_dir, bolton_dir, out_dir, antcat_refs=None):
    os.makedirs(out_dir, exist_ok=True)
    summary = []

    # ---------------- SPECIES ----------------
    ac_sp_keys = set(tuple(k.split('|')) for k in json.load(open(os.path.join(antcat_dir, 'antcat_species_keys.json'))))
    bo_sp = load_csv(os.path.join(bolton_dir, 'bolton_species.csv'))
    ac_sp = load_csv(os.path.join(antcat_dir, 'antcat_species.csv'))

    # AntCat lookups for classifying unmatched Bolton names. Keyed with the
    # publication YEAR as well as the epithet stem, because ant epithets recur
    # across genera (sinense, gracilis, omega...) -- a shared stem alone is weak
    # evidence. The same taxon keeps its original author+year through any
    # recombination or gender re-spelling, so (stem, year) is a strong key.
    from collections import defaultdict
    def year4(s):
        m = re.search(r'(1[6789]\d\d|20\d\d)', s or '')
        return m.group(1) if m else ''
    ac_gy_genera = defaultdict(set)        # (gstem, year) -> {genus}
    ac_genus_year_epi = defaultdict(list)  # genus -> [(year, epithet)]
    for r in ac_sp:
        g = norm_genus(r['genus']); y = year4(r.get('year', ''))
        ac_gy_genera[(r['gstem'], y)].add(g)
        ac_genus_year_epi[g].append((y, r['terminal']))
        cvn = r.get('current_valid_name', '')
        if cvn:
            body = cvn.split()
            if len(body) >= 3:                       # subfamily genus species [subsp]
                cg = norm_genus(body[1]); ct = body[-1]
                ac_gy_genera[(gstem(ct), y)].add(cg)
                ac_genus_year_epi[cg].append((y, ct))

    def classify(bg, bep, byear):
        """Return (reason, antcat_has) for a Bolton name absent from AntCat."""
        y = year4(byear); bgs = gstem(bep)
        other = sorted(ac_gy_genera.get((bgs, y), set()) - {bg})
        if other:                                    # same taxon, different genus
            ex = other[0]
            full = next((e for yy, e in ac_genus_year_epi[ex]
                         if yy == y and gstem(e) == bgs), bep)
            return ('recombination', f'{ex.title()} {full}')
        best, bestd = None, 99                       # near-spelling, same genus+year
        for yy, e in ac_genus_year_epi.get(bg, ()):
            if yy != y:
                continue
            d = levenshtein(bep, e)
            if d < bestd:
                best, bestd = e, d
        if best is not None and bestd <= 2:
            return ('spelling_variant', f'{bg.title()} {best}')
        return ('new', '')

    bo_sp_keys = set()
    add_list = []
    for r in bo_sp:
        k = (norm_genus(r['genus']), gstem(r['epithet']))
        bo_sp_keys.add(k)
        if k not in ac_sp_keys:
            reason, has = classify(norm_genus(r['genus']), r['epithet'], r.get('year', ''))
            rr = dict(r); rr['diff_reason'] = reason; rr['antcat_has'] = has
            add_list.append(rr)
    # new taxa first, then recombinations, then spelling variants; by genus within
    order = {'new': 0, 'recombination': 1, 'spelling_variant': 2}
    add_list.sort(key=lambda r: (order.get(r['diff_reason'], 9), r['genus'], r['epithet']))
    write_csv(os.path.join(out_dir, 'species_in_bolton_not_antcat.csv'), add_list,
              ['diff_reason', 'antcat_has', 'genus', 'epithet', 'rank', 'fossil', 'year',
               'original_combination', 'headword_text', 'source_file'])

    # AntCat VALID names Bolton doesn't list (low-noise reverse direction)
    rev_list = []
    for r in ac_sp:
        if r['status'] != 'valid':
            continue
        k = (norm_genus(r['genus']), gstem(r['terminal']))
        if k not in bo_sp_keys:
            rev_list.append(r)
    # living first (fossils are expected to be absent from Bolton's extant catalogue)
    rev_list.sort(key=lambda r: (r.get('fossil', '') in ('True', 'true', True), r['genus'], r['terminal']))
    write_csv(os.path.join(out_dir, 'species_in_antcat_not_bolton.csv'), rev_list,
              ['fossil', 'antcat_id', 'genus', 'species', 'subspecies', 'status', 'author_date',
               'year', 'current_valid_name'])

    summary.append(f"SPECIES-GROUP")
    summary.append(f"  Bolton headwords:                 {len(bo_sp):>6}")
    summary.append(f"  AntCat names (all statuses):      {len(ac_sp):>6}")
    summary.append(f"  In Bolton, NOT matched in AntCat: {len(add_list):>6}   -> species_in_bolton_not_antcat.csv")
    n_new = sum(r['diff_reason'] == 'new' for r in add_list)
    n_rec = sum(r['diff_reason'] == 'recombination' for r in add_list)
    n_spv = sum(r['diff_reason'] == 'spelling_variant' for r in add_list)
    summary.append(f"      new taxa (genuine ADD):       {n_new:>6}")
    summary.append(f"      recombination (verify genus): {n_rec:>6}")
    summary.append(f"      spelling variant (verify):    {n_spv:>6}")
    summary.append(f"  AntCat-valid, NOT found in Bolton:{len(rev_list):>6}   -> species_in_antcat_not_bolton.csv")
    summary.append("")

    # ---------------- GENERA ----------------
    ac_gn_keys = set(json.load(open(os.path.join(antcat_dir, 'antcat_genera_keys.json'))))
    bo_gn = load_csv(os.path.join(bolton_dir, 'bolton_genera.csv'))
    ac_gn = load_csv(os.path.join(antcat_dir, 'antcat_genera.csv'))

    bo_gn_keys = set()
    g_add = []
    for r in bo_gn:
        k = norm_genus(r['name'])
        bo_gn_keys.add(k)
        if k not in ac_gn_keys:
            g_add.append(r)
    write_csv(os.path.join(out_dir, 'genera_in_bolton_not_antcat.csv'), g_add,
              ['name', 'status', 'classification', 'header_text', 'source_file'])

    g_rev = []
    for r in ac_gn:
        if r['status'] != 'valid':
            continue
        if norm_genus(r['name']) not in bo_gn_keys:
            g_rev.append(r)
    g_rev.sort(key=lambda r: (r.get('fossil', '') in ('True', 'true', True), r['name']))
    write_csv(os.path.join(out_dir, 'genera_in_antcat_not_bolton.csv'), g_rev,
              ['fossil', 'antcat_id', 'name', 'rank', 'status', 'author_date', 'current_valid_name'])

    summary.append(f"GENUS-GROUP")
    summary.append(f"  Bolton headwords:                 {len(bo_gn):>6}")
    summary.append(f"  AntCat names (all statuses):      {len(ac_gn):>6}")
    summary.append(f"  In Bolton, NOT matched in AntCat: {len(g_add):>6}   -> genera_in_bolton_not_antcat.csv")
    summary.append(f"  AntCat-valid, NOT found in Bolton:{len(g_rev):>6}   -> genera_in_antcat_not_bolton.csv")
    summary.append("")

    # ---------------- REFERENCES ----------------
    bo_rf = load_csv(os.path.join(bolton_dir, 'bolton_references.csv'))
    summary.append(f"REFERENCES")
    summary.append(f"  Bolton reference entries:         {len(bo_rf):>6}")
    if antcat_refs and os.path.exists(antcat_refs):
        ac_rf = load_csv(antcat_refs)
        def field(r, *names):
            for n in names:
                if n in r and r[n]:
                    return r[n]
            return ''

        # Reference key = normalised author string + BARE 4-digit year. The
        # disambiguation letter (1990a/b) is deliberately dropped: AntCat and
        # Bolton assign letters independently and AntCat's Bolton-letter field is
        # only sparsely filled, so the letter can't be matched across the two.
        # Accents are folded (Brandao == Brandão) and Bolton's parenthetical
        # forenames ("Andre, E. (Ernest)") are stripped before keying.
        def refkey(author, year):
            a = unicodedata.normalize('NFKD', author or '')
            a = ''.join(c for c in a if not unicodedata.combining(c))
            a = re.sub(r'\([^)]*\)', ' ', a)
            ak = re.sub(r'[^a-z]', '', a.lower())
            ym = re.search(r'(1[6789]\d\d|20\d\d)', year or '')
            return f'{ak}|{ym.group(1)}' if (ak and ym) else None

        ac_keys = set()
        for r in ac_rf:
            k = refkey(field(r, 'author_names_string', 'authors', 'author'),
                       field(r, 'citation_year', 'year'))
            if k:
                ac_keys.add(k)
        ref_add = []
        for r in bo_rf:
            k = refkey(r.get('author', ''), r.get('year', ''))
            if k and k not in ac_keys:
                ref_add.append(r)
        write_csv(os.path.join(out_dir, 'references_in_bolton_not_antcat.csv'), ref_add,
                  ['author', 'year', 'reference_text', 'source_file'])
        summary.append(f"  AntCat reference entries:         {len(ac_rf):>6}")
        summary.append(f"  In Bolton, NOT matched in AntCat: {len(ref_add):>6}   -> references_in_bolton_not_antcat.csv")
    else:
        summary.append("  AntCat reference export not supplied -- run export_references.rb on the")
        summary.append("  server, then re-run with:  --antcat-refs antcat_references.csv")
    summary.append("")

    txt = "\n".join(summary)
    with open(os.path.join(out_dir, 'SUMMARY.txt'), 'w') as f:
        f.write(txt + "\n")
    print(txt)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--antcat-dir', default='antcat_out')
    ap.add_argument('--bolton-dir', default='bolton_out')
    ap.add_argument('--out-dir', default='diff_out')
    ap.add_argument('--antcat-refs', default=None)
    a = ap.parse_args()
    run(a.antcat_dir, a.bolton_dir, a.out_dir, a.antcat_refs)
