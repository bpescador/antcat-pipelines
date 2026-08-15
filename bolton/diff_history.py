#!/usr/bin/env python3
"""
diff_history.py -- content-level ("taxonomic acts") diff, Bolton vs AntCat.

The name-level diff (diff_catalogue.py) answers "what NAMES is AntCat missing".
This answers the deeper question: for names BOTH catalogues already have, what
taxonomic ACTS has Bolton recorded that AntCat has not -- a new synonymy, a
status change, a new combination, a type designation?

How it works. AntCat's `taxonomic history html` column (in worldants.txt) and
Bolton's per-name block contain the same kind of content -- the full synonymic /
combination / status history, each act trailed by its citations. We pair each
Bolton block with its AntCat record on (terminal-epithet stem, original-
description year) -- i.e. protonym identity, which survives genus recombination
-- and compare the CITATIONS each side records. A reference Bolton cites in a
name's history that AntCat's history does NOT contain is a flag: Bolton has
folded in a taxonomic act AntCat may be missing. We focus the worklist on
RECENT citations, because an old citation Bolton has and AntCat lacks is usually
just completeness, whereas a recent one is more likely a real change.

Comparison is on citations, not raw prose, because the two sources never line up
character-for-character. It is a REVIEW list -- the original publication remains
the authority, same principle as the name-level diff.

Inputs:
  bolton_out/bolton_species_blocks.jsonl   (from parse_bolton.py)
  worldants.txt                            (AntCat dump)

Outputs (diff_out/):
  history_recent_acts_to_check.csv   one row per recent Bolton citation AntCat lacks
  history_by_species.csv             one row per shared name: counts + newest gap
  HISTORY_SUMMARY.txt
"""
import csv, sys, json, os, re, html
from parse_antcat import gstem

csv.field_size_limit(sys.maxsize)

# Citations are formatted inconsistently across the two sources -- "Smith, M.R.
# 1944c", "Sosa-Calvo, et al. 2006" (Bolton) vs "Czechowski et al., 2002"
# (AntCat). Rather than match a whole author block, anchor on the YEAR and take
# the nearest preceding surname. That key is stable across both formats. (Using
# the last surname before the year, not the first, is fine: both catalogues
# order co-authors the same way, so the key is consistent for set comparison.)
YEARTOK = re.compile(r'(1[6789]\d\d|20\d\d)([a-z]?)\b')
SURTOK = re.compile(r"[A-Z\u00C0-\u00DE][a-z\u00C0-\u00FF][\w\u00C0-\u00FF'’-]*")

def year4(s):
    m = re.search(r'(1[6789]\d\d|20\d\d)', s or '')
    return m.group(1) if m else ''

def authorkey(a):
    return re.sub(r'[^a-z0-9\u00C0-\u00FF]', '', a.lower())

def citations(text):
    """citekey -> (surname, 'year+letter'); citekey = surnamekey|yearletter."""
    out = {}
    for m in YEARTOK.finditer(text):
        if m.start() > 0 and text[m.start() - 1] == '.':
            continue                              # a date like "viii.1894", not a citation
        yr, lt = m.group(1), m.group(2)
        if int(yr) > 2026:
            continue                              # page number / specimen code, not a year
        pre = text[max(0, m.start() - 45):m.start()]
        sur = None
        for sm in SURTOK.finditer(pre):
            sur = sm.group(0)                     # nearest surname before the year
        if not sur:
            continue
        out[f"{authorkey(sur)}|{yr}{lt}"] = (sur, yr + lt)
    return out

def loose(citekey):
    """drop the disambiguation letter: authorkey|1987a -> authorkey|1987."""
    ak, yl = citekey.split('|')
    return f"{ak}|{yl[:4]}"

def strip_html(h):
    h = re.sub(r'<a\b[^>]*class="pdf-link"[^>]*>.*?</a>', ' ', h)   # drop PDF links
    h = re.sub(r'<[^>]+>', ' ', h)
    h = html.unescape(h)
    h = h.replace('\n', ' ')
    h = re.sub(r'\bPDF\b', ' ', h)
    h = re.sub(r'\s+', ' ', h)
    return h.strip()

def act_line(block, citekey):
    """the Bolton block line (≈ one taxonomic act) that carries this citation."""
    for line in block.split('\n'):
        c = citations(line)
        if citekey in c or any(loose(k) == loose(citekey) for k in c):
            return line.strip()
    return ''

# Placement / synonymy acts. Comparing CITATIONS is too noisy -- Bolton lists
# every faunistic confirmation of an act, AntCat lists the act. So we compare
# the RELATIONSHIP each act asserts: (act type, target name). Bolton names the
# target by epithet ("Junior synonym of clara"); AntCat by binomial ("Junior
# synonym of Formica clara"); both reduce to the terminal epithet, so the keys
# align. A relationship Bolton asserts that AntCat's history does not contain =
# a placement act AntCat may be missing.
ACTLABELS = (r'(Junior synonym of|Senior synonym of|Combination in|Subspecies of|'
             r'Replacement name for|Variety or race of|Unjustified emendation of)')
ACT = re.compile(ACTLABELS + r'\s+([^:]+?)\s*:')

def targetkey(s):
    toks = re.findall(r"[A-Za-z\u00C0-\u00FF'’\-]+", s)
    toks = [t for t in toks if t.lower() not in ('the', 'of', 'in', 'and')]
    return toks[-1].lower() if toks else ''

def antcat_relations(blob):
    """set of (act_type, target_epithet) asserted anywhere in AntCat's history."""
    rel = set()
    for m in ACT.finditer(blob):
        tk = targetkey(m.group(2))
        if tk:
            rel.add((m.group(1).lower(), tk))
    return rel

def bolton_relations(block):
    """(act_type, target_epithet) -> {newest year, snippet, cites} from a block.
    Bolton blocks are line-structured (one act per line), so the citations on a
    line belong to that act."""
    rel = {}
    for line in block.split('\n'):
        m = ACT.search(line)
        if not m:
            continue
        tk = targetkey(m.group(2))
        if not tk:
            continue
        key = (m.group(1).lower(), tk)
        cites = citations(line[m.end() - 1:])
        yrs = [int(k.split('|')[1][:4]) for k in cites]
        d = rel.setdefault(key, dict(newest=0, snippet=line.strip()[:200], cites=''))
        if yrs:
            d['newest'] = max(d['newest'], max(yrs))
            d['cites'] = '; '.join(f'{s}, {y}' for s, y in list(cites.values())[:5])
    return rel

def first_surname_key(s):
    """first surname in an author string: 'Schultz & Seifert, 2026' -> 'schultz'."""
    m = SURTOK.search(s or '')
    return authorkey(m.group(0)) if m else ''

def load_antcat_histories(worldants):
    """(gstem, year4) -> list of candidate records, each with its author key.
    Pairing by epithet-stem + year alone collides ~6% of the time; carrying the
    first-author surname lets run() disambiguate."""
    from collections import defaultdict
    hist = defaultdict(list)
    with open(worldants, encoding='utf-8', errors='replace', newline='') as fh:
        rd = csv.reader(fh, delimiter='\t')
        hdr = next(rd)
        ix = {h: i for i, h in enumerate(hdr)}
        gi, si, subi = ix['genus'], ix['species'], ix['subspecies']
        thi, yi, idi = ix['taxonomic history html'], ix['year'], ix['antcat id']
        adi = ix.get('author date', ix.get('authors'))
        for row in rd:
            if len(row) <= thi:
                continue
            term = (row[subi].strip() or row[si].strip())
            if not term:
                continue
            key = (gstem(term), year4(row[yi]))
            txt = strip_html(row[thi])
            hist[key].append(dict(text=txt, len=len(txt), antcat_id=row[idi].strip(),
                                  genus=row[gi].strip(), terminal=term,
                                  authkey=first_surname_key(row[adi] if adi is not None else '')))
    return hist

def pick_candidate(cands, bolton_authkey):
    """choose the AntCat record matching Bolton's author; else richest history."""
    if not cands:
        return None
    if bolton_authkey:
        m = [c for c in cands if c['authkey'] == bolton_authkey]
        if m:
            return max(m, key=lambda c: c['len'])
    return max(cands, key=lambda c: c['len'])

def run(bolton_dir, worldants, out_dir, recent_from=2015):
    os.makedirs(out_dir, exist_ok=True)
    hist = load_antcat_histories(worldants)

    act_rows, per_species, addref_rows = [], [], []
    n_blocks = n_paired = 0
    with open(os.path.join(bolton_dir, 'bolton_species_blocks.jsonl'), encoding='utf-8') as f:
        for ln in f:
            b = json.loads(ln)
            n_blocks += 1
            blk = b.get('block_text') or ''
            ah = pick_candidate(hist.get((b['gstem'], year4(b.get('year', '')))),
                                authorkey(b.get('author', '')))
            if not ah:
                continue                         # not in AntCat -> name-level diff covers it
            n_paired += 1
            bo_rel = bolton_relations(blk)
            ac_rel = antcat_relations(ah['text'])
            ac_cites = set(citations(ah['text']))
            ac_loose = {loose(k) for k in ac_cites}

            # (1) NEW LINES: placement/synonymy relationships AntCat's history lacks
            missing = {k: v for k, v in bo_rel.items() if k not in ac_rel}
            if missing:
                newest = max((v['newest'] for v in missing.values()), default=0)
                per_species.append(dict(genus=b['genus'], epithet=b['epithet'],
                                        year=b.get('year', ''), antcat_id=ah['antcat_id'],
                                        missing_acts=len(missing), newest_gap=newest))
                for (typ, tgt), v in missing.items():
                    act_rows.append(dict(newest=v['newest'], genus=b['genus'], epithet=b['epithet'],
                                         antcat_id=ah['antcat_id'], act=typ, target=tgt,
                                         bolton_citations=v['cites'], bolton_line=v['snippet']))

            # (2) ADDITIONAL REFERENCES: a citation Bolton attaches to a nomenclatural-act
            # line that AntCat's history does not carry. Restricted to act lines (synonymy /
            # combination / subspecies / ...) -- NOT the faunistic "Status as species" dumps,
            # which is where the citation-completeness noise lives. act_status distinguishes a
            # citation on an act AntCat already asserts ('existing' -- the genuine "extra ref
            # on an existing item") from one on an act AntCat lacks ('new_act' -- corroborates
            # the new-lines list above).
            for line in blk.split('\n'):
                m = ACT.search(line)
                if not m:
                    continue
                tk = targetkey(m.group(2))
                if not tk:
                    continue
                rel = (m.group(1).lower(), tk)
                for k, (sur, yl) in citations(line[m.end() - 1:]).items():
                    yr = int(k.split('|')[1][:4])
                    if yr < recent_from or k in ac_cites or loose(k) in ac_loose:
                        continue
                    addref_rows.append(dict(newest=yr, genus=b['genus'], epithet=b['epithet'],
                                            antcat_id=ah['antcat_id'], act=m.group(1).lower(),
                                            target=tk, added_citation=f'{sur}, {yl}',
                                            act_status=('existing' if rel in ac_rel else 'new_act'),
                                            bolton_line=line.strip()[:200]))

    # the actionable list: placement acts AntCat lacks, recent first
    recent = [r for r in act_rows if r['newest'] >= recent_from]
    recent.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))
    act_rows.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))
    per_species.sort(key=lambda r: (-r['newest_gap'], -r['missing_acts']))
    # additional refs: existing-act (the unique signal) first, then newest
    addref_rows.sort(key=lambda r: (r['act_status'] != 'existing', -r['newest'], r['genus'], r['epithet']))

    def write(path, rows, fields):
        with open(os.path.join(out_dir, path), 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader(); w.writerows(rows)

    fields = ['newest', 'genus', 'epithet', 'antcat_id', 'act', 'target',
              'bolton_citations', 'bolton_line']
    write('history_recent_acts_to_check.csv', recent, fields)
    write('history_all_acts_to_check.csv', act_rows, fields)
    write('history_by_species.csv', per_species,
          ['genus', 'epithet', 'year', 'antcat_id', 'missing_acts', 'newest_gap'])
    write('history_added_refs_to_check.csv', addref_rows,
          ['act_status', 'newest', 'genus', 'epithet', 'antcat_id', 'act', 'target',
           'added_citation', 'bolton_line'])

    from collections import Counter
    bytype = Counter(r['act'] for r in recent)
    n_addref_exist = sum(1 for r in addref_rows if r['act_status'] == 'existing')
    L = [
        "CONTENT-LEVEL DIFF (placement acts in Bolton that AntCat's history lacks)",
        f"  Bolton species blocks:                 {n_blocks:>6}",
        f"  paired to an AntCat record:            {n_paired:>6}",
        f"  names with a placement act AntCat lacks: {len(per_species):>5}   -> history_by_species.csv",
        f"  total such acts:                         {len(act_rows):>5}   -> history_all_acts_to_check.csv",
        f"  of those, recent (>= {recent_from}):              {len(recent):>5}   -> history_recent_acts_to_check.csv",
        "",
        "  recent acts by type:",
    ]
    for t, n in bytype.most_common():
        L.append(f"      {t:22} {n:>5}")
    L += [
        "",
        f"ADDITIONAL REFERENCES on nomenclatural-act lines (recent >= {recent_from})   -> history_added_refs_to_check.csv",
        f"  total:                                   {len(addref_rows):>5}",
        f"    act_status=existing (extra ref on an act AntCat already has): {n_addref_exist:>5}",
        f"    act_status=new_act (corroborates the new-lines list above):   {len(addref_rows)-n_addref_exist:>5}",
        "  Faunistic 'Status as species' / non-act citations are deliberately excluded",
        "  (that comparison runs to ~50k rows, almost all regional-checklist noise).",
    ]
    L += [
        "",
        "  Each row = a placement/synonymy relationship Bolton asserts (act + target)",
        "  that AntCat's taxonomic history does not contain. Recent first. The original",
        "  publication is the authority -- verify, then enter in AntCat if confirmed.",
        "",
    ]
    txt = "\n".join(L)
    with open(os.path.join(out_dir, 'HISTORY_SUMMARY.txt'), 'w') as f:
        f.write(txt + "\n")
    print(txt)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--bolton-dir', default='bolton_out')
    ap.add_argument('--worldants', required=True)
    ap.add_argument('--out-dir', default='diff_out')
    ap.add_argument('--recent-from', type=int, default=2015)
    a = ap.parse_args()
    run(a.bolton_dir, a.worldants, a.out_dir, a.recent_from)
